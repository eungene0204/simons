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
        
        # 1. Generate Indicators
        all_conditions = req['entry']['conditions'] + req['exit']['conditions']
        df_pl = self.calculate_indicators(df_pl, all_conditions)
        
        # 2. Extract Signals (Proprietary Strategy Logic)
        # We still use our evaluate_group to decide when to enter/exit
        entries = []
        exits = []
        data_len = len(df_pl)
        
        # Vectorized signal evaluation using Polars/Numpy would be faster, 
        # but for complex DSL we use the existing evaluate_group logic.
        # To keep it "Proprietary", we keep this part custom.
        for i in range(data_len):
            entries.append(self.evaluate_group(req['entry'], i, df_pl))
            exits.append(self.evaluate_group(req['exit'], i, df_pl))
            
        entries_series = pd.Series(entries)
        exits_series = pd.Series(exits)
        
        # 3. T+1 Execution Logic (Safety)
        # Shift signals by 1 to execute on the NEXT day's Open
        entries_shifted = entries_series.shift(1).fillna(False)
        exits_shifted = exits_series.shift(1).fillna(False)
        
        prices_open = df_pl['open'].to_pandas()
        prices_close = df_pl['close'].to_pandas()
        dates = df_pl['date'].to_list()
        
        # 4. Money Management (Proprietary)
        # Position sizing from DSL
        pos_size_pct = req['risk'].get('position_size_pct', 100) / 100
        
        # 5. vectorbt Execution (Standardization & Accuracy)
        # Use Open prices for execution because of T+1 shift
        pf = vbt.Portfolio.from_signals(
            close=prices_open, # Execute at Open
            entries=entries_shifted,
            exits=exits_shifted,
            size=pos_size_pct,
            size_type='Percent',
            init_cash=10000000.0,
            freq='D'
        )
        
        # 6. Professional Metrics from vectorbt
        # Note: vectorbt returns np.nan for some metrics if no trades
        def safe(val):
            return float(val) if not (np.isnan(val) or np.isinf(val)) else 0.0

        # Construct Signal List for UI
        vbt_trades = pf.trades.records_readable
        signals_list = []
        for _, trade in vbt_trades.iterrows():
            # Entry Signal
            signals_list.append({
                "date": dates[int(trade['Entry Index'])],
                "type": "entry",
                "price": float(trade['Entry Price']),
                "condition": "Entry Signal"
            })
            # Exit Signal
            signals_list.append({
                "date": dates[int(trade['Exit Index'])],
                "type": "exit",
                "price": float(trade['Exit Price']),
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
            "signals": signals_list
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
            if np.isnan(r): return False
            val, op = p.get('value', 30), p.get('operator', '<')
            if op == '<': return r < val
            if op == '>': return r > val
            if op == '<=': return r <= val
            if op == '>=': return r >= val
        return False
