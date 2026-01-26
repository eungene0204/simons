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
            
            # 1. Handle Series/Index/Arrays
            if isinstance(val, (pd.Series, pd.Index, np.ndarray)):
                if len(val) == 0: return 0.0
                try:
                    # Mean usually returns a scalar. If not, take the first item.
                    m = val.mean()
                    if hasattr(m, 'iloc'): m = m.iloc[0]
                    elif hasattr(m, '__getitem__'): m = m[0]
                    return float(m)
                except:
                    # Fallback to first element if mean fails
                    v = val.iloc[0] if hasattr(val, 'iloc') else val[0]
                    return float(v)
            
            # 2. Handle DataFrames
            if isinstance(val, pd.DataFrame):
                if val.empty: return 0.0
                return float(val.values.mean())

            # 3. Handle standard numeric types
            if isinstance(val, (int, float, np.number)):
                if np.isnan(val) or np.isinf(val):
                    return 0.0
                return float(val)
            
            # 4. Handle anything with .item() (like single-element numpy arrays)
            if hasattr(val, 'item'):
                try:
                    return float(val.item())
                except:
                    pass

            # 5. Last resort: try float conversion
            return float(val)
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
            # Data is already adjusted (verified via 005930 sample)
            pass
        
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
                sdf[f'close_{period}_max'] = sdf['close'].rolling(window=period).max()
                sdf[f'close_{period}_min'] = sdf['close'].rolling(window=period).min()
        
        res_pdf = pd.DataFrame(sdf)
        if res_pdf.index.name == 'date' or 'date' not in res_pdf.columns:
            res_pdf = res_pdf.reset_index()
            
        return pl.from_pandas(res_pdf) # Returning sdf as standard pandas DF with date column included

    def run_backtest(self, req: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.warnings = set()
            symbols = req.get('symbols', [req.get('symbol')])
            print(f"[DEBUG] ENGINE: Starting backtest for {len(symbols)} symbols: {symbols}")
            
            # Risk & Options
            risk_params = req.get('risk', {})
            init_cash = float(risk_params.get('init_cash') or 10000000.0)
            liquidity_mult = float(risk_params.get('liquidity_multiplier') or 0.0)
            pos_size_pct = float(risk_params.get('position_size_pct') or 100.0)
            max_positions = int(risk_params.get('max_positions') or 1)
            
            options = req.get('options', {})
            exec_type = options.get('execution_type', 'next_open') 
            fee_rate = float(options.get('fee_rate') or 0.0015)
            slippage_val = float(options.get('slippage_rate') or 0.0020)
            
            period_req = req.get('period', 'full')
            start_date_req = req.get('startDate')
            end_date_req = req.get('endDate')

            # 1. Load and process each symbol
            all_prices = {}
            all_exec_prices = {}
            all_entries = {}
            all_exits = {}
            all_entry_reasons = {}
            all_exit_reasons = {}
            
            processed_symbols = []
            common_index = None

            for sym in symbols:
                try:
                    df_pl = self.load_data(sym)
                    # Indicators
                    all_conditions = req['entry']['conditions'] + req['exit']['conditions']
                    df_pl = self.calculate_indicators(df_pl, all_conditions)
                    
                    # Filtering
                    if period_req != 'full' or start_date_req or end_date_req:
                        last_date = df_pl['date'].max()
                        ref_date = last_date if isinstance(last_date, datetime) else pd.to_datetime(last_date)
                        if start_date_req: df_pl = df_pl.filter(pl.col("date") >= pd.to_datetime(start_date_req))
                        elif period_req == '6M': df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(months=6)))
                        elif period_req == '1Y': df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=1)))
                        elif period_req == '5Y': df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=5)))
                        if end_date_req: df_pl = df_pl.filter(pl.col("date") <= pd.to_datetime(end_date_req))

                    if len(df_pl) < 10:
                        print(f"[WARNING] ENGINE: Too little data for {sym}. Skipping.")
                        continue

                    data_len = len(df_pl)
                    pdf = df_pl.to_pandas()
                    pdf.set_index('date', inplace=True)
                    pdf.index = pd.to_datetime(pdf.index)
                    
                    # Liquidity check
                    target_amount = init_cash * (pos_size_pct / 100.0 / max_positions)
                    vol_val = (pdf['close'] * pdf['volume']).values
                    liquidity_ok = np.ones(data_len, dtype=bool)
                    if liquidity_mult > 0:
                        liquidity_ok = np.zeros(data_len, dtype=bool)
                        for i in range(1, data_len):
                            liquidity_ok[i] = vol_val[i-1] >= (liquidity_mult * target_amount)

                    # Signals
                    entries = []
                    exits = []
                    entry_descs = [None] * data_len
                    exit_descs = [None] * data_len
                    
                    for i in range(data_len):
                        can_enter, entry_desc = self.evaluate_group(req['entry'], i, df_pl)
                        if can_enter and not liquidity_ok[i]:
                            can_enter = False
                            entry_desc = None
                        entries.append(can_enter)
                        entry_descs[i] = entry_desc
                        
                        can_exit, exit_desc = self.evaluate_group(req['exit'], i, df_pl)
                        exits.append(can_exit)
                        exit_descs[i] = exit_desc
                    
                    # Store data indexed by datetime
                    sym_prices = pdf['close']
                    sym_open = pdf['open'] if 'open' in pdf.columns else pdf['close']
                    
                    entries_s = pd.Series(entries, index=pdf.index)
                    exits_s = pd.Series(exits, index=pdf.index)
                    
                    if exec_type == 'next_open':
                        entries_exec = entries_s.shift(1).fillna(False)
                        exits_exec = exits_s.shift(1).fillna(False)
                        exec_prices = sym_open
                    else:
                        entries_exec = entries_s
                        exits_exec = exits_s
                        exec_prices = sym_prices

                    all_prices[sym] = sym_prices
                    all_exec_prices[sym] = exec_prices
                    all_entries[sym] = entries_exec
                    all_exits[sym] = exits_exec
                    all_entry_reasons[sym] = entry_descs
                    all_exit_reasons[sym] = exit_descs
                    processed_symbols.append(sym)
                    
                    if common_index is None:
                        common_index = pdf.index
                    else:
                        common_index = common_index.union(pdf.index).sort_values()

                except Exception as e:
                    print(f"[ERROR] ENGINE: Failed to process {sym}: {e}")

            if not processed_symbols:
                raise Exception("No valid data found for any of the symbols.")

            # Align all DataFrames to common_index
            price_df = pd.DataFrame(all_prices, index=common_index).ffill()
            exec_price_df = pd.DataFrame(all_exec_prices, index=common_index).ffill()
            entries_df = pd.DataFrame(all_entries, index=common_index).fillna(False)
            exits_df = pd.DataFrame(all_exits, index=common_index).fillna(False)

            # vectorbt Execution
            sl_pct = float(risk_params.get('stop_loss_pct') or 0)
            tp_pct = float(risk_params.get('take_profit_pct') or 0)
            ts_pct = float(risk_params.get('trailing_stop_pct') or 0)
            min_cash_reserve = float(risk_params.get('min_cash_reserve_pct') or 0)
            max_daily_buy = float(risk_params.get('max_daily_buy_pct') or 100.0)
            max_mdd_limit = float(risk_params.get('max_mdd_limit_pct') or 0)

            # size_per_pos: Percent of equity to use for EACH position.
            # Example: 10% means EACH stock gets 10% of NAV.
            size_per_pos = pos_size_pct / 100.0
            
            vbt_kwargs = dict(
                size=size_per_pos,
                size_type='Percent',
                init_cash=init_cash,
                fees=fee_rate,
                slippage=slippage_val,
                freq='D',
                sl_stop=sl_pct / 100 if sl_pct > 0 else None,
                tp_stop=tp_pct / 100 if tp_pct > 0 else None,
                sl_trail=ts_pct / 100 if ts_pct > 0 else None,
                cash_sharing=True,
                group_by=False, # Each symbol has its own column
                allow_partial=False
            )

            pf = vbt.Portfolio.from_signals(
                close=price_df, price=exec_price_df,
                entries=entries_df, exits=exits_df,
                accumulate=False, direction='longonly',
                **vbt_kwargs
            )

            # Results
            signals_list = []
            if len(pf.trades.records) > 0:
                vbt_trades = pf.trades.records_readable
                raw_records = pf.trades.records
                dates_str = [d.strftime('%Y-%m-%d') for d in common_index]

                for i, (idx_row, trade) in enumerate(vbt_trades.iterrows()):
                    # Column can be the symbol directly if group_by=False
                    sym = trade.get('Column')
                    if sym is None:
                        col_idx = trade.get('Column Idx', 0)
                        sym = processed_symbols[int(col_idx)]
                    
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

                    def get_dt_str(ts):
                        if isinstance(ts, (pd.Timestamp, datetime)): return ts.strftime('%Y-%m-%d')
                        return str(ts)

                    # Entry Reason
                    e_reason = "전략 진입"
                    try:
                        # Find original index in sym's data
                        sym_dates = [d.strftime('%Y-%m-%d') for d in all_entries[sym].index]
                        dt_s = get_dt_str(e_idx)
                        if dt_s in sym_dates:
                            idx_in_sym = sym_dates.index(dt_s)
                            # Adjust for next_open
                            p_idx = idx_in_sym - 1 if exec_type == 'next_open' and idx_in_sym > 0 else idx_in_sym
                            if all_entry_reasons[sym][p_idx]:
                                e_reason = all_entry_reasons[sym][p_idx]
                    except: pass

                    # Round price for SSOT (Consistent with UI display)
                    e_price_rounded = round(e_price)
                    final_qty = int(np.floor(self.safe(trade.get('Size'))))
                    
                    if final_qty >= 1: # Only log if we at least bought 1 share
                        signals_list.append({
                            "date": get_dt_str(e_idx), "symbol": str(sym), "type": "buy",
                            "price": float(e_price_rounded), "quantity": final_qty,
                            "amount": float(e_price_rounded * final_qty), "condition": e_reason
                        })
                    else:
                        self.warnings.add(f"{sym}: 자금 부족으로 인해 최소 수량(1주)을 매수하지 못했습니다. (필요 금액: {e_price:,.0f}원)")

                    # Exit Reason mapping
                    reason_kr = "전략 청산"
                    
                    # 1. Try to find signal-based reason first
                    # If exit_type is 0 (Signal) or -1 (Missing/Unknown), check strategy signals
                    if exit_type <= 0:
                        try:
                            sym_dates = [d.strftime('%Y-%m-%d') for d in all_exits[sym].index]
                            dt_s = get_dt_str(x_idx)
                            if dt_s in sym_dates:
                                idx_in_sym = sym_dates.index(dt_s)
                                # For next_open, signal occurred at p_idx
                                p_idx = idx_in_sym - 1 if exec_type == 'next_open' and idx_in_sym > 0 else idx_in_sym
                                if p_idx >= 0 and p_idx < len(all_exit_reasons[sym]) and all_exit_reasons[sym][p_idx]:
                                    reason_kr = all_exit_reasons[sym][p_idx]
                        except Exception as e:
                            print(f"[DEBUG] Reason lookup failed for {sym}: {e}")

                    # 2. Override with stop-loss/etc if exit_type indicates it
                    if exit_type > 0:
                        if exit_type in [1, 5]: reason_kr = f"손절매 (-{sl_pct}%)" if sl_pct > 0 else "손절매"
                        elif exit_type == 2: reason_kr = f"트레일링 스탑 (-{ts_pct}%)" if ts_pct > 0 else "트레일링 스탑"
                        elif exit_type == 3: reason_kr = f"익절매 (+{tp_pct}%)" if tp_pct > 0 else "익절매"
                        elif exit_type == 4: reason_kr = "기한 만료 청산"

                    if final_qty >= 1:
                        # Round price for SSOT
                        x_price_rounded = round(x_price)
                        signals_list.append({
                            "date": get_dt_str(x_idx), "symbol": str(sym), "type": "sell",
                            "price": float(x_price_rounded), "quantity": final_qty,
                            "amount": float(x_price_rounded * final_qty),
                            "condition": f"{reason_kr} (수익: {pnl:,.0f}원)"
                        })

            # Sort signals by date
            signals_list.sort(key=lambda x: x['date'])

            # Helper to ensure Series/List
            def to_list(obj):
                if isinstance(obj, pd.DataFrame):
                    return obj.iloc[:, 0].tolist()
                if isinstance(obj, pd.Series):
                    return obj.tolist()
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                return list(obj)

            # Calculate per-asset stats
            per_asset_stats = {}
            if len(processed_symbols) > 1:
                col_total_returns = pf.total_return()
                col_trade_counts = pf.trades.count()
                col_win_rates = pf.trades.win_rate()
                col_profits = pf.total_profit()
                
                for i, sym in enumerate(processed_symbols):
                    wr = col_win_rates.iloc[i]
                    per_asset_stats[sym] = {
                        "symbol": sym,
                        "totalReturn": self.safe(col_total_returns.iloc[i] * 100),
                        "trades": int(self.safe(col_trade_counts.iloc[i])),
                        "winRate": self.safe(wr * 100),
                        "profit": self.safe(col_profits.iloc[i])
                    }
            elif len(processed_symbols) == 1:
                sym = processed_symbols[0]
                per_asset_stats[sym] = {
                    "symbol": sym,
                    "totalReturn": self.safe(pf.total_return() * 100),
                    "trades": int(self.safe(pf.trades.count())),
                    "winRate": self.safe(pf.trades.win_rate() * 100),
                    "profit": self.safe(pf.total_profit())
                }

            # Portfolio-wide Win Rate and Kelly
            total_trades = len(pf.trades)
            win_count = len(pf.trades.winning)
            agg_win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
            
            # Kelly Criterion: K = W - (1-W)/R where W is win rate, R is win/loss ratio
            # Use safe to ensure scalar values
            print(f"[DEBUG] ENGINE: Calculating Portfolio stats (v5.6 fix)...")
            avg_win = self.safe(pf.trades.winning.pnl.mean())
            avg_loss = abs(self.safe(pf.trades.losing.pnl.mean()))
            
            r = 0.0
            if self.safe(avg_loss) > 0:
                r = avg_win / avg_loss
            
            w = agg_win_rate / 100
            kelly_val = 0.0
            if self.safe(r) > 0:
                kelly_val = w - (1 - w) / r

            final_res = {
                "symbols": processed_symbols,
                "totalReturn": self.safe(pf.total_return() * 100),
                "cagr": self.safe(pf.annualized_return() * 100),
                "buyAndHoldReturn": self.safe(pf.benchmark_returns().sum().mean() * 100), # Simple mean of returns
                "maxDrawdown": self.safe(pf.max_drawdown() * 100),
                "winRate": agg_win_rate,
                "trades": total_trades,
                "profitFactor": self.safe(pf.trades.profit_factor()),
                "sharpe": self.safe(pf.sharpe_ratio()),
                "sortino": self.safe(pf.sortino_ratio()),
                "kelly": self.safe(kelly_val),
                "volatility": self.safe(pf.returns().std() * np.sqrt(252) * 100),
                "equity": to_list(pf.value()),
                "benchmark_equity": to_list(init_cash * (1 + pf.benchmark_returns().mean(axis=1).cumsum())),
                "dates": [d.strftime('%Y-%m-%d') for d in common_index],
                "signals": signals_list,
                "perAssetStats": per_asset_stats,
                "warnings": list(self.warnings),
                "version": "5.5"
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
