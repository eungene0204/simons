import logging
import pandas as pd
import polars as pl
from stockstats import StockDataFrame
from typing import List, Dict, Any

# Fix 6: 멀티스레드 안전한 표준 logging 모듈로 교체
_logger = logging.getLogger(__name__)

class IndicatorEngine:
    @staticmethod
    def calculate(df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        log = _logger.debug   # 한 줄 alias — 호출부 변경 불필요

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
                        short_p = p.get('shortPeriod', p.get('short'))
                        long_p = p.get('longPeriod', p.get('long'))
                        if short_p is not None and long_p is not None:
                            target_cols.add(f'close_{int(short_p)}_ema')
                            target_cols.add(f'close_{int(long_p)}_ema')
                        else:
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
                        # min_periods=1: 데이터가 period보다 적어도 가용 데이터로 계산
                        # (예: 52주=252일 breakout에서 신규 상장 종목도 유효한 값 생성)
                        sdf[f'high_{period}_max'] = sdf['high'].rolling(window=period, min_periods=1).max()
                        sdf[f'low_{period}_min'] = sdf['low'].rolling(window=period, min_periods=1).min()
                        target_cols.add(f'high_{period}_max')
                        target_cols.add(f'low_{period}_min')
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
                    sdf[c]  # side-effect: stockstats computes and caches the column
                    final_cols.append(c)
                except Exception as e:
                    log(f"Failed to calculate {c}: {e}")
            
            log(f"Calculated {len(final_cols)} columns")
            # Convert to standard pandas to avoid stockstats __getitem__ issues with 'date'
            res_pdf = pd.DataFrame(pdf.copy())
            for c in final_cols:
                if c not in res_pdf.columns:
                    # Use .values to ignore index alignment since sdf index is 'date' but res_pdf is RangeIndex
                    res_pdf[c] = sdf[c].values
            
            res_pdf = res_pdf[final_cols]
            
            if 'date' not in res_pdf.columns:
                res_pdf = res_pdf.reset_index()
                
            log("calculate finished")
            return pl.from_pandas(res_pdf)
        except Exception as e:
            # Fix 6: logging.exception이 traceback을 자동 포함하므로 파일 I/O 불필요
            _logger.exception(f"CRITICAL ERROR in calculate: {e}")
            raise e
