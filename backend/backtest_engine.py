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
        self.simulator = Simulator()
        
        # Load AI Engine lazily
        self._ai_engine = None

    @property
    def ai_engine(self):
        if self._ai_engine is None:
            from ai.ai_engine import AIEngine
            try:
                self._ai_engine = AIEngine()
            except Exception as e:
                print(f"[ERROR] Failed to initialize AIEngine: {e}", flush=True)
                self._ai_engine = "FAILED"
        return None if self._ai_engine == "FAILED" else self._ai_engine

    def run_backtest(self, req: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 1. Parameter Extraction
            self.warnings = set()
            symbols = req.get('symbols') or [req.get('symbol')]
            if not symbols or symbols == [None]:
                symbols = []
                
            # Risk & Options
            risk_params = req.get('risk_params') or req.get('risk') or {}
            
            # Explicitly check for None to allow 0 values
            init_cash_raw = risk_params.get('init_cash') or risk_params.get('initial_cash')
            init_cash = float(init_cash_raw) if init_cash_raw is not None else 10000000.0
            
            pos_size_raw = risk_params.get('position_size_pct')
            pos_size_pct = float(pos_size_raw) if pos_size_raw is not None else 100.0
            
            liquid_limit_raw = risk_params.get('liquidity_limit_pct')
            liquid_limit = float(liquid_limit_raw) if liquid_limit_raw is not None else 10.0
            
            options = req.get('options', {})
            exec_type = options.get('execution_type', 'next_open') 
            
            period_req = req.get('period', 'full')
            start_date_req = req.get('startDate')
            end_date_req = req.get('endDate')

            # Detect if AI is needed
            def check_ai_needed(group):
                if not group: return False
                for c in group.get('conditions', []):
                    if c.get('id') == 'ai_model': return True
                    if 'conditions' in c:
                        if check_ai_needed(c): return True
                return False
            
            ai_needed = check_ai_needed(req.get('entry')) or check_ai_needed(req.get('exit'))

            # Reference date for relative periods
            ref_date = pd.to_datetime(end_date_req) if end_date_req else pd.to_datetime('today').normalize()

            # 2. Data Structures for Vectorbt
            all_prices, all_exec_prices, all_entries, all_exits = {}, {}, {}, {}
            all_entry_reasons, all_exit_reasons = {}, {}
            all_ranks = {'pbr': {}, 'roe': {}}
            processed_symbols = []
            common_index = None

            # Pre-load AI engine to avoid race conditions during lazy loading
            if ai_needed:
                self.ai_engine

            def _process_symbol(sym):
                try:
                    # 1.1 Load Data
                    df_pl = self.loader.load_symbol_data(sym)
                    if df_pl is None or len(df_pl) == 0:
                        return None
                    
                    # 3.2 Indicators
                    indicators = []
                    def collect_indicators(group):
                        if not group: return
                        for c in group.get('conditions', []):
                            if 'conditions' in c: collect_indicators(c)
                            else: indicators.append(c)
                    
                    collect_indicators(req.get('entry'))
                    collect_indicators(req.get('exit'))
                    df_pl = self.indicator_engine.calculate(df_pl, indicators)

                    # 3.3 AI Model Inference
                    if ai_needed:
                        engine = self.ai_engine
                        if engine:
                            pdf_ai = df_pl.to_pandas()
                            ai_probs = engine.predict_signals(pdf_ai)
                            df_pl = df_pl.with_columns(pl.Series("ai_score", ai_probs))
                        else:
                            df_pl = df_pl.with_columns(pl.Series("ai_score", [0.0] * len(df_pl)))
                    
                    # 3.4 Period Filtering
                    if period_req != 'full' or start_date_req or end_date_req:
                        if start_date_req: 
                            df_pl = df_pl.filter(pl.col("date") >= pd.to_datetime(start_date_req))
                        elif period_req == '6M': 
                            df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(months=6)))
                        elif period_req == '1Y': 
                            df_pl = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=1)))
                        elif period_req in ['5Y', '10Y', '20Y']:
                            y = int(period_req[:-1])
                            df_pl = df_pl.filter(pl.col("date") >= pd.Timestamp(year=ref_date.year - (y-1), month=1, day=1))
                        
                        if end_date_req: 
                            df_pl = df_pl.filter(pl.col("date") <= ref_date)
                        else:
                            df_pl = df_pl.filter(pl.col("date") <= ref_date)

                    if len(df_pl) < 1:
                        return None

                    # 3.5 Preprocessing (Adjusted Prices)
                    pdf = self.loader.preprocess_data(df_pl)
                    
                    # 3.6 Liquidity Check
                    target_pos_amount = init_cash * (pos_size_pct / 100.0)
                    liquidity_ok = self.loader.check_liquidity(pdf, target_pos_amount, liquid_limit)
                    if liquidity_ok.sum() == 0:
                        return ("warning", f"{sym}: 유동성 기준 미달 (거래대금 부족)")

                    # 3.7 Signal Generation
                    entry_signals, entry_reasons = self.signal_engine.generate_signals(df_pl, req.get('entry'))
                    exit_signals, exit_reasons = self.signal_engine.generate_signals(df_pl, req.get('exit'))
                    
                    if entry_signals is None: 
                        return None
                    
                    # Return result package
                    res = {
                        "symbol": sym,
                        "price": pdf['close'],
                        "exec_price": pdf['open'],
                        "entries": pd.Series(entry_signals, index=pdf.index),
                        "exits": pd.Series(exit_signals, index=pdf.index),
                        "entry_reasons": pd.Series(entry_reasons, index=pdf.index),
                        "exit_reasons": pd.Series(exit_reasons, index=pdf.index),
                        "index": pdf.index
                    }
                    if 'pbr' in pdf.columns: res["pbr"] = pdf['pbr']
                    if 'roe_or_gpa' in pdf.columns: res["roe"] = pdf['roe_or_gpa']
                    return ("success", res)

                except Exception as e:
                    return ("warning", f"{sym}: 처리 오류 ({e})")

            import concurrent.futures
            # Limit workers to avoid too many threads (e.g., CPU count * 2 or fixed number)
            # AI Inference is heavy on CPU, but loading is I/O.
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                future_to_sym = {executor.submit(_process_symbol, sym): sym for sym in symbols}
                for future in concurrent.futures.as_completed(future_to_sym):
                    result = future.result()
                    if result is None: continue
                    
                    status, data = result
                    if status == "warning":
                        self.warnings.add(data)
                    if status == "success":
                        sym = data["symbol"]
                        
                        all_prices[sym] = data["price"]
                        all_exec_prices[sym] = data["exec_price"]
                        all_entries[sym] = data["entries"]
                        all_exits[sym] = data["exits"]
                        all_entry_reasons[sym] = data["entry_reasons"]
                        all_exit_reasons[sym] = data["exit_reasons"]
                        
                        if "pbr" in data: all_ranks['pbr'][sym] = data["pbr"]
                        if "roe" in data: all_ranks['roe'][sym] = data["roe"]
                        processed_symbols.append(sym)

            # 4. Simulation
            if not processed_symbols:
                raise Exception("분석 가능한 유효한 데이터가 없습니다.")

            # Let pandas infer the united index across all symbols
            price_df = pd.DataFrame(all_prices).sort_index()
            common_index = price_df.index
            
            price_df = price_df.ffill().bfill()
            exec_px_df = pd.DataFrame(all_exec_prices, index=common_index).ffill().bfill()
            ents_df = pd.DataFrame(all_entries, index=common_index).fillna(False)
            exts_df = pd.DataFrame(all_exits, index=common_index).fillna(False)

            rank_df = None
            if risk_params.get('ranking_enabled', True) and all_ranks['pbr'] and all_ranks['roe']:
                try:
                    pbr_df = pd.DataFrame(all_ranks['pbr'], index=common_index).ffill().fillna(1.0)
                    roe_df = pd.DataFrame(all_ranks['roe'], index=common_index).ffill().fillna(0.0)
                    v_score = 1.0 - pbr_df.rank(axis=1, pct=True)
                    q_score = roe_df.rank(axis=1, pct=True)
                    w_v = float(risk_params.get('ranking_weight_value', 0.5))
                    w_q = float(risk_params.get('ranking_weight_quality', 0.5))
                    rank_df = (v_score * w_v) + (q_score * w_q)
                except:
                    rank_df = None

            pf = self.simulator.run(price_df, exec_px_df, ents_df, exts_df, risk_params, options, rank_df=rank_df)
            
            # 5. Format
            final = self.handler.format_results(pf, processed_symbols, all_entries, all_exits, all_entry_reasons, all_exit_reasons, common_index, risk_params, exec_type, init_cash)
            final["warnings"] = list(self.warnings) + list(getattr(pf, 'warnings', []))
            return final

        except Exception as e:
            import traceback; traceback.print_exc()
            raise e
