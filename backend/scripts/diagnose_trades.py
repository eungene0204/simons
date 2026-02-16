import pandas as pd
import vectorbt as vbt
import numpy as np
from datetime import datetime
import os
import sys

# Add backend dir to path to import engine modules
sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.loader import DataLoader
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine
from engine.simulator import Simulator
from engine.result_handler import ResultHandler

def diagnose():
    data_dir = "data/ohlcv"
    loader = DataLoader(data_dir)
    indicators = IndicatorEngine()
    signals = SignalEngine()
    
    # Symbols to test
    symbols = ["005930", "000660"] # Samsung, SK Hynix
    
    req = {
        'entry': {'conditions': [{'id': 'ma_crossover', 'params': {'short': 5, 'long': 20, 'signalType': 'buy'}}], 'logic': 'AND'},
        'exit': {'conditions': [{'id': 'ma_crossover', 'params': {'short': 5, 'long': 20, 'signalType': 'sell'}}], 'logic': 'AND'},
        'risk': {'init_cash': 10000000, 'position_size_pct': 100},
        'options': {'execution_type': 'next_open'}
    }
    
    all_prices = {}
    all_exec_prices = {}
    all_entries = {}
    all_exits = {}
    common_index = None
    
    for sym in symbols:
        df_pl = loader.load_symbol_data(sym)
        df_pl = indicators.calculate(df_pl, req['entry']['conditions'] + req['exit']['conditions'])
        pdf = loader.preprocess_data(df_pl)
        data_len = len(pdf)
        
        entries = []
        exits = []
        for i in range(data_len):
            can_enter, _ = signals.evaluate_group(req['entry'], i, df_pl)
            entries.append(can_enter)
            can_exit, _ = signals.evaluate_group(req['exit'], i, df_pl)
            exits.append(can_exit)
            
        entries_s = pd.Series(entries, index=pdf.index)
        exits_s = pd.Series(exits, index=pdf.index)
        
        entries_exec = entries_s.shift(1).fillna(False)
        exits_exec = exits_s.shift(1).fillna(False)
        
        all_prices[sym] = pdf['close']
        all_exec_prices[sym] = pdf['open']
        all_entries[sym] = entries_exec
        all_exits[sym] = exits_exec
        
        if common_index is None: common_index = pdf.index
        else: common_index = common_index.union(pdf.index).sort_values()

    price_df = pd.DataFrame(all_prices, index=common_index).ffill()
    exec_price_df = pd.DataFrame(all_exec_prices, index=common_index).ffill()
    entries_df = pd.DataFrame(all_entries, index=common_index).fillna(False)
    exits_df = pd.DataFrame(all_exits, index=common_index).fillna(False)
    
    print("\n--- Diagnostic: entries_df (Head) ---")
    print(entries_df.sum()) # Sum of signals per column
    
    pf = Simulator.run(price_df, exec_price_df, entries_df, exits_df, req['risk'], req['options'])
    
    print("\n--- Diagnostic: vbt_trades.records_readable ---")
    if len(pf.trades.records) > 0:
        trades = pf.trades.records_readable
        print(trades[['Column', 'Entry Timestamp', 'Avg Entry Price', 'Size']].head(20))
        
        print("\n--- Diagnostic: Column content types ---")
        print(trades['Column'].value_counts())
    else:
        print("No trades generated.")

if __name__ == "__main__":
    diagnose()
