import os
import polars as pl
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import refactored modules
from engine.loader import DataLoader
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine
from engine.simulator import Simulator
from engine.result_handler import ResultHandler

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
        self.handler = ResultHandler()

    def calculate_indicators(self, df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        return self.indicator_engine.calculate(df_pl, conditions)

    def run_backtest(self, req: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.warnings = set()
            symbols = req.get('symbols', [req.get('symbol')])
            
            # Risk & Options
            risk_params = req.get('risk', {})
            print(f"[DEBUG] BacktestEngine: Received risk_params: {risk_params}")
            init_cash = float(risk_params.get('init_cash') or 10000000.0)
            pos_size_pct = float(risk_params.get('position_size_pct') or 100.0)
            
            # Support both naming conventions for compatibility, respect 0.0
            liquidity_limit_pct = risk_params.get('liquidity_limit_pct')
            if liquidity_limit_pct is None:
                liquidity_limit_pct = risk_params.get('liquidity_multiplier')
            if liquidity_limit_pct is None:
                liquidity_limit_pct = 10.0
            liquidity_limit_pct = float(liquidity_limit_pct)
            
            options = req.get('options', {})
            exec_type = options.get('execution_type', 'next_open') 
            
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
                    # 1.1 Load Data
                    df_pl = self.loader.load_symbol_data(sym)
                    
                    # 1.2 Calculate Indicators
                    all_conditions = req['entry']['conditions'] + req['exit']['conditions']
                    df_pl = self.indicator_engine.calculate(df_pl, all_conditions)
                    
                    # 1.3 Filtering by Period
                    if period_req != 'full' or start_date_req or end_date_req:
                        last_date = df_pl['date'].max()
                        ref_date = last_date if isinstance(last_date, datetime) else pd.to_datetime(last_date)
                        if start_date_req: df_pl = df_pl.filter(pl.col("date") >= pd.to_datetime(start_date_req))
                        elif period_req == '6M': df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(months=6)))
                        elif period_req == '1Y': df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=1)))
                        elif period_req == '5Y': df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=5)))
                        if end_date_req: df_pl = df_pl.filter(pl.col("date") <= pd.to_datetime(end_date_req))

                    if len(df_pl) < 1:
                        self.warnings.add(f"{sym}: 충분한 OHLCV 데이터가 없어 백테스트에서 제외되었습니다.")
                        continue

                    # 1.4 Preprocess (Adjusted Prices, Datetime Index)
                    pdf = self.loader.preprocess_data(df_pl)
                    data_len = len(pdf)
                    
                    # 1.5 Liquidity check
                    target_pos_amount = init_cash * (pos_size_pct / 100.0)
                    liquidity_ok = self.loader.check_liquidity(pdf, target_pos_amount, liquidity_limit_pct)

                    # 1.6 Generate Signals
                    entries = []
                    exits = []
                    entry_descs = [None] * data_len
                    exit_descs = [None] * data_len
                    
                    # Core risk blocks that should be handled by the simulator strictly
                    SIMULATOR_ONLY_BLOCKS = ['max_holding_days', 'trailing_stop']
                    
                    # Extract Risk Params recursively from Step 2 Strategy
                    pure_percentage_exits = set()

                    def extract_risk_from_group(group):
                        if not group or 'conditions' not in group: return
                        for cond in group['conditions']:
                            if 'conditions' in cond: # Nested group
                                extract_risk_from_group(cond)
                                continue
                                
                            cid = cond.get('id')
                            p = cond.get('params', {})
                            
                            if cid == 'price_limit_exit':
                                sl, tp = p.get('stopLoss'), p.get('takeProfit')
                                sl_m, tp_m = p.get('stopLossMode', 'pct'), p.get('takeProfitMode', 'pct')
                                is_pct = False
                                if sl_m == 'pct' and sl:
                                    risk_params['stop_loss_pct'] = sl
                                    is_pct = True
                                if tp_m == 'pct' and tp:
                                    risk_params['take_profit_pct'] = tp
                                    is_pct = True
                                if is_pct: pure_percentage_exits.add(id(cond))

                            elif cid == 'max_holding_days':
                                if p.get('maxHoldingDays'): risk_params['max_holding_days'] = p['maxHoldingDays']
                            elif cid == 'trailing_stop':
                                if p.get('trailingStop'): risk_params['trailing_stop_pct'] = p['trailingStop']

                    extract_risk_from_group(req['entry'])
                    extract_risk_from_group(req['exit'])

                    # Prepare filtered condition groups (clean signals)
                    def filter_risk_blocks(group):
                        if not group: return None
                        new_conds = []
                        for c in group.get('conditions', []):
                            if 'conditions' in c: # Nested group
                                filtered_sub = filter_risk_blocks(c)
                                if filtered_sub and filtered_sub['conditions']:
                                    new_conds.append(filtered_sub)
                            elif c['id'] not in SIMULATOR_ONLY_BLOCKS and id(c) not in pure_percentage_exits:
                                new_conds.append(c)
                        return {**group, "conditions": new_conds}

                    entry_config = filter_risk_blocks(req['entry'])
                    exit_config = filter_risk_blocks(req['exit'])
                    
                    for i in range(data_len):
                        can_enter, entry_desc = self.signal_engine.evaluate_group(entry_config, i, df_pl)
                        if can_enter and not liquidity_ok[i]:
                            can_enter = False
                            entry_desc = None
                        entries.append(can_enter)
                        entry_descs[i] = entry_desc
                        
                        can_exit, exit_desc = self.signal_engine.evaluate_group(exit_config, i, df_pl)
                        exits.append(can_exit)
                        exit_descs[i] = exit_desc
                    
                    # 1.7 Execution Alignment
                    entries_s = pd.Series(entries, index=pdf.index)
                    exits_s = pd.Series(exits, index=pdf.index)
                    
                    if exec_type == 'next_open':
                        entries_exec = entries_s.shift(1).fillna(False)
                        exits_exec = exits_s.shift(1).fillna(False)
                        exec_prices = pdf['open'] if 'open' in pdf.columns else pdf['close']
                    else:
                        entries_exec = entries_s
                        exits_exec = exits_s
                        exec_prices = pdf['close']

                    # 1.8 Store results for vectorbt
                    all_prices[sym] = pdf['close']
                    all_exec_prices[sym] = exec_prices
                    all_entries[sym] = entries_exec
                    all_exits[sym] = exits_exec
                    all_entry_reasons[sym] = pd.Series(entry_descs, index=pdf.index)
                    all_exit_reasons[sym] = pd.Series(exit_descs, index=pdf.index)
                    processed_symbols.append(sym)
                    
                    if common_index is None: common_index = pdf.index
                    else: common_index = common_index.union(pdf.index).sort_values()

                    # Final verification for this symbol
                    sig_dates = [entries_s.index[i].strftime('%Y-%m-%d') for i, val in enumerate(entries) if val]
                    print(f"[DEBUG] ENGINE: Symbol {sym} has {len(sig_dates)} entries. Sample dates: {sig_dates[:3]}")

                except Exception as e:
                    self.warnings.add(f"{sym}: 처리 중 오류 ({str(e)})")

            if not processed_symbols:
                raise Exception("분석 가능한 유효한 데이터가 없습니다.")

            # 2. Vectorbt Simulation
            price_df = pd.DataFrame(all_prices, index=common_index).ffill()
            exec_price_df = pd.DataFrame(all_exec_prices, index=common_index).ffill()
            entries_df = pd.DataFrame(all_entries, index=common_index).fillna(False)
            exits_df = pd.DataFrame(all_exits, index=common_index).fillna(False)

            pf = Simulator.run(price_df, exec_price_df, entries_df, exits_df, risk_params, options)

            # Check for zero trades
            if len(pf.trades) == 0:
                self.warnings.add("매매 조건에 부합하는 종목이 없어 매매 기록이 생성되지 않았습니다. 매수 조건을 확인해 주세요.")

            # 3. Format Results
            final_res = self.handler.format_results(
                pf, processed_symbols, all_entries, all_exits, 
                all_entry_reasons, all_exit_reasons, common_index, 
                risk_params, exec_type, init_cash
            )
            
            final_res["warnings"] = list(self.warnings) + list(getattr(pf, 'warnings', []))
            return final_res

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
