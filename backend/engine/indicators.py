import logging
import pandas as pd
import numpy as np
import polars as pl
from stockstats import StockDataFrame
from typing import List, Dict, Any, Optional

from engine.result_handler import KRX_TRADING_DAYS_PER_YEAR
from engine.indicator_columns import (
    BOLLINGER_DEFAULT_STD,
    bollinger_columns,
    bollinger_params,
    macd_columns,
    stochastic_columns,
)

# Fix 6: 멀티스레드 안전한 표준 logging 모듈로 교체
_logger = logging.getLogger(__name__)

def annualized_volatility_panel(raw_price_df, lookback: int):
    """종목별 연환산 변동성 패널(%) — 저변동성 랭킹용 횡단면 계산.

    입력은 **bfill 전** 원시 종가 패널이어야 한다. 상장 전 구간을 bfill로 채운 패널을
    넘기면 평평한 가짜 가격의 수익률 0이 변동성을 0으로 위장해, 신규 상장 종목이
    저변동성 최상위로 선정된다(2022-07-01 백테스트 실측: 상장 21일째 마스턴프리미어리츠가
    '120거래일 변동성 하위 7%'로 매수 — 실제로는 120일 변동성이 정의될 수 없다).
    ffill(거래정지 구간 전진 충전)만 허용하며, 수익률 관측치가 lookback개 미만인 구간은
    NaN이다(pandas rolling 기본 min_periods=window) — 후보에서 자연 배제된다.
    연환산 계수는 결과 통계와 동일한 KRX 실측 연 거래일(√246, v12.0)이다.
    """
    ret = raw_price_df.ffill().pct_change()
    return ret.rolling(lookback).std() * (KRX_TRADING_DAYS_PER_YEAR ** 0.5) * 100.0


def lookback_return_panel(raw_price_df, lookback: int, skip_days: int = 0):
    """종목별 N거래일 수익률 패널 — 모멘텀(상대강도) 랭킹용 횡단면 계산.

    입력은 **bfill 전** 원시 종가 패널이어야 한다(annualized_volatility_panel과 같은
    계약, v13.3). 상장 전 구간을 bfill로 채운 패널의 pct_change는 신규 상장 종목의
    'N일 수익률'을 상장 이후 수익률로 위장한다(2023-12-01 백테스트 실측: 상장
    10거래일째 에코프로머티가 '최근 60거래일 수익률 상위 1%'로 매수 — 60일 수익률이
    정의될 수 없는 종목). ffill(거래정지 구간 전진 충전)만 허용 — 상장 전 구간은
    NaN이 남아 첫 실봉 이후 lookback 봉이 쌓이기 전까지 NaN이고, 랭킹 후보에서
    자연 배제된다(valid = momentum.notna()).

    skip_days(v16.14): 최근 skip_days 거래일을 뺀 수익률 — '12개월 수익률에서 최근 1개월
    제외'(12-1 모멘텀)는 lookback=252, skip_days=21로 t-252 → t-21 구간 수익률이다.
    단기 반전 효과를 빼는 표준 모멘텀 정의. 0(기본)이면 종전 계산 그대로다.
    """
    if not skip_days:
        return raw_price_df.ffill().pct_change(lookback)
    if skip_days >= lookback:
        raise ValueError(f"최근 제외 기간({skip_days})은 산정 기간({lookback})보다 짧아야 합니다")
    return raw_price_df.ffill().pct_change(lookback - skip_days).shift(skip_days)


def atr_pct_panel(high_df, low_df, close_df, period: int):
    """종목별 ATR(period, 단순 평균 True Range) ÷ 종가 패널 — ATR 포지션 사이징(v16.28)용.

    창 안의 고가·저가·종가만으로 계산하므로 창 첫 period봉은 NaN이다(호출부가 동일 비중으로 대체하고
    그 횟수를 고지한다). True Range = max(고−저, |고−전일 종가|, |저−전일 종가|).
    """
    prev_close = close_df.shift(1)
    tr1 = high_df - low_df
    tr2 = (high_df - prev_close).abs()
    tr3 = (low_df - prev_close).abs()
    true_range = pd.DataFrame(np.fmax(np.fmax(tr1.values, tr2.values), tr3.values),
                              index=close_df.index, columns=close_df.columns)
    atr = true_range.rolling(int(period)).mean()
    return atr / close_df.where(close_df > 0)



# ── 다중 타임프레임(v16.29) ─────────────────────────────────────────────────
TIMEFRAMES = {"weekly": "W-FRI", "monthly": "ME"}


def timeframe_of(params: Dict[str, Any]) -> Optional[str]:
    """조건 파라미터의 타임프레임('weekly'|'monthly') — 일봉(없음)은 None."""
    tf = (params or {}).get('timeframe')
    return tf if tf in TIMEFRAMES else None


def resample_ohlcv(pdf: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """일봉 → 주봉(금요일 라벨)/월봉(월말 라벨) OHLCV. 라벨은 봉이 끝나는 날이라 그날 종가부터 보인다."""
    frame = pdf.copy()
    frame['date'] = pd.to_datetime(frame['date'])
    frame = frame.set_index('date').sort_index()
    agg = {c: f for c, f in (('open', 'first'), ('high', 'max'), ('low', 'min'), ('close', 'last'),
                             ('volume', 'sum')) if c in frame.columns}
    for extra in frame.columns:
        if extra not in agg:
            agg[extra] = 'last'
    out = frame.resample(TIMEFRAMES[timeframe]).agg(agg)
    out = out.dropna(subset=['close']) if 'close' in out.columns else out.dropna(how='all')
    return out.reset_index()


def timeframe_column(col: str, timeframe: Optional[str]) -> str:
    """타임프레임 조건의 지표 열 이름 — 일봉 열과 같은 이름 뒤에 `__weekly`/`__monthly`를 붙인다."""
    return f"{col}__{timeframe}" if timeframe else col


# ── 캔들 패턴(v16.29) ────────────────────────────────────────────────────────
CANDLE_PATTERNS = (
    "hammer", "hanging_man", "inverted_hammer", "shooting_star", "doji",
    "bullish_engulfing", "bearish_engulfing", "piercing_line", "dark_cloud_cover",
    "morning_star", "evening_star", "three_white_soldiers", "three_black_crows",
)


def candle_pattern_mask(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
                        pattern: str) -> np.ndarray:
    """OHLC 배열에서 캔들 패턴이 완성되는 봉을 True로 표시한다(그 봉 종가 기준, 미래 정보 없음).

    정의는 통상의 기술적 분석 관례를 따른다 — 몸통=|종−시|, 위꼬리=고−max(시,종), 아래꼬리=min(시,종)−저.
    망치형·역망치형은 직전 5봉 하락 뒤, 교수형·유성형은 직전 5봉 상승 뒤에만 인정한다(추세 문맥).
    '긴 몸통'은 직전 10봉 평균 몸통 이상이다. 자료가 모자란 초기 봉은 False.
    """
    n = len(c)
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    body = np.abs(c - o)
    rng = h - l
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    bull = c > o
    bear = c < o
    with np.errstate(invalid='ignore', divide='ignore'):
        avg_body = pd.Series(body).rolling(10, min_periods=5).mean().shift(1).to_numpy()
    long_body = body >= np.where(np.isfinite(avg_body), avg_body, np.inf)

    def prev(a, k=1):
        out = np.full(n, np.nan)
        if n > k:
            out[k:] = a[:-k]
        return out

    def prev_bool(a, k=1):
        out = np.zeros(n, dtype=bool)
        if n > k:
            out[k:] = a[:-k]
        return out

    c1, o1, body1, c5 = prev(c), prev(o), prev(body), prev(c, 6)
    with np.errstate(invalid='ignore'):
        down_before = c1 < c5      # 직전 봉이 6봉 전보다 낮다(하락 문맥)
        up_before = c1 > c5
        small_body = body <= 0.1 * rng
        if pattern == "doji":
            return (rng > 0) & small_body
        if pattern in ("hammer", "hanging_man"):
            # 아래꼬리 ≥ 몸통 2배, 위꼬리는 봉 길이의 1/4 이하(작은 몸통에서 위꼬리가 몸통보다 조금 길어도 망치형).
            shape = (body > 0) & (lower >= 2.0 * body) & (upper <= 0.25 * rng) & (rng > 0)
            return shape & (down_before if pattern == "hammer" else up_before)
        if pattern in ("inverted_hammer", "shooting_star"):
            shape = (body > 0) & (upper >= 2.0 * body) & (lower <= 0.25 * rng) & (rng > 0)
            return shape & (down_before if pattern == "inverted_hammer" else up_before)
        if pattern == "bullish_engulfing":
            return bull & prev_bool(bear) & (o <= c1) & (c >= o1) & (body > body1)
        if pattern == "bearish_engulfing":
            return bear & prev_bool(bull) & (o >= c1) & (c <= o1) & (body > body1)
        if pattern == "piercing_line":
            return bull & prev_bool(bear) & (o < c1) & (c > (o1 + c1) / 2.0) & (c < o1)
        if pattern == "dark_cloud_cover":
            return bear & prev_bool(bull) & (o > c1) & (c < (o1 + c1) / 2.0) & (c > o1)
        o2, c2, body2 = prev(o, 2), prev(c, 2), prev(body, 2)
        long2 = prev_bool(long_body, 2)
        if pattern == "morning_star":
            return (prev_bool(bear, 2) & long2 & (body1 <= 0.3 * body2) & bull
                    & (c > (o2 + c2) / 2.0))
        if pattern == "evening_star":
            return (prev_bool(bull, 2) & long2 & (body1 <= 0.3 * body2) & bear
                    & (c < (o2 + c2) / 2.0))
        if pattern in ("three_white_soldiers", "three_black_crows"):
            rising = pattern == "three_white_soldiers"
            d = bull if rising else bear
            step = (c > c1) if rising else (c < c1)
            inside = ((o > o1) & (o < c1)) if rising else ((o < o1) & (o > c1))
            shadow_ok = (upper <= 0.3 * body) if rising else (lower <= 0.3 * body)
            today = d & step & inside & shadow_ok
            return today & prev_bool(d & step & inside & shadow_ok, 1) & prev_bool(d, 2)
    return np.zeros(n, dtype=bool)


def _add_condition_columns(sdf, cid, p, target_cols, log) -> None:
    """조건 하나가 필요로 하는 지표 열을 StockDataFrame에 더한다(일봉·타임프레임 프레임 공용)."""
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
        elif cid == 'volatility':
            # 연환산 변동성(%): 일수익률 롤링 표준편차 × √246 × 100.
            # 연환산 계수는 결과 통계와 동일한 KRX 실측 연 거래일(v12.0 정정)을
            # 쓴다 — 결과 화면의 '변동성'과 같은 눈금이라 임계값이 비교 가능하다.
            # stockstats에 없는 지표라 breakout처럼 직접 계산한다.
            period = p.get('period', 60)
            ret = sdf['close'].pct_change()
            sdf[f'volatility_{period}'] = (
                ret.rolling(window=period).std()
                * (KRX_TRADING_DAYS_PER_YEAR ** 0.5) * 100.0
            )
            target_cols.add(f'volatility_{period}')
        elif cid == 'relative_return':
            # 시장 대비 초과수익률(%p): 종목 N봉 수익률 − 비교 지수 N봉 수익률.
            # 지수 종가(index_close)는 engine/market_index.attach_index_close가
            # 종목의 상장 시장 지수를 날짜 조인으로 미리 붙인다 — 이 엔진은 심볼을
            # 모르므로 컬럼이 없으면 NaN을 남겨 조건이 fail-closed(False)로 떨어진다.
            # stockstats에 없는 지표라 volatility처럼 직접 계산한다.
            period = p.get('period', 60)
            col = f'relative_return_{period}'
            if 'index_close' in sdf.columns:
                stock_ret = sdf['close'].pct_change(period)
                index_ret = sdf['index_close'].astype(float).pct_change(period)
                sdf[col] = (stock_ret - index_ret) * 100.0
            else:
                sdf[col] = float('nan')
            target_cols.add(col)
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
        elif cid == 'volume_ratio':
            # 거래량 배수(v16.10): 당일 거래량 ÷ **직전** N일 평균 거래량. 평균에서
            # 당일을 빼는 이유는 '평소 대비'의 평소가 오늘을 포함하면 배수가 자기
            # 자신에 희석되기 때문이다(HTS '거래량 평균 대비'와 같은 정의).
            # 신호 판정(signals.py)은 배수 임계값과 부등호로 비교한다.
            period = p.get('period', 20)
            col = f'volume_{period}_prev_sma'
            sdf[col] = sdf['volume'].rolling(window=period).mean().shift(1)
            target_cols.add(col)
        elif cid == 'trading_value_ratio':
            # 거래대금 배수(v16.13): 당일 거래대금 ÷ **직전** N일 평균 거래대금.
            # 거래대금은 trading_value 지표와 같은 정의(종가 × 거래량)이고, 당일을
            # 평균에서 빼는 이유는 volume_ratio와 같다.
            period = p.get('period', 20)
            col = f'trading_value_{period}_prev_sma'
            tv = sdf['close'] * sdf['volume']
            sdf[col] = tv.rolling(window=period).mean().shift(1)
            target_cols.add(col)
        elif cid == 'breakout':
            log("Handling breakout")
            period = p.get('lookbackPeriod', 20)
            # min_periods=1: 데이터가 period보다 적어도 가용 데이터로 계산
            # (예: 52주=252일 breakout에서 신규 상장 종목도 유효한 값 생성)
            sdf[f'high_{period}_max'] = sdf['high'].rolling(window=period, min_periods=1).max()
            sdf[f'low_{period}_min'] = sdf['low'].rolling(window=period, min_periods=1).min()
            target_cols.add(f'high_{period}_max')
            target_cols.add(f'low_{period}_min')
        elif cid == 'candle_pattern':
            # 캔들 패턴(v16.29): 완성 봉에 True. 열 이름 candle_<pattern>(0/1).
            pattern = str(p.get('pattern') or '')
            if pattern in CANDLE_PATTERNS:
                col = f'candle_{pattern}'
                mask = candle_pattern_mask(sdf['open'].values, sdf['high'].values,
                                           sdf['low'].values, sdf['close'].values, pattern)
                sdf[col] = mask.astype(float)
                target_cols.add(col)
    except Exception as e:
        log(f"WARNING: Indicator {cid} failed: {e}")


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
            
            tf_frames: Dict[str, tuple] = {}
            for cond in conditions:
                cid = cond.get('id')
                p = cond.get('params', {})
                log(f"Processing condition: {cid}")
                tf = timeframe_of(p)
                if tf:
                    # 다중 타임프레임(v16.29): 주봉·월봉 프레임에서 같은 지표를 계산해 아래에서 일봉에 맞춘다.
                    if tf not in tf_frames:
                        tf_pdf = resample_ohlcv(pdf, tf)
                        tf_frames[tf] = (tf_pdf, StockDataFrame.retype(tf_pdf.copy()),
                                         {c for c in ('open', 'high', 'low', 'close', 'volume') if c in tf_pdf.columns})
                    _add_condition_columns(tf_frames[tf][1], cid, p, tf_frames[tf][2], log)
                else:
                    _add_condition_columns(sdf, cid, p, target_cols, log)

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
            if tf_frames:
                daily_dates = pd.to_datetime(pdf['date'])
                for tf, (tf_pdf, tf_sdf, tf_cols) in tf_frames.items():
                    tf_index = pd.DatetimeIndex(pd.to_datetime(tf_pdf['date']))
                    for c in tf_cols:
                        try:
                            values = tf_sdf[c].values
                        except Exception as e:
                            log(f"Failed to calculate {c}@{tf}: {e}")
                            continue
                        if c.startswith('mfi_'):
                            values = values * 100.0
                        ser = pd.Series(np.asarray(values, dtype=float), index=tf_index)
                        # 봉 라벨(끝나는 날)부터 다음 봉 전까지 같은 값 — 미완성 봉은 보이지 않는다.
                        res_pdf[timeframe_column(c, tf)] = ser.reindex(daily_dates, method='ffill').to_numpy()
            
            if 'date' not in res_pdf.columns:
                res_pdf = res_pdf.reset_index()
                
            log("calculate finished")
            return pl.from_pandas(res_pdf)
        except Exception as e:
            # Fix 6: logging.exception이 traceback을 자동 포함하므로 파일 I/O 불필요
            _logger.exception(f"CRITICAL ERROR in calculate: {e}")
            raise e
