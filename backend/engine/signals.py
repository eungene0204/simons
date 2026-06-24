from typing import List, Dict, Any, Tuple, Optional
import os
import json
import functools
import polars as pl
import numpy as np


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

        # Fix 4: 이유 문자열은 True인 행에 대해서만 생성 (희소 접근으로 오버헤드 최소화)
        reasons: List[Optional[str]] = [None] * data_len
        true_indices = np.where(final)[0]
        if len(true_indices) > 0:
            sig_descs = [self.get_condition_description(c) for c in signals]
            fil_descs = [self.get_condition_description(c) for c in filters]
            for i in true_indices:
                active_sig = [d for d, arr in zip(sig_descs, sig_arrays) if arr[i] and d]
                active_fil = [d for d, arr in zip(fil_descs, fil_arrays) if arr[i] and d]
                sig_joiner = " + " if logic == 'AND' else " 또는 "
                sig_part = sig_joiner.join(active_sig)
                fil_part = " + ".join(active_fil)
                if sig_part and fil_part:
                    reasons[i] = f"({sig_part}) + {fil_part}"
                else:
                    reasons[i] = sig_part or fil_part or None

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
                direction = 'dead' if p.get('signalType') == 'sell' else 'golden'
                return crossover(fast, slow, direction)
            period = p.get('period', 20)
            ema_arr = get_col(f'close_{period}_ema')
            close = get_col('close')
            if ema_arr is None or close is None:
                return result
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
            # Fix 3: MACD 평가자 — 크로스오버 또는 제로선 돌파
            macd = get_col('macd')
            macds = get_col('macds')  # signal line
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
            # Fix 3: Stochastic 평가자 — K/D 크로스오버 또는 과매수/과매도 레벨
            k = get_col('kdjk')
            d = get_col('kdjd')
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

        elif cid in ['price_level', 'price']:
            c = get_col('close')
            return compare_vec(c, p.get('operator', '>'), float(p.get('value', 0)))

        elif cid == 'bollinger_bands':
            c = get_col('close')
            if c is None:
                return result
            if p.get('signalType') == 'sell':
                ub = get_col('boll_ub')
                if ub is None:
                    return result
                with np.errstate(invalid='ignore'):
                    return c >= ub
            else:
                lb = get_col('boll_lb')
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
            curr_val = get_col('trading_value_20_sma')
            if curr_val is None:
                c = get_col('close')
                v = get_col('volume')
                if c is not None and v is not None:
                    curr_val = c * v
            return compare_vec(curr_val, p.get('operator', '>='), val)

        elif cid in ['per', 'pbr', 'roe_or_gpa', 'debt_ratio', 'market_cap']:
            val = float(p.get('value') or 0)
            curr = get_col(cid)
            if curr is None:
                # 재무 데이터 컬럼이 없으면 필터 통과로 처리 (데이터 누락)
                return np.ones(data_len, dtype=bool)
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
        sig_desc = None

        for cond in signals:
            res = self.evaluate_condition(cond, idx, df)
            if logic == 'AND':
                if not res:
                    sig_res = False
                elif sig_res:
                    desc = self.get_condition_description(cond)
                    if desc:
                        sig_desc = f"{sig_desc} + {desc}" if sig_desc else desc
            else:
                if res:
                    sig_res = True
                    desc = self.get_condition_description(cond)
                    if desc:
                        sig_desc = f"{sig_desc} 또는 {desc}" if sig_desc else desc

        fil_res = True
        fil_desc = None

        for cond in filters:
            res = self.evaluate_condition(cond, idx, df)
            if not res:
                fil_res = False
                fil_desc = None
                break
            else:
                desc = self.get_condition_description(cond)
                if desc:
                    fil_desc = f"{fil_desc} + {desc}" if fil_desc else desc

        final_res = sig_res and fil_res

        if final_res:
            if sig_desc and fil_desc:
                final_desc = f"({sig_desc}) + {fil_desc}"
            else:
                final_desc = sig_desc or fil_desc
            return True, str(final_desc) if final_desc else None

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
            if idx == 0 or ema_val is None or c is None:
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
            # Fix 3: MACD 행별 평가자
            macd = safe_get('macd', idx)
            macds = safe_get('macds', idx)
            sig_type = p.get('signalType', 'buy')
            mode = p.get('mode', 'crossover')
            if mode == 'zero':
                return compare(macd, '>' if sig_type != 'sell' else '<', 0.0)
            else:
                if idx == 0 or macd is None or macds is None:
                    return False
                p_macd = safe_get('macd', idx - 1)
                p_macds = safe_get('macds', idx - 1)
                if p_macd is None or p_macds is None:
                    return False
                return (p_macd >= p_macds and macd < macds) if sig_type == 'sell' else (p_macd <= p_macds and macd > macds)

        elif cid == 'stochastic':
            # Fix 3: Stochastic 행별 평가자
            k = safe_get('kdjk', idx)
            d = safe_get('kdjd', idx)
            sig_type = p.get('signalType', 'buy')
            mode = p.get('mode', 'crossover')
            if mode == 'level':
                default_val = 20.0 if sig_type != 'sell' else 80.0
                default_op = '<' if sig_type != 'sell' else '>'
                return compare(k, p.get('operator', default_op), float(p.get('value', default_val)))
            else:
                if idx == 0 or k is None or d is None:
                    return False
                pk = safe_get('kdjk', idx - 1)
                pd_ = safe_get('kdjd', idx - 1)
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

        elif cid in ['price_level', 'price']:
            c = safe_get('close', idx)
            val, op = p.get('value', 0), p.get('operator', '>')
            return compare(c, op, val)

        elif cid == 'bollinger_bands':
            c, ub, lb = safe_get('close', idx), safe_get('boll_ub', idx), safe_get('boll_lb', idx)
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
            curr_val = safe_get('trading_value_20_sma', idx)
            if curr_val is None:
                c, v = safe_get('close', idx), safe_get('volume', idx)
                if c and v:
                    curr_val = c * v
            return compare(curr_val, op, val)

        elif cid in ['per', 'pbr', 'roe_or_gpa', 'debt_ratio', 'market_cap']:
            val, op = float(p.get('value') or 0), p.get('operator', '<')
            curr = safe_get(cid, idx)
            if curr is None:
                # 재무 데이터 컬럼이 없으면 필터 통과로 처리 (데이터 누락)
                return True
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
        cid, p = cond['id'], cond['params']
        op = p.get('operator', '')
        op_kr = {"<": "이하", ">": "이상", "<=": "이하", ">=": "이상", "==": "동일"}.get(op, op)

        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long_ = p.get('longMA', p.get('long_period', p.get('long', 20)))
            return f"{short}일선-{long_}일선 골든크로스" if p.get('signalType') != 'sell' else f"{short}일선-{long_}일선 데드크로스"
        elif cid == 'rsi':
            val = p.get('value', 30)
            if p.get('mode') == 'rebound':
                return f"RSI {val} 상향 돌파(과매도 반등)" if p.get('signalType') != 'sell' else f"RSI {val} 하향 돌파"
            return f"RSI {val} {op_kr}"
        elif cid == 'ema':
            short_p = p.get('shortPeriod', p.get('short'))
            long_p = p.get('longPeriod', p.get('long'))
            if short_p and long_p:
                return f"EMA{short_p}-EMA{long_p} 골든크로스" if p.get('signalType') != 'sell' else f"EMA{short_p}-EMA{long_p} 데드크로스"
            period = p.get('period', 20)
            return f"가격 EMA{period} 상향 돌파" if p.get('signalType') != 'sell' else f"가격 EMA{period} 하향 돌파"
        elif cid == 'macd':
            mode = p.get('mode', 'crossover')
            sig_type = p.get('signalType', 'buy')
            if mode == 'zero':
                return "MACD 제로선 상향 돌파" if sig_type != 'sell' else "MACD 제로선 하향 돌파"
            return "MACD 골든크로스" if sig_type != 'sell' else "MACD 데드크로스"
        elif cid == 'stochastic':
            mode = p.get('mode', 'crossover')
            sig_type = p.get('signalType', 'buy')
            if mode == 'level':
                val = p.get('value', 20 if sig_type != 'sell' else 80)
                return f"Stochastic K {val} {op_kr}"
            return "Stochastic 골든크로스" if sig_type != 'sell' else "Stochastic 데드크로스"
        elif cid == 'cci':
            period = p.get('period', 14)
            val = p.get('value', -100 if p.get('signalType') != 'sell' else 100)
            return f"CCI({period}) {val} {op_kr}"
        elif cid == 'adx':
            val = p.get('value', 25)
            return f"ADX {val} {op_kr} (추세 강도)"
        elif cid in ['price', 'price_level']:
            val = float(p.get('value') or 0)
            return f"현재가 {val:,.0f}원 {op_kr}"
        elif cid == 'bollinger_bands':
            return "볼린저 밴드 하단 돌파(매수)" if p.get('signalType') != 'sell' else "볼린저 밴드 상단 돌파(매도)"
        elif cid == 'trading_value':
            val = p.get('value', 100)
            return f"거래대금 {val}억 이상"
        elif cid == 'volume_spike':
            return "거래량 OBV 골든크로스" if p.get('signalType') != 'sell' else "거래량 OBV 데드크로스"
        elif cid == 'breakout':
            period = p.get('lookbackPeriod', 20)
            return f"{period}일 신고가 돌파" if p.get('signalType') != 'sell' else f"{period}일 신저가 돌파"
        elif cid in ['ai_model', 'ai_drop_model']:
            target_type = p.get('targetType')
            if cid == 'ai_drop_model' and not target_type:
                target_type = 'down'
            elif not target_type:
                target_type = 'up'
            sig_type = p.get('signalType', 'sell' if target_type == 'down' else 'buy')
            threshold = p.get('minProbability', 70)
            suffix = "%" if isinstance(threshold, (int, float)) and threshold > 1 else ""
            if target_type == 'up':
                target = p.get('targetThreshold', p.get('buyThreshold', 7))
                direction = f"{target}% 상승"
                return f"AI {direction} 확률 {threshold}{suffix} 이하 (매도)" if sig_type == 'sell' else f"AI {direction} 확률 {threshold}{suffix} 이상 (매수)"
            else:
                target = p.get('targetThreshold', p.get('sellThreshold', 7))
                direction = f"{target}% 하락"
                label = "이하 (안전 진입)" if sig_type == 'buy' else "이상 (위험 청산)"
                return f"AI {direction} 확률 {threshold}{suffix} {label}"
        elif cid == 'price_limit_exit':
            sl, tp = p.get('stopLoss'), p.get('takeProfit')
            sl_m, tp_m = p.get('stopLossMode', 'pct'), p.get('takeProfitMode', 'pct')
            reasons = []
            if sl is not None:
                unit = "원" if sl_m == 'krw' else "%"
                reasons.append(f"현재가 {sl:,.0f}{unit} 이하")
            if tp is not None:
                unit = "원" if tp_m == 'krw' else "%"
                reasons.append(f"현재가 {tp:,.0f}{unit} 이상")
            return " 또는 ".join(reasons) if reasons else "가격 제한 청산"
        elif cid == 'max_holding_days':
            days = p.get('days', 0)
            return f"최대 {days}일 보유 만료"
        elif cid == 'trailing_stop':
            pct = p.get('pips', 0)
            return f"트레일링 스탑 {pct}%"
        elif cid in ['per', 'pbr', 'roe_or_gpa', 'debt_ratio', 'market_cap']:
            labels = {"per": "PER", "pbr": "PBR", "roe_or_gpa": "ROE", "debt_ratio": "부채비율", "market_cap": "시가총액"}
            label = labels.get(cid, cid.upper())
            suffix = "억" if cid == 'market_cap' else ""
            return f"{label} {p.get('value')}{suffix} {op_kr}"

        return cid
