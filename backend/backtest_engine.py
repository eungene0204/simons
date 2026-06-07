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

            # Reference date for relative periods
            ref_date = pd.to_datetime(end_date_req) if end_date_req else pd.to_datetime('today').normalize()

            # 2. Data Structures for Vectorbt
            all_prices, all_exec_prices, all_entries, all_exits = {}, {}, {}, {}
            all_entry_reasons, all_exit_reasons = {}, {}
            all_ranks = {'pbr': {}, 'roe': {}}
            all_resolution_logs: List[Dict[str, str]] = []
            processed_symbols = []
            common_index = None

            # Pre-load AI engine to avoid race conditions during lazy loading
            if ai_needed:
                self.ai_engine

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

            _WARMUP_CALENDAR_DAYS = 400  # ≈280 trading days; covers MA-200 warmup
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

            def _filter_to_backtest_window(df_pl: pl.DataFrame) -> pl.DataFrame:
                if not _has_period_filter:
                    return df_pl

                date_col = pl.col("date").cast(pl.Utf8)
                if _period_start_str is not None:
                    df_pl = df_pl.filter(date_col >= _period_start_str)
                return df_pl.filter(date_col <= _end_str)

            def _close_at_last_available_row(entry_signals, exit_signals, exit_reasons):
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
                    exit_reasons[exit_idx] = "데이터 종료"

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
                    pdf = self.loader.preprocess_data(df_pl)
                    
                    # 3.6 Liquidity Check
                    skip_risk = risk_params.get('skip_risk_management', False)
                    skip_pos = risk_params.get('skip_position_setting', False)
                    
                    if not (skip_risk or skip_pos):
                        target_pos_amount = init_cash * (pos_size_pct / 100.0)
                        liquidity_ok = self.loader.check_liquidity(pdf, target_pos_amount, liquid_limit)
                        if liquidity_ok.sum() == 0:
                            return ("warning", f"{sym}: 유동성 기준 미달 (거래대금 부족)")

                    # 3.7 Signal Generation
                    entry_signals, entry_reasons = self.signal_engine.generate_signals(df_pl, req.get('entry'))
                    exit_signals, exit_reasons = self.signal_engine.generate_signals(df_pl, req.get('exit'))
                    _close_at_last_available_row(entry_signals, exit_signals, exit_reasons)

                    # Apply Liquidity Mask
                    if not (skip_risk or skip_pos):
                        entry_signals = entry_signals & liquidity_ok
                    
                    if entry_signals is None: 
                        return None
                    
                    # Return result package
                    res = {
                        "symbol": sym,
                        "price": pdf['close'],
                        "exec_price": pdf['close'] if exec_type == 'same_close' else pdf['open'],
                        "entries": pd.Series(entry_signals, index=pdf.index),
                        "exits": pd.Series(exit_signals, index=pdf.index),
                        "entry_reasons": pd.Series(entry_reasons, index=pdf.index),
                        "exit_reasons": pd.Series(exit_reasons, index=pdf.index),
                        "index": pdf.index
                    }
                    if 'pbr' in pdf.columns: res["pbr"] = pdf['pbr']
                    if 'roe_or_gpa' in pdf.columns: res["roe"] = pdf['roe_or_gpa']
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
                    all_entries[sym] = data["entries"]
                    all_exits[sym] = data["exits"]
                    all_entry_reasons[sym] = data["entry_reasons"]
                    all_exit_reasons[sym] = data["exit_reasons"]
                    if "pbr" in data: all_ranks['pbr'][sym] = data["pbr"]
                    if "roe" in data: all_ranks['roe'][sym] = data["roe"]
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

                        pdf = self.loader.preprocess_data(df_pl)
                        skip_risk = risk_params.get('skip_risk_management', False)
                        skip_pos = risk_params.get('skip_position_setting', False)

                        if not (skip_risk or skip_pos):
                            target_pos_amount = init_cash * (pos_size_pct / 100.0)
                            liquidity_ok = self.loader.check_liquidity(pdf, target_pos_amount, liquid_limit)
                            if liquidity_ok.sum() == 0:
                                return ("warning", f"{sym}: 유동성 기준 미달 (거래대금 부족)")

                        entry_signals, entry_reasons = self.signal_engine.generate_signals(df_pl, req.get('entry'))
                        exit_signals, exit_reasons = self.signal_engine.generate_signals(df_pl, req.get('exit'))
                        _close_at_last_available_row(entry_signals, exit_signals, exit_reasons)

                        if not (skip_risk or skip_pos):
                            entry_signals = entry_signals & liquidity_ok

                        if entry_signals is None:
                            return None

                        res = {
                            "symbol": sym,
                            "price": pdf['close'],
                            "exec_price": pdf['close'] if exec_type == 'same_close' else pdf['open'],
                            "entries": pd.Series(entry_signals, index=pdf.index),
                            "exits": pd.Series(exit_signals, index=pdf.index),
                            "entry_reasons": pd.Series(entry_reasons, index=pdf.index),
                            "exit_reasons": pd.Series(exit_reasons, index=pdf.index),
                            "index": pdf.index,
                        }
                        if 'pbr' in pdf.columns: res["pbr"] = pdf['pbr']
                        if 'roe_or_gpa' in pdf.columns: res["roe"] = pdf['roe_or_gpa']
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
            available_df = raw_price_df.notna()
            price_df = raw_price_df
            common_index = price_df.index
            
            price_df = price_df.ffill().bfill()
            exec_px_df = pd.DataFrame(all_exec_prices, index=common_index, columns=processed_symbols).ffill().bfill()
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

            rank_df = None
            skip_pos = risk_params.get('skip_position_setting', False)
            ranking_metric = risk_params.get('ranking_metric')
            if ranking_metric == 'return':
                # 상대강도(모멘텀) 랭킹: N일 수익률 순위로 상위 종목 선정.
                # 종목 간 횡단면 순위라 진입 신호 없이 순위 자체가 진입이 된다. 회전(월간 등)은
                # max_holding_days 만료로 구동(엔진에 별도 리밸런싱 로직 없음).
                try:
                    lookback = int(risk_params.get('ranking_lookback_days') or 60)
                    momentum = price_df.pct_change(lookback)
                    rank_df = momentum.rank(axis=1, pct=True)
                    if exec_type == 'next_open':
                        rank_df = rank_df.shift(1)
                    rank_df = rank_df.fillna(0.0)
                    # 진입 신호가 없으면(선정=진입) 전 종목을 후보로 만들어 순위로 상위 K를 채운다.
                    _entry_conditions = (req.get('entry') or {}).get('conditions') or []
                    if not _entry_conditions:
                        ents_df = available_df.copy()
                        if exec_type == 'next_open':
                            ents_df = ents_df.shift(1, fill_value=False)
                        ents_df &= available_df
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
                price_df, exec_px_df, ents_df, exts_df, risk_params, simulator_options, rank_df=rank_df
            )
            _t3 = _time.time()
            print(f"[BT-ENGINE] Simulator 완료: {_t3-_t2:.2f}s", flush=True)

            # 5. Benchmark ETF 로드
            _benchmark_sym, _benchmark_name = self.benchmark_for_universe(req.get('universe_id') or '')
            benchmark_prices = None
            try:
                _bench_df = self.loader.load_symbol_data(_benchmark_sym)
                if _bench_df is not None:
                    _bench_pd = self.loader.preprocess_data(_bench_df)
                    benchmark_prices = _bench_pd['close'].sort_index()
            except Exception as _be:
                print(f"[BT-ENGINE] 벤치마크 로드 실패 ({_benchmark_sym}): {_be}", flush=True)

            # 5. Format
            final = self.handler.format_results(
                pf, processed_symbols, all_entries, all_exits,
                all_entry_reasons, all_exit_reasons, common_index,
                risk_params, exec_type, init_cash,
                benchmark_prices=benchmark_prices,
                benchmark_label=_benchmark_name,
            )
            final["universe_id"] = req.get('universe_id') or ''
            _t4 = _time.time()
            print(f"[BT-ENGINE] Format 완료: {_t4-_t3:.2f}s", flush=True)
            print(f"[BT-ENGINE] 총 소요: {_t4-_t0:.2f}s", flush=True)

            # Add no-trades warning
            if pf.trades.count() == 0:
                self.warnings.add("매매 조건에 부합하는 종목이 없어 매매 기록이 생성되지 않았습니다. 매수 조건을 확인해 주세요.")

            final["warnings"] = list(self.warnings) + list(getattr(pf, 'warnings', []))
            final["resolution_logs"] = all_resolution_logs
            return final

        except Exception as e:
            import traceback; traceback.print_exc()
            raise e
