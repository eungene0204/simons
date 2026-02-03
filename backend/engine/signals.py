from typing import List, Dict, Any, Tuple, Optional
import polars as pl

class SignalEngine:
    def __init__(self):
        pass

    def evaluate_group(self, group: Dict[str, Any], idx: int, df: pl.DataFrame) -> Tuple[bool, Optional[str]]:
        if not group.get('conditions'): return False, None
        
        results = []
        descriptions = []
        for cond in group['conditions']:
            res = self.evaluate_condition(cond, idx, df)
            results.append(res)
            if res: 
                desc = self.get_condition_description(cond)
                descriptions.append(desc)
        
        if group.get('logic') == 'AND':
            if all(results): return True, " + ".join(descriptions)
            return False, None
        else:
            if any(results):
                return True, " 또는 ".join(descriptions)
            return False, None

    def evaluate_condition(self, cond: Dict[str, Any], idx: int, df: pl.DataFrame) -> bool:
        cid, p = cond['id'], cond['params']
        
        def safe_get(col, i):
            try:
                val = df[col][i]
                return float(val) if val is not None else None
            except: return None

        def compare(val1, op, val2):
            if val1 is None or val2 is None: return False
            try:
                if op == '>': return val1 > val2
                if op == '<': return val1 < val2
                if op == '>=': return val1 >= val2
                if op == '<=': return val1 <= val2
                if op == '==': return val1 == val2
            except: return False
            return False

        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long = p.get('longMA', p.get('long_period', p.get('long', 20)))
            s = safe_get(f'close_{short}_sma', idx)
            l = safe_get(f'close_{long}_sma', idx)
            if idx == 0 or s is None or l is None: return False
            ps = safe_get(f'close_{short}_sma', idx-1)
            pl_val = safe_get(f'close_{long}_sma', idx-1)
            if ps is None or pl_val is None: return False
            return (ps >= pl_val and s < l) if p.get('signalType') == 'sell' else (ps <= pl_val and s > l)
            
        elif cid == 'rsi':
            period = p.get('period', p.get('rsi_period', 14))
            r = safe_get(f'rsi_{period}', idx)
            val, op = p.get('value', 30), p.get('operator', '<')
            return compare(r, op, val)
            
        elif cid == 'price_level' or cid == 'price':
            c = safe_get('close', idx)
            val, op = p.get('value', 0), p.get('operator', '>')
            return compare(c, op, val)
            
        elif cid == 'bollinger_bands':
            c, ub, lb = safe_get('close', idx), safe_get('boll_ub', idx), safe_get('boll_lb', idx)
            return compare(c, '>=', ub) if p.get('signalType') == 'sell' else compare(c, '<=', lb)
            
        elif cid == 'volume_spike':
            period = p.get('period', 20)
            obv, obv_sma = safe_get('obv', idx), safe_get(f'obv_{period}_sma', idx)
            if idx == 0 or obv is None or obv_sma is None: return False
            p_obv, p_obv_sma = safe_get('obv', idx-1), safe_get(f'obv_{period}_sma', idx-1)
            if p_obv is None or p_obv_sma is None: return False
            return (p_obv >= p_obv_sma and obv < obv_sma) if p.get('signalType') == 'sell' else (p_obv <= p_obv_sma and obv > obv_sma)
            
        elif cid == 'breakout':
            period = p.get('lookbackPeriod', 20)
            c = safe_get('close', idx)
            if idx < period or c is None: return False
            if p.get('signalType') == 'sell':
                prev_min = safe_get(f'close_{period}_min', idx-1)
                return compare(c, '<', prev_min)
            else:
                prev_max = safe_get(f'close_{period}_max', idx-1)
                return compare(c, '>', prev_max)
                
        elif cid == 'trading_value':
            val, op = float(p.get('value', 0)) * 100_000_000, p.get('operator', '>=')
            curr_val = safe_get('trading_value_20_sma', idx)
            if curr_val is None:
                # Fallback to current bar trading value
                c, v = safe_get('close', idx), safe_get('volume', idx)
                if c and v: curr_val = c * v
            return compare(curr_val, op, val)
            
        elif cid in ['per', 'pbr', 'roe_or_gpa', 'debt_ratio', 'market_cap']:
            val, op = float(p.get('value') or 0), p.get('operator', '<')
            curr = safe_get(cid, idx)
            return compare(curr, op, val)

        elif cid == 'price_limit_exit':
            c = safe_get('close', idx)
            if c is None: return False
            sl, tp = p.get('stopLoss'), p.get('takeProfit')
            sl_mode, tp_mode = p.get('stopLossMode', 'pct'), p.get('takeProfitMode', 'pct')
            
            # We only handle fixed price (krw) mode here as signals.
            # Percentage mode is handled by vbt's risk_params.
            if sl_mode == 'krw' and sl is not None:
                if c <= float(sl): return True
            if tp_mode == 'krw' and tp is not None:
                if c >= float(tp): return True
            return False

        elif cid == 'max_holding_days' or cid == 'trailing_stop':
            # Pure risk blocks handled by simulator, return False to avoid signal interference
            return False

        return False

    def get_condition_description(self, cond: Dict[str, Any]) -> str:
        cid, p = cond['id'], cond['params']
        op = p.get('operator', '')
        op_kr = {"<": "이하", ">": "이상", "<=": "이하", ">=": "이상", "==": "동일"}.get(op, op)
        
        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long = p.get('longMA', p.get('long_period', p.get('long', 20)))
            return f"{short}일선-{long}일선 골든크로스" if p.get('signalType') != 'sell' else f"{short}일선-{long}일선 데드크로스"
        elif cid == 'rsi':
            val = p.get('value', 30)
            return f"RSI {val} {op_kr}"
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
            labels = {"per": "PER", "pbr": "PBR", "roe_or_gpa": "ROE/GPA", "debt_ratio": "부채비율", "market_cap": "시가총액"}
            label = labels.get(cid, cid.upper())
            suffix = "억" if cid == 'market_cap' else ""
            return f"{label} {p.get('value')}{suffix} {op_kr}"
        
        return cid
