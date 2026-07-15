import logging
import pandas as pd
import polars as pl
from stockstats import StockDataFrame
from typing import List, Dict, Any

from engine.indicator_columns import (
    BOLLINGER_DEFAULT_STD,
    bollinger_columns,
    bollinger_params,
    macd_columns,
    stochastic_columns,
)

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
                        # 기본(12/26/9)은 stockstats 기본 컬럼, 파라미터 지정 시 macd_f,s,g 문법.
                        # 시그널 라인(macds_f,s,g)은 macd_f,s,g 접근의 부수효과로만 생성되므로
                        # 여기서 즉시 트리거해 계산 순서 의존성을 없앤다.
                        macd_col, macds_col = macd_columns(p)
                        sdf[macd_col]  # side-effect: macd/macds/macdh 변형 컬럼 생성
                        target_cols.add(macd_col)
                        target_cols.add(macds_col)
                        if macd_col == 'macd':
                            target_cols.add('macdh')
                    elif cid == 'stochastic':
                        # D는 K에서 파생되므로 K를 먼저 트리거해 순서 의존성을 없앤다
                        k_col, d_col = stochastic_columns(p)
                        sdf[k_col]
                        target_cols.add(k_col)
                        target_cols.add(d_col)
                    elif cid == 'cci':
                        period = p.get('period', 14)
                        target_cols.add(f'cci_{period}')
                    elif cid == 'adx':
                        target_cols.add('adx')
                    elif cid == 'williams_r':
                        # stockstats wr_{n}: Williams %R, 범위 -100~0 (표준). 별도 스케일 불필요.
                        period = p.get('period', 14)
                        target_cols.add(f'wr_{period}')
                    elif cid == 'mfi':
                        # stockstats mfi_{n}: 0~1 비율로 반환 → 관례적 0~100 스케일로 아래에서 ×100.
                        period = p.get('period', 14)
                        target_cols.add(f'mfi_{period}')
                    elif cid == 'roc':
                        # stockstats close_{n}_roc: n봉 전 대비 변화율(%). 모멘텀 지표.
                        period = p.get('period', 12)
                        target_cols.add(f'close_{period}_roc')
                    elif cid == 'bollinger_bands':
                        period, std_times = bollinger_params(p)
                        ub_col, lb_col = bollinger_columns(p)
                        target_cols.add(f'close_{period}_sma')
                        if std_times == BOLLINGER_DEFAULT_STD:
                            # stockstats 기본(boll_ub/boll_lb) 또는 파라미터화(boll_ub_n) 경로
                            if ub_col != 'boll_ub':
                                sdf[f'boll_{period}']  # side-effect: boll_ub_{n}/boll_lb_{n} 생성
                            target_cols.add(ub_col)
                            target_cols.add(lb_col)
                        else:
                            # 커스텀 표준편차 배수: 검증된 항등식 boll_ub == sma + K·mstd 로 직접 계산
                            sma = sdf[f'close_{period}_sma']
                            mstd = sdf[f'close_{period}_mstd']
                            sdf[ub_col] = sma + std_times * mstd
                            sdf[lb_col] = sma - std_times * mstd
                            target_cols.add(ub_col)
                            target_cols.add(lb_col)
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
                    values = sdf[c].values
                    # MFI는 stockstats가 0~1 비율로 산출 → 관례적 0~100 스케일로 정규화.
                    if c.startswith('mfi_'):
                        values = values * 100.0
                    res_pdf[c] = values
            
            res_pdf = res_pdf[final_cols]
            
            if 'date' not in res_pdf.columns:
                res_pdf = res_pdf.reset_index()
                
            log("calculate finished")
            return pl.from_pandas(res_pdf)
        except Exception as e:
            # Fix 6: logging.exception이 traceback을 자동 포함하므로 파일 I/O 불필요
            _logger.exception(f"CRITICAL ERROR in calculate: {e}")
            raise e
