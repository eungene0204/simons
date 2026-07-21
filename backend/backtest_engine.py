import os
import polars as pl
import pandas as pd
from typing import Dict, List, Any

# Import refactored modules
from engine.loader import DataLoader
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine
from engine.simulator import Simulator
from engine.result_handler import ResultHandler
from engine.data_resolver import DataResolver
from engine import universe_pit
from engine import data_coverage

def _ai_signals_enabled() -> bool:
    """AI 예측 신호(ai_model/ai_drop_model) 실행 허용 여부. 운영 스위치(기본 ON).

    기능을 꺼둔 배포에서 파싱·캐시 등 다른 경로로 AI 신호가 흘러 들어와도
    엔진이 최종 관문에서 즉시 거절하게 한다(AI_SIGNALS_ENABLED=0).
    """
    return os.environ.get("AI_SIGNALS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _ai_model_train_end() -> str | None:
    """라이브 AI 모델 메타의 학습 종료일(train_end). 없으면 None. (감사 H7)"""
    import json
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
    for ver in ('v3', 'v2'):
        meta_path = os.path.join(base, 'model', ver, 'model_meta.json')
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    val = json.load(f).get('train_end')
                return str(val) if val else None
            except (ValueError, OSError):
                return None
    return None


def _max_indicator_period(*groups) -> int:
    """전략 조건들이 참조하는 최대 지표 기간(거래일). warm-up 산정용(H6).

    고정 400일 warm-up은 200일 초과 지표(예: 300일 MA)의 초기 구간을 NaN으로
    만들어 요청 기간에 따라 신호가 조용히 달라지게 했다. 조건에서 실제 최대
    기간을 뽑아 warm-up을 동적으로 늘린다.
    """
    max_p = 0

    def _visit(group):
        nonlocal max_p
        if not group:
            return
        for c in group.get('conditions', []):
            if 'conditions' in c:
                _visit(c)
                continue
            p = c.get('params') or {}
            cid = c.get('id')
            cands = []
            if cid == 'ma_crossover':
                cands = [p.get('shortMA', p.get('short_period', p.get('short', 5))),
                         p.get('longMA', p.get('long_period', p.get('long', 20)))]
            elif cid == 'ema':
                cands = [p.get('shortPeriod', p.get('short')),
                         p.get('longPeriod', p.get('long')), p.get('period', 20)]
            elif cid == 'rsi':
                cands = [p.get('period', p.get('rsi_period', 14))]
            elif cid == 'cci':
                cands = [p.get('period', 14)]
            elif cid == 'williams_r':
                cands = [p.get('period', 14)]
            elif cid == 'mfi':
                cands = [p.get('period', 14)]
            elif cid == 'roc':
                cands = [p.get('period', 12)]
            elif cid in ('bollinger_bands', 'volume_spike'):
                cands = [p.get('period', 20)]
            elif cid == 'breakout':
                cands = [p.get('lookbackPeriod', 20)]
            elif cid == 'macd':
                # slow + signal (파라미터화 지원, 기본 26+9)
                try:
                    cands = [int(p.get('slowPeriod', 26)) + int(p.get('signalPeriod', 9))]
                except (TypeError, ValueError):
                    cands = [35]
            elif cid == 'stochastic':
                # KDJ 재귀 평활 수렴 여유분 +21
                try:
                    cands = [int(p.get('period', 9)) + 21]
                except (TypeError, ValueError):
                    cands = [30]
            elif cid == 'adx':
                cands = [30]
            for v in cands:
                try:
                    if v is not None:
                        max_p = max(max_p, int(v))
                except (TypeError, ValueError):
                    pass

    for g in groups:
        _visit(g)
    return max_p


class BacktestEngine:
    def __init__(self, data_dir: str = None):
        self.warnings = set()
        
        # Robust path resolution
        if not data_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_data_dir = os.path.join(base_dir, "data", "ohlcv")
            local_data_dir = "data/ohlcv"
            data_dir = project_data_dir if os.path.exists(project_data_dir) else local_data_dir
            
        self.loader = DataLoader(data_dir)
        self.indicator_engine = IndicatorEngine()
        self.signal_engine = SignalEngine()
        self.data_resolver = DataResolver()
        self.handler = ResultHandler()
        self.simulator = Simulator()

        # Load AI Engine lazily
        self._ai_engine = None

    @property
    def ai_engine(self):
        if self._ai_engine is None:
            from ai.ai_engine import AIEngine
            try:
                self._ai_engine = AIEngine()
            except Exception as e:
                print(f"[ERROR] Failed to initialize AIEngine: {e}", flush=True)
                self._ai_engine = "FAILED"
        return None if self._ai_engine == "FAILED" else self._ai_engine

    def calculate_indicators(self, df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        """Compatibility method for tests."""
        return self.indicator_engine.calculate(df_pl, conditions)

    @staticmethod
    def benchmark_for_universe(universe_id: str) -> tuple[str, str]:
        normalized = (universe_id or "kospi200").lower()
        universe_parts = {part for part in normalized.split("_") if part}
        if "kosdaq" in universe_parts:
            return "229200", "KODEX KOSDAQ 150 (229200)"
        if "kospi" in universe_parts:
            return "226490", "KODEX 코스피 (226490)"
        return "069500", "KODEX 200 (069500)"

    def run_backtest(self, req: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import time as _time
            _t0 = _time.time()

            # 1. Parameter Extraction
            self.warnings = set()
            symbols = req.get('symbols') or [req.get('symbol')]
            if not symbols or symbols == [None]:
                symbols = []
                
            # Risk & Options
            risk_params = req.get('risk_params') or req.get('risk') or {}
            
            # Fix 9: or 연산자는 0.0을 falsy로 취급하므로 명시적 None 체크로 교체
            init_cash_raw = risk_params.get('init_cash')
            if init_cash_raw is None:
                init_cash_raw = risk_params.get('initial_cash')
            init_cash = float(init_cash_raw) if init_cash_raw is not None else 10000000.0

            pos_size_raw = risk_params.get('position_size_pct')
            pos_size_pct = float(pos_size_raw) if pos_size_raw is not None else 100.0

            liquid_limit_raw = risk_params.get('liquidity_limit_pct')
            if liquid_limit_raw is None:
                liquid_limit_raw = risk_params.get('liquidity_multiplier')
            liquid_limit = float(liquid_limit_raw) if liquid_limit_raw is not None else 10.0
            
            options = req.get('options', {})
            exec_type = options.get('execution_type', 'next_open')
            # 배당 재투자(토탈리턴)를 기본값으로 한다 — 가격리턴은 배당을 누락해
            # 수익을 과소평가하고 배당락을 가짜 손실로 오인한다(검증 #8). 전략과
            # 벤치마크 양쪽에 동일 적용해 비교 일관성을 유지한다. total_return=False로
            # 명시하면 과거 호환(가격리턴)으로 되돌릴 수 있다.
            apply_dividends = bool(options.get('total_return', True))

            # same_close fills a signal derived from bar i's close at that same
            # close — not realistically tradable (the close is only known once the
            # market has closed). next_open is the realistic default; warn loudly
            # when results are produced under the optimistic same_close model.
            if exec_type == 'same_close':
                self.warnings.add(
                    "체결 방식이 '당일 종가 체결'입니다 — 당일 종가 신호를 당일 종가에 체결하는 "
                    "비현실적 가정(룩어헤드)입니다. 실거래 판단에는 '익일 시가 체결' 방식 사용을 권장합니다."
                )
            
            period_req = (req.get('period') or '5Y').upper()
            start_date_req = req.get('startDate')
            end_date_req = req.get('endDate')

            # Detect if AI is needed
            def check_ai_needed(group):
                if not group: return False
                for c in group.get('conditions', []):
                    if c.get('id') in ['ai_model', 'ai_drop_model']: return True
                    if 'conditions' in c:
                        if check_ai_needed(c): return True
                return False
            
            ai_needed = check_ai_needed(req.get('entry')) or check_ai_needed(req.get('exit'))

            # AI 신호 fail-fast: 기능이 꺼져 있거나(운영 스위치) 모델을 로드할 수 없으면
            # 조용히 0점 처리(0거래)하거나 추론에서 멈추지 않고 즉시 명확한 에러로 거절한다.
            if ai_needed and not _ai_signals_enabled():
                raise Exception(
                    "AI 예측 신호 기능이 현재 비활성화되어 있습니다. "
                    "AI 신호(ai_model/ai_drop_model)를 제거하고 다시 실행해 주세요."
                )

            # 횡단면 AI 하락 랭킹 청산: exit에 ai_drop_model(exitMode='rank')이 있으면 매일
            # 유니버스 상위 X% 하락위험 종목을 청산. 상위 비율(0~1, %는 자동 환산)을 추출.
            def _detect_rank_drop_exit(group):
                if not group:
                    return None
                for c in group.get('conditions', []):
                    if c.get('id') == 'ai_drop_model' and (c.get('params') or {}).get('exitMode') == 'rank':
                        pp = c.get('params') or {}
                        pct = float(pp.get('rankPercentile', pp.get('percentile', 0.1)) or 0.1)
                        return pct / 100.0 if pct > 1.0 else pct
                    if 'conditions' in c:
                        found = _detect_rank_drop_exit(c)
                        if found is not None:
                            return found
                return None
            drop_rank_pct = _detect_rank_drop_exit(req.get('exit'))

            # Reference date for relative periods
            ref_date = pd.to_datetime(end_date_req) if end_date_req else pd.to_datetime('today').normalize()

            # 2. Data Structures for Vectorbt
            all_prices, all_exec_prices, all_entries, all_exits = {}, {}, {}, {}
            all_entry_reasons, all_exit_reasons = {}, {}
            all_highs, all_lows = {}, {}          # 장중 스탑 감지용 (C5)
            all_liquidity = {}                     # 유동성 마스크 패널 (C4/H5)
            all_trading_values = {}                # 전일 거래대금 — 체결 규모 사후 검증 (H5)
            all_drop_scores: dict = {}  # sym → ai_drop_score 시계열 (횡단면 랭킹 청산용)
            all_ranks = {'pbr': {}, 'roe': {}}
            all_resolution_logs: List[Dict[str, str]] = []
            processed_symbols = []
            common_index = None

            # 데이터 커버리지 추적 — 전략이 참조하는 펀더멘털 지표가 창(window)에서 실제로
            # 얼마나 존재했는지 종목·기간 축으로 집계해 결과 로그에 투명하게 드러낸다.
            _tracked_metrics = data_coverage.tracked_metrics(req.get('entry'), req.get('exit'))
            _coverage_acc = (
                data_coverage.CoverageAccumulator(_tracked_metrics) if _tracked_metrics else None
            )

            # Pre-load AI engine to avoid race conditions during lazy loading
            if ai_needed and self.ai_engine is None:
                raise Exception(
                    "AI 모델을 로드할 수 없어 AI 신호가 포함된 백테스트를 실행할 수 없습니다. "
                    "AI 신호를 제거하고 다시 실행해 주세요."
                )

            # AI 백테스트: Phase1(데이터/지표 준비) → Phase2(일괄 AI 추론) → Phase3(신호 생성)
            # 비AI 백테스트: 기존 단일 패스 유지
            _phase1_data: dict = {}  # sym → {df_pl, pdf_for_ai}

            # ── Pre-compute period filter strings (once, shared across all symbol threads) ──
            # KOSPI200 stocks avg 3000+ rows/file vs KOSPI avg 428 rows.
            # Without pre-filtering, indicator calculation wastes ~67% of work on history
            # that gets discarded by the period filter afterwards.
            def _ts_str(ts) -> str:
                if isinstance(ts, str):
                    return pd.to_datetime(ts).strftime("%Y-%m-%d")
                return ts.strftime("%Y-%m-%d")

            # ≈280 trading days baseline (covers MA-200); 장주기 지표는 동적 확장(H6).
            # 거래일→캘린더일 환산 ≈ ×1.45에 여유분을 더해 ×1.6 + 40일.
            _max_period = _max_indicator_period(req.get('entry'), req.get('exit'))
            _WARMUP_CALENDAR_DAYS = max(400, int(_max_period * 1.6) + 40)
            _has_period_filter = (period_req != 'FULL') or bool(start_date_req) or bool(end_date_req)
            _end_str = _ts_str(ref_date)
            _period_start_str: str | None = None
            _warmup_start_str: str | None = None

            if _has_period_filter:
                if start_date_req:
                    _period_start_dt = pd.to_datetime(start_date_req)
                elif period_req == '6M':
                    _period_start_dt = ref_date - pd.DateOffset(months=6)
                elif period_req == '1Y':
                    _period_start_dt = ref_date - pd.DateOffset(years=1)
                elif period_req == '3Y':
                    _period_start_dt = ref_date - pd.DateOffset(years=3)
                elif period_req in ['5Y', '10Y', '20Y']:
                    y = int(period_req[:-1])
                    _period_start_dt = pd.Timestamp(year=ref_date.year - (y-1), month=1, day=1)
                else:
                    _period_start_dt = None

                if _period_start_dt is not None:
                    _period_start_str = _period_start_dt.strftime("%Y-%m-%d")
                    _warmup_start_str = (_period_start_dt - pd.DateOffset(days=_WARMUP_CALENDAR_DAYS)).strftime("%Y-%m-%d")

            # ── Survivorship-bias-free universe (point-in-time membership) ──
            # When the request targets a market universe (kospi/kosdaq/kospi200), re-resolve
            # the symbol list from the point-in-time stock master so that names which delisted
            # *during* the window are included for the period they were alive. The legacy caller
            # passes only currently-listed symbols, which silently drops every delisted name and
            # inflates returns. universe_id=None (custom symbol set) leaves the list untouched.
            _markets, _is_large_cap = universe_pit.parse_universe_markets(req.get('universe_id'))
            _is_etf_universe = universe_pit.is_etf_universe(req.get('universe_id'))
            if _markets:
                _aof_symbols = universe_pit.resolve_symbols(req.get('universe_id'), _period_start_str, _end_str)
                if _aof_symbols:
                    symbols = _aof_symbols
                    print(f"[BT-ENGINE] PIT universe: {len(symbols)}종목 "
                          f"(markets={_markets}, large_cap={_is_large_cap})", flush=True)
            elif _is_etf_universe:
                # ETF 유니버스 — 주식과 혼합하지 않고 ETF 마스터만 조회한다. 마스터는 현재
                # 상장 ETF만 담으므로(상폐 ETF 미포함) 생존 편향 가능성을 정직하게 알린다.
                # ETF 매도에는 증권거래세가 부과되지 않는다 — 명시 옵션이 없으면 0으로 둔다.
                if options.get('sell_tax_rate') is None:
                    options['sell_tax_rate'] = 0.0
                _etf_symbols = universe_pit.resolve_etf_symbols(_period_start_str, _end_str)
                if _etf_symbols:
                    symbols = _etf_symbols
                # 상폐 ETF가 백필된 마스터(scripts/backfill_delisted_etf.py)면 경고하지
                # 않는다 — 미백필 상태에서만 생존 편향 가능성을 정직하게 알린다.
                if not universe_pit.etf_master_includes_delisted():
                    self.warnings.add(
                        "ETF 유니버스는 현재 상장 ETF만 포함합니다 — 기간 중 상장폐지된 ETF는 "
                        "빠져 있어 생존 편향 가능성이 있습니다."
                    )
                _etf_theme = req.get('etf_theme')
                if _etf_theme:
                    _themed = universe_pit.filter_etf_by_theme(symbols, _etf_theme)
                    if _themed:
                        symbols = _themed
                    else:
                        self.warnings.add(
                            f"'{_etf_theme}' 테마와 이름이 일치하는 ETF를 찾지 못해 "
                            "전체 ETF를 대상으로 백테스트했습니다."
                        )
                print(f"[BT-ENGINE] ETF universe: {len(symbols)}종목 "
                      f"(theme={req.get('etf_theme')})", flush=True)

            # ── 섹터/업종 제한 ──
            # 섹터 분류는 현재 상장(korea-stocks.json) + 상폐 백필(stock-master.json sector,
            # scripts/backfill_delisted_sectors.py)로 상폐 종목까지 커버한다. 그래도 업종
            # 미상으로 남아 필터에서 빠지는 종목이 실제로 있을 때만 생존 편향을 경고한다.
            # ETF엔 종목 섹터 분류가 적용되지 않는다(테마는 위 etf_theme가 담당) — 저장
            # DSL 등으로 sector가 남아 들어와도 전체가 빈 유니버스로 오폭하지 않게 무시한다.
            _sector = None if _is_etf_universe else req.get('sector')
            if _sector:
                # 복수 섹터는 합집합 필터(FR-STR-066 ⑦ — "반도체 + 기계/장비 업종").
                _sector_label = "·".join(universe_pit.sector_value_as_list(_sector))
                _sector_unknown = universe_pit.sector_unknown_delisted(symbols)
                symbols = universe_pit.filter_by_sector(symbols, _sector)
                if not symbols:
                    raise ValueError(f"'{_sector_label}' 섹터에 해당하는 종목을 찾지 못했습니다.")
                if _sector_unknown:
                    self.warnings.add(
                        f"섹터({_sector_label}) 필터: 업종 분류가 없는 상장폐지 종목 "
                        f"{len(_sector_unknown)}개가 제외되었습니다 — 생존 편향 가능성이 있습니다."
                    )
                print(f"[BT-ENGINE] 섹터 필터({_sector_label}): {len(symbols)}종목 "
                      f"(업종 미상 상폐 {len(_sector_unknown)})", flush=True)

            def _filter_to_backtest_window(df_pl: pl.DataFrame) -> pl.DataFrame:
                if not _has_period_filter:
                    return df_pl

                date_col = pl.col("date").cast(pl.Utf8)
                if _period_start_str is not None:
                    df_pl = df_pl.filter(date_col >= _period_start_str)
                return df_pl.filter(date_col <= _end_str)

            # Delisted names (per point-in-time master): their OHLCV ends at the delisting
            # day, so the forced exit there is a real liquidation, labelled accordingly.
            _delisted_dates = universe_pit.get_delisting_dates(symbols)

            def _close_at_last_available_row(entry_signals, exit_signals, exit_reasons, sym=None):
                if len(exit_signals) == 0:
                    return
                if exec_type == 'next_open':
                    if len(exit_signals) < 2:
                        return
                    exit_idx = len(exit_signals) - 2
                else:
                    exit_idx = len(exit_signals) - 1
                entry_signals[exit_idx:] = False
                exit_signals[exit_idx] = True
                if not exit_reasons[exit_idx]:
                    exit_reasons[exit_idx] = "상장폐지" if sym in _delisted_dates else "데이터 종료"

            def _process_symbol(sym):
                try:
                    # 1.1 Load Data
                    df_pl = self.loader.load_symbol_data(sym)
                    if df_pl is None or len(df_pl) == 0:
                        self.warnings.add(f"{sym}: 데이터 없음 — 백테스트 대상에서 제외되었습니다.")
                        return None

                    # 3.1.5 Pre-filter: clip to warmup window BEFORE indicator calculation.
                    # Reduces KOSPI200 from ~3000 rows to ~1400 rows before expensive indicator work.
                    if _warmup_start_str is not None:
                        df_pl = df_pl.filter(pl.col("date").cast(pl.Utf8) >= _warmup_start_str)
                    if len(df_pl) == 0:
                        return None

                    # 3.2 Indicators
                    indicators = []
                    def collect_indicators(group):
                        if not group: return
                        for c in group.get('conditions', []):
                            if 'conditions' in c: collect_indicators(c)
                            else: indicators.append(c)

                    collect_indicators(req.get('entry'))
                    collect_indicators(req.get('exit'))
                    df_pl = self.indicator_engine.calculate(df_pl, indicators)

                    # 3.2.5 DataResolver: 누락 데이터 즉시 해결
                    resolver = DataResolver()
                    df_pl, res_logs = resolver.resolve(sym, df_pl, req.get('entry'), req.get('exit'))
                    if res_logs:
                        all_resolution_logs.extend(res_logs)

                    # 3.3 AI: Phase1 전용 — df_pl과 AI 입력용 pdf를 저장하고 추론은 나중에 일괄 처리
                    if ai_needed:
                        _phase1_data[sym] = {
                            "df_pl": df_pl,
                            "pdf_for_ai": df_pl.to_pandas(),
                        }
                        return ("phase1_done", sym)
                    # AI 불필요: 기존 흐름 계속

                    # 3.4 Period Filtering (strip warmup rows, apply exact period bounds)
                    df_pl = _filter_to_backtest_window(df_pl)

                    if len(df_pl) < 1:
                        return None

                    # 3.5 Preprocessing (Adjusted Prices)
                    pdf = self.loader.preprocess_data(df_pl, apply_dividends=apply_dividends)
                    
                    # 3.6 Liquidity Check — compute the mask now, but defer the exclusion
                    # warning until we know the strategy actually wants to enter this symbol.
                    # Otherwise every fully-illiquid universe name (e.g. a delisted stock whose
                    # only in-window rows are 거래정지) emits noise even when the strategy would
                    # never trade it.
                    skip_risk = risk_params.get('skip_risk_management', False)
                    skip_pos = risk_params.get('skip_position_setting', False)

                    liquidity_ok = None
                    if not (skip_risk or skip_pos):
                        target_pos_amount = init_cash * (pos_size_pct / 100.0)
                        liquidity_ok = self.loader.check_liquidity(pdf, target_pos_amount, liquid_limit)

                    # 3.7 Signal Generation
                    entry_signals, entry_reasons = self.signal_engine.generate_signals(df_pl, req.get('entry'))
                    exit_signals, exit_reasons = self.signal_engine.generate_signals(df_pl, req.get('exit'))
                    _close_at_last_available_row(entry_signals, exit_signals, exit_reasons, sym)

                    if entry_signals is None:
                        return None

                    # Apply Liquidity Mask. Warn only when the strategy WANTED to enter but
                    # liquidity blocked every entry — a name the strategy never enters needs no message.
                    if liquidity_ok is not None:
                        wanted_entry = bool(entry_signals.any())
                        entry_signals = entry_signals & liquidity_ok
                        if wanted_entry and not entry_signals.any():
                            return ("warning", f"{sym}: 유동성 기준 미달 (거래대금 부족)")
                    
                    # Return result package
                    res = {
                        "symbol": sym,
                        "price": pdf['close'],
                        "exec_price": pdf['close'] if exec_type == 'same_close' else pdf['open'],
                        "high": pdf['high'] if 'high' in pdf.columns else pdf['close'],
                        "low": pdf['low'] if 'low' in pdf.columns else pdf['close'],
                        "entries": pd.Series(entry_signals, index=pdf.index),
                        "exits": pd.Series(exit_signals, index=pdf.index),
                        "entry_reasons": pd.Series(entry_reasons, index=pdf.index),
                        "exit_reasons": pd.Series(exit_reasons, index=pdf.index),
                        "index": pdf.index
                    }
                    if not (skip_risk or skip_pos):
                        res["liquidity"] = pd.Series(liquidity_ok, index=pdf.index)
                    if 'volume' in pdf.columns:
                        res["trading_value"] = pdf['close'] * pdf['volume']
                    if 'pbr' in pdf.columns: res["pbr"] = pdf['pbr']
                    if 'roe_or_gpa' in pdf.columns: res["roe"] = pdf['roe_or_gpa']
                    if _tracked_metrics:
                        res["coverage"] = data_coverage.symbol_stats(pdf, _tracked_metrics)
                    return ("success", res)

                except Exception as e:
                    return ("warning", f"{sym}: 처리 오류 ({e})")

            import concurrent.futures
            import os

            # Maximize threads for I/O and pre-processing. The global lock in AIEngine will protect the GPU/CPU Inference.
            max_threads = min(32, (os.cpu_count() or 1) + 4)

            def _collect_result(result):
                """결과 dict를 공유 컬렉션에 병합"""
                if result is None:
                    return
                status, data = result
                if status == "warning":
                    self.warnings.add(data)
                elif status == "success":
                    sym = data["symbol"]
                    all_prices[sym] = data["price"]
                    all_exec_prices[sym] = data["exec_price"]
                    all_highs[sym] = data["high"]
                    all_lows[sym] = data["low"]
                    all_entries[sym] = data["entries"]
                    all_exits[sym] = data["exits"]
                    all_entry_reasons[sym] = data["entry_reasons"]
                    all_exit_reasons[sym] = data["exit_reasons"]
                    if "liquidity" in data: all_liquidity[sym] = data["liquidity"]
                    if "trading_value" in data: all_trading_values[sym] = data["trading_value"]
                    if "pbr" in data: all_ranks['pbr'][sym] = data["pbr"]
                    if "roe" in data: all_ranks['roe'][sym] = data["roe"]
                    if "ai_drop_score" in data: all_drop_scores[sym] = data["ai_drop_score"]
                    if _coverage_acc is not None and "coverage" in data:
                        _coverage_acc.fold(data["coverage"])
                    processed_symbols.append(sym)

            # Phase 1: 병렬 데이터 로드 + 지표 계산
            _t1 = _time.time()
            print(f"[BT-ENGINE] Phase1 시작: {len(symbols)}종목, period={period_req}", flush=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
                future_to_sym = {executor.submit(_process_symbol, sym): sym for sym in symbols}
                for future in concurrent.futures.as_completed(future_to_sym):
                    result = future.result()
                    if result is None:
                        continue
                    status, data = result
                    if status == "phase1_done":
                        pass  # AI 종목: Phase2에서 일괄 처리
                    else:
                        _collect_result(result)

            # Phase 2: AI 일괄 추론 (단일 lock, 단일 XGBoost 호출)
            if ai_needed and _phase1_data:
                engine = self.ai_engine
                t_ai_start = pd.Timestamp.now()
                if engine:
                    print(f"[AI-Batch] {len(_phase1_data)}종목 일괄 추론 시작...", flush=True)
                    batch_scores = engine.predict_signals_batch(
                        {sym: d["pdf_for_ai"] for sym, d in _phase1_data.items()}
                    )
                    elapsed = (pd.Timestamp.now() - t_ai_start).total_seconds()
                    print(f"[AI-Batch] 완료: {elapsed:.1f}s ({len(_phase1_data)}종목)", flush=True)
                else:
                    batch_scores = {}

                # Phase 3: AI 점수 주입 후 신호 생성 (병렬)
                def _finalize_symbol(sym):
                    try:
                        d = _phase1_data[sym]
                        df_pl = d["df_pl"]
                        zeros = [0.0] * len(df_pl)
                        ai_probs, ai_drop_probs = batch_scores.get(sym, (zeros, zeros))
                        df_pl = df_pl.with_columns([
                            pl.Series("ai_score", list(ai_probs) if not isinstance(ai_probs, list) else ai_probs),
                            pl.Series("ai_drop_score", list(ai_drop_probs) if not isinstance(ai_drop_probs, list) else ai_drop_probs),
                        ])

                        # 3.2.5 DataResolver: 누락 데이터 즉시 해결 (AI 경로)
                        resolver = DataResolver()
                        df_pl, res_logs = resolver.resolve(sym, df_pl, req.get('entry'), req.get('exit'))
                        if res_logs:
                            all_resolution_logs.extend(res_logs)

                        # Use pre-computed period strings (data already warmup-pre-filtered in Phase1)
                        df_pl = _filter_to_backtest_window(df_pl)

                        if len(df_pl) < 1:
                            return None

                        pdf = self.loader.preprocess_data(df_pl, apply_dividends=apply_dividends)
                        skip_risk = risk_params.get('skip_risk_management', False)
                        skip_pos = risk_params.get('skip_position_setting', False)

                        liquidity_ok = None
                        if not (skip_risk or skip_pos):
                            target_pos_amount = init_cash * (pos_size_pct / 100.0)
                            liquidity_ok = self.loader.check_liquidity(pdf, target_pos_amount, liquid_limit)

                        entry_signals, entry_reasons = self.signal_engine.generate_signals(df_pl, req.get('entry'))
                        exit_signals, exit_reasons = self.signal_engine.generate_signals(df_pl, req.get('exit'))
                        _close_at_last_available_row(entry_signals, exit_signals, exit_reasons, sym)

                        if entry_signals is None:
                            return None

                        # Warn only when the strategy wanted to enter but liquidity blocked every entry.
                        if liquidity_ok is not None:
                            wanted_entry = bool(entry_signals.any())
                            entry_signals = entry_signals & liquidity_ok
                            if wanted_entry and not entry_signals.any():
                                return ("warning", f"{sym}: 유동성 기준 미달 (거래대금 부족)")

                        res = {
                            "symbol": sym,
                            "price": pdf['close'],
                            "exec_price": pdf['close'] if exec_type == 'same_close' else pdf['open'],
                            "high": pdf['high'] if 'high' in pdf.columns else pdf['close'],
                            "low": pdf['low'] if 'low' in pdf.columns else pdf['close'],
                            "entries": pd.Series(entry_signals, index=pdf.index),
                            "exits": pd.Series(exit_signals, index=pdf.index),
                            "entry_reasons": pd.Series(entry_reasons, index=pdf.index),
                            "exit_reasons": pd.Series(exit_reasons, index=pdf.index),
                            "index": pdf.index,
                        }
                        if not (skip_risk or skip_pos):
                            res["liquidity"] = pd.Series(liquidity_ok, index=pdf.index)
                        if 'volume' in pdf.columns:
                            res["trading_value"] = pdf['close'] * pdf['volume']
                        if 'pbr' in pdf.columns: res["pbr"] = pdf['pbr']
                        if 'roe_or_gpa' in pdf.columns: res["roe"] = pdf['roe_or_gpa']
                        if drop_rank_pct is not None and 'ai_drop_score' in pdf.columns:
                            res["ai_drop_score"] = pdf['ai_drop_score']
                        if _tracked_metrics:
                            res["coverage"] = data_coverage.symbol_stats(pdf, _tracked_metrics)
                        return ("success", res)
                    except Exception as e:
                        return ("warning", f"{sym}: 처리 오류 ({e})")

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
                    for result in executor.map(_finalize_symbol, _phase1_data.keys()):
                        _collect_result(result)

            # 4. Simulation
            if not processed_symbols:
                raise Exception("분석 가능한 유효한 데이터가 없습니다.")

            # Determinism: Sort symbols so column order is always the same
            processed_symbols.sort()
            
            # Create DataFrames with explicit sorted column list
            raw_price_df = pd.DataFrame(all_prices, columns=processed_symbols).sort_index()
            # available_df is captured from the RAW (pre-fill) frame, so it is True
            # only where a real price existed. ffill/bfill below make the price grid
            # NaN-free for VectorBT, but bfill pulls a symbol's first listing price
            # *backward* into its pre-listing slots — a potential look-ahead leak.
            # That leak is neutralised by masking every entry/exit signal AND the
            # ranking candidate pool with available_df (see &= available_df below and
            # the ranking blocks): no trade can occur in a back-filled region.
            # test_lookahead_no_prelisting_trades.py locks this invariant.
            available_df = raw_price_df.notna()
            # 거래정지 추정: 봉은 존재하나 당일 거래량이 0(가격 동결)인 날은 실제로
            # 체결이 불가능하므로 available_df에서 제외한다. 거래대금(=종가×거래량)은
            # 종가>0(정제 후)이므로 거래대금 0 ⇔ 거래량 0과 동치다. 이렇게 하면
            # 시뮬레이터가 정지 봉의 진입·청산을 다음 거래 가능일로 이월(pending_exit)하고,
            # 대형주·랭킹 후보 풀에서도 자동 제외된다. NaN(거래대금 미수집·미상장 구간)은
            # 정지로 간주하지 않아 기존 동작을 유지한다.
            if all_trading_values:
                halted_df = pd.DataFrame(
                    all_trading_values, index=raw_price_df.index, columns=processed_symbols
                ).eq(0.0)  # NaN == 0.0 → False
                available_df &= ~halted_df
            price_df = raw_price_df
            common_index = price_df.index

            price_df = price_df.ffill().bfill()
            exec_px_df = pd.DataFrame(all_exec_prices, index=common_index, columns=processed_symbols).ffill().bfill()
            # 장중 스탑 감지용 고가/저가 패널 (C5). ffill 구간(거래정지 등)은
            # available_df가 False라 시뮬레이터가 체결을 이월한다.
            high_df = pd.DataFrame(all_highs, index=common_index, columns=processed_symbols).ffill().bfill()
            low_df = pd.DataFrame(all_lows, index=common_index, columns=processed_symbols).ffill().bfill()
            _raw_ents = pd.DataFrame(all_entries, index=common_index, columns=processed_symbols)
            _raw_exts = pd.DataFrame(all_exits, index=common_index, columns=processed_symbols)
            import numpy as np
            ents_df = pd.DataFrame(np.where(_raw_ents.isna(), False, _raw_ents).astype(bool), index=common_index, columns=processed_symbols)
            exts_df = pd.DataFrame(np.where(_raw_exts.isna(), False, _raw_exts).astype(bool), index=common_index, columns=processed_symbols)

            if exec_type == 'next_open':
                ents_df = ents_df.shift(1, fill_value=False)
                exts_df = exts_df.shift(1, fill_value=False)
            ents_df &= available_df
            exts_df &= available_df

            # 횡단면 AI 하락 랭킹 청산 주입: 매일 유니버스 상위 X% 하락위험 종목을 청산 신호로.
            # 시뮬레이터는 보유 종목에만 청산을 적용하므로 유니버스 전체에 신호를 켜도 안전.
            if drop_rank_pct is not None and all_drop_scores:
                from engine.rank_exit import compute_topk_drop_exits
                drop_df = pd.DataFrame(all_drop_scores, index=common_index, columns=processed_symbols)
                rank_exits = compute_topk_drop_exits(drop_df, drop_rank_pct, available_df)
                if rank_exits is not None:
                    if exec_type == 'next_open':
                        rank_exits = rank_exits.shift(1, fill_value=False)
                    exts_df = (exts_df | rank_exits.astype(bool)) & available_df

            # ── "대형주" / KOSPI200 = point-in-time top-N by market cap ──
            # Static current KOSPI200 membership is itself survivorship-biased, so we define the
            # large-cap universe as the daily top-LARGE_CAP_TOP_N alive KOSPI names by market cap
            # (close × listed shares). Market cap is evaluated only where price data is actually
            # available that day, so delisted names drop out of the ranking once they stop trading.
            large_cap_mask = None
            if _is_large_cap:
                shares_map = universe_pit.get_shares(processed_symbols)
                shares_vec = pd.Series(
                    {s: shares_map.get(s, np.nan) for s in processed_symbols},
                    dtype=float,
                )
                mcap = price_df.mul(shares_vec, axis=1).where(available_df)
                mcap_rank = mcap.rank(axis=1, ascending=False, method="first")
                large_cap_mask = (mcap_rank <= universe_pit.LARGE_CAP_TOP_N).fillna(False)
                if exec_type == 'next_open':
                    # 진입 신호는 이미 1일 shift됨 — 시총 순위도 전일 종가 기준으로
                    # 맞춰야 당일 종가를 미리 아는 look-ahead가 없다.
                    large_cap_mask = large_cap_mask.shift(1, fill_value=False)
                ents_df &= large_cap_mask
                self.warnings.add(
                    "대형주(시가총액 상위) 판정은 현재 상장주식수 × 과거 주가의 근사입니다 — "
                    "과거 증자·분할 이력은 반영되지 않아 실제 당시 KOSPI200 구성과 다를 수 있습니다."
                )

            rank_df = None
            skip_pos = risk_params.get('skip_position_setting', False)
            ranking_metric = risk_params.get('ranking_metric')
            if ranking_metric == 'return':
                # 상대강도(모멘텀) 랭킹: N일 수익률 순위로 상위 종목 선정.
                # 종목 간 횡단면 순위라 진입 신호 없이 순위 자체가 진입이 된다. 회전(월간 등)은
                # 달력 리밸런싱(engine/rebalance.py + simulator의 목표비중/재구성 경로)이 구동한다.
                try:
                    lookback = int(risk_params.get('ranking_lookback_days') or 60)
                    momentum = price_df.pct_change(lookback)
                    rank_df = momentum.rank(axis=1, pct=True)
                    # 수익률이 정의되지 않은 초기 lookback 구간(NaN)에는 종목을 후보에서 제외한다.
                    # 그러지 않으면 순위가 0으로 동률이 되어 임의 종목을 사서 들고 있게 된다.
                    valid = momentum.notna()
                    if exec_type == 'next_open':
                        rank_df = rank_df.shift(1)
                        valid = valid.shift(1, fill_value=False)
                    rank_df = rank_df.fillna(0.0)
                    # 진입 신호가 없으면(선정=진입) 수익률이 정의된 전 종목을 후보로 만들어 상위 K를 채운다.
                    # C4: 이 오버라이드가 대형주(KOSPI200) 마스크와 유동성 게이트를
                    # 덮어쓰지 않도록 두 마스크를 후보 풀에 다시 결합한다.
                    _entry_conditions = (req.get('entry') or {}).get('conditions') or []
                    if not _entry_conditions:
                        pool = available_df & valid
                        if large_cap_mask is not None:
                            pool &= large_cap_mask
                        if all_liquidity:
                            liq_df = pd.DataFrame(
                                all_liquidity, index=common_index, columns=processed_symbols
                            ).eq(True)  # NaN(데이터 없는 날) → False, bool dtype 보장
                            if exec_type == 'next_open':
                                liq_df = liq_df.shift(1, fill_value=False)
                            pool &= liq_df
                        ents_df = pool
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 수익률 랭킹 계산 실패: {e}")
                    rank_df = None
            elif (not skip_pos) and risk_params.get('ranking_enabled', True) and all_ranks['pbr'] and all_ranks['roe']:
                try:
                    pbr_df = pd.DataFrame(all_ranks['pbr'], index=common_index, columns=processed_symbols).ffill().fillna(1.0)
                    roe_df = pd.DataFrame(all_ranks['roe'], index=common_index, columns=processed_symbols).ffill().fillna(0.0)

                    if exec_type == 'next_open':
                        pbr_df = pbr_df.shift(1).ffill()
                        roe_df = roe_df.shift(1).ffill()

                    v_score = 1.0 - pbr_df.rank(axis=1, pct=True)
                    q_score = roe_df.rank(axis=1, pct=True)
                    w_v = float(risk_params.get('ranking_weight_value', 0.5))
                    w_q = float(risk_params.get('ranking_weight_quality', 0.5))
                    rank_df = (v_score * w_v) + (q_score * w_q)
                except Exception as e:
                    # Fix 12: 무음 예외 대신 경고 로깅으로 원인 추적 가능하게
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 랭킹 계산 실패: {e}")
                    rank_df = None

            _t2 = _time.time()
            print(f"[BT-ENGINE] Phase1 완료: {_t2-_t1:.2f}s ({len(processed_symbols)}종목 처리)", flush=True)

            simulator_options = dict(options)
            simulator_options.setdefault('execution_type', exec_type)

            pf = self.simulator.run(
                price_df, exec_px_df, ents_df, exts_df, risk_params, simulator_options,
                rank_df=rank_df, high_df=high_df, low_df=low_df, available_df=available_df,
            )
            _t3 = _time.time()
            print(f"[BT-ENGINE] Simulator 완료: {_t3-_t2:.2f}s", flush=True)

            # 5. Benchmark ETF 로드
            _benchmark_sym, _benchmark_name = self.benchmark_for_universe(req.get('universe_id') or '')
            benchmark_prices = None
            try:
                _bench_df = self.loader.load_symbol_data(_benchmark_sym)
                if _bench_df is not None:
                    _bench_pd = self.loader.preprocess_data(_bench_df, apply_dividends=apply_dividends)
                    benchmark_prices = _bench_pd['close'].sort_index()
                    # H1: 벤치마크 ETF 상장 이전 구간은 수익률 0%로 고정되어 비교가 왜곡됨
                    if len(common_index) > 0 and benchmark_prices.index[0] > pd.Timestamp(common_index[0]):
                        self.warnings.add(
                            f"벤치마크({_benchmark_name}) 데이터가 "
                            f"{benchmark_prices.index[0].strftime('%Y-%m-%d')}부터 존재합니다 — "
                            "그 이전 구간의 벤치마크 수익률은 0%로 표시되어 전략 대비 비교가 과장될 수 있습니다."
                        )
                    # M3: 전략은 토탈리턴인데 벤치마크에 분배금 데이터가 없으면 비대칭 비교
                    if apply_dividends and 'dividends' not in _bench_df.columns:
                        self.warnings.add(
                            "벤치마크 ETF에 분배금 데이터가 없어 가격리턴 기준으로 비교됩니다 — "
                            "전략(배당 재투자 기본)이 상대적으로 유리하게 보일 수 있습니다."
                        )
            except Exception as _be:
                print(f"[BT-ENGINE] 벤치마크 로드 실패 ({_benchmark_sym}): {_be}", flush=True)

            # 5. Format
            final = self.handler.format_results(
                pf, processed_symbols, all_entries, all_exits,
                all_entry_reasons, all_exit_reasons, common_index,
                risk_params, exec_type, init_cash,
                benchmark_prices=benchmark_prices,
                benchmark_label=_benchmark_name,
                risk_free_rate=float(options.get('risk_free_rate') or 0.0),
                exit_reason_overrides=getattr(self.simulator, 'exit_reason_overrides', None),
            )
            final["universe_id"] = req.get('universe_id') or ''
            _t4 = _time.time()
            print(f"[BT-ENGINE] Format 완료: {_t4-_t3:.2f}s", flush=True)
            print(f"[BT-ENGINE] 총 소요: {_t4-_t0:.2f}s", flush=True)

            # 단계별 소요 시간 — 워크포워드 진행 모달에서 시도(trial)마다 표시한다.
            # (BacktestResponse 스키마엔 없어 /backtest HTTP 응답에선 자동으로 무시됨)
            final["timing"] = {
                "phase1": round(_t2 - _t1, 2),
                "simulator": round(_t3 - _t2, 2),
                "format": round(_t4 - _t3, 2),
                "total": round(_t4 - _t0, 2),
                "symbols": len(processed_symbols),
            }

            # Add no-trades warning
            if pf.trades.count() == 0:
                liquidity_excluded = [
                    w.split(":", 1)[0]
                    for w in self.warnings
                    if isinstance(w, str) and "유동성 기준 미달" in w
                ]
                msg = "매매 기록이 생성되지 않았습니다. 매수 조건 또는 유동성/포지션 설정을 확인해 주세요."
                if liquidity_excluded:
                    preview = ", ".join(liquidity_excluded[:3])
                    suffix = f" 외 {len(liquidity_excluded) - 3}종목" if len(liquidity_excluded) > 3 else ""
                    msg += (
                        f" (유동성 기준 미달로 제외된 종목 {len(liquidity_excluded)}개: {preview}{suffix}"
                        " — 포지션 크기를 줄이거나 유동성 한도를 낮추면 포함될 수 있습니다)"
                    )
                self.warnings.add(msg)

            # ── 신뢰성 공시 경고 (감사 H5/H7/H8 등) ──────────────────────────
            _rebal_period = str(risk_params.get('rebalancing_period') or 'none')
            _has_pos_risk = (not risk_params.get('skip_risk_management', False)) and any(
                float(risk_params.get(k) or 0) > 0
                for k in ('stop_loss_pct', 'take_profit_pct', 'trailing_stop_pct', 'max_holding_days')
            )
            if _rebal_period != 'none' and risk_params.get('max_positions') and _has_pos_risk:
                # H8: 리스크 관리와 혼합된 리밸런싱은 종목 교체(reconstitution)만 수행
                self.warnings.add(
                    "리밸런싱과 손절/익절/트레일링/보유기간 제한이 함께 설정되어 리밸런싱일에는 "
                    "종목 교체만 수행합니다 — 유지 종목의 비중은 목표 비중으로 리셋되지 않습니다."
                )

            _tax_raw = options.get('sell_tax_rate')
            _tax_val = float(_tax_raw) if _tax_raw is not None else 0.0015
            if _tax_val > 0:
                self.warnings.add(
                    f"매도 체결에 증권거래세 {_tax_val * 100:.2f}%가 반영되었습니다."
                )

            _n_trades = int(pf.trades.count())
            if 0 < _n_trades < 30:
                self.warnings.add(
                    f"거래 수가 {_n_trades}건으로 30건 미만입니다 — "
                    "승률·Profit Factor 등 통계의 표본 신뢰도가 낮습니다."
                )

            if ai_needed:
                # H7: 백테스트 구간이 AI 모델 학습 데이터와 겹치면 인샘플 낙관 편향
                _train_end = _ai_model_train_end()
                if _train_end and (_period_start_str is None or _period_start_str < _train_end):
                    self.warnings.add(
                        f"AI 모델 학습 데이터(~{_train_end})와 백테스트 기간이 겹칩니다 — "
                        "겹치는 구간의 AI 신호 성과는 인샘플(낙관 편향)일 수 있습니다."
                    )

            # H5: 체결 규모 사후 검증 — 매수 금액이 전일 거래대금 한도를 초과한 거래 수
            try:
                _liq_viol = 0
                if all_trading_values and liquid_limit > 0:
                    for sig in final.get("signals", []):
                        if sig.get("type") != "buy":
                            continue
                        tv_ser = all_trading_values.get(sig.get("symbol"))
                        if tv_ser is None or len(tv_ser) < 2:
                            continue
                        pos = tv_ser.index.searchsorted(pd.Timestamp(sig["date"]))
                        if pos >= 1:
                            prev_tv = float(tv_ser.iloc[pos - 1])
                            if prev_tv > 0 and sig.get("amount", 0) > prev_tv * (liquid_limit / 100.0):
                                _liq_viol += 1
                if _liq_viol > 0:
                    self.warnings.add(
                        f"매수 {_liq_viol}건이 전일 거래대금의 {liquid_limit:.0f}%를 초과하는 규모입니다 — "
                        "실전에서는 시장충격으로 이 가격에 전량 체결되기 어려울 수 있습니다."
                    )
            except Exception:
                pass

            # 데이터 커버리지 리포트 — 각 펀더멘털 지표가 실제로 어떤 데이터로/얼마나
            # 계산됐는지 결과 로그에 투명하게 남기고, 부족 시 경고를 warnings에 합류시킨다.
            if _coverage_acc is not None:
                _coverage_report = _coverage_acc.build()
                final["dataCoverage"] = _coverage_report
                for _w in _coverage_report.get("warnings", []):
                    self.warnings.add(_w)

            final["warnings"] = list(self.warnings) + list(getattr(pf, 'warnings', []))
            final["resolution_logs"] = all_resolution_logs
            return final

        except Exception as e:
            import traceback; traceback.print_exc()
            raise e
