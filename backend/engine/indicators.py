import pandas as pd
import polars as pl
from stockstats import StockDataFrame
from typing import List, Dict, Any

class IndicatorEngine:
    @staticmethod
    def calculate(df_pl: pl.DataFrame, conditions: List[Dict[str, Any]]) -> pl.DataFrame:
        pdf = df_pl.to_pandas()
        # Preserve original Close before stockstats conversion
        if 'date' not in pdf.columns and pdf.index.name == 'date':
            pdf = pdf.reset_index()
            
        sdf = StockDataFrame.retype(pdf.copy())
        
        for cond in conditions:
            cid = cond.get('id')
            p = cond.get('params', {})
            
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
                _ = sdf[f'boll_ub']
                _ = sdf[f'boll_lb']
            elif cid == 'volume_spike':
                _ = sdf['obv']
                # Pre-calculate SMA for OBV if needed
                period = p.get('period', 20)
                sdf[f'obv_{period}_sma'] = sdf['obv'].rolling(window=period).mean()
            elif cid == 'breakout':
                period = p.get('lookbackPeriod', 20)
                sdf[f'close_{period}_max'] = sdf['close'].rolling(window=period).max()
                sdf[f'close_{period}_min'] = sdf['close'].rolling(window=period).min()
        
        res_pdf = pd.DataFrame(sdf)
        if 'date' not in res_pdf.columns:
            res_pdf = res_pdf.reset_index()
            
        return pl.from_pandas(res_pdf)
