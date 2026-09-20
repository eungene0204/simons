import contextlib
import os
import polars as pl
import pandas as pd
from typing import Dict, List, Any, Optional

# Import refactored modules
from engine.loader import DataLoader
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine, FUNDAMENTAL_LABELS
from engine.simulator import Simulator, applied_trading_costs
from engine.result_handler import ResultHandler
from engine.data_resolver import DataResolver
from engine.prep_cache import SymbolPrepCache
from engine.phase1 import date_key
from engine import phase1 as _phase1
from engine import phase1_pool as _phase1_pool
from engine import trade_reason as tr
from engine import result_warnings as rw
from engine import universe_pit
from engine import data_coverage


def _composite_ranking_components(risk_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """복합 순위 합산(FR-BT-063)의 구성 지표 목록. ranking_metric='composite'가 아니거나
    구성 지표가 2개 미만이면 빈 리스트(합산이 성립하지 않는다 — 단일 지표는 기존 분기)."""
    if risk_params.get('ranking_metric') != 'composite':
        return []
    comps = [
        c for c in (risk_params.get('ranking_components') or [])
        if isinstance(c, dict) and c.get('metric')
    ]
    return comps if len(comps) >= 2 else []


# 리밸런싱 주기의 한국어 정본 템플릿 — 매수 사유에 인자로 꽂힌다.
_REBAL_PERIOD_TEMPLATES = {
    'daily': tr.REBAL_PERIOD_DAILY, 'weekly': tr.REBAL_PERIOD_WEEKLY,
    'monthly': tr.REBAL_PERIOD_MONTHLY, 'bimonthly': tr.REBAL_PERIOD_BIMONTHLY,
    'quarterly': tr.REBAL_PERIOD_QUARTERLY, 'yearly': tr.REBAL_PERIOD_YEARLY,
}


def _composite_ranking_label_segment(components: List[Dict[str, Any]], default_lookback=None) -> Dict[str, Any]:
    """복합 순위 라벨의 구조화 표현 — '복합 순위(ROE 높은·PER 낮은)'."""
    parts = []
    for c in components:
        m = str(c.get('metric'))
        lookback = int(c.get('lookback_days') or default_lookback or 60)
        if m == 'return':
            skip = int(c.get('skip_days') or 0)
            name = (tr.part(tr.COMPOSITE_RETURN_SKIP_METRIC, lookback, skip) if skip
                    else tr.part(tr.COMPOSITE_RETURN_METRIC, lookback))
        elif m == 'relative_return':
            name = tr.part(tr.COMPOSITE_RELATIVE_RETURN_METRIC, lookback)
        elif m == 'volatility':
            name = tr.part(tr.COMPOSITE_VOLATILITY_METRIC, lookback)
        else:
            name = tr.part(FUNDAMENTAL_LABELS.get(m, m))
        bottom = c.get('direction') == 'bottom'
        parts.append([tr.part(tr.COMPOSITE_COMPONENT_LOW if bottom else tr.COMPOSITE_COMPONENT_HIGH, name)])
    return tr.part(tr.COMPOSITE_RANK, tr.join(parts, [tr.SEP_MID_DOT]))


def _composite_ranking_label(components: List[Dict[str, Any]], default_lookback=None) -> str:
    """매수 사유·그룹 라벨용 한글 표기 — '복합 순위(ROE 높은·PER 낮은)'."""
    return tr.render_kr([_composite_ranking_label_segment(components, default_lookback)])

def _ai_signals_enabled() -> bool:
    """AI 예측 신호(ai_model/ai_drop_model) 실행 허용 여부. 운영 스위치(기본 ON).

    기능을 꺼둔 배포에서 파싱·캐시 등 다른 경로로 AI 신호가 흘러 들어와도
    엔진이 최종 관문에서 즉시 거절하게 한다(AI_SIGNALS_ENABLED=0).
    """
    return os.environ.get("AI_SIGNALS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _ai_model_meta() -> dict:
    """라이브 AI 모델 메타(model/v3 → v2). 없거나 깨졌으면 빈 dict."""
    import json
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
    for ver in ('v3', 'v2'):
        meta_path = os.path.join(base, 'model', ver, 'model_meta.json')
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    return json.load(f) or {}
            except (ValueError, OSError):
                return {}
    return {}


def _ai_model_train_end() -> str | None:
    """라이브 AI 모델 메타의 학습 종료일(train_end). 없으면 None. (감사 H7)"""
    val = _ai_model_meta().get('train_end')
    return str(val) if val else None


def _ai_model_val_end(meta: dict | None = None) -> str | None:
    """검증 구간 종료일 — 'val_range': "2023-01-21 ~ 2024-07-01" 형식의 뒤쪽 날짜.
    임계값 보정·조기종료가 이 구간으로 정해지므로 학습 구간과 같은 인샘플이다."""
    val = (meta if meta is not None else _ai_model_meta()).get('val_range')
    if not val or '~' not in str(val):
        return None
    end = str(val).split('~')[-1].strip()
    return end or None


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


# 날짜 키(YYYY-MM-DD 문자열 비교)는 Phase1 모듈이 정본 — 종목별 파이프라인과 같은 규칙을 쓴다.
_date_key = date_key


# 랭킹을 말하지 않은 전략의 후보 우선순위 산정 기간(거래일, v16.3) — 매수 조건 충족 종목이
# 빈 자리보다 많은 날에만 쓰이며, 쓰였으면 경고로 고지한다.
_TIEBREAK_LOOKBACK_DAYS = 60


INVERSE_VOLATILITY_ALLOCATION = 'inverse_volatility'


def _inverse_volatility_allocation(risk_params: Dict[str, Any]) -> bool:
    """변동성 역비중(v16.14) — 리밸런싱일 목표 종목의 비중을 1/σ(N일)에 비례시킨다."""
    return risk_params.get('allocation_type') == INVERSE_VOLATILITY_ALLOCATION


def _ranking_lookback_max(risk_params: Dict[str, Any]) -> int:
    """가격 기반 랭킹 패널이 읽는 최대 lookback(거래일) — 워밍업 산정용(v16.12).

    랭킹 패널은 워밍업 포함 종가로 계산되므로(phase1.window_boundary_prep), lookback이
    워밍업보다 길면 창 첫날 순위가 여전히 비어 있다. 후보 우선순위(tie-break)도 포함한다.
    """
    cands = [_TIEBREAK_LOOKBACK_DAYS]
    default = risk_params.get('ranking_lookback_days')
    if risk_params.get('ranking_metric') in ('return', 'relative_return', 'volatility'):
        cands.append(default or 60)
    for c in _composite_ranking_components(risk_params) or []:
        if c.get('metric') in ('return', 'relative_return', 'volatility'):
            cands.append(c.get('lookback_days') or default or 60)
    if _inverse_volatility_allocation(risk_params):
        # 변동성 역비중(v16.14)의 변동성 패널도 같은 워밍업 종가로 계산한다.
        cands.append(risk_params.get('allocation_lookback_days'))
    out = 0
    for v in cands:
        try:
            out = max(out, int(v))
        except (TypeError, ValueError):
            pass
    return out


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

        # 최적화·워크포워드 세션 동안만 켜지는 Phase1 산출물 캐시(engine/prep_cache.py).
        # None이면 세션 밖(단일 백테스트의 기본 경로).
        self._prep_cache: Optional[SymbolPrepCache] = None

    @contextlib.contextmanager
    def optimization_session(self):
        """최적화·워크포워드처럼 지표(metrics)만 쓰는 백테스트를 반복하는 동안 켜는 세션.

        - 종목별 Phase1 산출물을 재사용한다(같은 날짜 범위 + 같은 구조 파라미터면 적중).
          결과 지표·거래·자산곡선은 세션 유무와 무관하게 동일하다.
        - 결과 화면 전용 부가 산출물(리밸런싱 6주기 비교, FR-BT-064)은 만들지 않는다 —
          시도(trial)마다 버려지는 재시뮬레이션이라 적중 시 남는 시간의 절반이었다.
        중첩 호출은 바깥 세션을 그대로 쓴다. 세션이 끝나면 캐시를 버린다.
        """
        if self._prep_cache is not None:
            yield self._prep_cache
            return
        cache = SymbolPrepCache()
        self._prep_cache = cache
        # Phase1 프로세스 풀이 켜져 있으면 워커들도 같은 세션을 연다(워커별 캐시).
        pool = self._phase1_pool() if self.phase1_pool_active else None
        if pool is not None:
            pool.session("open")
        try:
            yield cache
        finally:
            self._prep_cache = None
            worker_stats = None
            if pool is not None:
                try:
                    worker_stats = pool.session("close")
                except Exception as exc:
                    print(f"[BT-ENGINE] Phase1 풀 세션 종료 실패: {exc}", flush=True)
            print(f"[BT-ENGINE] optimization-session 종료: {cache.stats()}"
                  + (f", workers={worker_stats}" if worker_stats else ""), flush=True)

    @property
    def in_optimization_session(self) -> bool:
        return self._prep_cache is not None

    def _phase1_pool(self):
        """설정상 켜져 있으면 상주 Phase1 프로세스 풀(engine/phase1_pool.py), 아니면 None."""
        try:
            return _phase1_pool.get_pool(self.worker_spec())
        except Exception as exc:  # 풀 기동 실패는 스레드 경로로 조용히 폴백하지 않고 로그로 드러낸다
            print(f"[BT-ENGINE] Phase1 풀 기동 실패 — 스레드 경로로 실행: {exc}", flush=True)
            return None

    @property
    def phase1_pool_active(self) -> bool:
        return _phase1_pool.resolve_worker_count() > 1

    def worker_spec(self) -> Dict[str, Any]:
        """워커 프로세스에서 이 엔진과 같은 엔진을 다시 만들 생성자 kwargs
        (워크포워드 창 병렬, engine/wfa_workers.py). 이 메서드가 있는 엔진만 병렬 대상이다."""
        return {"data_dir": self.loader.data_dir}

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
    def _build_rebal_note(rebal_period: str, max_pos, qg_n: int, sel_pct, group_cap=None) -> Dict[str, Any]:
        """랭킹 매수 사유에 붙는 편입 대상 설명 — 선정 방식(분위/비율/상위 K)별 표기.

        rebal_period는 리밸런싱 주기의 한국어 정본 템플릿(tr.REBAL_PERIOD_*)이고, 반환은
        사유 템플릿에 인자로 꽂히는 세그먼트다(주기 미지정이면 빈 리터럴).
        """
        if not rebal_period:
            return tr.literal("")
        period = tr.part(rebal_period)
        if qg_n and qg_n >= 2:
            cap_note = tr.part(tr.REBAL_NOTE_GROUP_CAP, int(group_cap)) if group_cap else tr.literal("")
            return tr.part(tr.REBAL_NOTE_QUANTILE, period, int(qg_n), cap_note)
        if sel_pct:
            return tr.part(tr.REBAL_NOTE_PCT, period, f"{float(sel_pct):g}")
        if max_pos:
            return tr.part(tr.REBAL_NOTE_TOP_N, period, int(max_pos))
        return tr.literal("")

    @staticmethod
    def _resolve_signal_delay(options, risk_params, exec_type) -> int:
        """신호 봉 → 체결 봉 간격(거래일). next_open 분기의 shift 폭이며 기본 1(다음 거래일 시가).

        options.execution_delay_days(프론트 BacktestService가 risk.execution_delay_days를 옵션에
        싣는다) → risk.execution_delay_days 순으로 읽는다. 1 미만·정수 아님은 거절하고, 지연은
        next_open에서만 의미가 있으므로 same_close에 1 초과 값을 주면 조용히 무시하지 않고 거절한다.
        """
        raw = options.get('execution_delay_days')
        if raw is None:
            raw = (risk_params or {}).get('execution_delay_days')
        if raw is None:
            return 1
        try:
            delay = int(raw)
            if delay != float(raw):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"체결 지연(execution_delay_days)은 정수여야 합니다: {raw!r}")
        if delay < 1:
            raise ValueError(f"체결 지연(execution_delay_days)은 1 이상이어야 합니다: {delay}")
        if exec_type != 'next_open' and delay != 1:
            raise ValueError(
                "체결 지연(execution_delay_days)은 '다음 날 시가 체결'(next_open)에서만 지원합니다"
                f" — execution_type={exec_type}, delay={delay}")
        return delay

    def _market_regime_exposure(self, regime, ext_index, n_pre, delay):
        """시장 국면 필터(v16.14)의 거래일별 목표 노출 비율(0~1) 배열 — 창 구간 길이.

        지수 종가가 ma_period일 단순이동평균 **아래**인 날은 exposure_pct/100, 그 밖(위·같음·
        이동평균이 아직 정의되지 않은 초기 구간)은 1.0이다. 지수 휴장일과 종목 거래일이
        어긋나는 날은 직전 지수 값을 쓴다(ffill). next_open이면 delay만큼 밀어 체결일에
        전일 판정을 쓴다 — 창 직전 N거래일(ext_index 앞부분)을 붙여 밀므로 창 첫날도 창 직전
        판정을 본다(랭킹 패널과 같은 규칙). 지수 파일이 없으면 None.
        """
        import numpy as np
        from engine.market_index import load_index_frame, INDEX_CLOSE_COL

        market = str(regime.get('index') or 'KOSPI')
        frame = load_index_frame(market, self.loader.data_dir)
        if frame is None:
            return None
        close = frame.to_pandas().set_index("date")[INDEX_CLOSE_COL].astype(float)
        close.index = pd.DatetimeIndex(close.index)
        ma = close.rolling(int(regime.get('ma_period') or 200)).mean()
        below = close < ma                             # NaN 이동평균 → False → 전액 투자
        ratio = float(regime.get('exposure_pct') or 0.0) / 100.0
        exp_ser = pd.Series(np.where(below, ratio, 1.0), index=close.index)
        exp_ser = exp_ser.reindex(pd.DatetimeIndex(ext_index), method='ffill')
        if delay:
            exp_ser = exp_ser.shift(delay)
        out = exp_ser.iloc[n_pre:].fillna(1.0).to_numpy(dtype=float)
        return out

    @staticmethod
    def _ranking_selection_pool(available_df, valid, large_cap_mask, liq_pool):
        """랭킹 단독 전략(선정=진입)의 후보 풀 — 값이 정의된 종목에 대형주 마스크·유동성
        게이트를 다시 결합한다(모멘텀 분기 C4 계약과 동일). 마스크는 호출부가 next_open
        지연(창 직전 원천 포함, v16.12)까지 맞춰 넘긴다."""
        pool = available_df & valid
        if large_cap_mask is not None:
            pool &= large_cap_mask
        if liq_pool is not None:
            pool &= liq_pool
        return pool

    @staticmethod
    def _composite_rank_panel(components, raw_price_df, all_fund_rank_values,
                              common_index, processed_symbols, exec_type,
                              default_lookback=None, signal_delay=1, data_dir=None,
                              ext_index=None, pre_fund_values=None):
        """복합 순위 합산(FR-BT-063) 점수 패널.

        반환 (rank_df, valid, missing_labels). rank_df는 [0,1] 백분위 평균(높을수록 상위),
        valid는 전 구성 지표가 정의된 종목·일자 마스크. 데이터가 전무한 구성 지표가 있으면
        (rank_df=None, valid=None, 그 지표 라벨들)을 돌려 호출부가 경고로 드러낸다.

        구성 지표 값 패널: 재무 컬럼은 as-of ffill, 'return'/'volatility'는 raw_price_df
        (bfill 오염 없는 원시 가격 — 호출부는 워밍업 포함 종가 패널을 넘긴다, v16.12)에서
        산출하고 common_index로 되돌린다 — 단일 랭킹 분기들과 같은 계약(v13.2/13.3).
        가격 산출 지표의 산정 기간은 구성 지표 자체 값 → 전략 공통값(ranking_lookback_days,
        되묻기 칩 답이 여기로 결속된다) → 60 순으로 정한다.
        백분위는 전 지표가 정의된 풀 안에서만 매긴다 — 그래야 백분위 평균이 순위 합산과
        같은 정렬이 된다(지표마다 유효 종목 수가 달라 생기는 가중 왜곡 방지).
        """
        from engine.indicators import lookback_return_panel, annualized_volatility_panel

        # ext_index(v16.12): next_open 창 직전 N거래일 + 창. 값·순위를 여기서 계산해 민 뒤 창만
        # 남긴다 — 창 첫날이 창 직전 거래일 값을 본다. 없으면 창 인덱스 그대로(종전).
        idx = common_index if ext_index is None else ext_index
        n_pre = len(idx) - len(common_index)
        panels: list = []
        missing: list = []
        for c in components:
            m = str(c.get('metric'))
            lookback = int(c.get('lookback_days') or default_lookback or 60)
            if m == 'return':
                panel = lookback_return_panel(raw_price_df, lookback, int(c.get('skip_days') or 0))
            elif m == 'relative_return':
                # 시장 대비 초과수익률(v16.10) — 종목마다 제 시장 지수 수익률을 뺀다.
                from engine.market_index import relative_return_panel
                panel = relative_return_panel(raw_price_df, lookback, data_dir)
            elif m == 'volatility':
                panel = annualized_volatility_panel(raw_price_df, lookback)
            else:
                values = all_fund_rank_values.get(m) or {}
                if not values:
                    missing.append(FUNDAMENTAL_LABELS.get(m, m))
                    continue
                panel = pd.DataFrame(values, index=common_index, columns=processed_symbols)
                pre = (pre_fund_values or {}).get(m)
                if n_pre and pre is not None:
                    panel = pd.concat([pre.astype(float), panel])
                panel = panel.ffill()
            panel = panel.reindex(index=idx, columns=processed_symbols)
            panels.append((panel, c.get('direction') == 'bottom', c.get('group')))
        if missing:
            return None, None, missing
        valid = None
        for panel, _, _ in panels:
            valid = panel.notna() if valid is None else (valid & panel.notna())
        scores = []
        for panel, lower_better, _ in panels:
            pct = panel.where(valid).rank(axis=1, pct=True)
            scores.append((1.0 - pct) if lower_better else pct)
        if any(g for _, _, g in panels):
            # 묶음 점수(v16.14): 같은 group 이름의 구성 지표는 먼저 백분위를 평균해 한 점수
            # (예: 품질 점수 = ROE·영업이익률·부채비율 평균)로 만들고, 그 묶음 점수들과 묶음
            # 없는 지표를 다시 동일 가중 평균한다 — '품질 점수 + 모멘텀'에서 품질 지표 수가
            # 많다고 품질이 더 큰 가중을 받지 않게 한다. group이 하나도 없으면 아래 종전 식.
            buckets: Dict[str, list] = {}
            for (_, _, g), sc in zip(panels, scores):
                buckets.setdefault(str(g) if g else f"__solo_{len(buckets)}", []).append(sc)
            group_scores = [sum(b) / float(len(b)) for b in buckets.values()]
            rank_df = sum(group_scores) / float(len(group_scores))
        else:
            rank_df = sum(scores) / float(len(scores))
        if exec_type == 'next_open':
            # 진입 신호는 이미 1일 shift됨 — 랭킹도 전일 값 기준(look-ahead 방지).
            rank_df = rank_df.shift(signal_delay)
            valid = valid.shift(signal_delay, fill_value=False)
        rank_df, valid = rank_df.iloc[n_pre:], valid.iloc[n_pre:]
        rank_df.index = common_index
        valid.index = common_index
        return rank_df.fillna(0.0), valid, []

    @staticmethod
    def _quantile_group_summary(pf, init_cash: float, max_points: int = 300) -> Dict[str, Any]:
        """분위 그룹 1개의 요약 지표 + 다운샘플 자산곡선 (FR-BT-060).

        전체 결과(format_results)는 신호·거래 목록까지 만들어 그룹 수만큼 곱하면
        응답·저장 페이로드가 과도해진다 — 그룹 비교에 필요한 지표만 추린다.
        자산곡선은 그래프용으로 최대 max_points 포인트로 다운샘플한다(마지막 봉 보존).
        """
        import numpy as np
        val = pf.value()
        if isinstance(val, pd.DataFrame):
            val = val.sum(axis=1)
        n = len(val)
        final_eq = float(val.iloc[-1]) if n else init_cash
        total_return = (final_eq / init_cash - 1.0) * 100.0 if init_cash > 0 else 0.0
        # 메인 결과(format_results)와 같은 연환산 기준을 쓴다 — 그러지 않으면
        # "메인 = 1그룹"인데 두 CAGR이 다르게 나온다.
        years, ppy = ResultHandler.time_base(val.index)
        cagr = ResultHandler.annualize_return(total_return / 100.0, years)
        # 낙폭·수익률은 초기자본을 기준점으로 포함한다(메인 결과와 같은 규약, v16.12).
        mdd = ResultHandler.max_drawdown_pct(val.values, init_cash) if n else 0.0
        rets = ResultHandler.anchored_returns(val.values, init_cash) if n else None
        sharpe = (
            float(rets.mean() / rets.std(ddof=1) * np.sqrt(ppy))
            if rets is not None and len(rets) > 1 and float(rets.std(ddof=1)) > 0 else 0.0
        )
        trades = int(pf.trades.count())
        try:
            win_rate = float(pf.trades.win_rate() * 100.0) if trades else 0.0
        except Exception:
            win_rate = 0.0
        stride = max(1, n // max_points)
        idx = list(range(0, n, stride))
        if n and idx[-1] != n - 1:
            idx.append(n - 1)
        return {
            "totalReturn": round(total_return, 2),
            "cagr": round(cagr, 2),
            "maxDrawdown": round(mdd, 2),
            "sharpe": round(sharpe, 2),
            "winRate": round(win_rate, 2),
            "trades": trades,
            "finalEquity": round(final_eq, 2),
            "equity": [round(float(val.iloc[j]), 2) for j in idx],
            "dates": [pd.Timestamp(val.index[j]).strftime('%Y-%m-%d') for j in idx],
        }

    @staticmethod
    def benchmark_for_universe(universe_id: str, symbols: "list[str] | None" = None) -> tuple[str, str]:
        """비교 대상 지수 ETF (심볼, 표시명).

        벤치마크는 "이 전략을 쓰지 않았다면 대신 들고 있었을 것"의 대체재여야 한다.
        universe_id의 시장 토큰으로 고르되, 지정 종목·테마 유니버스처럼 universe_id가
        비어 있으면 보유 심볼의 실제 시장으로 판정한다(그러지 않으면 코스닥 종목만
        담긴 백테스트도 KODEX 200과 비교됐다).

        시장을 끝내 알 수 없으면(ETF 유니버스 등) KODEX 200으로 둔다.
        """
        # 미국 유니버스·미국 지정 종목 — 지수별 대응 ETF(SPY/QQQ/DIA)로 비교한다.
        _us_kind = universe_pit.us_universe_kind(universe_id)
        if _us_kind:
            return universe_pit.us_benchmark(_us_kind)
        if symbols and universe_pit.is_us_symbol_set(symbols):
            return universe_pit.us_benchmark(None)

        universe_parts = {part for part in (universe_id or "").lower().split("_") if part}
        # 대형주 지수(kospi200)는 그 지수 ETF가 따로 있어 별도 분기지만, kosdaq150은
        # 벤치마크가 코스닥 전체와 같은 KODEX KOSDAQ 150이라 코스닥 계열로 묶는다.
        has_kospi200 = "kospi200" in universe_parts
        has_kospi = "kospi" in universe_parts
        has_kosdaq = bool(universe_parts & {"kosdaq", "kosdaq150"})

        if not (has_kospi200 or has_kospi or has_kosdaq) and symbols:
            inferred = universe_pit.dominant_market(symbols)
            has_kospi = inferred == "KOSPI"
            has_kosdaq = inferred == "KOSDAQ"

        if has_kosdaq and not (has_kospi or has_kospi200):
            return "229200", "KODEX KOSDAQ 150 (229200)"
        # 코스피 단독, 그리고 코스피+코스닥 혼합(시총 비중이 큰 쪽의 전 종목 지수가
        # 대형주 200종목 지수보다 가깝다) — 과거에는 혼합 유니버스가 코스닥을 먼저
        # 검사하는 순서 때문에 KODEX KOSDAQ 150과 비교됐다.
        if has_kospi:
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
            # 대화 레인(인터프리터·nl_parser)의 '당일 종가 체결' 어휘는 'current_close'다.
            # 엔진은 'same_close'/'next_open'만 알아, 정규화 없이는 어느 분기에도 걸리지 않아
            # 신호 shift 없이 **당일 시가**에 체결되고(종가보다 앞선 룩어헤드) 경고도 빠졌다
            # (2026-09-13 실측). 여기 한 곳에서 정규화해 phase1·시뮬레이터·경고가 같은 값을 본다.
            if exec_type == 'current_close':
                exec_type = 'same_close'
                options['execution_type'] = exec_type
            # 신호 후 N거래일 지연 체결 — next_open 분기들이 신호·랭킹·마스크를 미는 shift 폭.
            # 1(기본)=다음 거래일 시가, N=N번째 거래일 시가. same_close는 지연 개념이 없다.
            signal_delay = self._resolve_signal_delay(options, risk_params, exec_type)
            # 거래 비용 옵션 검증 — 음수는 리베이트가 되어 결과를 부풀린다(Fail Fast).
            # 0은 허용하되(연구용) 조용히 지나가지 않는다.
            for _ck in ('fee_rate', 'buy_fee_rate', 'sell_fee_rate', 'sell_tax_rate', 'slippage_rate'):
                _cv = options.get(_ck)
                if _cv is not None and float(_cv) < 0:
                    raise ValueError(f"거래 비용({_ck})은 음수일 수 없습니다: {_cv}")
            _fee_keys = [k for k in ('fee_rate', 'buy_fee_rate', 'sell_fee_rate') if options.get(k) is not None]
            _fee_zero = bool(_fee_keys) and all(float(options[k]) == 0 for k in _fee_keys)
            _slip_zero = options.get('slippage_rate') is not None and float(options['slippage_rate']) == 0
            if _fee_zero and _slip_zero:
                self.warnings.add(rw.warning(rw.ZERO_COST))
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
                self.warnings.add(rw.warning(rw.SAME_CLOSE_EXECUTION))
            
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
            # 미국 유니버스 × AI 신호는 모델 선로드(아래 fail-fast) 전에 거절한다 —
            # 한국 데이터로 학습된 모델이라 미국에서 쓸 수 없고, 로드할 이유도 없다.
            if ai_needed and universe_pit.us_universe_kind(req.get('universe_id')):
                raise Exception(
                    "AI 예측 신호(ai_model/ai_drop_model)는 한국 시장 데이터로 학습된 "
                    "모델이라 미국 유니버스에서는 사용할 수 없습니다. AI 신호를 제거하고 "
                    "다시 실행해 주세요."
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
            all_market_caps = {}                   # 일별 실측 시가총액(억원) — 지수 상위 N 판정
            all_drop_scores: dict = {}  # sym → ai_drop_score 시계열 (횡단면 랭킹 청산용)
            # 재무 팩터 랭킹(예: 영업이익률 상위 20종목) — 랭킹 지표의 as-of 컬럼을
            # 심볼별로 수집한다(pbr/roe 블렌드와 같은 경로, 지표만 요청값).
            # 복합 순위 합산(FR-BT-063, ranking_metric='composite')은 구성 지표 여러 개를
            # 한 번에 수집한다 — 컬럼명 → {심볼 → 시계열}의 2단 dict.
            _rank_components = _composite_ranking_components(risk_params)
            _rank_metric_cols = [
                m for m in (
                    [risk_params.get('ranking_metric')] if not _rank_components
                    else [c['metric'] for c in _rank_components]
                )
                # 모멘텀·변동성은 price_df에서 직접 계산 — 컬럼 수집 불필요
                if m and m not in ('return', 'relative_return', 'volatility', 'composite')
            ]
            all_fund_rank_values: dict = {col: {} for col in _rank_metric_cols}
            # 랭킹 lookback 패널 전용 워밍업 포함 종가(phase1.window_boundary_prep) — 창 시작 절단이
            # 있는 요청에서만 채워진다. 창 종가 패널(raw_price_df)의 의미는 바꾸지 않는다.
            all_warm_closes: dict = {}
            # next_open 창 직전 N봉의 shift 원천(phase1.symbol_signals "pre") — 창 첫날 신호·순위·
            # 유동성·시총 마스크가 창 직전 거래일 정보를 보게 한다(v16.12).
            all_pre: dict = {}
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
            # 랭킹 lookback(N거래일 수익률·변동성)도 창 첫날부터 값이 있으려면 워밍업이 그만큼
            # 길어야 한다 — 기본 400일(≈275거래일)을 넘는 긴 lookback에서만 늘어난다.
            _max_period = max(_max_indicator_period(req.get('entry'), req.get('exit')),
                              _ranking_lookback_max(risk_params))
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
            # ── 미국 유니버스 (US 레인 Phase 1) ──
            # 미국 데이터셋은 현재 상장 종목만 담고 있어(상장폐지 부재) PIT 시총 근사도
            # 같은 생존편향을 가진다 — 지수는 현행 구성종목 명부를 쓰고 정직하게 고지한다.
            # 미국 시장에는 증권거래세(매도세)가 없다 — 명시 옵션이 없으면 0으로 둔다.
            _us_kind = universe_pit.us_universe_kind(req.get('universe_id'))
            _markets, _index_top_n = ([], None) if _us_kind else \
                universe_pit.parse_universe_markets(req.get('universe_id'))
            _is_etf_universe = (not _us_kind) and universe_pit.is_etf_universe(req.get('universe_id'))
            if _us_kind:
                # AI 신호 거절은 모델 선로드 전(위 fail-fast 구역)에서 이미 처리됐다.
                if req.get('sector'):
                    # 한국 섹터 정본이 미국 유니버스로 들어온 경우 — 분류 체계가 달라
                    # 적용할 수 없다(미국 업종은 us_industry 필드가 담당).
                    raise ValueError("한국 업종 분류는 미국 유니버스에 적용할 수 없습니다.")
                if req.get('listing_from') or req.get('listing_to'):
                    raise ValueError("미국 유니버스의 신규 상장 필터는 아직 지원되지 않습니다.")
                _us_symbols = universe_pit.resolve_us_symbols(_us_kind)
                if not _us_symbols:
                    raise ValueError(
                        f"미국 유니버스({_us_kind}) 종목을 찾지 못했습니다 — "
                        "미국 데이터(us-index-membership.json 등) 수집 상태를 확인해 주세요."
                    )
                symbols = _us_symbols
                if options.get('sell_tax_rate') is None:
                    options['sell_tax_rate'] = 0.0
                self.warnings.add(rw.warning(rw.US_UNIVERSE_SURVIVORSHIP))
                if _us_kind in ("sp500", "nasdaq100", "dow30"):
                    self.warnings.add(rw.warning(rw.INDEX_UNIVERSE_CURRENT_LIST))
                # ── 미국 업종 필터(FR-STR-074 ⑩) ──
                # 분류 정본은 us-stocks.json의 GICS 섹터·산업이다. 미국 ETF 유니버스엔
                # 기업 분류가 없으므로 적용하지 않는다(한국 ETF와 같은 계약).
                _us_industry = req.get('us_industry')
                if _us_industry and _us_kind != "us_etf":
                    _before = len(symbols)
                    symbols = universe_pit.filter_by_us_industry(symbols, _us_industry)
                    if not symbols:
                        raise ValueError(
                            f"'{_us_industry}' 업종에 해당하는 종목을 찾지 못했습니다."
                        )
                    # 분류는 **현행 기준**이다 — 과거의 업종 재분류·편입은 반영되지 않는다
                    # (테마와 갈리는 지점: 테마는 소속 최초 관측일을 갖는다, FR-STR-074 ⑦).
                    self.warnings.add(rw.warning(rw.US_INDUSTRY_CURRENT_CLASSIFICATION, _us_industry))
                    print(f"[BT-ENGINE] US 업종 필터({_us_industry}): "
                          f"{_before}→{len(symbols)}종목", flush=True)
                print(f"[BT-ENGINE] US universe({_us_kind}): {len(symbols)}종목", flush=True)
            elif _markets:
                _aof_symbols = universe_pit.resolve_symbols(req.get('universe_id'), _period_start_str, _end_str)
                if _aof_symbols:
                    symbols = _aof_symbols
                    print(f"[BT-ENGINE] PIT universe: {len(symbols)}종목 "
                          f"(markets={_markets}, index_top_n={_index_top_n})", flush=True)
                else:
                    # as-of 해석이 비면 프론트가 보낸 **현재 상장** 목록이 그대로 남는다 —
                    # 생존 편향 제거가 조용히 꺼지는 것이라 반드시 고지한다(2026-09-16 실측:
                    # 마스터 생성일 이후로 시작하는 창은 전부 0종목이었고 경고도 없었다).
                    _gen = universe_pit.master_generated_at()
                    self.warnings.add(rw.warning(rw.PIT_UNIVERSE_MASTER_STALE,
                                                 _gen or tr.part(rw.MASTER_GENERATED_UNKNOWN)))
                    print(f"[BT-ENGINE] PIT universe 비어 있음(마스터 {_gen}) — "
                          f"현재 상장 목록 {len(symbols)}종목으로 진행(생존 편향 고지)", flush=True)
                # 상폐 이력은 마스터의 delistingFloor(2015-01-01)부터만 있다 — 그 이전 구간은
                # 생존 종목만으로 돌아가므로 조용히 지나가지 않는다.
                _floor = universe_pit.delisting_floor()
                if _floor and (_period_start_str is None or _period_start_str < _floor):
                    self.warnings.add(rw.warning(rw.DELISTING_HISTORY_FLOOR, _floor))
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
                    self.warnings.add(rw.warning(rw.ETF_UNIVERSE_SURVIVORSHIP))
                _etf_theme = req.get('etf_theme')
                if _etf_theme:
                    _themed = universe_pit.filter_etf_by_theme(symbols, _etf_theme)
                    if _themed:
                        symbols = _themed
                    else:
                        self.warnings.add(rw.warning(rw.ETF_THEME_NOT_FOUND, _etf_theme))
                print(f"[BT-ENGINE] ETF universe: {len(symbols)}종목 "
                      f"(theme={req.get('etf_theme')})", flush=True)

            # 지정 종목 모드(universe_id=None): 한·미 혼합은 거절한다 — 세금·벤치마크·
            # 통화가 시장 단위 계약이라 혼합하면 어느 쪽 기준도 성립하지 않는다.
            # 전부 미국 티커면 증권거래세 0(미국 유니버스 분기와 같은 규칙).
            if not _us_kind and symbols:
                _us_cnt = sum(1 for s in symbols if universe_pit.is_us_symbol(s))
                if 0 < _us_cnt < len(symbols):
                    raise ValueError(
                        "한국 종목과 미국 종목을 한 백테스트에 함께 지정할 수 없습니다 — "
                        "시장별로 나눠 실행해 주세요."
                    )
                if _us_cnt == len(symbols):
                    if options.get('sell_tax_rate') is None:
                        options['sell_tax_rate'] = 0.0
                    # 미국 데이터셋에는 상폐 종목 가격 이력이 없다 — 테마·지정 종목 경로도
                    # 유니버스 경로와 같은 생존 편향을 지니므로 같은 고지를 붙인다.
                    self.warnings.add(rw.warning(rw.US_SYMBOLS_SURVIVORSHIP))

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
                # 섹터 소속의 정본은 지식그래프다(FR-STR-070 ⑦-2). 정본을 못 읽어 파일
                # 캐시로 폴백했다면 조용히 넘기지 않고 사용자에게 고지한다 — 정본이 아닌
                # 데이터로 유니버스가 확정되면 결과가 달라질 수 있다.
                _sector_src = universe_pit.sector_map_source()
                if _sector_src.get("source") == "files":
                    self.warnings.add(rw.warning(
                        rw.SECTOR_MAP_FROM_FILE_CACHE, _sector_label,
                        _sector_src.get('reason') or tr.part(rw.SECTOR_MAP_REASON_UNKNOWN),
                    ))
                symbols = universe_pit.filter_by_sector(symbols, _sector)
                if not symbols:
                    raise ValueError(f"'{_sector_label}' 섹터에 해당하는 종목을 찾지 못했습니다.")
                if _sector_unknown:
                    self.warnings.add(rw.warning(
                        rw.SECTOR_UNKNOWN_DELISTED_EXCLUDED, _sector_label, len(_sector_unknown),
                    ))
                print(f"[BT-ENGINE] 섹터 필터({_sector_label}): {len(symbols)}종목 "
                      f"(업종 미상 상폐 {len(_sector_unknown)})", flush=True)

            # ── 신규 상장 유니버스 (FR-STR-073) ──
            # "2026년 신규 상장 종목"은 상장일이 그 구간에 속하는 종목 집합이다 — 종목의
            # 상장일 하나로 결정되므로 섹터 필터와 같은 자리에서 같은 방식으로 거른다.
            # 상장 전 구간은 가격 데이터가 없어(available_df) 매매가 생기지 않는다.
            _listing_from = req.get('listing_from')
            _listing_to = req.get('listing_to')
            if _listing_from or _listing_to:
                _listing_label = f"{_listing_from or '제한 없음'}~{_listing_to or '제한 없음'}"
                _new_symbols, _listing_unknown = universe_pit.filter_by_listing_window(
                    symbols, _listing_from, _listing_to
                )
                if not _new_symbols:
                    raise ValueError(
                        f"{_listing_label} 사이에 상장한 종목을 찾지 못했습니다."
                    )
                symbols = _new_symbols
                if _listing_unknown:
                    self.warnings.add(rw.warning(rw.LISTING_DATE_UNKNOWN_EXCLUDED, len(_listing_unknown)))
                print(f"[BT-ENGINE] 신규 상장 필터(상장일 {_listing_label}): "
                      f"{len(symbols)}종목 (상장일 미상 {len(_listing_unknown)})", flush=True)

            def _filter_to_backtest_window(df_pl: pl.DataFrame) -> pl.DataFrame:
                if not _has_period_filter:
                    return df_pl

                date_col = _date_key()
                if _period_start_str is not None:
                    df_pl = df_pl.filter(date_col >= _period_start_str)
                return df_pl.filter(date_col <= _end_str)

            # Delisted names (per point-in-time master): their OHLCV ends at the delisting
            # day, so the forced exit there is a real liquidation, labelled accordingly.
            _delisted_dates = universe_pit.get_delisting_dates(symbols)

            # ── 종목별 Phase1 파이프라인은 engine/phase1.py(순수 함수)가 정본 ──
            # 요청-수준 상수는 피클 가능한 ctx로 묶는다 — 엔진 안 스레드 경로와
            # 프로세스 풀 경로(engine/phase1_pool.py)가 같은 코드·같은 입력으로 돈다.
            _p1_ctx = _phase1.build_context(
                entry=req.get('entry'), exit_=req.get('exit'),
                warmup_start_str=_warmup_start_str, has_period_filter=_has_period_filter,
                period_start_str=_period_start_str, end_str=_end_str,
                apply_dividends=apply_dividends,
                skip_risk=bool(risk_params.get('skip_risk_management', False)),
                skip_pos=bool(risk_params.get('skip_position_setting', False)),
                init_cash=init_cash, pos_size_pct=pos_size_pct, liquid_limit=liquid_limit,
                exec_type=exec_type, signal_delay=signal_delay,
                delisted_symbols=set(_delisted_dates or {}),
                rank_metric_cols=_rank_metric_cols, tracked_metrics=_tracked_metrics,
                ai_needed=ai_needed,
            )
            # 최적화 세션 캐시 — AI 백테스트(Phase2 일괄 추론 경로)는 대상 밖.
            _prep = self._prep_cache if not ai_needed else None

            def _apply_side(side: Dict[str, Any]) -> None:
                for w in side.get("warnings") or ():
                    self.warnings.add(w)
                if side.get("res_logs"):
                    all_resolution_logs.extend(side["res_logs"])

            def _process_symbol(sym):
                """스레드 경로: 순수 파이프라인 호출 + 부수효과 반영. 반환은 기존 규약(None | (status, data))."""
                status, data, side = _phase1.process_symbol(
                    sym, _p1_ctx, self.loader, self.indicator_engine, self.signal_engine, prep_cache=_prep,
                )
                _apply_side(side)
                if status == "skip":
                    return None
                if status == "phase1_done":
                    _phase1_data[sym] = data
                    return ("phase1_done", sym)
                return (status, data)

            import concurrent.futures
            import os

            # Maximize threads for I/O and pre-processing. The global lock in AIEngine will protect the GPU/CPU Inference.
            # BACKTEST_PHASE1_THREADS: 워크포워드 창 병렬 워커처럼 프로세스가 여럿일 때 코어를 나눠 쓰기 위한 상한.
            max_threads = min(32, (os.cpu_count() or 1) + 4)
            _thr_env = os.environ.get("BACKTEST_PHASE1_THREADS")
            if _thr_env:
                try:
                    max_threads = max(1, min(max_threads, int(_thr_env)))
                except ValueError:
                    pass

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
                    if "market_cap" in data: all_market_caps[sym] = data["market_cap"]
                    if data.get("warm_close") is not None: all_warm_closes[sym] = data["warm_close"]
                    if data.get("pre") is not None: all_pre[sym] = data["pre"]
                    for _col, _ser in (data.get("fund_rank_values") or {}).items():
                        all_fund_rank_values[_col][sym] = _ser
                    if "ai_drop_score" in data: all_drop_scores[sym] = data["ai_drop_score"]
                    if _coverage_acc is not None and "coverage" in data:
                        _coverage_acc.fold(data["coverage"])
                    processed_symbols.append(sym)

            # Phase 1: 종목별 데이터 로드 + 지표 계산.
            # 프로세스 풀(engine/phase1_pool.py)이 켜져 있고 AI 경로가 아니면 워커에 샤딩해 돌린다 —
            # Phase1은 GIL에 묶여 스레드로는 코어를 못 쓴다(2026-08-19 실측). 아니면 기존 스레드 경로.
            _t1 = _time.time()
            _pool = self._phase1_pool() if (not ai_needed and len(symbols) >= _phase1_pool.min_symbols()) else None
            print(f"[BT-ENGINE] Phase1 시작: {len(symbols)}종목, period={period_req}"
                  + (f", workers={_pool.n_workers}" if _pool is not None else ""), flush=True)
            if _pool is not None:
                _job_timeout = float(os.environ.get("BACKTEST_TIMEOUT_S", "600")) + 30.0
                for status, data, side in _pool.run(_p1_ctx, symbols, timeout_s=_job_timeout):
                    _apply_side(side)
                    if status in ("warning", "success"):
                        _collect_result((status, data))
            else:
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
                        _bprep = _phase1.window_boundary_prep(df_pl, sym, _p1_ctx, self.loader)
                        df_pl = _filter_to_backtest_window(df_pl)

                        if len(df_pl) < 1:
                            return None

                        pdf = self.loader.preprocess_data(df_pl, apply_dividends=apply_dividends)
                        skip_risk = risk_params.get('skip_risk_management', False)
                        skip_pos = risk_params.get('skip_position_setting', False)

                        # 신호·유동성(+next_open 창 직전 shift 원천)은 phase1 정본과 같은 함수.
                        _sig = _phase1.symbol_signals(df_pl, pdf, _bprep, sym, _p1_ctx,
                                                      self.loader, self.signal_engine)
                        if _sig is None:
                            return None
                        # Warn only when the strategy wanted to enter but liquidity blocked every entry.
                        if _sig["liquidity_blocked"]:
                            return ("warning", rw.warning(rw.SYMBOL_LIQUIDITY_BELOW, sym))
                        entry_signals, entry_reasons = _sig["entries"], _sig["entry_reasons"]
                        exit_signals, exit_reasons = _sig["exits"], _sig["exit_reasons"]
                        liquidity_ok = _sig["liquidity"]

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
                        if _bprep["warm_close"] is not None:
                            res["warm_close"] = _bprep["warm_close"]
                        if _sig["pre"] is not None:
                            res["pre"] = _sig["pre"]
                        if not (skip_risk or skip_pos):
                            res["liquidity"] = pd.Series(liquidity_ok, index=pdf.index)
                        if 'volume' in pdf.columns:
                            res["trading_value"] = pdf['close'] * pdf['volume']
                        if 'market_cap' in pdf.columns:
                            res["market_cap"] = pdf['market_cap']
                        if 'pbr' in pdf.columns: res["pbr"] = pdf['pbr']
                        if 'roe_or_gpa' in pdf.columns: res["roe"] = pdf['roe_or_gpa']
                        if _rank_metric_cols:
                            res["fund_rank_values"] = {
                                col: pdf[col] for col in _rank_metric_cols if col in pdf.columns
                            }
                        if drop_rank_pct is not None and 'ai_drop_score' in pdf.columns:
                            res["ai_drop_score"] = pdf['ai_drop_score']
                        if _tracked_metrics:
                            res["coverage"] = data_coverage.symbol_stats(pdf, _tracked_metrics)
                        return ("success", res)
                    except Exception as e:
                        return ("warning", rw.warning(rw.SYMBOL_PROCESSING_ERROR, sym, e))

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
            # 랭킹 lookback 패널(N거래일 수익률·변동성·초과수익률)의 입력 — 워밍업 구간을 포함한
            # 원시 종가. 창으로 잘린 raw_price_df로 계산하면 창의 첫 lookback 거래일 동안 순위가
            # 없어 현금으로 앉아 있었다(2026-09-17 실측, v16.12). 상장 전 NaN은 그대로라 관측
            # 미달 신규 상장 종목은 여전히 lookback 봉이 쌓일 때까지 NaN이다(v13.3 계약).
            # 패널은 계산 뒤 반드시 common_index로 되돌린다(_to_window).
            rank_price_df = (
                pd.DataFrame(all_warm_closes, columns=processed_symbols).sort_index()
                if all_warm_closes else raw_price_df
            )

            # ── 창 경계 shift(v16.12) ──
            # next_open은 신호·순위·유동성·시총 마스크를 N거래일 민다. 창 안에서만 밀면 창 첫
            # N일(첫날 = 첫 리밸런싱일)이 늘 비어 첫 주기가 현금이었다. 창 직전 N거래일(_pre_dates,
            # 전 종목 창 직전 봉의 합집합 중 마지막 N일)을 앞에 붙여 민 뒤 창 구간만 남긴다 — 창 첫날의
            # 결정은 창 직전 거래일 정보만 쓴다(룩어헤드 없음, 창 중간 리밸런싱일과 같은 규칙).
            # 창 이전 봉이 없는 종목(창 안 신규 상장)은 원천이 NaN → 후보가 아니다. same_close·
            # 창 시작 절단 없는 요청은 _pre_dates가 비어 종전과 같다.
            if exec_type == 'next_open' and all_pre:
                _pre_dates = pd.DatetimeIndex(sorted(set().union(
                    *[set(p["index"]) for p in all_pre.values()])))[-signal_delay:]
            else:
                _pre_dates = pd.DatetimeIndex([])
            _n_pre = len(_pre_dates)
            ext_index = (pd.DatetimeIndex(_pre_dates).append(pd.DatetimeIndex(common_index))
                         if _n_pre else pd.DatetimeIndex(common_index))

            def _to_window(panel):
                return panel.reindex(index=common_index, columns=processed_symbols)

            def _to_ext(panel):
                return panel.reindex(index=ext_index, columns=processed_symbols)

            def _pre_panel(key, col=None):
                """창 직전 N거래일 × 종목 원천 패널(없는 칸 NaN)."""
                data = {}
                for _s, _p in all_pre.items():
                    _v = _p.get(key) if col is None else (_p.get(key) or {}).get(col)
                    if _v is not None:
                        data[_s] = _v
                return pd.DataFrame(data, index=_pre_dates, columns=processed_symbols)

            def _extend(window_df, pre_df):
                if not _n_pre:
                    return window_df
                return pd.concat([pre_df, window_df])

            def _delay_to_window(ext_df, fill_value=None):
                """ext(창 직전 N일 + 창) 패널을 signal_delay만큼 밀고 창 구간만 남긴다."""
                shifted = (ext_df.shift(signal_delay) if fill_value is None
                           else ext_df.shift(signal_delay, fill_value=fill_value))
                out = shifted.iloc[_n_pre:]
                out.index = common_index   # 이어 붙인 인덱스의 dtype·이름 차이를 지운다(vbt strict 정렬)
                return out

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
                ents_df = _delay_to_window(_extend(ents_df, _pre_panel("entries").eq(True)), fill_value=False)
                exts_df = _delay_to_window(_extend(exts_df, _pre_panel("exits").eq(True)), fill_value=False)
                # 창 첫날 체결의 사유는 창 직전 신호 봉의 사유다 — 결과 처리기가 체결일 직전 사유를 찾는다.
                for _s, _p in all_pre.items():
                    if _s in all_entry_reasons:
                        all_entry_reasons[_s] = pd.concat([_p["entry_reasons"], all_entry_reasons[_s]])
                    if _s in all_exit_reasons:
                        all_exit_reasons[_s] = pd.concat([_p["exit_reasons"], all_exit_reasons[_s]])
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
                        rank_exits = rank_exits.shift(signal_delay, fill_value=False)
                    exts_df = (exts_df | rank_exits.astype(bool)) & available_df

            # 상폐·데이터 종료 강제청산(phase1.close_at_last_available_row)은 거래정지 마스크를
            # 넘어 집행한다. 정지 상태로 끝나는 상폐 종목(합병·해산·SPAC 등 — 2026-09-02 실측
            # 474개 중 168개)은 마지막 봉 거래량이 0이라 available_df가 강제청산 신호까지 지워
            # 포지션이 백테스트 끝까지 동결가로 남고 슬롯을 점유했다. 마지막 실봉의 (동결)
            # 시가로 정산한다 — 합병·만료는 실제로도 그 가격 부근에서 현금·승계주식을 받는다.
            _forced_exit = pd.DataFrame(False, index=common_index, columns=processed_symbols)
            for _s in processed_symbols:
                _last = raw_price_df[_s].last_valid_index()
                if _last is not None:
                    _forced_exit.at[_last, _s] = True
            exts_df |= _forced_exit

            # ── 지수 유니버스(KOSPI200·KOSDAQ150) = point-in-time top-N by market cap ──
            # Static current index membership is itself survivorship-biased, so we define the
            # index universe as the daily top-N alive names of that market by market cap.
            # 시총은 파케이의 일별 실측 시가총액(억원, KRX 스냅샷 — scripts/rebuild_market_cap.py)을
            # 정본으로 쓰고, 실측이 없는 셀만 현재 상장주식수 × 주가로 근사한다(정적 주식수는
            # 증자·분할 이력을 모른다). Market cap is evaluated only where price data is actually
            # available that day, so delisted names drop out of the ranking once they stop trading.
            large_cap_mask = None
            if _index_top_n:
                shares_map = universe_pit.get_shares(processed_symbols)
                shares_vec = pd.Series(
                    {s: shares_map.get(s, np.nan) for s in processed_symbols},
                    dtype=float,
                )
                mcap_static = price_df.mul(shares_vec, axis=1) / 1e8   # 억원 — 실측 컬럼과 단위 통일
                # 창 직전 N거래일(next_open shift 원천)을 앞에 붙여 같은 규칙으로 판정한다.
                _pre_close = _pre_panel("close").astype(float)
                mcap_static = _extend(mcap_static, _pre_close.mul(shares_vec, axis=1) / 1e8)
                _pre_avail = _pre_close.notna()
                if all_trading_values:
                    _pre_avail &= ~_pre_panel("trading_value").astype(float).eq(0.0)
                _avail_ext = _extend(available_df, _pre_avail)
                _pit_ratio = 0.0
                if all_market_caps:
                    mcap_pit = pd.DataFrame(
                        all_market_caps, index=common_index, columns=processed_symbols
                    ).astype(float)
                    mcap_pit = mcap_pit.where(mcap_pit > 0)
                    _avail_cells = int(available_df.values.sum())
                    _pit_cells = int((mcap_pit.notna() & available_df).values.sum())
                    _pit_ratio = _pit_cells / _avail_cells if _avail_cells else 0.0
                    mcap_pit = _extend(mcap_pit, _pre_panel("market_cap").astype(float))
                    mcap_pit = mcap_pit.where(mcap_pit > 0)
                    mcap = mcap_pit.where(mcap_pit.notna(), mcap_static)
                else:
                    mcap = mcap_static
                mcap = mcap.where(_avail_ext)
                mcap_rank = mcap.rank(axis=1, ascending=False, method="first")
                large_cap_mask = (mcap_rank <= _index_top_n).fillna(False)
                if exec_type == 'next_open':
                    # 진입 신호는 이미 1일 shift됨 — 시총 순위도 전일 종가 기준으로
                    # 맞춰야 당일 종가를 미리 아는 look-ahead가 없다.
                    large_cap_mask = _delay_to_window(large_cap_mask, fill_value=False)
                ents_df &= large_cap_mask
                _index_label = "KOSDAQ150" if _index_top_n == 150 else "KOSPI200"
                if _pit_ratio >= 0.99:
                    self.warnings.add(rw.warning(rw.INDEX_TOP_N_MEASURED, _index_top_n, _index_label))
                else:
                    self.warnings.add(rw.warning(
                        rw.INDEX_TOP_N_APPROXIMATED,
                        _index_top_n, f"{(1 - _pit_ratio) * 100:.0f}", _index_label,
                    ))

            # 랭킹 단독 전략 후보 풀의 유동성 게이트(C4) — next_open이면 창 직전 원천과 함께 민다.
            _liq_pool = None
            if all_liquidity:
                _liq_pool = pd.DataFrame(
                    all_liquidity, index=common_index, columns=processed_symbols
                ).eq(True)  # NaN(데이터 없는 날) → False, bool dtype 보장
                if exec_type == 'next_open':
                    _liq_pool = _delay_to_window(
                        _extend(_liq_pool, _pre_panel("liquidity").eq(True)), fill_value=False)

            rank_df = None
            _tiebreak_rank_used = False
            skip_pos = risk_params.get('skip_position_setting', False)
            ranking_metric = risk_params.get('ranking_metric')
            # 분위(퀀타일) 그룹 비교(FR-BT-060): 랭킹 후보를 종목 수 동일한 G개 그룹으로
            # 나눠 그룹별로 각각 백테스트한다. 메인 결과는 1그룹(랭킹 최상위 구간)이다.
            _qg_n = int(risk_params.get('ranking_quantile_groups') or 0)
            _sel_pct = risk_params.get('max_positions_pct')
            if ranking_metric in ('return', 'relative_return'):
                # 상대강도(모멘텀) 랭킹: N일 수익률 순위로 상위 종목 선정. 'relative_return'
                # (v16.10)은 같은 계약으로 종목 수익률에서 **자기 시장 지수** 수익률을 뺀
                # 초과수익률 순위다 — 코스피·코스닥 혼합 유니버스에서도 종목마다 제 지수를 빼므로
                # 정확하고, 지수가 없는 종목(미국)은 NaN → 후보 배제.
                # 종목 간 횡단면 순위라 진입 신호 없이 순위 자체가 진입이 된다. 회전(월간 등)은
                # 달력 리밸런싱(engine/rebalance.py + simulator의 목표비중/재구성 경로)이 구동한다.
                try:
                    from engine.indicators import lookback_return_panel

                    lookback = int(risk_params.get('ranking_lookback_days') or 60)
                    # price_df(ffill+bfill)가 아니라 raw_price_df를 쓴다(v13.3) — 상장 전
                    # bfill 구간이 'N일 수익률'을 상장 이후 수익률로 위장해 관측 미달
                    # 신규 상장 종목이 상위권으로 매수됐다(2023-12-01 실측: 상장 10거래일째
                    # 에코프로머티 '상위 1%'). 변동성 랭킹 v13.2와 같은 계약 — 관측 미달은
                    # NaN → 아래 valid 마스크가 후보에서 배제한다.
                    if ranking_metric == 'relative_return':
                        from engine.market_index import relative_return_panel
                        momentum = relative_return_panel(rank_price_df, lookback, self.loader.data_dir)
                    else:
                        momentum = lookback_return_panel(
                            rank_price_df, lookback, int(risk_params.get('ranking_skip_days') or 0))
                    momentum = _to_ext(momentum)
                    pct = momentum.rank(axis=1, pct=True)
                    # 방향(v16.2): top(기본)=수익률 높은 순, bottom=낮은 순(역발상 — '최근
                    # 3개월 수익률 오름차순'). 변동성·재무·복합 분기는 모두 direction을 읽는데
                    # 이 분기만 읽지 않아 bottom 요청이 조용히 모멘텀으로 실행됐다(정반대 전략).
                    _direction = str(risk_params.get('ranking_direction') or 'top')
                    rank_df = (1.0 - pct) if _direction == 'bottom' else pct
                    # 수익률이 정의되지 않은 초기 lookback 구간(NaN)에는 종목을 후보에서 제외한다.
                    # 그러지 않으면 순위가 0으로 동률이 되어 임의 종목을 사서 들고 있게 된다.
                    valid = momentum.notna()
                    if exec_type == 'next_open':
                        rank_df = _delay_to_window(rank_df)
                        valid = _delay_to_window(valid, fill_value=False)
                    rank_df = _to_window(rank_df).fillna(0.0)
                    valid = _to_window(valid).fillna(False).astype(bool)
                    # 진입 신호가 없으면(선정=진입) 수익률이 정의된 전 종목을 후보로 만들어 상위 K를 채운다.
                    # C4: 이 오버라이드가 대형주(KOSPI200) 마스크와 유동성 게이트를
                    # 덮어쓰지 않도록 두 마스크를 후보 풀에 다시 결합한다.
                    _entry_conditions = (req.get('entry') or {}).get('conditions') or []
                    if not _entry_conditions:
                        pool = self._ranking_selection_pool(available_df, valid, large_cap_mask, _liq_pool)
                        ents_df = pool

                        # 랭킹 매수는 개별 조건식이 없어 SignalEngine이 사유를 만들지 못하고
                        # (entry.conditions 비어 있음 → generate_signals가 전부 None 반환)
                        # result_handler의 하드코딩 폴백("매수 조건 충족 (전략 시그널)")으로
                        # 뭉개진다. 후보일(pool=True)마다 그날의 수익률 백분위를 사유로
                        # 남겨 실제 매수 근거(몇 % 상위였는지)가 드러나게 한다.
                        _rebal_kr = _REBAL_PERIOD_TEMPLATES.get(
                            str(risk_params.get('rebalancing_period') or ''), '')
                        _max_pos = risk_params.get('max_positions')
                        _rebal_note = self._build_rebal_note(
                            _rebal_kr, _max_pos, _qg_n, _sel_pct,
                            group_cap=risk_params.get('ranking_group_cap'),
                        )
                        _dir_seg = tr.part(tr.RANK_BOTTOM if _direction == 'bottom' else tr.RANK_TOP)
                        _rank_tpl = (tr.RANKING_RELATIVE_RETURN if ranking_metric == 'relative_return'
                                     else tr.RANKING_RETURN)
                        _skip = int(risk_params.get('ranking_skip_days') or 0)
                        _top_pct_df = (1.0 - rank_df) * 100.0
                        for _sym in processed_symbols:
                            _mask = pool[_sym]
                            if not _mask.any():
                                continue
                            _pct_vals = _top_pct_df.loc[_mask, _sym]
                            _reason_ser = pd.Series(np.nan, index=common_index, dtype=object)
                            if _skip and ranking_metric == 'return':
                                _reason_ser.loc[_mask] = _pct_vals.apply(
                                    lambda p: tr.encode([tr.part(
                                        tr.RANKING_RETURN_SKIP, lookback, _skip, _dir_seg,
                                        max(1, round(p)), _rebal_note,
                                    )])
                                )
                            else:
                                _reason_ser.loc[_mask] = _pct_vals.apply(
                                    lambda p: tr.encode([tr.part(
                                        _rank_tpl, lookback, _dir_seg, max(1, round(p)), _rebal_note
                                    )])
                                )
                            all_entry_reasons[_sym] = _reason_ser
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 수익률 랭킹 계산 실패: {e}")
                    rank_df = None
            elif ranking_metric == 'volatility':
                # 변동성 랭킹: N일 일수익률 롤링 표준편차(연환산 %) 순위로 종목 선정.
                # 모멘텀('return')과 같은 계약 — 순위 자체가 진입, 회전은 달력 리밸런싱.
                # 방향 미지정 기본은 bottom(저변동성 선호)이다 — 무언의 top은 '가장 출렁이는
                # 종목 선정'으로 전략이 뒤집힌다(컴파일러도 온톨로지 lower_better로 bottom을 채움).
                try:
                    from engine.indicators import annualized_volatility_panel
                    lookback = int(risk_params.get('ranking_lookback_days') or 60)
                    # price_df(ffill+bfill)가 아니라 raw_price_df를 쓴다 — 상장 전 bfill
                    # 구간의 가짜 0% 수익률이 변동성을 0으로 위장해 신규 상장 종목이
                    # 최상위로 선정되는 오염 방지(v13.2, 함수 docstring 참조).
                    vol_df = _to_ext(annualized_volatility_panel(rank_price_df, lookback))
                    pct = vol_df.rank(axis=1, pct=True)
                    _direction = str(risk_params.get('ranking_direction') or 'bottom')
                    rank_df = (1.0 - pct) if _direction == 'bottom' else pct
                    # 변동성이 정의되지 않은 초기 lookback 구간(NaN)은 후보에서 제외한다
                    # (momentum 분기와 같은 이유 — 0 동률로 임의 종목이 선정되는 것 방지).
                    valid = vol_df.notna()
                    if exec_type == 'next_open':
                        rank_df = _delay_to_window(rank_df)
                        valid = _delay_to_window(valid, fill_value=False)
                    rank_df = _to_window(rank_df).fillna(0.0)
                    valid = _to_window(valid).fillna(False).astype(bool)
                    _entry_conditions = (req.get('entry') or {}).get('conditions') or []
                    if not _entry_conditions:
                        # 랭킹 단독 전략(선정=진입): 대형주 마스크·유동성 게이트 재결합(C4와 동일).
                        pool = self._ranking_selection_pool(available_df, valid, large_cap_mask, _liq_pool)
                        ents_df = pool

                        # 매수 사유: 그날의 변동성 백분위(momentum 분기와 같은 계약).
                        _rebal_kr = _REBAL_PERIOD_TEMPLATES.get(
                            str(risk_params.get('rebalancing_period') or ''), '')
                        _max_pos = risk_params.get('max_positions')
                        _rebal_note = self._build_rebal_note(
                            _rebal_kr, _max_pos, _qg_n, _sel_pct,
                            group_cap=risk_params.get('ranking_group_cap'),
                        )
                        _dir_seg = tr.part(tr.RANK_BOTTOM if _direction == 'bottom' else tr.RANK_TOP)
                        _top_pct_df = (1.0 - rank_df) * 100.0
                        for _sym in processed_symbols:
                            _mask = pool[_sym]
                            if not _mask.any():
                                continue
                            _pct_vals = _top_pct_df.loc[_mask, _sym]
                            _reason_ser = pd.Series(np.nan, index=common_index, dtype=object)
                            _reason_ser.loc[_mask] = _pct_vals.apply(
                                lambda p: tr.encode([tr.part(
                                    tr.RANKING_VOLATILITY, lookback, _dir_seg, max(1, round(p)), _rebal_note
                                )])
                            )
                            all_entry_reasons[_sym] = _reason_ser
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 변동성 랭킹 계산 실패: {e}")
                    rank_df = None
            elif ranking_metric == 'composite':
                # 복합 순위 합산(FR-BT-063): 구성 지표마다 횡단면 백분위 순위(방향 기준 '좋은
                # 쪽'이 높게)를 매겨 동일 가중 평균한다 — 순위 합산이 가장 낮은 종목이 최상위가
                # 되는 것과 같은 정렬. 어느 한 지표라도 없는 종목은 후보에서 배제한다(순위 합산이
                # 정의되지 않으므로 — 중립값 위장 금지, 재무 랭킹 NaN 계약과 동일). 구성 지표의
                # 순위는 전 지표가 정의된 종목 풀 안에서만 매긴다(그래야 백분위 평균 = 순위 합산).
                rank_df, valid, _missing_labels = self._composite_rank_panel(
                    _rank_components, rank_price_df, all_fund_rank_values,
                    common_index, processed_symbols, exec_type,
                    default_lookback=risk_params.get('ranking_lookback_days'),
                    signal_delay=signal_delay, data_dir=self.loader.data_dir,
                    ext_index=ext_index,
                    pre_fund_values={m: _pre_panel("fund_rank_values", m) for m in _rank_metric_cols},
                )
                if _missing_labels:
                    self.warnings.add(rw.warning(
                        rw.COMPOSITE_RANK_DATA_MISSING, rw.label_list(_missing_labels),
                    ))
                elif rank_df is not None:
                    _entry_conditions = (req.get('entry') or {}).get('conditions') or []
                    if not _entry_conditions:
                        # 랭킹 단독 전략(선정=진입): 다른 랭킹 분기와 같은 후보 풀 계약
                        # (대형주 마스크·유동성 게이트 재결합)과 매수 사유 계약.
                        pool = self._ranking_selection_pool(available_df, valid, large_cap_mask, _liq_pool)
                        ents_df = pool
                        _rebal_kr = _REBAL_PERIOD_TEMPLATES.get(
                            str(risk_params.get('rebalancing_period') or ''), '')
                        _rebal_note = self._build_rebal_note(
                            _rebal_kr, risk_params.get('max_positions'), _qg_n, _sel_pct,
                            group_cap=risk_params.get('ranking_group_cap'),
                        )
                        _metric_seg = _composite_ranking_label_segment(
                            _rank_components, risk_params.get('ranking_lookback_days'))
                        _top_pct_df = (1.0 - rank_df) * 100.0
                        for _sym in processed_symbols:
                            _mask = pool[_sym]
                            if not _mask.any():
                                continue
                            _pct_vals = _top_pct_df.loc[_mask, _sym]
                            _reason_ser = pd.Series(np.nan, index=common_index, dtype=object)
                            _reason_ser.loc[_mask] = _pct_vals.apply(
                                lambda p: tr.encode([tr.part(
                                    tr.RANKING_COMPOSITE, _metric_seg, max(1, round(p)), _rebal_note
                                )])
                            )
                            all_entry_reasons[_sym] = _reason_ser
            elif ranking_metric and not all_fund_rank_values.get(ranking_metric):
                # 재무 랭킹을 요청했는데 유니버스 전체에 그 컬럼이 없다 — 조용한 0거래로
                # 두지 않고 경고로 드러낸다(커버리지 로그 FR-BT-016과 같은 정직성 계약).
                self.warnings.add(rw.warning(
                    rw.RANK_METRIC_DATA_MISSING,
                    tr.part(FUNDAMENTAL_LABELS.get(ranking_metric, ranking_metric)),
                ))
            elif ranking_metric:
                # 재무 팩터 랭킹: as-of 재무 컬럼(연간 결산 전진충전) 값 순위로 상위 종목 선정.
                # 모멘텀('return') 랭킹과 같은 계약 — 순위 자체가 진입, 회전은 달력 리밸런싱.
                # NaN(재무 없음·자본잠식 등)은 중립값으로 위장시키지 않고 후보에서 자연 배제한다
                # (pbr/roe 블렌드와 같은 이유 — 아래 legacy 분기 주석 참고).
                try:
                    metric_df = pd.DataFrame(
                        all_fund_rank_values[ranking_metric], index=common_index,
                        columns=processed_symbols,
                    )
                    metric_df = _extend(metric_df, _pre_panel("fund_rank_values", ranking_metric).astype(float)).ffill()
                    if exec_type == 'next_open':
                        # 진입 신호는 이미 1일 shift됨 — 랭킹도 전일 값 기준으로 맞춘다(look-ahead 방지).
                        # 창 첫날은 창 직전 거래일 값(v16.12).
                        metric_df = _delay_to_window(metric_df).ffill()
                    pct = metric_df.rank(axis=1, pct=True)
                    # top=값 높은 순(기본), bottom=값 낮은 순(예: 'PER 낮은 상위 N종목').
                    _direction = str(risk_params.get('ranking_direction') or 'top')
                    rank_df = pct if _direction != 'bottom' else (1.0 - pct)
                    valid = metric_df.notna()
                    rank_df = rank_df.fillna(0.0)
                    _entry_conditions = (req.get('entry') or {}).get('conditions') or []
                    if not _entry_conditions:
                        # 랭킹 단독 전략(선정=진입): 값이 정의된 전 종목을 후보로 만들되
                        # 대형주 마스크·유동성 게이트를 다시 결합한다(momentum 분기 C4와 동일).
                        pool = self._ranking_selection_pool(available_df, valid, large_cap_mask, _liq_pool)
                        ents_df = pool

                        # 매수 사유: 그날의 지표 백분위(momentum 분기와 같은 계약 —
                        # 사유가 없으면 result_handler 폴백 문구로 뭉개진다).
                        _metric_seg = tr.part(FUNDAMENTAL_LABELS.get(ranking_metric, ranking_metric))
                        _dir_seg = tr.part(tr.RANK_LOWEST_FIRST) if _direction == 'bottom' else tr.literal("")
                        _rebal_kr = _REBAL_PERIOD_TEMPLATES.get(
                            str(risk_params.get('rebalancing_period') or ''), '')
                        _max_pos = risk_params.get('max_positions')
                        _rebal_note = self._build_rebal_note(
                            _rebal_kr, _max_pos, _qg_n, _sel_pct,
                            group_cap=risk_params.get('ranking_group_cap'),
                        )
                        _top_pct_df = (1.0 - rank_df) * 100.0
                        for _sym in processed_symbols:
                            _mask = pool[_sym]
                            if not _mask.any():
                                continue
                            _pct_vals = _top_pct_df.loc[_mask, _sym]
                            _reason_ser = pd.Series(np.nan, index=common_index, dtype=object)
                            _reason_ser.loc[_mask] = _pct_vals.apply(
                                lambda p: tr.encode([tr.part(
                                    tr.RANKING_FUNDAMENTAL, _metric_seg, _dir_seg, max(1, round(p)), _rebal_note
                                )])
                            )
                            all_entry_reasons[_sym] = _reason_ser
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 재무 팩터 랭킹 계산 실패: {e}")
                    rank_df = None
            elif (not skip_pos) and risk_params.get('ranking_enabled', True):
                # 후보 우선순위(v16.3, 2026-08-18 사용자 결정): 사용자가 랭킹을 말하지 않은
                # 전략에서 매수 조건 충족 종목이 빈 자리(최대 보유)보다 많은 날 — 리밸런싱일
                # 포함 — 은 **최근 N거래일 수익률이 높은 순**으로 우선 담는다. 종전에는 저PBR·
                # 고ROE 블렌드가 이 자리를 조용히 채웠다(사용자가 말한 적 없는 선정 기준).
                # 랭킹 전략(ranking_metric)이 아니므로 후보 자체는 매수 조건이 정하고, 이 순위는
                # 넘치는 날의 우선순위일 뿐이다 — 실제로 넘친 날이 있었으면 경고로 고지한다.
                try:
                    from engine.indicators import lookback_return_panel

                    _tiebreak = _to_ext(lookback_return_panel(rank_price_df, _TIEBREAK_LOOKBACK_DAYS))
                    rank_df = _tiebreak.rank(axis=1, pct=True)
                    if exec_type == 'next_open':
                        rank_df = _delay_to_window(rank_df)
                    rank_df = _to_window(rank_df)
                    # 수익률이 정의되지 않은 종목(신규 상장 등)은 후보에서 빼지 않고 최하위로
                    # 둔다 — 후보 자격은 매수 조건이 정하므로 우선순위만 뒤로 보낸다.
                    rank_df = rank_df.fillna(0.0)
                    _tiebreak_rank_used = True
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 후보 우선순위 계산 실패: {e}")
                    rank_df = None

            _t2 = _time.time()
            print(f"[BT-ENGINE] Phase1 완료: {_t2-_t1:.2f}s ({len(processed_symbols)}종목 처리)", flush=True)

            simulator_options = dict(options)
            simulator_options.setdefault('execution_type', exec_type)

            # ── 분위 그룹 모드 게이트 ──
            # 성립 조건: 랭킹(rank_df)과 정기 리밸런싱이 있어야 한다. 성립하면 메인
            # 실행을 1그룹(랭킹 최상위 분위 구간) 포트폴리오로 잡는다.
            _quantile_active = False
            if _qg_n >= 2:
                _rebal_ok = str(risk_params.get('rebalancing_period') or 'none') != 'none'
                if rank_df is None:
                    self.warnings.add(rw.warning(rw.QUANTILE_NEEDS_RANKING))
                elif not _rebal_ok:
                    self.warnings.add(rw.warning(rw.QUANTILE_NEEDS_REBALANCE))
                else:
                    _quantile_active = True
                    risk_params = dict(risk_params)
                    risk_params['ranking_band'] = [1, _qg_n]

            # 매수 조건이 있는 전략(신호·재무 필터)은 리밸런싱을 켜도 매수 조건이 후보를 정한다
            # (v16.3): 리밸런싱일이 아닌 날의 매수 신호도 빈 자리만큼 담고, 매도 신호도 그대로
            # 청산한다. 순수 랭킹 전략(선정=진입, entry.conditions 비어 있음)만 달력 회전이다.
            _entry_signal_driven = bool((req.get('entry') or {}).get('conditions'))
            if _entry_signal_driven:
                risk_params = dict(risk_params)
                risk_params['entry_signal_driven'] = True

            # ── 변동성 역비중·시장 국면 필터(v16.14) ──
            # 둘 다 신호·순위와 같은 지연 규칙으로 맞춘다(next_open이면 전일 정보, 창 첫날은 창
            # 직전 거래일 정보). 역비중은 σ가 정의된 종목만 담을 수 있으므로(1/σ) 후보를 σ 유효
            # 종목으로 좁힌다 — 신규 상장 종목이 σ 없이 들어와 비중을 정할 수 없는 일을 막는다.
            vol_df = None
            if _inverse_volatility_allocation(risk_params):
                if str(risk_params.get('rebalancing_period') or 'none') == 'none':
                    self.warnings.add(rw.warning(rw.INVERSE_VOL_NEEDS_REBALANCE))
                else:
                    from engine.indicators import annualized_volatility_panel
                    _alloc_lb = int(risk_params.get('allocation_lookback_days') or 60)
                    _vol_ext = _to_ext(annualized_volatility_panel(rank_price_df, _alloc_lb))
                    vol_df = (_delay_to_window(_vol_ext) if exec_type == 'next_open'
                              else _to_window(_vol_ext))
                    ents_df = ents_df & vol_df.notna()
            exposure = None
            _regime = risk_params.get('market_regime')
            if _regime:
                exposure = self._market_regime_exposure(
                    _regime, ext_index, _n_pre, signal_delay if exec_type == 'next_open' else 0)
                if exposure is None:
                    self.warnings.add(rw.warning(
                        rw.MARKET_REGIME_INDEX_MISSING, str(_regime.get('index') or 'KOSPI')))
                else:
                    _off_days = int((exposure < 1.0).sum())
                    _pct = float(_regime.get('exposure_pct') or 0.0)
                    self.warnings.add(rw.warning(
                        rw.MARKET_REGIME_APPLIED, str(_regime.get('index') or 'KOSPI'),
                        int(_regime.get('ma_period') or 0), _off_days,
                        str(int(_pct)) if _pct == int(_pct) else f"{_pct:g}",
                    ))

            pf = self.simulator.run(
                price_df, exec_px_df, ents_df, exts_df, risk_params, simulator_options,
                rank_df=rank_df, high_df=high_df, low_df=low_df, available_df=available_df,
                vol_df=vol_df, exposure=exposure,
            )
            _t3 = _time.time()
            print(f"[BT-ENGINE] Simulator 완료: {_t3-_t2:.2f}s", flush=True)

            # ── 리밸런싱 기간별 비교(FR-BT-064)를 Phase1 풀 워커에 미리 제출 ──
            # 결과 화면 전용 재시뮬레이션(6주기)이라 메인 결과 정리(Format)와 겹쳐 돌린다 —
            # 시뮬레이터 입력 프레임을 넘기고 아래 조립 지점에서 행을 받는다. 풀이 없거나
            # 최적화 세션이면 제출하지 않는다(세션은 아예 만들지 않음, 풀 없음은 동기 경로).
            _rc_job = None
            _rc_periods_todo = None
            if not self.in_optimization_session:
                from engine.rebalance_comparison import periods_to_simulate
                _rc_periods_todo = periods_to_simulate(risk_params)
                _rc_pool = self._phase1_pool() if len(_rc_periods_todo) > 1 else None
                if _rc_pool is not None:
                    try:
                        _rc_job = _rc_pool.submit_rebalance_rows(
                            {
                                "frames": {
                                    "price_df": price_df, "exec_px_df": exec_px_df, "ents_df": ents_df,
                                    "exts_df": exts_df, "rank_df": rank_df, "high_df": high_df,
                                    "low_df": low_df, "available_df": available_df,
                                    "vol_df": vol_df, "exposure": exposure,
                                },
                                "simulator_options": simulator_options,
                                "risk_params": risk_params,
                                "init_cash": float(risk_params.get('init_cash') or 10000000.0),
                            },
                            list(_rc_periods_todo),
                        )
                    except Exception as _rc_exc:
                        print(f"[BT-ENGINE] 리밸런싱 비교 워커 제출 실패 — 동기 경로: {_rc_exc}", flush=True)
                        _rc_job = None

            # 넘친 날 고지(v16.3): 랭킹을 말하지 않은 전략에서 매수 조건 충족 종목이 빈 자리보다
            # 많았던 날이 있으면, 무엇이 골랐는지 결과에 남긴다(조용한 기본값 금지).
            _overflow_days = int(getattr(self.simulator, 'overflow_days', 0) or 0)
            if _tiebreak_rank_used and _overflow_days > 0:
                _cap_note = risk_params.get('max_positions')
                self.warnings.add(rw.warning(
                    rw.OVERFLOW_TIEBREAK, _cap_note, _overflow_days, _TIEBREAK_LOOKBACK_DAYS,
                ))

            # 5. Benchmark ETF 로드
            _benchmark_sym, _benchmark_name = self.benchmark_for_universe(
                req.get('universe_id') or '', processed_symbols
            )
            benchmark_prices = None
            try:
                _bench_df = self.loader.load_symbol_data(_benchmark_sym)
                if _bench_df is not None:
                    _bench_pd = self.loader.preprocess_data(
                        _bench_df, apply_dividends=apply_dividends,
                        sanitize_corporate_actions=not universe_pit.is_us_symbol(_benchmark_sym),
                    )
                    benchmark_prices = _bench_pd['close'].sort_index()
                    # H1: 벤치마크가 자기 존재 구간만, 전략은 전체 구간을 복리로 쌓으므로
                    # 두 수익률의 기간이 다르다 — 전략에 유리한 쪽으로 기우는 비교이고,
                    # 데이터로 메울 수 없어 값 보정 대신 공시한다.
                    if len(common_index) > 0 and benchmark_prices.index[0] > pd.Timestamp(common_index[0]):
                        self.warnings.add(rw.warning(
                            rw.BENCHMARK_PARTIAL_PERIOD,
                            _benchmark_name, benchmark_prices.index[0].strftime('%Y-%m-%d'),
                        ))
                    # M3: 전략은 토탈리턴인데 벤치마크에 분배금 데이터가 없으면 비대칭 비교
                    if apply_dividends and 'dividends' not in _bench_df.columns:
                        self.warnings.add(rw.warning(rw.BENCHMARK_NO_DIVIDENDS))
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
                entry_reason_overrides=getattr(self.simulator, 'entry_reason_overrides', None),
            )
            final["universe_id"] = req.get('universe_id') or ''
            # 이 결과가 실제로 적용한 거래 비용 — 설정 화면 값이 아니라 엔진이 해석한 값을 결과
            # 로그에 남긴다(기록에서 다시 연 결과도 어떤 비용으로 계산됐는지 알 수 있게).
            final["tradingCosts"] = applied_trading_costs(options, common_index)
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

            # ── 분위 그룹 비교 실행 (FR-BT-060) ──
            # rank_df·신호는 이미 계산돼 있으므로 그룹별로는 시뮬레이션만 반복한다.
            # 그룹 비교는 순수 리밸런싱 기준(개별 손절/익절/트레일링/보유기간 미적용) —
            # 동일 규칙으로 G개 그룹을 나란히 비교하기 위해서다.
            if _quantile_active:
                _init_cash_val = float(risk_params.get('init_cash') or 10000000.0)
                _group_rp_base = dict(risk_params)
                for _k in ('stop_loss_pct', 'take_profit_pct', 'trailing_stop_pct',
                           'max_holding_days', 'max_mdd_limit_pct'):
                    _group_rp_base[_k] = None
                # 변동성 랭킹의 방향 미지정 기본은 bottom(저변동성 선호) — 랭킹 분기와 동일.
                _dir_default = 'bottom' if ranking_metric == 'volatility' else 'top'
                _dir_bottom = str(risk_params.get('ranking_direction') or _dir_default) == 'bottom'
                if ranking_metric == 'return':
                    _metric_kr = f"최근 {int(risk_params.get('ranking_lookback_days') or 60)}거래일 수익률"
                elif ranking_metric == 'relative_return':
                    _metric_kr = f"최근 {int(risk_params.get('ranking_lookback_days') or 60)}거래일 시장 대비 초과수익률"
                elif ranking_metric == 'volatility':
                    _metric_kr = f"최근 {int(risk_params.get('ranking_lookback_days') or 60)}거래일 변동성"
                elif ranking_metric == 'composite':
                    _metric_kr = _composite_ranking_label(_rank_components, risk_params.get('ranking_lookback_days'))
                else:
                    _metric_kr = FUNDAMENTAL_LABELS.get(ranking_metric, ranking_metric)
                # 복합 순위는 구성 지표마다 방향이 다르다(라벨 안에 병기) — 합산 점수의 상위 순.
                _order_kr = "상위" if ranking_metric == 'composite' else ("낮은" if _dir_bottom else "높은")
                _groups_out = []
                _group_sim = Simulator()
                for _g in range(1, _qg_n + 1):
                    _rp = dict(_group_rp_base)
                    _rp['ranking_band'] = [_g, _qg_n]
                    try:
                        _pf_g = _group_sim.run(
                            price_df, exec_px_df, ents_df, exts_df, _rp, simulator_options,
                            rank_df=rank_df, high_df=high_df, low_df=low_df,
                            available_df=available_df, vol_df=vol_df, exposure=exposure,
                        )
                        _summary = self._quantile_group_summary(_pf_g, _init_cash_val)
                    except Exception as _ge:
                        import logging
                        logging.getLogger(__name__).warning(
                            f"[BacktestEngine] 분위 그룹 {_g}/{_qg_n} 시뮬레이션 실패: {_ge}"
                        )
                        continue
                    _lo = round((_g - 1) * 100 / _qg_n)
                    _hi = round(_g * 100 / _qg_n)
                    _summary.update({
                        "group": _g,
                        "pctRange": [_lo, _hi],
                        "label": f"{_g}그룹 ({_metric_kr} {_order_kr} 순 {_lo}~{_hi}%)",
                    })
                    _groups_out.append(_summary)
                if _groups_out:
                    final["quantileGroups"] = {
                        "groups": _groups_out,
                        "metricLabel": _metric_kr,
                        "orderLabel": f"{_metric_kr} {_order_kr} 순",
                        "groupCount": _qg_n,
                        "mainGroup": 1,
                        # 그룹당 보유 상한(FR-BT-060b) — 없으면 그룹 구간 전체 보유.
                        "groupCap": risk_params.get('ranking_group_cap'),
                    }
                    self.warnings.add(rw.warning(rw.QUANTILE_GROUPS_PURE_REBALANCE, _qg_n))
                _t5 = _time.time()
                final["timing"]["quantileGroups"] = round(_t5 - _t4, 2)
                print(f"[BT-ENGINE] 분위 {_qg_n}그룹 완료: {_t5-_t4:.2f}s", flush=True)

            # ── 리밸런싱 기간별 결과 비교 (FR-BT-064) ──
            # 1단계 입력(가격·신호·랭킹)은 그대로 두고 rebalancing_period만 6주기로 바꿔
            # 시뮬레이션만 반복한다 — 결과 화면 탭이 별도 실행 없이 바로 보여준다.
            # 비교 실패는 메인 결과에 영향을 주지 않는다(로그만).
            # 최적화 세션(시도별 지표만 쓰는 반복) 안에서는 만들지 않는다 — 결과 화면 전용.
            if self.in_optimization_session:
                final["rebalanceComparison"] = None
            else:
                try:
                    from engine.rebalance_comparison import (
                        assemble_comparison, run_rebalance_period_comparison,
                    )
                    _t_rc0 = _time.time()
                    _rc_rows = None
                    if _rc_job is not None:
                        # 워커가 Format 동안 돌려 둔 행을 받는다 — 실패하면 동기 경로로 다시 계산한다.
                        try:
                            _rc_rows = _rc_job.result(timeout_s=float(os.environ.get("BACKTEST_TIMEOUT_S", "600")))
                        except Exception as _rc_exc:
                            print(f"[BT-ENGINE] 리밸런싱 비교 워커 결과 실패 — 동기 재계산: {_rc_exc}", flush=True)
                            _rc_rows = None
                    if _rc_rows is not None:
                        final["rebalanceComparison"] = assemble_comparison(_rc_rows, risk_params)
                        _rc_where = f"워커 {len(_rc_rows)}행 대기"
                    else:
                        final["rebalanceComparison"] = run_rebalance_period_comparison(
                            lambda _rp: Simulator().run(
                                price_df, exec_px_df, ents_df, exts_df, _rp, simulator_options,
                                rank_df=rank_df, high_df=high_df, low_df=low_df, available_df=available_df,
                                vol_df=vol_df, exposure=exposure,
                            ),
                            risk_params,
                            float(risk_params.get('init_cash') or 10000000.0),
                        )
                        _rc_where = f"동기 {len(_rc_periods_todo or ())}주기"
                    final["timing"]["rebalanceComparison"] = round(_time.time() - _t_rc0, 2)
                    print(f"[BT-ENGINE] 리밸런싱 6주기 비교 완료: {_time.time()-_t_rc0:.2f}s ({_rc_where})", flush=True)
                except Exception as _rce:
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 리밸런싱 기간별 비교 실패: {_rce}")

            # Add no-trades warning
            if pf.trades.count() == 0:
                liquidity_excluded = [
                    rw.symbol_of(w)
                    for w in self.warnings
                    if tr.first_template(w) == rw.SYMBOL_LIQUIDITY_BELOW
                ]
                if liquidity_excluded:
                    excluded_list = [tr.literal(", ".join(liquidity_excluded[:3]))]
                    if len(liquidity_excluded) > 3:
                        excluded_list.append(tr.part(rw.MORE_SYMBOLS, len(liquidity_excluded) - 3))
                    self.warnings.add(rw.compose(
                        tr.part(rw.NO_TRADES),
                        tr.part(rw.NO_TRADES_LIQUIDITY_DETAIL, len(liquidity_excluded), excluded_list),
                    ))
                else:
                    self.warnings.add(rw.warning(rw.NO_TRADES))

            # ── 신뢰성 공시 경고 (감사 H5/H7/H8 등) ──────────────────────────
            _rebal_period = str(risk_params.get('rebalancing_period') or 'none')
            _has_pos_risk = (not risk_params.get('skip_risk_management', False)) and any(
                float(risk_params.get(k) or 0) > 0
                for k in ('stop_loss_pct', 'take_profit_pct', 'trailing_stop_pct', 'max_holding_days')
            )
            _weights_only = str(
                risk_params.get('rebalance_method') or 'reconstitute'
            ) == 'weights_only'
            if _rebal_period != 'none' and risk_params.get('max_positions') and (
                _has_pos_risk or _entry_signal_driven
            ):
                # H8: 리스크 관리와 혼합된 리밸런싱, 그리고 매수 조건이 있는 전략의 리밸런싱은
                # 커스텀 루프로 돈다. 방식에 따라 하는 일이 반대다 — 종목 교체(reconstitution)는
                # 목표 밖 보유를 편출하고 비중은 리셋하지 않으며, 비중 유지(weights_only)는
                # 편출 없이 비중만 균등으로 되돌린다(FR-BT-067).
                if _weights_only:
                    self.warnings.add(rw.warning(rw.REBALANCE_WEIGHTS_ONLY))
                elif _entry_signal_driven:
                    self.warnings.add(rw.warning(rw.REBALANCE_RECONSTITUTE))
                else:
                    self.warnings.add(rw.warning(rw.REBALANCE_WITH_RISK_EXITS))

            _tax_raw = options.get('sell_tax_rate')
            if _tax_raw is not None:
                if float(_tax_raw) > 0:
                    self.warnings.add(rw.warning(rw.SELL_TAX_APPLIED, f"{float(_tax_raw) * 100:.2f}"))
            else:
                from engine.transaction_tax import kr_sell_tax_rates
                _rates = kr_sell_tax_rates(common_index)
                _lo, _hi = float(_rates.min()) * 100, float(_rates.max()) * 100
                if _lo == _hi:
                    self.warnings.add(rw.warning(rw.SELL_TAX_APPLIED_WITH_RURAL, f"{_hi:.2f}"))
                else:
                    self.warnings.add(rw.warning(rw.SELL_TAX_SCHEDULE_APPLIED, f"{_hi:.2f}", f"{_lo:.2f}"))

            # 1년 미만 구간의 CAGR은 정의대로 연환산하지만, 짧은 표본을 1년으로
            # 늘리는 과정에서 잡음이 함께 증폭된다 — 값을 왜곡하는 대신 고지한다.
            _bt_years, _ = ResultHandler.time_base(common_index)
            if 0 < _bt_years < 1.0:
                self.warnings.add(rw.warning(rw.SHORT_PERIOD_ANNUALIZED, f"{_bt_years * 12:.0f}"))

            _n_trades = int(pf.trades.count())
            if 0 < _n_trades < 30:
                self.warnings.add(rw.warning(rw.FEW_TRADES, _n_trades))

            if ai_needed:
                # H7: 백테스트 구간이 AI 모델 학습 데이터와 겹치면 인샘플 낙관 편향
                _meta = _ai_model_meta()
                _train_end = _ai_model_train_end()
                _val_end = _ai_model_val_end(_meta)
                if _train_end and (_period_start_str is None or _period_start_str < _train_end):
                    self.warnings.add(rw.warning(rw.AI_TRAIN_OVERLAP, _train_end))
                # 검증 구간도 인샘플이다 — 신호 임계값·조기종료가 이 구간으로 정해졌다.
                if _val_end and (_period_start_str is None or _period_start_str < _val_end):
                    self.warnings.add(rw.warning(rw.AI_VALIDATION_OVERLAP, _val_end))

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
                    self.warnings.add(rw.warning(rw.LIQUIDITY_LIMIT_EXCEEDED, _liq_viol, f"{liquid_limit:.0f}"))
            except Exception:
                pass

            # 데이터 커버리지 리포트 — 각 펀더멘털 지표가 실제로 어떤 데이터로/얼마나
            # 계산됐는지 결과 로그에 투명하게 남기고, 부족 시 경고를 warnings에 합류시킨다.
            if _coverage_acc is not None:
                _coverage_report = _coverage_acc.build()
                final["dataCoverage"] = _coverage_report
                for _parts in _coverage_report.get("warningParts", []):
                    self.warnings.add(tr.encode(_parts))

            # 경고는 한국어 문장(warnings, 종전과 동일)과 세그먼트(warningParts)를 같은 순서로
            # 싣는다 — 프론트가 세그먼트를 t()로 옮긴다(/us 영어). engine/result_warnings.py 참조.
            _warning_texts, _warning_parts = rw.finalize(self.warnings)
            _pf_warnings = [str(w) for w in getattr(pf, 'warnings', [])]
            final["warnings"] = _warning_texts + _pf_warnings
            final["warningParts"] = _warning_parts + [[tr.literal(w)] for w in _pf_warnings]
            final["resolution_logs"] = all_resolution_logs
            return final

        except Exception as e:
            import traceback; traceback.print_exc()
            raise e
