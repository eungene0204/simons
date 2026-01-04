import polars as pl
import os
import numpy as np
import pandas as pd
from stockstats import StockDataFrame
import vectorbt as vbt
from typing import Dict, List, Any

class BacktestEngine:
    def __init__(self, data_dir: str = "data/ohlcv"):
        self.data_dir = data_dir if os.path.exists(data_dir) else "../data/ohlcv"

    def load_data(self, symbol: str) -> pl.DataFrame:
        file_path = os.path.join(self.data_dir, f"{symbol}.parquet")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Data for {symbol} not found at {file_path}")
        return pl.read_parquet(file_path)

    def calculate_indicators(self, df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        pdf = df_pl.to_pandas()
        sdf = StockDataFrame.retype(pdf)
        
        for cond in conditions:
            cid, p = cond['id'], cond['params']
            if cid == 'ma_crossover':
                short, long = p.get('shortMA', 5), p.get('longMA', 20)
                _ = sdf[f'close_{short}_sma']
                _ = sdf[f'close_{long}_sma']
            elif cid == 'rsi':
                period = p.get('period', 14)
                _ = sdf[f'rsi_{period}']
            elif cid == 'macd':
                _ = sdf['macd']
                _ = sdf['macds']
        
        return pl.from_pandas(sdf.reset_index())

    def run_backtest(self, req: Dict[str, Any]) -> Dict[str, Any]:
        symbol = req['symbol']
        df_pl = self.load_data(symbol)
        
        # 1. Adjusted Price Handling
        # If 'adj_close' exists in data, we use it for indicator calculation.
        # Otherwise, we use 'close'. (Note: Data loading should provide this distinction)
        price_col = 'adj_close' if 'adj_close' in df_pl.columns else 'close'
        
        # 2. Generate Indicators (using Adjusted Price if available)
        all_conditions = req['entry']['conditions'] + req['exit']['conditions']
        df_pl = self.calculate_indicators(df_pl, all_conditions)
        
        # 3. Extract Signals
        entries = []
        exits = []
        data_len = len(df_pl)
        
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
        
        for i in range(data_len):
            can_enter = self.evaluate_group(req['entry'], i, df_pl)
            # Apply Liquidity Filter to Entry
            if can_enter and not liquidity_ok[i]:
                can_enter = False
                
            entries.append(can_enter)
            exits.append(self.evaluate_group(req['exit'], i, df_pl))
            
        entries_series = pd.Series(entries)
        exits_series = pd.Series(exits)
        
        # 5. Execution Logic Parameters (Configurable)
        options = req.get('options', {})
        exec_type = options.get('execution_type', 'next_open') # 'next_open' or 'same_close'
        fee_rate = float(options.get('fee_rate', 0.0015))
        slippage_rate = float(options.get('slippage_rate', 0.0020))
        
        # 6. Signal & Price Preparation
        # Shift signals by 1 if using Next Day Open (to avoid look-ahead bias)
        if exec_type == 'next_open':
            entries_exec = entries_series.shift(1).fillna(False)
            exits_exec = exits_series.shift(1).fillna(False)
            exec_prices = df_pl['open'].to_pandas()
        else: # same_close
            entries_exec = entries_series
            exits_exec = exits_series
            exec_prices = df_pl['close'].to_pandas()
            
        prices_close = df_pl['close'].to_pandas()
        dates = df_pl['date'].to_list()
        
        pos_size_pct = req['risk'].get('position_size_pct', 100) / 100
        
        # 7. vectorbt Execution
        # common kwargs for consistency
        vbt_kwargs = dict(
            size=pos_size_pct,
            size_type='Percent',
            init_cash=init_cash,
            fees=fee_rate,
            slippage=slippage_rate,
            freq='D'
        )

        # Full Portfolio for signals and main results
        pf = vbt.Portfolio.from_signals(
            close=exec_prices, 
            entries=entries_exec,
            exits=exits_exec,
            **vbt_kwargs
        )
        
        # 8. Overfitting Check (IS/OOS 70/30 Split)
        # We run separate portfolios to avoid complex slicing issues in vbt
        split_idx = int(data_len * 0.7)
        
        pf_is = vbt.Portfolio.from_signals(
            close=exec_prices.iloc[:split_idx],
            entries=entries_exec.iloc[:split_idx],
            exits=exits_exec.iloc[:split_idx],
            **vbt_kwargs
        )
        
        pf_oos = vbt.Portfolio.from_signals(
            close=exec_prices.iloc[split_idx:],
            entries=entries_exec.iloc[split_idx:],
            exits=exits_exec.iloc[split_idx:],
            **vbt_kwargs
        )
        
        def safe(val):
            return float(val) if not (np.isnan(val) or np.isinf(val)) else 0.0

        # Construct Signal List
        signals_list = []
        if not pf.trades.records.empty:
            vbt_trades = pf.trades.records_readable
            for _, trade in vbt_trades.iterrows():
                # Handling both string and index based access depending on vbt version
                e_idx = trade.get('Entry Index', trade.get('Entry Timestamp', trade.get('Entry Idx')))
                x_idx = trade.get('Exit Index', trade.get('Exit Timestamp', trade.get('Exit Idx')))
                e_price = trade.get('Avg Entry Price', trade.get('Entry Price'))
                x_price = trade.get('Avg Exit Price', trade.get('Exit Price'))

                if e_idx is not None:
                    signals_list.append({
                        "date": dates[int(e_idx)],
                        "type": "entry",
                        "price": float(e_price) if e_price is not None else 0.0,
                        "condition": "Entry Signal"
                    })
                if x_idx is not None:
                    signals_list.append({
                        "date": dates[int(x_idx)],
                        "type": "exit",
                        "price": float(x_price) if x_price is not None else 0.0,
                        "condition": "Exit Signal"
                    })

        return {
            "symbol": symbol,
            "totalReturn": safe(pf.total_return() * 100),
            "cagr": safe(pf.annualized_return() * 100),
            "buyAndHoldReturn": safe((prices_close.iloc[-1] / prices_close.iloc[0] - 1) * 100),
            "maxDrawdown": safe(pf.max_drawdown() * 100),
            "winRate": safe(pf.trades.win_rate() * 100),
            "profitFactor": safe(pf.trades.profit_factor()),
            "sharpe": safe(pf.sharpe_ratio()),
            "sortino": safe(pf.sortino_ratio()),
            "volatility": safe(pf.annualized_volatility() * 100),
            "equity": pf.value().tolist(), 
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
            }
        }

    def evaluate_group(self, group: Dict[str, Any], idx: int, df: pl.DataFrame) -> bool:
        if not group['conditions']: return False
        res = [self.evaluate_condition(c, idx, df) for c in group['conditions']]
        return all(res) if group['logic'] == 'AND' else any(res)

    def evaluate_condition(self, cond: Dict[str, Any], idx: int, df: pl.DataFrame) -> bool:
        cid, p = cond['id'], cond['params']
        if cid == 'ma_crossover':
            s_col, l_col = f"close_{p.get('shortMA',5)}_sma", f"close_{p.get('longMA',20)}_sma"
            s, l = df[s_col][idx], df[l_col][idx]
            if idx == 0 or np.isnan(s) or np.isnan(l): return False
            ps, pl_val = df[s_col][idx-1], df[l_col][idx-1]
            return ps >= pl_val and s < l if p.get('signalType') == 'sell' else ps <= pl_val and s > l
        elif cid == 'rsi':
            r = df[f"rsi_{p.get('period', 14)}"][idx]
            if r is None or (isinstance(r, float) and np.isnan(r)): return False
            val, op = p.get('value', 30), p.get('operator', '<')
            if op == '<': return r < val
            if op == '>': return r > val
            if op == '<=': return r <= val
            if op == '>=': return r >= val
        elif cid == 'price':
            val, op = p.get('value', 0), p.get('operator', '>')
            c = df['close'][idx]
            if op == '>': return c > val
            if op == '<': return c < val
        return False
