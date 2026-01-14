from datetime import datetime
import polars as pl
import os
import numpy as np
import pandas as pd
from stockstats import StockDataFrame
import vectorbt as vbt
from typing import Dict, List, Any, Optional, Tuple

class BacktestEngine:
    def __init__(self, data_dir: str = None):
        self.warnings = set()
        if data_dir:
            self.data_dir = data_dir
        else:
            # Robust path resolution
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_data_dir = os.path.join(base_dir, "data", "ohlcv")
            local_data_dir = "data/ohlcv"
            
            if os.path.exists(project_data_dir):
                self.data_dir = project_data_dir
            elif os.path.exists(local_data_dir):
                self.data_dir = local_data_dir
            else:
                self.data_dir = "../data/ohlcv" # Fallback
                
        print(f"BacktestEngine initialized with data_dir: {self.data_dir}")

    def load_data(self, symbol: str) -> pl.DataFrame:
        file_path = os.path.join(self.data_dir, f"{symbol}.parquet")
        if not os.path.exists(file_path):
            # Try one more fallback (absolute from home for this specific user environment)
            abs_fallback = f"/Users/eugene/nullalgo/simons/data/ohlcv/{symbol}.parquet"
            if os.path.exists(abs_fallback):
                file_path = abs_fallback
            else:
                raise FileNotFoundError(f"Data for {symbol} not found")
        return pl.read_parquet(file_path)

    def safe(self, val):
        try:
            if val is None:
                return 0.0
            if isinstance(val, (pd.Series, pd.Index, np.ndarray)):
                if len(val) == 0: return 0.0
                val = val.iloc[0] if hasattr(val, 'iloc') else val[0]
            
            # Check if it's a numeric type before calling isnan
            if isinstance(val, (int, float, np.number)):
                if np.isnan(val) or np.isinf(val):
                    return 0.0
                return float(val)
            
            # If it's a single-element array/series that didn't match above
            if hasattr(val, 'item'):
                return float(val.item())

            return 0.0
        except:
            return 0.0

    def calculate_indicators(self, df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        pdf = df_pl.to_pandas()
        
        # Preserve raw close for execution if needed
        pdf['raw_close_ref'] = pdf['close']
        
        # Log first 5 rows to see what we're working with
        print(f"[DEBUG] ENGINE: Data sample (first 5 rows):\n{pdf[['date', 'open', 'close', 'change']].head(5)}")
        
        # 1. Simple Adjusted Price Handling
        if 'adj_close' in pdf.columns:
            print("[DEBUG] ENGINE: Aligning prices to adj_close")
            factor = pdf['adj_close'] / pdf['close']
            pdf['open'] *= factor
            pdf['high'] *= factor
            pdf['low'] *= factor
            pdf['close'] = pdf['adj_close']
        else:
            self.warnings.add("데이터베이스에 수정주가(adj_close)가 존재하지 않습니다. 액면분할이 있었던 종목의 경우 백테스트 결과가 왜곡될 수 있습니다.")
        
        sdf = StockDataFrame.retype(pdf)
        
        for cond in conditions:
            cid, p = cond['id'], cond['params']
            print(f"[DEBUG] ENGINE: Pre-calculating indicators for {cid}")
            if cid == 'ma_crossover':
                short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
                long = p.get('longMA', p.get('long_period', p.get('long', 20)))
                _ = sdf[f'close_{short}_sma']
                _ = sdf[f'close_{long}_sma']
            elif cid == 'rsi':
                period = p.get('period', p.get('rsi_period', 14))
                _ = sdf[f'rsi_{period}']
            elif cid == 'macd':
                _ = sdf['macd']
                _ = sdf['macds']
            elif cid == 'bollinger_bands':
                period = p.get('period', 20)
                _ = sdf[f'close_{period}_sma']
                _ = sdf[f'boll_ub'] # Upper
                _ = sdf[f'boll_lb'] # Lower
            elif cid == 'volume_spike':
                _ = sdf['obv']
            elif cid == 'breakout':
                period = p.get('lookbackPeriod', 20)
                # Donchian channel / High/Low breakout
                pdf[f'close_{period}_max'] = pdf['close'].rolling(window=period).max()
                pdf[f'close_{period}_min'] = pdf['close'].rolling(window=period).min()
                # Re-sync to sdf if needed, but we can just use pdf for these
                sdf = StockDataFrame.retype(pdf)
        
        return pl.from_pandas(sdf.reset_index())

    def run_backtest(self, req: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.warnings = set()
            symbol = req['symbol']
            print(f"[DEBUG] ENGINE: Starting backtest for {symbol}")
            df_pl = self.load_data(symbol)
            print(f"[DEBUG] ENGINE: Data loaded. Rows: {len(df_pl)}")
            
            # 1. Adjusted Price Handling
            price_col = 'adj_close' if 'adj_close' in df_pl.columns else 'close'
            
            # 2. Generate Indicators
            all_conditions = req['entry']['conditions'] + req['exit']['conditions']
            df_pl = self.calculate_indicators(df_pl, all_conditions)
            
            # 3. Period Filtering
            period = req.get('period', 'full')
            start_date = req.get('startDate')
            end_date = req.get('endDate')
            
            if period != 'full' or start_date or end_date:
                last_date = df_pl['date'].max()
                ref_date = last_date if isinstance(last_date, datetime) else pd.to_datetime(last_date)
                    
                if start_date:
                    df_pl = df_pl.filter(pl.col("date") >= pd.to_datetime(start_date))
                elif period == '6M':
                    df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(months=6)))
                elif period == '1Y':
                    df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=1)))
                elif period == '5Y':
                    df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=5)))
                
                if end_date:
                    df_pl = df_pl.filter(pl.col("date") <= pd.to_datetime(end_date))

            data_len = len(df_pl)
            if data_len < 10:
                 print("[WARNING] ENGINE: Too little data for backtest.")

            # 4. Extract Signals
            entries = []
            exits = []
            
            risk_params = req.get('risk', {})
            init_cash = float(risk_params.get('init_cash') or 10000000.0)
            liquidity_mult = float(risk_params.get('liquidity_multiplier') or 10.0)
            pos_size_pct = float(risk_params.get('position_size_pct') or 100.0)
            target_amount = init_cash * (pos_size_pct / 100.0)
            
            vol_val = (df_pl['close'] * df_pl['volume']).to_numpy()
            liquidity_ok = np.ones(data_len, dtype=bool)
            if (liquidity_mult or 0) > 0:
                liquidity_ok = np.zeros(data_len, dtype=bool)
                for i in range(1, data_len):
                    liquidity_ok[i] = vol_val[i-1] >= (liquidity_mult * target_amount)
            
            entry_reasons = [None] * data_len
            exit_reasons = [None] * data_len
            
            for i in range(data_len):
                can_enter, entry_desc = self.evaluate_group(req['entry'], i, df_pl)
                if can_enter and not liquidity_ok[i]:
                    can_enter = False
                    entry_desc = None
                entries.append(can_enter)
                entry_reasons[i] = entry_desc
                
                can_exit, exit_desc = self.evaluate_group(req['exit'], i, df_pl)
                exits.append(can_exit)
                exit_reasons[i] = exit_desc
                
            entries_series = pd.Series(entries)
            exits_series = pd.Series(exits)
            
            print(f"[DEBUG] ENGINE: Entry signals generated: {sum(entries)}")
            print(f"[DEBUG] ENGINE: Exit signals generated: {sum(exits)}")
            
            if sum(entries) == 0:
                 self.warnings.add("선택한 기간 동안 매수 조건이 한 번도 충족되지 않았습니다 (매매 없음).")
            
            options = req.get('options', {})
            exec_type = options.get('execution_type', 'next_open') 
            fee_rate = float(options.get('fee_rate') or 0.0015)
            slippage_rate = float(options.get('slippage_rate') or 0.0020)
            
            price_col = 'close'
            open_col = 'open' if 'open' in df_pl.columns else 'close'
            price_series = df_pl[price_col].to_pandas()
            dates_list = df_pl['date'].to_list()
            dt_index = pd.to_datetime(dates_list)
            
            if exec_type == 'next_open':
                entries_exec = entries_series.shift(1).fillna(False)
                exits_exec = exits_series.shift(1).fillna(False)
                exec_prices = df_pl[open_col].to_pandas()
            else:
                entries_exec = entries_series
                exits_exec = exits_series
                exec_prices = price_series
                
            exec_prices.index = dt_index
            entries_exec.index = dt_index
            exits_exec.index = dt_index
            prices_val = price_series
            prices_val.index = dt_index
            dates = [d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d) for d in dates_list]
            
            # 7. vectorbt Execution
            risk_management = req.get('risk', {})
            sl_pct = float(risk_management.get('stop_loss_pct') or 0)
            tp_pct = float(risk_management.get('take_profit_pct') or 0)
            ts_pct = float(risk_management.get('trailing_stop_pct') or 0)
            
            # New Risk Factors
            min_cash_reserve = float(risk_management.get('min_cash_reserve_pct') or 0)
            max_daily_buy = float(risk_management.get('max_daily_buy_pct') or 100.0)
            max_mdd_limit = float(risk_management.get('max_mdd_limit_pct') or 0)

            # Adjust position size based on cash reserve and daily buy limit
            effective_pos_size = (pos_size_pct / 100.0) * (1 - min_cash_reserve / 100.0)
            effective_pos_size = min(effective_pos_size, max_daily_buy / 100.0)

            vbt_kwargs = dict(
                size=effective_pos_size,
                size_type='Percent',
                init_cash=init_cash,
                fees=fee_rate,
                slippage=slippage_rate,
                freq='D',
                sl_stop=sl_pct / 100 if sl_pct > 0 else None,
                tp_stop=tp_pct / 100 if tp_pct > 0 else None,
                sl_trail=ts_pct / 100 if ts_pct > 0 else None,
                allow_partial=False
            )

            # Initial Portfolio Calculation
            pf = vbt.Portfolio.from_signals(
                close=prices_val, price=exec_prices,
                entries=entries_exec, exits=exits_exec,
                accumulate=False, direction='longonly', cash_sharing=False,
                **vbt_kwargs
            )

            # MDD Circuit Breaker Check
            if max_mdd_limit > 0:
                # vbt drawdown is typically negative, e.g., -0.27 for 27% drawdown
                drawdowns = np.abs(pf.drawdown()) * 100
                hit_mask = drawdowns > max_mdd_limit
                if hit_mask.any():
                    # Find the first date drawdown exceeded limit
                    stop_date = hit_mask.idxmax() if hasattr(hit_mask, 'idxmax') else hit_mask.index[hit_mask.argmax()]
                    self.warnings.add(f"최대 낙폭 제한({max_mdd_limit}%) 도달로 인한 매매 중단 ({stop_date.strftime('%Y-%m-%d')})")
                    
                    # Zero out all entries after stop_date and ensure an exit occurs
                    entries_exec.loc[stop_date:] = False
                    # Force exit on stop_date to close existing positions
                    exits_exec.loc[stop_date] = True
                    # Zero out future exits (though vbt handles it, it's cleaner)
                    exits_exec.loc[stop_date + pd.Timedelta(days=1):] = False
                    
                    # Re-calculate pf to reflect the stop
                    pf = vbt.Portfolio.from_signals(
                        close=prices_val, price=exec_prices,
                        entries=entries_exec, exits=exits_exec,
                        accumulate=False, direction='longonly', cash_sharing=False,
                        **vbt_kwargs
                    )
            
            split_idx = int(data_len * 0.7)
            pf_is = vbt.Portfolio.from_signals(
                close=prices_val.iloc[:split_idx], price=exec_prices.iloc[:split_idx],
                entries=entries_exec.iloc[:split_idx], exits=exits_exec.iloc[:split_idx],
                accumulate=False, direction='longonly', cash_sharing=False,
                **vbt_kwargs
            )
            pf_oos = vbt.Portfolio.from_signals(
                close=prices_val.iloc[split_idx:], price=exec_prices.iloc[split_idx:],
                entries=entries_exec.iloc[split_idx:], exits=exits_exec.iloc[split_idx:],
                accumulate=False, direction='longonly', cash_sharing=False,
                **vbt_kwargs
            )
            
            signals_list = []
            if len(pf.trades.records) > 0:
                vbt_trades = pf.trades.records_readable
                raw_records = pf.trades.records
                
                for i, (idx, trade) in enumerate(vbt_trades.iterrows()):
                    e_idx = trade.get('Entry Index', trade.get('Entry Idx', trade.get('Entry Timestamp')))
                    x_idx = trade.get('Exit Index', trade.get('Exit Idx', trade.get('Exit Timestamp')))
                    e_price = self.safe(trade.get('Avg Entry Price', trade.get('Entry Price')))
                    x_price = self.safe(trade.get('Avg Exit Price', trade.get('Exit Price')))
                    size = self.safe(trade.get('Size'))
                    pnl = self.safe(trade.get('PnL'))
                    
                    exit_type = -1
                    try:
                        raw_record = raw_records.iloc[i]
                        exit_type = int(raw_record['exit_type']) if 'exit_type' in raw_records.columns else -1
                    except: pass

                    def get_date_str(idx):
                        if isinstance(idx, (pd.Timestamp, datetime)): return idx.strftime('%Y-%m-%d')
                        try: return dates[int(idx)]
                        except: return str(idx)

                    if e_idx is not None and e_price > 0:
                        e_reason = "전략 진입"
                        try:
                            if isinstance(e_idx, (pd.Timestamp, datetime)):
                                target_dt = e_idx.strftime('%Y-%m-%d')
                                if target_dt in dates:
                                    idx_int = dates.index(target_dt)
                                    potential_indices = [idx_int]
                                    if exec_type == 'next_open' and idx_int > 0: potential_indices.append(idx_int - 1)
                                    for p_idx in potential_indices:
                                        if entry_reasons[p_idx]:
                                            e_reason = entry_reasons[p_idx]
                                            break
                            else:
                                idx_int = int(e_idx)
                                potential_indices = [idx_int]
                                if exec_type == 'next_open' and idx_int > 0: potential_indices.append(idx_int - 1)
                                for p_idx in potential_indices:
                                    if 0 <= p_idx < len(entry_reasons) and entry_reasons[p_idx]:
                                        e_reason = entry_reasons[p_idx]
                                        break
                        except: pass
                        
                        final_qty = int(np.floor(size))
                        if final_qty > 0:
                            signals_list.append({
                                "date": get_date_str(e_idx), "type": "buy",
                                "price": e_price, "quantity": final_qty,
                                "amount": e_price * final_qty, "condition": e_reason
                            })

                    if x_idx is not None and x_price > 0:
                        reason_kr = "전략 청산"
                        if exit_type >= 0:
                            if exit_type in [1, 5]: reason_kr = f"손절매 (-{sl_pct}%)" if sl_pct > 0 else "손절매"
                            elif exit_type == 2: reason_kr = f"트레일링 스탑 (-{ts_pct}%)" if ts_pct > 0 else "트레일링 스탑"
                            elif exit_type in [3, 4]: reason_kr = f"익절매 (+{tp_pct}%)" if tp_pct > 0 else "익절매"
                            elif exit_type == 0:
                                try:
                                    if isinstance(x_idx, (pd.Timestamp, datetime)):
                                        target_dt = x_idx.strftime('%Y-%m-%d')
                                        if target_dt in dates:
                                            idx_int = dates.index(target_dt)
                                            potential_indices = [idx_int-1] if exec_type == 'next_open' and idx_int > 0 else [idx_int]
                                            for p_idx in potential_indices:
                                                if exit_reasons[p_idx]:
                                                    reason_kr = exit_reasons[p_idx]
                                                    break
                                except: pass
                        
                        final_qty = int(np.floor(size))
                        if final_qty > 0:
                            signals_list.append({
                                "date": get_date_str(x_idx), "type": "sell",
                                "price": x_price, "quantity": final_qty,
                                "amount": x_price * final_qty,
                                "condition": f"{reason_kr} (수익: {pnl:,.0f}원)"
                            })
            
            final_res = {
                "symbol": req['symbol'],
                "totalReturn": self.safe(pf.total_return() * 100),
                "cagr": self.safe(pf.annualized_return() * 100),
                "buyAndHoldReturn": self.safe(pf.benchmark_returns().sum() * 100),
                "maxDrawdown": self.safe(pf.max_drawdown() * 100),
                "winRate": self.safe(pf.trades.win_rate() * 100),
                "profitFactor": self.safe(pf.trades.profit_factor()),
                "sharpe": self.safe(pf.sharpe_ratio()),
                "sortino": self.safe(pf.sortino_ratio()),
                "volatility": self.safe(pf.returns().std() * np.sqrt(252) * 100),
                "equity": pf.value().tolist(),
                "benchmark_equity": (init_cash * (1 + pf.benchmark_returns().cumsum())).tolist(),
                "dates": dates,
                "signals": signals_list,
                "validation": {
                    "inSample": {"cagr": self.safe(pf_is.annualized_return() * 100), "mdd": self.safe(pf_is.max_drawdown() * 100), "period": f"{dates[0]} ~ {dates[split_idx-1]}"},
                    "outOfSample": {"cagr": self.safe(pf_oos.annualized_return() * 100), "mdd": self.safe(pf_oos.max_drawdown() * 100), "period": f"{dates[split_idx]} ~ {dates[-1]}"}
                },
                "warnings": list(self.warnings),
                "version": "5.0"
            }
            return final_res
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def evaluate_group(self, group: Dict[str, Any], idx: int, df: pl.DataFrame) -> Tuple[bool, Optional[str]]:
        if not group['conditions']: return False, None
        results = []
        descriptions = []
        for cond in group['conditions']:
            res = self.evaluate_condition(cond, idx, df)
            results.append(res)
            if res: descriptions.append(self.get_condition_description(cond))
        
        if group['logic'] == 'AND':
            if all(results): return True, " + ".join(descriptions)
            return False, None
        else:
            if any(results):
                matching_descriptions = [descriptions[i] for i, r in enumerate(results) if r]
                return True, " 또는 ".join(matching_descriptions)
            return False, None

    def get_condition_description(self, cond: Dict[str, Any]) -> str:
        cid, p = cond['id'], cond['params']
        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long = p.get('longMA', p.get('long_period', p.get('long', 20)))
            return f"{short}/{long}일 이동평균선 골든크로스" if p.get('signalType') != 'sell' else f"{short}/{long}일 이동평균선 데드크로스"
        elif cid == 'rsi':
            val = p.get('value', 30)
            op = p.get('operator', '<')
            op_kr = {"<": "이하", ">": "이상", "<=": "이하", ">=": "이상"}.get(op, op)
            return f"RSI {val} {op_kr}"
        elif cid == 'price':
            val = p.get('value', 0)
            op = p.get('operator', '>')
            op_kr = {"<": "이하", ">": "이상", "<=": "이하", ">=": "이상"}.get(op, op)
            return f"가격 {val:,.0f}원 {op_kr}"
        elif cid == 'bollinger_bands':
            return "볼린저 밴드 하단 돌파" if p.get('signalType') == 'buy' else "볼린저 밴드 상단 돌파"
        elif cid == 'trading_value':
            val = p.get('value', 100)
            return f"거래대금 {val}억 이상"
        return cid

    def evaluate_condition(self, cond: Dict[str, Any], idx: int, df: pl.DataFrame) -> bool:
        cid, p = cond['id'], cond['params']
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
            s = self.safe(df[f'close_{short}_sma'][idx])
            l = self.safe(df[f'close_{long}_sma'][idx])
            if idx == 0: return False
            ps, pl_val = self.safe(df[f'close_{short}_sma'][idx-1]), self.safe(df[f'close_{long}_sma'][idx-1])
            return (ps >= pl_val and s < l) if p.get('signalType') == 'sell' else (ps <= pl_val and s > l)
        elif cid == 'rsi':
            period = p.get('period', p.get('rsi_period', 14))
            r = self.safe(df[f'rsi_{period}'][idx])
            val, op = p.get('value', 30), p.get('operator', '<')
            return compare(r, op, val)
        elif cid == 'price_level':
            c = self.safe(df['close'][idx])
            val, op = p.get('value', 0), p.get('operator', '>')
            return compare(c, op, val)
        elif cid == 'bollinger_bands':
            curr_price, ub, lb = self.safe(df['close'][idx]), self.safe(df['boll_ub'][idx]), self.safe(df['boll_lb'][idx])
            return compare(curr_price, '>=', ub) if p.get('signalType') == 'sell' else compare(curr_price, '<=', lb)
        elif cid == 'volume_spike':
            period = p.get('period', 20)
            obv_sma_name = f'obv_{period}_sma'
            if obv_sma_name not in df.columns: return False
            obv, obv_sma = self.safe(df['obv'][idx]), self.safe(df[obv_sma_name][idx])
            if idx == 0: return False
            p_obv, p_obv_sma = self.safe(df['obv'][idx-1]), self.safe(df[obv_sma_name][idx-1])
            return (p_obv >= p_obv_sma and obv < obv_sma) if p.get('signalType') == 'sell' else (p_obv <= p_obv_sma and obv > obv_sma)
        elif cid == 'breakout':
            period = p.get('lookbackPeriod', 20)
            curr_price = self.safe(df['close'][idx])
            if idx < period: return False
            if p.get('signalType') == 'sell':
                return compare(curr_price, '<', self.safe(df[f'close_{period}_min'][idx-1]))
            else:
                return compare(curr_price, '>', self.safe(df[f'close_{period}_max'][idx-1]))
        elif cid == 'trading_value':
            val, op = p.get('value', 0) * 100000000, p.get('operator', '>=')
            curr_val = self.safe(df['trading_value_20_sma'][idx] if 'trading_value_20_sma' in df.columns else df['close'][idx] * df['volume'][idx])
            return compare(curr_val, op, val)
        elif cid in ['per', 'pbr', 'roe_or_gpa', 'debt_ratio', 'market_cap']:
            if cid not in df.columns: return False
            val, op, curr = float(p.get('value') or 0), p.get('operator', '<'), self.safe(df[cid][idx])
            return compare(curr, op, val)
        elif cid == 'investor_net_buy': return False
        return False
