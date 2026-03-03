import pandas as pd
import polars as pl
from stockstats import StockDataFrame
from typing import List, Dict, Any

class IndicatorEngine:
    @staticmethod
    def calculate(df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        log_file = "backend_execution.log"
        def log(msg):
            from datetime import datetime
            with open(log_file, "a") as f:
                f.write(f"[{datetime.now()}] [IndicatorEngine] {msg}\n")
        
        log(f"calculate started with {len(conditions)} conditions")
        try:
            log("Converting polars to pandas")
            pdf = df_pl.to_pandas()
            log("Pandas conversion successful")
            orig_cols = [c.lower() for c in pdf.columns]
            pdf.columns = orig_cols
            
            # Preserve original state
            if 'date' not in pdf.columns and pdf.index.name == 'date':
                log("Resetting index")
                pdf = pdf.reset_index()
            
            log("Retyping to StockDataFrame")
            sdf = StockDataFrame.retype(pdf.copy())
            log("StockDataFrame retype successful")
            
            # Ensure we can calculate basic columns first
            target_cols = set(orig_cols)
            
            for cond in conditions:
                cid = cond.get('id')
                p = cond.get('params', {})
                log(f"Processing condition: {cid}")
                
                try:
                    if cid == 'ma_crossover':
                        short = p.get('shortMA', p.get('short_period', p.get('short', 5)))
                        long = p.get('longMA', p.get('long_period', p.get('long', 20)))
                        target_cols.add(f'close_{short}_sma')
                        target_cols.add(f'close_{long}_sma')
                    elif cid == 'rsi':
                        period = p.get('period', p.get('rsi_period', 14))
                        target_cols.add(f'rsi_{period}')
                    elif cid == 'ema':
                        period = p.get('period', 20)
                        target_cols.add(f'close_{period}_ema')
                    elif cid == 'macd':
                        target_cols.add('macd')
                        target_cols.add('macds')
                        target_cols.add('macdh')
                    elif cid == 'stochastic':
                        target_cols.add('kdjk')
                        target_cols.add('kdjd')
                    elif cid == 'cci':
                        period = p.get('period', 14)
                        target_cols.add(f'cci_{period}')
                    elif cid == 'adx':
                        target_cols.add('adx')
                    elif cid == 'bollinger_bands':
                        period = p.get('period', 20)
                        target_cols.add(f'close_{period}_sma')
                        target_cols.add('boll_ub')
                        target_cols.add('boll_lb')
                    elif cid == 'volume_spike':
                        log("Handling volume_spike (Manual OBV)")
                        # Manual OBV to avoid stockstats issues
                        close_diff = sdf['close'].diff()
                        # direction = 1 if diff > 0, -1 if diff < 0, else 0
                        direction = (close_diff > 0).astype(int) - (close_diff < 0).astype(int)
                        # First row has no diff, set to 0
                        direction.iloc[0] = 0
                        sdf['obv'] = (direction * sdf['volume']).cumsum()
                        
                        period = p.get('period', 20)
                        sdf[f'obv_{period}_sma'] = sdf['obv'].rolling(window=period).mean()
                        target_cols.add('obv')
                        target_cols.add(f'obv_{period}_sma')
                    elif cid == 'breakout':
                        log("Handling breakout")
                        period = p.get('lookbackPeriod', 20)
                        sdf[f'close_{period}_max'] = sdf['close'].rolling(window=period).max()
                        sdf[f'close_{period}_min'] = sdf['close'].rolling(window=period).min()
                        target_cols.add(f'close_{period}_max')
                        target_cols.add(f'close_{period}_min')
                except Exception as e:
                    log(f"WARNING: Indicator {cid} failed: {e}")

            # Trigger bulk calculation
            log(f"Triggering bulk calculation for {len(target_cols)} cols")
            final_cols = []
            for c in target_cols:
                try:
                    # StockDataFrame triggers calculation on access
                    if c == 'date':
                        final_cols.append(c)
                        continue
                    
                    # Accessing triggers calculation if it doesn't exist
                    _ = sdf[c]
                    final_cols.append(c)
                except Exception as e:
                    log(f"Failed to calculate {c}: {e}")
            
            log(f"Calculated {len(final_cols)} columns")
            # Convert to standard pandas to avoid stockstats __getitem__ issues with 'date'
            res_pdf = pd.DataFrame(pdf.copy())
            for c in final_cols:
                if c not in res_pdf.columns:
                    res_pdf[c] = sdf[c]
            
            res_pdf = res_pdf[final_cols]
            
            if 'date' not in res_pdf.columns:
                res_pdf = res_pdf.reset_index()
                
            log("calculate finished")
            return pl.from_pandas(res_pdf)
        except Exception as e:
            log(f"CRITICAL ERROR in calculate: {e}")
            import traceback
            with open(log_file, "a") as f:
                traceback.print_exc(file=f)
            raise e
