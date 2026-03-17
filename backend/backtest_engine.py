import os
import polars as pl
import pandas as pd
from typing import Dict, List, Any

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

    def calculate_indicators(self, df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        """Compatibility method for tests."""
        return self.indicator_engine.calculate(df_pl, conditions)

    def run_backtest(self, req: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 1. Parameter Extraction
            self.warnings = set()
            symbols = req.get('symbols') or [req.get('symbol')]
            if not symbols or symbols == [None]:
                symbols = []
                
            # Risk & Options
            risk_params = req.get('risk_params') or req.get('risk') or {}
            
            # Fix 9: or 연산자는 0.0을 falsy로 취급하므로 명시적 None 체크로 교체
            init_cash_raw = risk_params.get('init_cash')
            if init_cash_raw is None:
                init_cash_raw = risk_params.get('initial_cash')
            init_cash = float(init_cash_raw) if init_cash_raw is not None else 10000000.0

            pos_size_raw = risk_params.get('position_size_pct')
            pos_size_pct = float(pos_size_raw) if pos_size_raw is not None else 100.0

            liquid_limit_raw = risk_params.get('liquidity_limit_pct')
            if liquid_limit_raw is None:
                liquid_limit_raw = risk_params.get('liquidity_multiplier')
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
                    if c.get('id') in ['ai_model', 'ai_drop_model']: return True
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
                            ai_probs, ai_drop_probs = engine.predict_signals(pdf_ai)
                            df_pl = df_pl.with_columns([
                                pl.Series("ai_score", ai_probs),
                                pl.Series("ai_drop_score", ai_drop_probs)
                            ])
                        else:
                            df_pl = df_pl.with_columns([
                                pl.Series("ai_score", [0.0] * len(df_pl)),
                                pl.Series("ai_drop_score", [0.0] * len(df_pl))
                            ])
                    
                    # 3.4 Period Filtering
                    # date 컬럼이 Utf8(문자열) 또는 Date 타입 모두에 대응하기 위해
                    # 필터 값을 "YYYY-MM-DD" 문자열로 통일하고 컬럼도 Utf8로 캐스팅
                    def _ts_str(ts) -> str:
                        if isinstance(ts, str):
                            return pd.to_datetime(ts).strftime("%Y-%m-%d")
                        return ts.strftime("%Y-%m-%d")

                    if period_req != 'full' or start_date_req or end_date_req:
                        date_col = pl.col("date").cast(pl.Utf8)
                        if start_date_req:
                            df_pl = df_pl.filter(date_col >= _ts_str(start_date_req))
                        elif period_req == '6M':
                            df_pl = df_pl.filter(date_col >= _ts_str(ref_date - pd.DateOffset(months=6)))
                        elif period_req == '1Y':
                            df_pl = df_pl.filter(date_col >= _ts_str(ref_date - pd.DateOffset(years=1)))
                        elif period_req in ['5Y', '10Y', '20Y']:
                            y = int(period_req[:-1])
                            df_pl = df_pl.filter(date_col >= _ts_str(pd.Timestamp(year=ref_date.year - (y-1), month=1, day=1)))

                        # Fix 2: 두 분기가 동일했던 중복 코드 제거
                        df_pl = df_pl.filter(date_col <= _ts_str(ref_date))

                    if len(df_pl) < 1:
                        return None

                    # 3.5 Preprocessing (Adjusted Prices)
                    pdf = self.loader.preprocess_data(df_pl)
                    
                    # 3.6 Liquidity Check
                    skip_risk = risk_params.get('skip_risk_management', False)
                    skip_pos = risk_params.get('skip_position_setting', False)
                    
                    if not (skip_risk or skip_pos):
                        target_pos_amount = init_cash * (pos_size_pct / 100.0)
                        liquidity_ok = self.loader.check_liquidity(pdf, target_pos_amount, liquid_limit)
                        if liquidity_ok.sum() == 0:
                            return ("warning", f"{sym}: 유동성 기준 미달 (거래대금 부족)")

                    # 3.7 Signal Generation
                    entry_signals, entry_reasons = self.signal_engine.generate_signals(df_pl, req.get('entry'))
                    exit_signals, exit_reasons = self.signal_engine.generate_signals(df_pl, req.get('exit'))

                    # 재무 필터 데이터 누락 경고 (첫 번째 심볼에서만 한 번 확인)
                    FUNDAMENTAL_IDS = {'per', 'pbr', 'roe_or_gpa', 'debt_ratio', 'market_cap'}
                    all_conditions = list(req.get('entry', {}).get('conditions', [])) + list(req.get('exit', {}).get('conditions', []))
                    missing_funds = [c['id'] for c in all_conditions if c.get('id') in FUNDAMENTAL_IDS and c['id'] not in df_pl.columns]
                    if missing_funds:
                        self.warnings.add(f"재무 데이터({', '.join(set(missing_funds))}) 없음 — 해당 필터는 무시되었습니다. 백테스트는 기술적 신호만으로 실행됩니다.")
                    
                    # Apply Liquidity Mask
                    if not (skip_risk or skip_pos):
                        entry_signals = entry_signals & liquidity_ok
                    
                    if entry_signals is None: 
                        return None
                    
                    # Return result package
                    res = {
                        "symbol": sym,
                        "price": pdf['close'],
                        "exec_price": pdf['close'] if exec_type == 'same_close' else pdf['open'],
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
            import os
            
            # Maximize threads for I/O and pre-processing. The global lock in AIEngine will protect the GPU/CPU Inference.
            max_threads = min(32, (os.cpu_count() or 1) + 4)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
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

            # Determinism: Sort symbols so column order is always the same
            processed_symbols.sort()
            
            # Create DataFrames with explicit sorted column list
            price_df = pd.DataFrame(all_prices, columns=processed_symbols).sort_index()
            common_index = price_df.index
            
            price_df = price_df.ffill().bfill()
            exec_px_df = pd.DataFrame(all_exec_prices, index=common_index, columns=processed_symbols).ffill().bfill()
            ents_df = pd.DataFrame(all_entries, index=common_index, columns=processed_symbols).fillna(False)
            exts_df = pd.DataFrame(all_exits, index=common_index, columns=processed_symbols).fillna(False)

            if exec_type == 'next_open':
                ents_df = ents_df.shift(1).fillna(False)
                exts_df = exts_df.shift(1).fillna(False)

            rank_df = None
            skip_pos = risk_params.get('skip_position_setting', False)
            if (not skip_pos) and risk_params.get('ranking_enabled', True) and all_ranks['pbr'] and all_ranks['roe']:
                try:
                    pbr_df = pd.DataFrame(all_ranks['pbr'], index=common_index, columns=processed_symbols).ffill().fillna(1.0)
                    roe_df = pd.DataFrame(all_ranks['roe'], index=common_index, columns=processed_symbols).ffill().fillna(0.0)
                    
                    if exec_type == 'next_open':
                        pbr_df = pbr_df.shift(1).ffill()
                        roe_df = roe_df.shift(1).ffill()

                    v_score = 1.0 - pbr_df.rank(axis=1, pct=True)
                    q_score = roe_df.rank(axis=1, pct=True)
                    w_v = float(risk_params.get('ranking_weight_value', 0.5))
                    w_q = float(risk_params.get('ranking_weight_quality', 0.5))
                    rank_df = (v_score * w_v) + (q_score * w_q)
                except Exception as e:
                    # Fix 12: 무음 예외 대신 경고 로깅으로 원인 추적 가능하게
                    import logging
                    logging.getLogger(__name__).warning(f"[BacktestEngine] 랭킹 계산 실패: {e}")
                    rank_df = None

            pf = self.simulator.run(price_df, exec_px_df, ents_df, exts_df, risk_params, options, rank_df=rank_df)
            
            # 5. Format
            final = self.handler.format_results(pf, processed_symbols, all_entries, all_exits, all_entry_reasons, all_exit_reasons, common_index, risk_params, exec_type, init_cash)
            
            # Add no-trades warning
            if pf.trades.count() == 0:
                self.warnings.add("매매 조건에 부합하는 종목이 없어 매매 기록이 생성되지 않았습니다. 매수 조건을 확인해 주세요.")
                
            final["warnings"] = list(self.warnings) + list(getattr(pf, 'warnings', []))
            return final

        except Exception as e:
            import traceback; traceback.print_exc()
            raise e
