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
                raise FileNotFoundError(f"Data for {symbol} not found at {file_path}")
        return pl.read_parquet(file_path)

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
        self.warnings = set()
        symbol = req['symbol']
        print(f"[DEBUG] ENGINE: Starting backtest for {symbol}")
        df_pl = self.load_data(symbol)
        print(f"[DEBUG] ENGINE: Data loaded. Rows: {len(df_pl)}")
        
        # 1. Adjusted Price Handling
        # If 'adj_close' exists in data, we use it for indicator calculation.
        # Otherwise, we use 'close'. (Note: Data loading should provide this distinction)
        price_col = 'adj_close' if 'adj_close' in df_pl.columns else 'close'
        
        # 2. Generate Indicators (using Adjusted Price if available)
        all_conditions = req['entry']['conditions'] + req['exit']['conditions']
        df_pl = self.calculate_indicators(df_pl, all_conditions)
        
        # 3. Period Filtering
        period = req.get('period', 'full')
        start_date = req.get('startDate')
        end_date = req.get('endDate')
        
        print(f"[DEBUG] ENGINE: Requested period: {period}, startDate: {start_date}, endDate: {end_date}")
        
        if period != 'full' or start_date or end_date:
            # Convert polars date to datetime for comparison if needed
            # For simplicity, if we have strings, we compare as strings or convert
            last_date = df_pl['date'].max()
            if isinstance(last_date, datetime):
                ref_date = last_date
            else:
                ref_date = pd.to_datetime(last_date)
                
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
        print(f"[DEBUG] ENGINE: Data length after filtering: {data_len}")
        
        if data_len < 10:
             print("[WARNING] ENGINE: Too little data for backtest.")

        # 4. Extract Signals
        entries = []
        exits = []
        
        # 4. Liquidity Filter Logic
        # Goal: Daily Volume Value (D-1) > 10 * Target Purchase Amount
        risk_params = req.get('risk', {})
        init_cash = float(risk_params.get('init_cash', 10000000.0))
        liquidity_mult = float(risk_params.get('liquidity_multiplier', 10.0))
        target_amount = init_cash * (risk_params.get('position_size_pct', 100) / 100)
        
        # Pre-calculate liquidity status (True if sufficient)
        vol_val = (df_pl['close'] * df_pl['volume']).to_numpy()
        liquidity_ok = np.ones(data_len, dtype=bool) # Default to True if we want to bypass
        
        # Apply filter only if intended (liquidity_mult > 0)
        if liquidity_mult > 0:
            liquidity_ok = np.zeros(data_len, dtype=bool)
            for i in range(1, data_len):
                liquidity_ok[i] = vol_val[i-1] >= (liquidity_mult * target_amount)
        
        entry_reasons = [None] * data_len
        exit_reasons = [None] * data_len
        
        for i in range(data_len):
            can_enter, entry_desc = self.evaluate_group(req['entry'], i, df_pl)
            # Apply Liquidity Filter to Entry
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
             print("[WARNING] ENGINE: Zero entry signals. Backtest will have no trades.")
             self.warnings.add("선택한 기간 동안 매수 조건이 한 번도 충족되지 않았습니다 (매매 없음).")
        
        # 5. Execution Logic Parameters (Configurable)
        options = req.get('options', {})
        exec_type = options.get('execution_type', 'next_open') 
        fee_rate = float(options.get('fee_rate', 0.0015))
        slippage_rate = float(options.get('slippage_rate', 0.0020))
        
        # Consistent Price column for execution and valuation
        # If we replaced 'close' with 'adj_close' in calculate_indicators, use it.
        price_col = 'close'
        open_col = 'open' if 'open' in df_pl.columns else 'close'

        price_series = df_pl[price_col].to_pandas()
        dates_list = df_pl['date'].to_list()
        dt_index = pd.to_datetime(dates_list)
        
        if exec_type == 'next_open':
            entries_exec = entries_series.shift(1).fillna(False)
            exits_exec = exits_series.shift(1).fillna(False)
            exec_prices = df_pl[open_col].to_pandas()
        else: # same_close
            entries_exec = entries_series
            exits_exec = exits_series
            exec_prices = price_series
            
        exec_prices.index = dt_index
        entries_exec.index = dt_index
        exits_exec.index = dt_index
        
        # The price series for Valuation (important for equity curve)
        prices_val = price_series
        prices_val.index = dt_index
        
        dates = [d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d) for d in dates_list]
        
        pos_size_pct = req['risk'].get('position_size_pct', 100) / 100
        
        # 7. vectorbt Execution
        # Extract risk management params for vectorbt
        risk_management = req.get('risk', {})
        sl_pct = risk_management.get('stop_loss_pct', 0)
        tp_pct = risk_management.get('take_profit_pct', 0)
        ts_pct = risk_management.get('trailing_stop_pct', 0)

        # common kwargs for consistency
        vbt_kwargs = dict(
            size=pos_size_pct,
            size_type='Percent',
            init_cash=init_cash,
            fees=fee_rate,
            slippage=slippage_rate,
            freq='D',
            sl_stop=sl_pct / 100 if sl_pct > 0 else None,
            tp_stop=tp_pct / 100 if tp_pct > 0 else None,
            sl_trail=ts_pct / 100 if ts_pct > 0 else None,
            allow_partial=True # CRITICAL: Prevents leverage/negative cash
        )

        print(f"[DEBUG] ENGINE: VectorBT simulation with kwargs: {vbt_kwargs}")

        # Full Portfolio for signals and main results
        pf = vbt.Portfolio.from_signals(
            close=prices_val, # Evaluation price
            price=exec_prices, # Actual entry/exit price
            entries=entries_exec,
            exits=exits_exec,
            accumulate=False,
            direction='longonly', # Explicitly long-only
            cash_sharing=False,
            **vbt_kwargs
        )
        
        # 8. Overfitting Check (IS/OOS 70/30 Split)
        split_idx = int(data_len * 0.7)
        
        pf_is = vbt.Portfolio.from_signals(
            close=prices_val.iloc[:split_idx],
            price=exec_prices.iloc[:split_idx],
            entries=entries_exec.iloc[:split_idx],
            exits=exits_exec.iloc[:split_idx],
            accumulate=False,
            direction='longonly',
            cash_sharing=False,
            **vbt_kwargs
        )
        
        pf_oos = vbt.Portfolio.from_signals(
            close=prices_val.iloc[split_idx:],
            price=exec_prices.iloc[split_idx:],
            entries=entries_exec.iloc[split_idx:],
            exits=exits_exec.iloc[split_idx:],
            accumulate=False,
            direction='longonly',
            cash_sharing=False,
            **vbt_kwargs
        )
        
        def safe(val):
            try:
                if val is None:
                    return 0.0
                if isinstance(val, (pd.Series, pd.Index, np.ndarray)):
                    if len(val) == 0: return 0.0
                    val = val.iloc[0] if hasattr(val, 'iloc') else val[0]
                
                # Check if it's a numeric type before calling isnan
                if not isinstance(val, (int, float, np.number)):
                    return 0.0
                    
                if np.isnan(val) or np.isinf(val):
                    return 0.0
                return float(val)
            except Exception as e:
                # print(f"Safe conversion error for {val}: {e}")
                return 0.0

        # Construct Signal List
        signals_list = []
        try:
            if len(pf.trades.records) > 0:
                vbt_trades = pf.trades.records_readable
                # Use raw records to get exit types (Signal, SL, TP, etc.)
                raw_records = pf.trades.records
                
                for i, (idx, trade) in enumerate(vbt_trades.iterrows()):
                    e_idx = trade.get('Entry Index', trade.get('Entry Timestamp', trade.get('Entry Idx')))
                    x_idx = trade.get('Exit Index', trade.get('Exit Timestamp', trade.get('Exit Idx')))
                    e_price = trade.get('Avg Entry Price', trade.get('Entry Price'))
                    x_price = trade.get('Avg Exit Price', trade.get('Exit Price'))
                    size = trade.get('Size')
                    pnl = trade.get('PnL')
                    
                    # Get raw record for this trade to check exit_type
                    raw_record = raw_records.iloc[i]
                    exit_type = raw_record['exit_type'] if 'exit_type' in raw_records.columns else -1

                    # Sanity check: if pnl is crazy, log it
                    if abs(pnl) > init_cash * 0.5:
                        print(f"[WARNING] ENGINE: Massive PnL trade detected! PnL: {pnl:,.0f} at {e_idx}")

                    def get_date_str(idx):
                        if isinstance(idx, (pd.Timestamp, datetime)):
                            return idx.strftime('%Y-%m-%d')
                        try:
                            return dates[int(idx)]
                        except:
                            return str(idx)

                    if e_idx is not None:
                        e_reason = "전략 진입 (매수)"
                        try:
                            if isinstance(e_idx, (pd.Timestamp, datetime)):
                                target_dt = e_idx.strftime('%Y-%m-%d')
                                if target_dt in dates:
                                    idx_int = dates.index(target_dt)
                                    potential_indices = [idx_int]
                                    if exec_type == 'next_open' and idx_int > 0:
                                        potential_indices.append(idx_int - 1)
                                    for p_idx in potential_indices:
                                        if entry_reasons[p_idx]:
                                            e_reason = entry_reasons[p_idx]
                                            break
                            else:
                                idx_int = int(e_idx)
                                potential_indices = [idx_int]
                                if exec_type == 'next_open' and idx_int > 0:
                                    potential_indices.append(idx_int - 1)
                                for p_idx in potential_indices:
                                    if 0 <= p_idx < len(entry_reasons) and entry_reasons[p_idx]:
                                        e_reason = entry_reasons[p_idx]
                                        break
                        except: pass
                        
                        signals_list.append({
                            "date": get_date_str(e_idx),
                            "type": "buy",
                            "price": float(e_price) if e_price is not None else 0.0,
                            "quantity": float(size) if size is not None else 0.0,
                            "condition": e_reason
                        })

                    if x_idx is not None:
                        # Improved Exit Reason Detection using native exit_type
                        # 0: Signal, 1: SL, 2: TSL, 3: TP, 4: TTP, 5: SLT, 6: EOD
                        reason_kr = "전략 청산"
                        
                        if exit_type == 1 or exit_type == 5: # Stop Loss or Stop Loss Timeout/Target
                            reason_kr = f"손절매 (-{sl_pct}%)" if sl_pct > 0 else "손절매"
                        elif exit_type == 2: # Trailing Stop
                            reason_kr = f"트레일링 스탑 (-{ts_pct}%)" if ts_pct > 0 else "트레일링 스탑"
                        elif exit_type == 3 or exit_type == 4: # Take Profit or Trailing TP
                            reason_kr = f"익절매 (+{tp_pct}%)" if tp_pct > 0 else "익절매"
                        elif exit_type == 0 or exit_type == -1: # Signal-based or fallback
                            # Try to find specific condition from strategy
                            try:
                                if isinstance(x_idx, (pd.Timestamp, datetime)):
                                    target_dt = x_idx.strftime('%Y-%m-%d')
                                    if target_dt in dates:
                                        idx_int = dates.index(target_dt)
                                        # For next_open execution, signal is at idx_int - 1
                                        potential_indices = []
                                        if exec_type == 'next_open':
                                            if idx_int > 0: potential_indices.append(idx_int - 1)
                                        else:
                                            potential_indices.append(idx_int)
                                        
                                        for p_idx in potential_indices:
                                            if exit_reasons[p_idx]:
                                                reason_kr = exit_reasons[p_idx]
                                                break
                            except: pass
                        
                        # Fallback for old VBT or missing exit_type
                        if reason_kr == "전략 청산" and exit_type == -1:
                           trade_return = trade.get('Return', 0)
                           if sl_pct > 0 and trade_return <= -(sl_pct/100) * 0.95:
                               reason_kr = f"손절매 (-{sl_pct}%)"
                           elif tp_pct > 0 and trade_return >= (tp_pct/100) * 0.95:
                               reason_kr = f"익절매 (+{tp_pct}%)"

                        signals_list.append({
                            "date": get_date_str(x_idx),
                            "type": "sell",
                            "price": float(x_price) if x_price is not None else 0.0,
                            "quantity": float(size) if size is not None else 0.0,
                            "condition": f"{reason_kr} (수익: {pnl:,.0f}원)" if pnl is not None else reason_kr
                        })
        except Exception as e:
            import traceback
            print(f"[ERROR] ENGINE: Results processing failed: {e}")
            traceback.print_exc()

        # debug metrics

        # debug metrics
        vbt_total_return = pf.total_return()
        
        # Log Equity Stats
        vals = pf.value()
        print(f"[DEBUG] ENGINE: Portfolio Value Stats - Min: {vals.min():,.0f}, Max: {vals.max():,.0f}, Final: {vals.iloc[-1]:,.0f}")
        # Check for absolute loss/bankruptcy
        if vals.min() < (init_cash * 0.01):
            self.warnings.add("시뮬레이션 중 자산의 99% 이상을 손실하여 사실상 파산 상태에 도달했습니다. 거래 비용이나 급격한 주가 하락을 확인하세요.")

        # Calculate Benchmark Equity (Buy & Hold curve)
        benchmark_pf = vbt.Portfolio.from_holding(prices_val, init_cash=init_cash)
        benchmark_equity = benchmark_pf.value().tolist()

        final_res = {
            "symbol": symbol,
            "totalReturn": safe(vbt_total_return * 100),
            "cagr": safe(pf.annualized_return() * 100),
            "buyAndHoldReturn": safe((prices_val.iloc[-1] / prices_val.iloc[0] - 1) * 100),
            "maxDrawdown": safe(pf.max_drawdown() * 100),
            "winRate": safe(pf.trades.win_rate() * 100),
            "profitFactor": safe(pf.trades.profit_factor()),
            "sharpe": safe(pf.sharpe_ratio()),
            "sortino": safe(pf.sortino_ratio()),
            "volatility": safe(pf.annualized_volatility() * 100),
            "equity": pf.value().tolist(),
            "benchmark_equity": benchmark_equity,
            "dates": dates,
            "signals": signals_list,
            "validation": {
                "inSample": {
                    "cagr": safe(pf_is.annualized_return() * 100),
                    "mdd": safe(pf_is.max_drawdown() * 100),
                    "period": f"{dates[0]} ~ {dates[split_idx-1]}"
                },
                "outOfSample": {
                    "cagr": safe(pf_oos.annualized_return() * 100),
                    "mdd": safe(pf_oos.max_drawdown() * 100),
                    "period": f"{dates[split_idx]} ~ {dates[-1]}"
                }
            },
            "warnings": list(self.warnings)
        }
        
        print(f"[DEBUG] ENGINE: Final Result Summary:")
        print(f"  Total Return: {final_res['totalReturn']}%")
        print(f"  Final Equity: {final_res['equity'][-1]:,.0f}")
        print(f"  Initial Equity: {final_res['equity'][0]:,.0f}")
        print(f"  Num Signals: {len(final_res['signals'])}")
        
        return final_res

    def evaluate_group(self, group: Dict[str, Any], idx: int, df: pl.DataFrame) -> Tuple[bool, Optional[str]]:
        if not group['conditions']: return False, None
        
        results = []
        descriptions = []
        
        for cond in group['conditions']:
            res = self.evaluate_condition(cond, idx, df)
            results.append(res)
            if res:
                descriptions.append(self.get_condition_description(cond))
        
        if group['logic'] == 'AND':
            if all(results):
                return True, " + ".join(descriptions)
            return False, None
        else: # OR
            if any(results):
                # Return joined descriptions of ALL matching conditions in OR as well
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
        if cid == 'ma_crossover':
            short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
            long = p.get('longMA', p.get('long_period', p.get('long', 20)))
            s_col, l_col = f"close_{short}_sma", f"close_{long}_sma"
            s, l = df[s_col][idx], df[l_col][idx]
            if idx == 0 or np.isnan(s) or np.isnan(l): return False
            ps, pl_val = df[s_col][idx-1], df[l_col][idx-1]
            res = ps >= pl_val and s < l if p.get('signalType') == 'sell' else ps <= pl_val and s > l
            if res and idx < 50: # Log first few matches
                 print(f"[DEBUG] ENGINE: Signal match at idx {idx} for {cid}")
            return res
        elif cid == 'rsi':
            period = p.get('period', p.get('rsi_period', 14))
            r_val = df[f"rsi_{period}"][idx]
            if r_val is None: return False
            try:
                r = float(r_val)
                if np.isnan(r): return False
            except:
                return False
            val, op = p.get('value', 30), p.get('operator', '<')
            if op == '<': res = r < val
            elif op == '>': res = r > val
            elif op == '<=': res = r <= val
            elif op == '>=': res = r >= val
            else: res = False
            return res
        elif cid == 'price':
            val, op = p.get('value', 0), p.get('operator', '>')
            c = df['close'][idx]
            if op == '>': return c > val
            if op == '<': return c < val
            if op == '>=': return c >= val
            if op == '<=': return c <= val
        elif cid == 'bollinger_bands':
            period = p.get('period', 20)
            sig_type = p.get('signalType', 'buy')
            curr_price = df['close'][idx]
            if sig_type == 'buy': # Lower band cross
                ub, lb = df['boll_ub'][idx], df['boll_lb'][idx]
                return curr_price <= lb
            else: # Upper band cross
                ub, lb = df['boll_ub'][idx], df['boll_lb'][idx]
                return curr_price >= ub
        elif cid == 'volume_spike':
            # OBV Crossover with its SMA
            period = p.get('period', 20)
            sdf = StockDataFrame.retype(df.to_pandas())
            obv_sma_name = f'obv_{period}_sma'
            if obv_sma_name not in df.columns:
                 # This is slow, ideally precompute in calculate_indicators
                 # For now, let's assume it might be missing and add a warning
                 self.warnings.add(f"거래량 지표({cid}) 계산에 필요한 데이터가 부족합니다.")
                 return False
            obv = df['obv'][idx]
            obv_sma = df[obv_sma_name][idx]
            if idx == 0: return False
            p_obv = df['obv'][idx-1]
            p_obv_sma = df[obv_sma_name][idx-1]
            if p.get('signalType') == 'sell':
                return p_obv >= p_obv_sma and obv < obv_sma
            else:
                return p_obv <= p_obv_sma and obv > obv_sma
        elif cid == 'breakout':
            period = p.get('lookbackPeriod', 20)
            curr_price = df['close'][idx]
            if idx < period: return False
            if p.get('signalType') == 'sell':
                low = df[f'close_{period}_min'][idx-1]
                return curr_price < low
            else:
                high = df[f'close_{period}_max'][idx-1]
                return curr_price > high
        elif cid == 'trading_value':
            val = p.get('value', 0) * 100000000 # Convert 억 to Won
            op = p.get('operator', '>=')
            # 20-day avg trading value
            if 'trading_value_20_sma' not in df.columns:
                # Fallback to current if avg not available
                curr_val = df['close'][idx] * df['volume'][idx]
            else:
                curr_val = df['trading_value_20_sma'][idx]
            
            if op == '>': return curr_val > val
            if op == '<': return curr_val < val
            if op == '>=': return curr_val >= val
            if op == '<=': return curr_val <= val
            
        elif cid in ['per', 'pbr', 'roe_or_gpa', 'debt_ratio', 'market_cap']:
            # Check if column exists
            if cid not in df.columns:
                self.warnings.add(f"재무 데이터({cid})가 현재 데이터베이스에 존재하지 않아 시뮬레이션에서 제외되었습니다.")
                return False
            # If exists, evaluate (implementation for when we have fundamental data later)
            val, op = p.get('value', 0), p.get('operator', '<')
            curr = df[cid][idx]
            if op == '<': return curr < val
            if op == '>': return curr > val
            if op == '<=': return curr <= val
            if op == '>=': return curr >= val
        
        elif cid == 'investor_net_buy':
            self.warnings.add(f"수급 데이터({cid})가 현재 데이터베이스에 존재하지 않아 시뮬레이션에서 제외되었습니다.")
            return False
            
        return False
