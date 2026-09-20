from typing import List, Dict, Any, Tuple, Optional
import os
import json
import functools
import polars as pl
import numpy as np

from engine.indicator_columns import (
    bollinger_columns, macd_columns, stochastic_columns, trading_value_sma_col,
)
from engine import trade_reason as tr


# Fundamental filter metrics. The condition id equals the parquet column name, so the
# eval branches are fully generic (get_col(cid) / safe_get(cid)). Single source of truth
# for which metrics are filterable and how their badges read.
FUNDAMENTAL_LABELS = {
    "per": "PER", "pbr": "PBR", "psr": "PSR", "pcr": "PCR",
    "ev_ebitda": "EV/EBITDA", "ev_ebit": "EV/EBIT",
    "roe_or_gpa": "ROE", "roa": "ROA",
    "debt_ratio": "부채비율", "current_ratio": "유동비율", "quick_ratio": "당좌비율",
    "reserve_ratio": "유보율", "net_margin": "순이익률", "gross_margin": "매출총이익률",
    "operating_margin": "영업이익률",
    "revenue_growth": "매출액증가율", "operating_income_growth": "영업이익증가율",
    "net_income_growth": "순이익증가율", "market_cap": "시가총액",
    "dividend_yield": "배당수익률", "payout_rate": "배당성향",
    "dividend_growth": "배당성장률",
    "eps_growth": "EPS증가율", "ebitda_growth": "EBITDA증가율",
    "ocf_growth": "영업현금흐름증가율", "fcf_growth": "잉여현금흐름증가율",
    # v16.14 — DART 원재료로 계산(fundamental_fetcher.compute_roic/compute_fcf_margin).
    "roic": "ROIC", "fcf_margin": "FCF 마진",
    # v16.15 — FCF 수익률(fcf ÷ market_cap, fundamental_fetcher.recompute_fcf_yield)·연속 배당
    # 연수(dividends 달력 연도 연속, dividends.dividend_streak_years). parquet에 없으면
    # data_resolver가 런타임에 계산한다. 라벨은 프론트 요약 표(lib/strategy-summary.ts)와 동일.
    "fcf_yield": "FCF 수익률", "dividend_streak_years": "연속 배당 연수",
    # eps(원)·ebit(억원) 부호 필터로 '흑자/적자'·'영업이익 흑자/적자' 키워드 조건을
    # 표현한다(nl_parser 참고).
    "eps": "EPS",
    "ebit": "영업이익",
    # 당기순이익 절대 금액(억원, 순이익률x매출액 재계산 — fundamental_fetcher 참고).
    # net_income은 비지배지분이 섞인 연결 전체, owner_net_income은 지배기업 소유주 귀속분
    # (DART 손익계산서)이다 — 서로 다른 지표이니 한쪽으로 뭉뚱그리지 말 것.
    "net_income": "당기순이익",
    "owner_net_income": "지배주주순이익",
    # 현금흐름 3분류 절대 금액(억원). 투자·재무는 통상 음수(자산 취득·차입 상환)라
    # 부호가 살아 있는 값을 그대로 비교한다 — fundamental_fetcher 참고.
    "operating_cf_amount": "영업활동현금흐름",
    "investing_cf_amount": "투자활동현금흐름",
    "financing_cf_amount": "재무활동현금흐름",
}
FUNDAMENTAL_CIDS = list(FUNDAMENTAL_LABELS)
# Metrics whose value is an amount (억원), not a ratio — for badge suffixing.
FUNDAMENTAL_AMOUNT_CIDS = {
    "market_cap", "net_income", "owner_net_income",
    "operating_cf_amount", "investing_cf_amount", "financing_cf_amount",
}


@functools.lru_cache(maxsize=1)
def _ai_calibrated_thresholds() -> Tuple[float, float]:
    """(buy_threshold, sell_threshold) from the live model's model_meta.json.

    Used as the *default* AI signal threshold when a strategy block omits one.
    A hardcoded default (the legacy 0.70) sits far above the heads' actual score
    range — the DOWN head maxes out near 0.38 — so it never fires. Defaulting to
    the model's own val-calibrated thresholds keeps the signal in-distribution.
    """
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for ver in ('v3', 'v2'):
        meta_path = os.path.join(base, 'model', ver, 'model_meta.json')
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    m = json.load(f)
                return float(m.get('buy_threshold', 0.5)), float(m.get('sell_threshold', 0.5))
            except (ValueError, OSError):
                break
    return 0.5, 0.5


def _ai_threshold(p: Dict[str, Any], target_type: str) -> float:
    """Resolve an AI signal threshold (0–1) from block params, falling back to
    the model's calibrated default for the given direction when none is given."""
    buy_thr, sell_thr = _ai_calibrated_thresholds()
    raw = p.get('threshold')
    if raw is None:
        raw = p.get('minProbability')
    if raw is None:
        return sell_thr if target_type == 'down' else buy_thr
    thr = float(raw)
    return thr / 100.0 if thr > 1.0 else thr


class SignalEngine:
    def __init__(self):
        pass

    # ──────────────────────────────────────────────────────────────────────────
    # Fix 4: generate_signals는 _eval_vec으로 전체 열을 한 번에 계산(벡터화)
    # evaluate_condition / evaluate_group은 테스트 호환성을 위해 그대로 유지
    # ──────────────────────────────────────────────────────────────────────────
    def generate_signals(self, df: pl.DataFrame, group: Dict[str, Any]) -> Tuple[np.ndarray, List[Optional[str]]]:
        if not group or not group.get('conditions'):
            data_len = len(df)
            return np.zeros(data_len, dtype=bool), [None] * data_len

        data_len = len(df)
        logic = str(group.get('logic', 'OR')).upper()
        filters = [c for c in group['conditions'] if c.get('type') == 'filter']
        signals = [c for c in group['conditions'] if c.get('type') != 'filter']

        # Fix 4: 조건별 boolean 배열을 한 번에 계산
        sig_arrays = [self._eval_vec(cond, df) for cond in signals]
        fil_arrays = [self._eval_vec(cond, df) for cond in filters]

        # Signal: group.logic에 따라 AND / OR 결합
        if sig_arrays:
            if logic == 'AND':
                sig_result = np.ones(data_len, dtype=bool)
                for arr in sig_arrays:
                    sig_result &= arr
            else:
                sig_result = np.zeros(data_len, dtype=bool)
                for arr in sig_arrays:
                    sig_result |= arr
        else:
            # 필터만 존재하는 경우 전체 통과로 처리
            sig_result = np.ones(data_len, dtype=bool) if filters else np.zeros(data_len, dtype=bool)

        # Filter: AND 결합
        fil_result = np.ones(data_len, dtype=bool)
        for arr in fil_arrays:
            fil_result &= arr

        final = sig_result & fil_result

        # Fix 4: 이유는 True인 행에 대해서만 생성 (희소 접근으로 오버헤드 최소화).
        # 표시 번역은 프론트 t() 소관이라 완성 문장이 아니라 한국어 정본 템플릿과 인자를
        # 실어 보낸다(engine/trade_reason.py).
        reasons: List[Optional[str]] = [None] * data_len
        true_indices = np.where(final)[0]
        if len(true_indices) > 0:
            sig_segs = [self.get_condition_segments(c) for c in signals]
            fil_segs = [self.get_condition_segments(c) for c in filters]
            # 실측값을 싣는 조건(시장 대비 초과수익률)은 행마다 서술이 달라진다 — 그 조건의
            # 지표 열만 미리 꺼내 두고, 나머지 조건은 정적 서술을 그대로 재사용한다.
            sig_measured = [self._measured_array(c, df) for c in signals]
            fil_measured = [self._measured_array(c, df) for c in filters]
            sig_joiner = [tr.SEP_AND] if logic == 'AND' else tr.or_separator()

            def segs_at(cond, static, measured, i):
                if measured is None:
                    return static
                return self.get_condition_segments(cond, measured=float(measured[i]))

            for i in true_indices:
                active_sig = [segs_at(c, d, m, i) for c, d, m, arr in zip(signals, sig_segs, sig_measured, sig_arrays) if arr[i] and d]
                active_fil = [segs_at(c, d, m, i) for c, d, m, arr in zip(filters, fil_segs, fil_measured, fil_arrays) if arr[i] and d]
                sig_part = tr.join(active_sig, sig_joiner)
                fil_part = tr.join(active_fil, [tr.SEP_AND])
                if sig_part and fil_part:
                    combined = [tr.PAREN_OPEN] + sig_part + [tr.PAREN_CLOSE, tr.SEP_AND] + fil_part
                else:
                    combined = sig_part or fil_part
                reasons[i] = tr.encode(combined) if combined else None

        return final, reasons

    # ──────────────────────────────────────────────────────────────────────────
    # Fix 4: 벡터화 평가 — 조건 하나를 전체 시계열에 대해 boolean 배열로 반환
    # Fix 3: ema / macd / stochastic / cci / adx 평가자 추가
    # ──────────────────────────────────────────────────────────────────────────
    def _eval_vec(self, cond: Dict[str, Any], df: pl.DataFrame) -> np.ndarray:
        cid, p = cond['id'], cond['params']
        data_len = len(df)
        result = np.zeros(data_len, dtype=bool)

        def get_col(col: str) -> Optional[np.ndarray]:
            try:
                return df[col].to_numpy().astype(float)
            except Exception:
                return None

        def compare_vec(arr: Optional[np.ndarray], op: str, val: float) -> np.ndarray:
            if arr is None:
                return np.zeros(data_len, dtype=bool)
            with np.errstate(invalid='ignore'):
                if op == '>':  return arr > val
                if op == '<':  return arr < val
                if op == '>=': return arr >= val
                if op == '<=': return arr <= val
                if op == '==': return arr == val
            return np.zeros(data_len, dtype=bool)

        def crossover(fast: Optional[np.ndarray], slow: Optional[np.ndarray], direction: str = 'golden') -> np.ndarray:
            """골든크로스(direction='golden'): fast가 slow를 상향 돌파
               데드크로스(direction='dead') : fast가 slow를 하향 돌파"""
            if fast is None or slow is None:
                return np.zeros(data_len, dtype=bool)
            res = np.zeros(data_len, dtype=bool)
            with np.errstate(invalid='ignore'):
                if direction == 'golden':
                    res[1:] = (fast[:-1] <= slow[:-1]) & (fast[1:] > slow[1:])
                else:
                    res[1:] = (fast[:-1] >= slow[:-1]) & (fast[1:] < slow[1:])
            return res

        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long_ = p.get('longMA', p.get('long_period', p.get('long', 20)))
            s = get_col(f'close_{short}_sma')
            l = get_col(f'close_{long_}_sma')
            # 지속 상태(mode='above'/'below') — "종가가 60일선 위에 있는 동안"·"20일선이
            # 60일선 위에 머무는" 게이트다. EMA(아래)와 같은 계약이며, 종전에는 SMA에
            # 이 모드가 없어 상태 표현이 교차 이벤트(하루)로 좁혀졌다(2026-09-10).
            # short=1이면 close_1_sma=종가라 '가격 vs N일선' 상태가 같은 식으로 나온다.
            mode = p.get('mode')
            if mode in ('above', 'below'):
                if s is None or l is None:
                    return result
                with np.errstate(invalid='ignore'):
                    return s >= l if mode == 'above' else s <= l
            direction = 'dead' if p.get('signalType') == 'sell' else 'golden'
            return crossover(s, l, direction)

        elif cid == 'rsi':
            period = p.get('period', p.get('rsi_period', 14))
            r = get_col(f'rsi_{period}')
            value = float(p.get('value', 30))
            if p.get('mode') == 'rebound':
                # 과매도/과매수 임계선을 '다시 돌파'하는 반등: 매수=상향 돌파, 매도=하향 돌파.
                if r is None:
                    return np.zeros(data_len, dtype=bool)
                const = np.full(data_len, value)
                direction = 'dead' if p.get('signalType') == 'sell' else 'golden'
                return crossover(r, const, direction)
            return compare_vec(r, p.get('operator', '<'), value)

        elif cid == 'ema':
            # Fix 3: EMA 평가자 — 듀얼 EMA 크로스오버 또는 가격 vs EMA 크로스오버
            short_p = p.get('shortPeriod', p.get('short'))
            long_p = p.get('longPeriod', p.get('long'))
            if short_p is not None and long_p is not None:
                fast = get_col(f'close_{int(short_p)}_ema')
                slow = get_col(f'close_{int(long_p)}_ema')
                # 두 EMA의 **지속 상태**(정배열/역배열) — "20일 EMA가 60일 EMA 위에 있는"은
                # 교차한 그 날이 아니라 위에 있는 동안 계속 참인 게이트다. 종전에는 이 모드가
                # 없어 두 기간을 살리면 교차 이벤트가 되고, 상태로 옮기려면 한 선을 버려야
                # 했다(가격 vs EMA) — 어느 쪽이든 사용자가 말한 것과 달랐다 (2026-08-18).
                mode = p.get('mode')
                if mode in ('above', 'below'):
                    if fast is None or slow is None:
                        return result
                    with np.errstate(invalid='ignore'):
                        return fast >= slow if mode == 'above' else fast <= slow
                direction = 'dead' if p.get('signalType') == 'sell' else 'golden'
                return crossover(fast, slow, direction)
            period = p.get('period', 20)
            ema_arr = get_col(f'close_{period}_ema')
            close = get_col('close')
            if ema_arr is None or close is None:
                return result
            # 추세 필터(지속 상태): mode='above'→가격이 EMA 위, 'below'→아래. 크로스오버가 아니라
            # 매 봉에서 참인 게이트라 filter 조건으로 진입 신호와 AND 결합할 때 쓴다.
            mode = p.get('mode')
            if mode in ('above', 'below'):
                with np.errstate(invalid='ignore'):
                    return close >= ema_arr if mode == 'above' else close <= ema_arr
            if p.get('signalType') == 'sell':
                # 가격이 EMA 하향 돌파
                res = np.zeros(data_len, dtype=bool)
                with np.errstate(invalid='ignore'):
                    res[1:] = (close[:-1] >= ema_arr[:-1]) & (close[1:] < ema_arr[1:])
                return res
            else:
                # 가격이 EMA 상향 돌파
                res = np.zeros(data_len, dtype=bool)
                with np.errstate(invalid='ignore'):
                    res[1:] = (close[:-1] <= ema_arr[:-1]) & (close[1:] > ema_arr[1:])
                return res

        elif cid == 'macd':
            # Fix 3: MACD 평가자 — 크로스오버 또는 제로선 돌파 (기간 파라미터화 지원)
            macd_col, macds_col = macd_columns(p)
            macd = get_col(macd_col)
            macds = get_col(macds_col)  # signal line
            sig_type = p.get('signalType', 'buy')
            mode = p.get('mode', 'crossover')
            if mode == 'zero':
                if macd is None:
                    return result
                return compare_vec(macd, '>' if sig_type != 'sell' else '<', 0.0)
            else:
                direction = 'dead' if sig_type == 'sell' else 'golden'
                return crossover(macd, macds, direction)

        elif cid == 'stochastic':
            # Fix 3: Stochastic 평가자 — K/D 크로스오버 또는 과매수/과매도 레벨 (기간 파라미터화 지원)
            k_col, d_col = stochastic_columns(p)
            k = get_col(k_col)
            d = get_col(d_col)
            sig_type = p.get('signalType', 'buy')
            mode = p.get('mode', 'crossover')
            if mode == 'level':
                default_val = 20.0 if sig_type != 'sell' else 80.0
                default_op = '<' if sig_type != 'sell' else '>'
                return compare_vec(k, p.get('operator', default_op), float(p.get('value', default_val)))
            else:
                direction = 'dead' if sig_type == 'sell' else 'golden'
                return crossover(k, d, direction)

        elif cid == 'cci':
            # Fix 3: CCI 평가자
            period = p.get('period', 14)
            cci_arr = get_col(f'cci_{period}')
            sig_type = p.get('signalType', 'buy')
            default_val = -100.0 if sig_type != 'sell' else 100.0
            default_op = '<' if sig_type != 'sell' else '>'
            return compare_vec(cci_arr, p.get('operator', default_op), float(p.get('value', default_val)))

        elif cid == 'adx':
            # Fix 3: ADX 평가자 — 추세 강도 필터
            adx_arr = get_col('adx')
            return compare_vec(adx_arr, p.get('operator', '>='), float(p.get('value', 25)))

        elif cid == 'williams_r':
            # Williams %R (범위 -100~0). 과매도(-80 이하) 매수 / 과매수(-20 이상) 매도 기본.
            period = p.get('period', 14)
            wr = get_col(f'wr_{period}')
            sig_type = p.get('signalType', 'buy')
            default_val = -80.0 if sig_type != 'sell' else -20.0
            default_op = '<=' if sig_type != 'sell' else '>='
            return compare_vec(wr, p.get('operator', default_op), float(p.get('value', default_val)))

        elif cid == 'mfi':
            # Money Flow Index (0~100). 과매도(20 이하) 매수 / 과매수(80 이상) 매도 기본.
            period = p.get('period', 14)
            mfi = get_col(f'mfi_{period}')
            sig_type = p.get('signalType', 'buy')
            default_val = 20.0 if sig_type != 'sell' else 80.0
            default_op = '<=' if sig_type != 'sell' else '>='
            return compare_vec(mfi, p.get('operator', default_op), float(p.get('value', default_val)))

        elif cid == 'roc':
            # Rate of Change / 모멘텀(%). 상승 모멘텀(0 초과) 매수 / 하락(0 미만) 매도 기본.
            period = p.get('period', 12)
            roc = get_col(f'close_{period}_roc')
            sig_type = p.get('signalType', 'buy')
            default_op = '>' if sig_type != 'sell' else '<'
            return compare_vec(roc, p.get('operator', default_op), float(p.get('value', 0)))

        elif cid == 'relative_return':
            # 시장 대비 초과수익률(%p). 시장보다 나은(0 초과) 매수 / 못한(0 미만) 매도 기본.
            period = p.get('period', 60)
            rr = get_col(f'relative_return_{period}')
            sig_type = p.get('signalType', 'buy')
            default_op = '>' if sig_type != 'sell' else '<'
            return compare_vec(rr, p.get('operator', default_op), float(p.get('value', 0)))

        elif cid == 'volatility':
            # 연환산 변동성(%). 저변동성(임계 이하) 매수 / 고변동성(임계 이상) 매도 기본.
            period = p.get('period', 60)
            vol = get_col(f'volatility_{period}')
            sig_type = p.get('signalType', 'buy')
            default_op = '<=' if sig_type != 'sell' else '>='
            return compare_vec(vol, p.get('operator', default_op), float(p.get('value', 30)))

        elif cid in ['price_level', 'price']:
            c = get_col('close')
            return compare_vec(c, p.get('operator', '>'), float(p.get('value', 0)))

        elif cid == 'bollinger_bands':
            c = get_col('close')
            if c is None:
                return result
            ub_col, lb_col = bollinger_columns(p)
            if p.get('signalType') == 'sell':
                ub = get_col(ub_col)
                if ub is None:
                    return result
                with np.errstate(invalid='ignore'):
                    return c >= ub
            else:
                lb = get_col(lb_col)
                if lb is None:
                    return result
                with np.errstate(invalid='ignore'):
                    return c <= lb

        elif cid == 'volume_spike':
            period = p.get('period', 20)
            obv = get_col('obv')
            obv_sma = get_col(f'obv_{period}_sma')
            direction = 'dead' if p.get('signalType') == 'sell' else 'golden'
            return crossover(obv, obv_sma, direction)

        elif cid == 'volume_ratio':
            # 거래량 배수(v16.10): 당일 거래량 ÷ 직전 N일 평균 거래량이 배수 임계를 넘는가.
            # 평균이 없는 초기 구간(NaN)·평균 0은 NaN → compare_vec가 False로 떨어뜨린다.
            period = p.get('period', 20)
            vol = get_col('volume')
            prev_sma = get_col(f'volume_{period}_prev_sma')
            if vol is None or prev_sma is None:
                return result
            with np.errstate(divide='ignore', invalid='ignore'):
                ratio = np.where(prev_sma > 0, vol / prev_sma, np.nan)
            return compare_vec(ratio, p.get('operator', '>='), float(p.get('value', 2)))

        elif cid == 'trading_value_ratio':
            # 거래대금 배수(v16.13): 당일 거래대금(종가×거래량) ÷ 직전 N일 평균 거래대금.
            # NaN·평균 0 처리는 volume_ratio와 같다(compare_vec가 False로 떨어뜨린다).
            period = p.get('period', 20)
            c, v = get_col('close'), get_col('volume')
            prev_sma = get_col(f'trading_value_{period}_prev_sma')
            if c is None or v is None or prev_sma is None:
                return result
            with np.errstate(divide='ignore', invalid='ignore'):
                ratio = np.where(prev_sma > 0, (c * v) / prev_sma, np.nan)
            return compare_vec(ratio, p.get('operator', '>='), float(p.get('value', 1)))

        elif cid == 'breakout':
            period = p.get('lookbackPeriod', 20)
            current_high = get_col('high')
            current_low = get_col('low')
            if current_high is None or current_low is None:
                return result
            if p.get('signalType') == 'sell':
                prev_min = get_col(f'low_{period}_min')
                if prev_min is None:
                    return result
                res = np.zeros(data_len, dtype=bool)
                with np.errstate(invalid='ignore'):
                    # Today's low breaks below the prior lookback low.
                    res[1:] = current_low[1:] < prev_min[:-1]
                return res
            else:
                prev_max = get_col(f'high_{period}_max')
                if prev_max is None:
                    return result
                res = np.zeros(data_len, dtype=bool)
                with np.errstate(invalid='ignore'):
                    # Today's high breaks above the prior lookback high.
                    res[1:] = current_high[1:] > prev_max[:-1]
                return res

        elif cid == 'trading_value':
            val = float(p.get('value', 0)) * 100_000_000
            curr_val = get_col(trading_value_sma_col(p.get('period')))
            if curr_val is None:
                c = get_col('close')
                v = get_col('volume')
                if c is not None and v is not None:
                    curr_val = c * v
            return compare_vec(curr_val, p.get('operator', '>='), val)

        elif cid in FUNDAMENTAL_CIDS:
            val = float(p.get('value') or 0)
            curr = get_col(cid)
            if curr is None:
                # 명시적 재무 필터인데 컬럼 자체가 없으면 검증 불가 → 제외(fail-closed).
                # (컬럼은 있으나 값이 NaN인 행은 compare_vec에서 이미 False=제외 처리됨.)
                # 스팩·우선주처럼 재무데이터 없는 종목이 가치 필터를 통과하는 것을 막는다.
                return np.zeros(data_len, dtype=bool)
            return compare_vec(curr, p.get('operator', '<'), val)

        elif cid == 'price_limit_exit':
            c = get_col('close')
            if c is None:
                return result
            sl, tp = p.get('stopLoss'), p.get('takeProfit')
            sl_mode = p.get('stopLossMode', 'pct')
            tp_mode = p.get('takeProfitMode', 'pct')
            res = np.zeros(data_len, dtype=bool)
            with np.errstate(invalid='ignore'):
                if sl_mode == 'krw' and sl is not None:
                    res |= c <= float(sl)
                if tp_mode == 'krw' and tp is not None:
                    res |= c >= float(tp)
            return res

        elif cid in ['ai_model', 'ai_drop_model']:
            # 횡단면 랭킹 청산(exitMode='rank')은 종목 간 비교가 필요해 엔진에서 일괄 처리.
            # 압축된 하락점수에 절대 임계값을 쓰지 않고 유니버스 상위 X%를 청산하는 모드.
            if cid == 'ai_drop_model' and p.get('exitMode') == 'rank':
                return result  # all False — backtest_engine이 drop_df 횡단면으로 주입
            target_type = p.get('targetType')
            if cid == 'ai_drop_model' and not target_type:
                target_type = 'down'
            elif not target_type:
                target_type = 'up'
            score_col = 'ai_drop_score' if target_type == 'down' else 'ai_score'
            score = get_col(score_col)
            if score is None:
                return result
            sig_type = p.get('signalType', 'sell' if target_type == 'down' else 'buy')
            # 프론트엔드는 'threshold', 구형 DSL은 'minProbability' 키 사용.
            # 둘 다 없으면 모델 meta의 보정 임계값으로 폴백(하드코딩 70 → 발화 0건 회피)
            threshold = _ai_threshold(p, target_type)
            with np.errstate(invalid='ignore'):
                if target_type == 'up':
                    return score >= threshold if sig_type == 'buy' else score <= threshold
                else:
                    return score <= threshold if sig_type == 'buy' else score >= threshold

        elif cid in ['max_holding_days', 'trailing_stop']:
            # 시뮬레이터에서 처리 — 신호 간섭 방지를 위해 항상 False
            return result

        return result

    # ──────────────────────────────────────────────────────────────────────────
    # 아래 메서드들은 기존 테스트 호환성을 위해 행별(row-by-row) 방식 유지
    # ──────────────────────────────────────────────────────────────────────────
    def evaluate_group(self, group: Dict[str, Any], idx: int, df: pl.DataFrame) -> Tuple[bool, Optional[str]]:
        if not group.get('conditions'):
            return False, None

        logic = str(group.get('logic', 'OR')).upper()
        filters = [c for c in group['conditions'] if c.get('type') == 'filter']
        signals = [c for c in group['conditions'] if c.get('type') != 'filter']

        if not signals and filters:
            sig_res = True
        else:
            sig_res = True if logic == 'AND' else False
        sig_segs: List[List[Dict[str, Any]]] = []

        for cond in signals:
            res = self.evaluate_condition(cond, idx, df)
            if logic == 'AND':
                if not res:
                    sig_res = False
                elif sig_res:
                    segs = self.get_condition_segments(cond, measured=self._measured_at(cond, df, idx))
                    if segs:
                        sig_segs.append(segs)
            else:
                if res:
                    sig_res = True
                    segs = self.get_condition_segments(cond, measured=self._measured_at(cond, df, idx))
                    if segs:
                        sig_segs.append(segs)

        fil_res = True
        fil_segs: List[List[Dict[str, Any]]] = []

        for cond in filters:
            res = self.evaluate_condition(cond, idx, df)
            if not res:
                fil_res = False
                fil_segs = []
                break
            else:
                segs = self.get_condition_segments(cond, measured=self._measured_at(cond, df, idx))
                if segs:
                    fil_segs.append(segs)

        final_res = sig_res and fil_res

        if final_res:
            sig_part = tr.join(sig_segs, [tr.SEP_AND] if logic == 'AND' else tr.or_separator())
            fil_part = tr.join(fil_segs, [tr.SEP_AND])
            if sig_part and fil_part:
                final_segs = [tr.PAREN_OPEN] + sig_part + [tr.PAREN_CLOSE, tr.SEP_AND] + fil_part
            else:
                final_segs = sig_part or fil_part
            return True, tr.encode(final_segs) if final_segs else None

        return False, None

    def evaluate_condition(self, cond: Dict[str, Any], idx: int, df: pl.DataFrame) -> bool:
        cid, p = cond['id'], cond['params']

        def safe_get(col, i):
            try:
                val = df[col][i]
                return float(val) if val is not None else None
            except Exception:
                return None

        def compare(val1, op, val2):
            if val1 is None or val2 is None:
                return False
            try:
                if op == '>':  return val1 > val2
                if op == '<':  return val1 < val2
                if op == '>=': return val1 >= val2
                if op == '<=': return val1 <= val2
                if op == '==': return val1 == val2
            except Exception:
                return False
            return False

        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long_ = p.get('longMA', p.get('long_period', p.get('long', 20)))
            s = safe_get(f'close_{short}_sma', idx)
            l = safe_get(f'close_{long_}_sma', idx)
            # 지속 상태(mode) — 벡터화 경로와 동일 의미. 교차가 아니라 매 봉에서 참인
            # 게이트라 idx==0에서도 판정할 수 있다.
            mode = p.get('mode')
            if mode in ('above', 'below'):
                if s is None or l is None:
                    return False
                return s >= l if mode == 'above' else s <= l
            if idx == 0 or s is None or l is None:
                return False
            ps = safe_get(f'close_{short}_sma', idx - 1)
            pl_val = safe_get(f'close_{long_}_sma', idx - 1)
            if ps is None or pl_val is None:
                return False
            return (ps >= pl_val and s < l) if p.get('signalType') == 'sell' else (ps <= pl_val and s > l)

        elif cid == 'rsi':
            period = p.get('period', p.get('rsi_period', 14))
            r = safe_get(f'rsi_{period}', idx)
            val, op = p.get('value', 30), p.get('operator', '<')
            if p.get('mode') == 'rebound':
                # 임계선 재돌파 반등: 직전 봉과 비교해 매수=상향 돌파, 매도=하향 돌파.
                if idx == 0 or r is None:
                    return False
                pr = safe_get(f'rsi_{period}', idx - 1)
                if pr is None:
                    return False
                return (pr >= val and r < val) if p.get('signalType') == 'sell' else (pr <= val and r > val)
            return compare(r, op, val)

        elif cid == 'ema':
            # Fix 3: EMA 행별 평가자
            short_p = p.get('shortPeriod', p.get('short'))
            long_p = p.get('longPeriod', p.get('long'))
            if short_p is not None and long_p is not None:
                fast = safe_get(f'close_{int(short_p)}_ema', idx)
                slow = safe_get(f'close_{int(long_p)}_ema', idx)
                # 두 EMA의 지속 상태(정배열/역배열) — 벡터화 경로와 동일 의미. 교차가 아니라
                # 매 봉에서 참인 게이트라 idx==0에서도 판정할 수 있다.
                mode = p.get('mode')
                if mode in ('above', 'below'):
                    if fast is None or slow is None:
                        return False
                    return fast >= slow if mode == 'above' else fast <= slow
                if idx == 0 or fast is None or slow is None:
                    return False
                p_fast = safe_get(f'close_{int(short_p)}_ema', idx - 1)
                p_slow = safe_get(f'close_{int(long_p)}_ema', idx - 1)
                if p_fast is None or p_slow is None:
                    return False
                return (p_fast >= p_slow and fast < slow) if p.get('signalType') == 'sell' else (p_fast <= p_slow and fast > slow)
            period = p.get('period', 20)
            ema_val = safe_get(f'close_{period}_ema', idx)
            c = safe_get('close', idx)
            if ema_val is None or c is None:
                return False
            # 추세 필터(지속 상태) — 벡터화 경로(_eval_vec)와 동일 의미. 크로스오버 아님.
            mode = p.get('mode')
            if mode in ('above', 'below'):
                return c >= ema_val if mode == 'above' else c <= ema_val
            if idx == 0:
                return False
            p_ema = safe_get(f'close_{period}_ema', idx - 1)
            p_close = safe_get('close', idx - 1)
            if p_ema is None or p_close is None:
                return False
            if p.get('signalType') == 'sell':
                return p_close >= p_ema and c < ema_val
            else:
                return p_close <= p_ema and c > ema_val

        elif cid == 'macd':
            # Fix 3: MACD 행별 평가자 (기간 파라미터화 지원)
            macd_col, macds_col = macd_columns(p)
            macd = safe_get(macd_col, idx)
            macds = safe_get(macds_col, idx)
            sig_type = p.get('signalType', 'buy')
            mode = p.get('mode', 'crossover')
            if mode == 'zero':
                return compare(macd, '>' if sig_type != 'sell' else '<', 0.0)
            else:
                if idx == 0 or macd is None or macds is None:
                    return False
                p_macd = safe_get(macd_col, idx - 1)
                p_macds = safe_get(macds_col, idx - 1)
                if p_macd is None or p_macds is None:
                    return False
                return (p_macd >= p_macds and macd < macds) if sig_type == 'sell' else (p_macd <= p_macds and macd > macds)

        elif cid == 'stochastic':
            # Fix 3: Stochastic 행별 평가자 (기간 파라미터화 지원)
            k_col, d_col = stochastic_columns(p)
            k = safe_get(k_col, idx)
            d = safe_get(d_col, idx)
            sig_type = p.get('signalType', 'buy')
            mode = p.get('mode', 'crossover')
            if mode == 'level':
                default_val = 20.0 if sig_type != 'sell' else 80.0
                default_op = '<' if sig_type != 'sell' else '>'
                return compare(k, p.get('operator', default_op), float(p.get('value', default_val)))
            else:
                if idx == 0 or k is None or d is None:
                    return False
                pk = safe_get(k_col, idx - 1)
                pd_ = safe_get(d_col, idx - 1)
                if pk is None or pd_ is None:
                    return False
                return (pk >= pd_ and k < d) if sig_type == 'sell' else (pk <= pd_ and k > d)

        elif cid == 'cci':
            # Fix 3: CCI 행별 평가자
            period = p.get('period', 14)
            cci_val = safe_get(f'cci_{period}', idx)
            sig_type = p.get('signalType', 'buy')
            default_val = -100.0 if sig_type != 'sell' else 100.0
            default_op = '<' if sig_type != 'sell' else '>'
            return compare(cci_val, p.get('operator', default_op), float(p.get('value', default_val)))

        elif cid == 'adx':
            # Fix 3: ADX 행별 평가자
            adx_val = safe_get('adx', idx)
            return compare(adx_val, p.get('operator', '>='), float(p.get('value', 25)))

        elif cid == 'williams_r':
            period = p.get('period', 14)
            wr_val = safe_get(f'wr_{period}', idx)
            sig_type = p.get('signalType', 'buy')
            default_val = -80.0 if sig_type != 'sell' else -20.0
            default_op = '<=' if sig_type != 'sell' else '>='
            return compare(wr_val, p.get('operator', default_op), float(p.get('value', default_val)))

        elif cid == 'mfi':
            period = p.get('period', 14)
            mfi_val = safe_get(f'mfi_{period}', idx)
            sig_type = p.get('signalType', 'buy')
            default_val = 20.0 if sig_type != 'sell' else 80.0
            default_op = '<=' if sig_type != 'sell' else '>='
            return compare(mfi_val, p.get('operator', default_op), float(p.get('value', default_val)))

        elif cid == 'roc':
            period = p.get('period', 12)
            roc_val = safe_get(f'close_{period}_roc', idx)
            sig_type = p.get('signalType', 'buy')
            default_op = '>' if sig_type != 'sell' else '<'
            return compare(roc_val, p.get('operator', default_op), float(p.get('value', 0)))

        elif cid == 'relative_return':
            period = p.get('period', 60)
            rr_val = safe_get(f'relative_return_{period}', idx)
            sig_type = p.get('signalType', 'buy')
            default_op = '>' if sig_type != 'sell' else '<'
            return compare(rr_val, p.get('operator', default_op), float(p.get('value', 0)))

        elif cid == 'volatility':
            period = p.get('period', 60)
            vol_val = safe_get(f'volatility_{period}', idx)
            sig_type = p.get('signalType', 'buy')
            default_op = '<=' if sig_type != 'sell' else '>='
            return compare(vol_val, p.get('operator', default_op), float(p.get('value', 30)))

        elif cid in ['price_level', 'price']:
            c = safe_get('close', idx)
            val, op = p.get('value', 0), p.get('operator', '>')
            return compare(c, op, val)

        elif cid == 'bollinger_bands':
            ub_col, lb_col = bollinger_columns(p)
            c, ub, lb = safe_get('close', idx), safe_get(ub_col, idx), safe_get(lb_col, idx)
            return compare(c, '>=', ub) if p.get('signalType') == 'sell' else compare(c, '<=', lb)

        elif cid == 'volume_spike':
            period = p.get('period', 20)
            obv, obv_sma = safe_get('obv', idx), safe_get(f'obv_{period}_sma', idx)
            if idx == 0 or obv is None or obv_sma is None:
                return False
            p_obv, p_obv_sma = safe_get('obv', idx - 1), safe_get(f'obv_{period}_sma', idx - 1)
            if p_obv is None or p_obv_sma is None:
                return False
            return (p_obv >= p_obv_sma and obv < obv_sma) if p.get('signalType') == 'sell' else (p_obv <= p_obv_sma and obv > obv_sma)

        elif cid == 'volume_ratio':
            period = p.get('period', 20)
            vol, prev_sma = safe_get('volume', idx), safe_get(f'volume_{period}_prev_sma', idx)
            if vol is None or prev_sma is None or not prev_sma > 0:
                return False
            return compare(vol / prev_sma, p.get('operator', '>='), float(p.get('value', 2)))

        elif cid == 'trading_value_ratio':
            period = p.get('period', 20)
            c, v = safe_get('close', idx), safe_get('volume', idx)
            prev_sma = safe_get(f'trading_value_{period}_prev_sma', idx)
            if c is None or v is None or prev_sma is None or not prev_sma > 0:
                return False
            return compare(c * v / prev_sma, p.get('operator', '>='), float(p.get('value', 1)))

        elif cid == 'breakout':
            period = p.get('lookbackPeriod', 20)
            current_high = safe_get('high', idx)
            current_low = safe_get('low', idx)
            if idx < period or current_high is None or current_low is None:
                return False
            if p.get('signalType') == 'sell':
                prev_min = safe_get(f'low_{period}_min', idx - 1)
                return compare(current_low, '<', prev_min)
            else:
                prev_max = safe_get(f'high_{period}_max', idx - 1)
                return compare(current_high, '>', prev_max)

        elif cid == 'trading_value':
            val, op = float(p.get('value', 0)) * 100_000_000, p.get('operator', '>=')
            curr_val = safe_get(trading_value_sma_col(p.get('period')), idx)
            if curr_val is None:
                c, v = safe_get('close', idx), safe_get('volume', idx)
                if c and v:
                    curr_val = c * v
            return compare(curr_val, op, val)

        elif cid in FUNDAMENTAL_CIDS:
            val, op = float(p.get('value') or 0), p.get('operator', '<')
            curr = safe_get(cid, idx)
            if curr is None:
                # 명시적 재무 필터인데 데이터가 없으면 검증 불가 → 제외(fail-closed).
                return False
            return compare(curr, op, val)

        elif cid == 'price_limit_exit':
            c = safe_get('close', idx)
            if c is None:
                return False
            sl, tp = p.get('stopLoss'), p.get('takeProfit')
            sl_mode, tp_mode = p.get('stopLossMode', 'pct'), p.get('takeProfitMode', 'pct')
            if sl_mode == 'krw' and sl is not None:
                if c <= float(sl):
                    return True
            if tp_mode == 'krw' and tp is not None:
                if c >= float(tp):
                    return True
            return False

        elif cid in ['ai_model', 'ai_drop_model']:
            # 횡단면 랭킹 청산은 엔진에서 일괄 처리 — 행별 평가에선 항상 False
            if cid == 'ai_drop_model' and p.get('exitMode') == 'rank':
                return False
            target_type = p.get('targetType')
            if cid == 'ai_drop_model' and not target_type:
                target_type = 'down'
            elif not target_type:
                target_type = 'up'
            score_col = 'ai_drop_score' if target_type == 'down' else 'ai_score'
            score = safe_get(score_col, idx)
            if score is None:
                return False
            sig_type = p.get('signalType', 'sell' if target_type == 'down' else 'buy')
            threshold = _ai_threshold(p, target_type)
            if target_type == 'up':
                return score >= threshold if sig_type == 'buy' else score <= threshold
            else:
                return score <= threshold if sig_type == 'buy' else score >= threshold

        elif cid in ['max_holding_days', 'trailing_stop']:
            return False

        return False

    def get_condition_description(self, cond: Dict[str, Any]) -> str:
        """조건의 한국어 서술. 표시용 구조화 표현은 get_condition_segments가 정본이다."""
        return tr.render_kr(self.get_condition_segments(cond))

    @staticmethod
    def _measured_column(cond: Dict[str, Any]) -> Optional[str]:
        """사유에 그 봉의 실측값을 싣는 조건의 지표 열 이름. 정적 서술이면 None.

        시장 대비 초과수익률은 기준값("0%p 이상")만 보여주면 얼마나 앞섰는지 읽을 수
        없어 실측값을 함께 싣는다(2026-09-13).
        """
        if cond.get('id') == 'relative_return':
            return f"relative_return_{cond.get('params', {}).get('period', 60)}"
        return None

    def _measured_array(self, cond: Dict[str, Any], df: pl.DataFrame) -> Optional[np.ndarray]:
        col = self._measured_column(cond)
        if col is None:
            return None
        try:
            return df[col].to_numpy().astype(float)
        except Exception:
            return None

    def _measured_at(self, cond: Dict[str, Any], df: pl.DataFrame, idx: int) -> Optional[float]:
        col = self._measured_column(cond)
        if col is None:
            return None
        try:
            val = df[col][idx]
            return float(val) if val is not None else None
        except Exception:
            return None

    def get_condition_segments(
        self, cond: Dict[str, Any], measured: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """조건 서술의 구조화 표현(한국어 정본 템플릿 + 인자).

        표시 번역은 프론트 t() 소관이라 완성 문장 대신 템플릿과 인자를 싣는다
        (engine/trade_reason.py 참고). `measured`는 그 봉의 실측 지표값 —
        `_measured_column`이 열을 정한 조건만 받으며, 없으면 정적 서술이다.
        """
        cid, p = cond['id'], cond['params']
        op = p.get('operator', '')
        op_seg = {
            "<": tr.part(tr.OP_LT), ">": tr.part(tr.OP_GT),
            "<=": tr.part(tr.OP_LTE), ">=": tr.part(tr.OP_GTE),
            "==": tr.part(tr.OP_EQ),
        }.get(op, tr.literal(op))

        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long_ = p.get('longMA', p.get('long_period', p.get('long', 20)))
            mode = p.get('mode')
            if mode in ('above', 'below'):
                above = mode == 'above'
                if short == 1:
                    # short=1은 close_1_sma=종가 — '1일선'이라고 쓰면 읽는 사람이 없다.
                    return [tr.part(tr.MA_PRICE_STAY_ABOVE if above else tr.MA_PRICE_STAY_BELOW,
                                    long_)]
                return [tr.part(tr.MA_STAY_ABOVE if above else tr.MA_STAY_BELOW, short, long_)]
            sell = p.get('signalType') == 'sell'
            if short == 1:
                return [tr.part(tr.MA_PRICE_CROSS_DOWN if sell else tr.MA_PRICE_CROSS_UP, long_)]
            return [tr.part(tr.MA_DEAD_CROSS if sell else tr.MA_GOLDEN_CROSS, short, long_)]
        elif cid == 'rsi':
            val = p.get('value', 30)
            if p.get('mode') == 'rebound':
                sell = p.get('signalType') == 'sell'
                return [tr.part(tr.RSI_REBOUND_DOWN if sell else tr.RSI_REBOUND_UP, val)]
            return [tr.part(tr.RSI_LEVEL, val, op_seg)]
        elif cid == 'ema':
            short_p = p.get('shortPeriod', p.get('short'))
            long_p = p.get('longPeriod', p.get('long'))
            if short_p and long_p:
                if p.get('mode') in ('above', 'below'):
                    above = p.get('mode') == 'above'
                    return [tr.part(tr.EMA_STAY_ABOVE if above else tr.EMA_STAY_BELOW, short_p, long_p)]
                sell = p.get('signalType') == 'sell'
                return [tr.part(tr.EMA_DEAD_CROSS if sell else tr.EMA_GOLDEN_CROSS, short_p, long_p)]
            period = p.get('period', 20)
            if p.get('mode') in ('above', 'below'):
                above = p.get('mode') == 'above'
                return [tr.part(tr.EMA_PRICE_STAY_ABOVE if above else tr.EMA_PRICE_STAY_BELOW,
                                period)]
            sell = p.get('signalType') == 'sell'
            return [tr.part(tr.EMA_PRICE_CROSS_DOWN if sell else tr.EMA_PRICE_CROSS_UP, period)]
        elif cid == 'macd':
            mode = p.get('mode', 'crossover')
            sell = p.get('signalType', 'buy') == 'sell'
            if mode == 'zero':
                return [tr.part(tr.MACD_ZERO_DOWN if sell else tr.MACD_ZERO_UP)]
            return [tr.part(tr.MACD_DEAD_CROSS if sell else tr.MACD_GOLDEN_CROSS)]
        elif cid == 'stochastic':
            mode = p.get('mode', 'crossover')
            sig_type = p.get('signalType', 'buy')
            if mode == 'level':
                val = p.get('value', 20 if sig_type != 'sell' else 80)
                return [tr.part(tr.STOCHASTIC_LEVEL, val, op_seg)]
            sell = sig_type == 'sell'
            return [tr.part(tr.STOCHASTIC_DEAD_CROSS if sell else tr.STOCHASTIC_GOLDEN_CROSS)]
        elif cid == 'cci':
            period = p.get('period', 14)
            val = p.get('value', -100 if p.get('signalType') != 'sell' else 100)
            return [tr.part(tr.CCI_LEVEL, period, val, op_seg)]
        elif cid == 'adx':
            val = p.get('value', 25)
            return [tr.part(tr.ADX_LEVEL, val, op_seg)]
        elif cid == 'williams_r':
            period = p.get('period', 14)
            sig_type = p.get('signalType', 'buy')
            val = p.get('value', -80 if sig_type != 'sell' else -20)
            return [tr.part(tr.WILLIAMS_R_LEVEL, period, val, op_seg)]
        elif cid == 'mfi':
            period = p.get('period', 14)
            sig_type = p.get('signalType', 'buy')
            val = p.get('value', 20 if sig_type != 'sell' else 80)
            return [tr.part(tr.MFI_LEVEL, period, val, op_seg)]
        elif cid == 'roc':
            period = p.get('period', 12)
            val = p.get('value', 0)
            return [tr.part(tr.ROC_LEVEL, period, val, op_seg)]
        elif cid == 'relative_return':
            period = p.get('period', 60)
            sig_type = p.get('signalType', 'buy')
            val = p.get('value', 0)
            # 기본 연산자는 평가 경로와 같다(매수 '>' / 매도 '<').
            rr_op_seg = op_seg if op else tr.part(tr.OP_GT if sig_type != 'sell' else tr.OP_LT)
            if measured is not None and np.isfinite(measured):
                return [tr.part(tr.RELATIVE_RETURN_MEASURED, period, f"{measured:+.1f}")]
            return [tr.part(tr.RELATIVE_RETURN_LEVEL, period, val, rr_op_seg)]
        elif cid == 'volatility':
            period = p.get('period', 60)
            sig_type = p.get('signalType', 'buy')
            val = p.get('value', 30)
            vol_op_seg = op_seg if op else tr.part(tr.OP_LTE if sig_type != 'sell' else tr.OP_GTE)
            return [tr.part(tr.VOLATILITY_LEVEL, period, val, vol_op_seg)]
        elif cid in ['price', 'price_level']:
            val = float(p.get('value') or 0)
            return [tr.part(tr.PRICE_LEVEL, val, op_seg, money=[0])]
        elif cid == 'bollinger_bands':
            sell = p.get('signalType') == 'sell'
            return [tr.part(tr.BOLLINGER_UPPER if sell else tr.BOLLINGER_LOWER)]
        elif cid == 'trading_value':
            val = p.get('value', 100)
            return [tr.part(tr.TRADING_VALUE, val)]
        elif cid == 'volume_spike':
            sell = p.get('signalType') == 'sell'
            return [tr.part(tr.VOLUME_OBV_DEAD_CROSS if sell else tr.VOLUME_OBV_GOLDEN_CROSS)]
        elif cid == 'volume_ratio':
            period = p.get('period', 20)
            val = p.get('value', 2)
            vr_op_seg = op_seg if op else tr.part(tr.OP_GTE)
            return [tr.part(tr.VOLUME_RATIO, period, f"{float(val):g}", vr_op_seg)]
        elif cid == 'trading_value_ratio':
            period = p.get('period', 20)
            val = p.get('value', 1)
            tvr_op_seg = op_seg if op else tr.part(tr.OP_GTE)
            return [tr.part(tr.TRADING_VALUE_RATIO, period, f"{float(val):g}", tvr_op_seg)]
        elif cid == 'breakout':
            period = p.get('lookbackPeriod', 20)
            sell = p.get('signalType') == 'sell'
            return [tr.part(tr.BREAKOUT_LOW if sell else tr.BREAKOUT_HIGH, period)]
        elif cid in ['ai_model', 'ai_drop_model']:
            target_type = p.get('targetType')
            if cid == 'ai_drop_model' and not target_type:
                target_type = 'down'
            elif not target_type:
                target_type = 'up'
            sig_type = p.get('signalType', 'sell' if target_type == 'down' else 'buy')
            threshold = p.get('minProbability', 70)
            suffix = "%" if isinstance(threshold, (int, float)) and threshold > 1 else ""
            prob = f"{threshold}{suffix}"
            if target_type == 'up':
                target = p.get('targetThreshold', p.get('buyThreshold', 7))
                template = tr.AI_UP_SELL if sig_type == 'sell' else tr.AI_UP_BUY
            else:
                target = p.get('targetThreshold', p.get('sellThreshold', 7))
                template = tr.AI_DOWN_BUY if sig_type == 'buy' else tr.AI_DOWN_SELL
            return [tr.part(template, target, prob)]
        elif cid == 'price_limit_exit':
            sl, tp = p.get('stopLoss'), p.get('takeProfit')
            sl_m, tp_m = p.get('stopLossMode', 'pct'), p.get('takeProfitMode', 'pct')
            limits: List[List[Dict[str, Any]]] = []
            if sl is not None:
                limits.append([tr.part(tr.PRICE_LIMIT_BELOW, sl, money=[0])] if sl_m == 'krw'
                              else [tr.part(tr.PRICE_LIMIT_BELOW, f"{sl:,.0f}%")])
            if tp is not None:
                limits.append([tr.part(tr.PRICE_LIMIT_ABOVE, tp, money=[0])] if tp_m == 'krw'
                              else [tr.part(tr.PRICE_LIMIT_ABOVE, f"{tp:,.0f}%")])
            if not limits:
                return [tr.part(tr.PRICE_LIMIT_EXIT)]
            return tr.join(limits, tr.or_separator())
        elif cid == 'max_holding_days':
            days = p.get('days', 0)
            return [tr.part(tr.MAX_HOLDING_EXPIRY, days)]
        elif cid == 'trailing_stop':
            pct = p.get('pips', 0)
            return [tr.part(tr.TRAILING_STOP_COND, pct)]
        elif cid in FUNDAMENTAL_CIDS:
            label = FUNDAMENTAL_LABELS.get(cid, cid.upper())
            template = tr.FUNDAMENTAL_AMOUNT_LEVEL if cid in FUNDAMENTAL_AMOUNT_CIDS else tr.FUNDAMENTAL_LEVEL
            return [tr.part(template, tr.part(label), p.get('value'), op_seg)]

        return [tr.literal(cid)]
