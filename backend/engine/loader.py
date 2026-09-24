import os
import logging
import polars as pl
import pandas as pd
import numpy as np

from .fundamental_fetcher import fetch_fundamentals, enrich_ohlcv_with_fundamentals

logger = logging.getLogger(__name__)


class DataLoader:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        # 미국 파케이는 형제 디렉터리(data/ohlcv-us) — 심볼 형태로 결정적 라우팅한다
        # (한국 6자리·숫자 시작 vs 미국 영문 시작, universe_pit.is_us_symbol).
        self.us_data_dir = os.path.join(
            os.path.dirname(os.path.normpath(data_dir)), "ohlcv-us")
        self._cache: dict[str, pl.DataFrame] = {}

    def load_symbol_data(self, symbol: str) -> pl.DataFrame:
        # Return cached data if available (avoids repeated parquet I/O during optimization)
        if symbol in self._cache:
            return self._cache[symbol]

        # 기본 디렉터리 우선, 없고 미국 티커 형태면 형제 디렉터리(ohlcv-us)로 폴백 —
        # 우선순위를 뒤집으면 테스트 픽스처 등 기본 디렉터리에 실재하는 대문자 심볼을
        # 납치한다(2026-08-25 전체 스위트 19건 실측).
        from_us = False
        file_path = os.path.join(self.data_dir, f"{symbol}.parquet")
        if not os.path.exists(file_path) and self._is_us(symbol):
            us_path = os.path.join(self.us_data_dir, f"{symbol}.parquet")
            if os.path.exists(us_path):
                file_path = us_path
                from_us = True

        if not os.path.exists(file_path):
            return None

        df = pl.read_parquet(file_path)

        # ROE 미보유 시 캐시에서 빠르게 enrichment 시도. ETF는 기업 재무제표가 없어
        # KIS 재무비율 API가 항상 실패/공백만 반환하므로 건너뛴다(불필요한 API 호출·
        # 로그 소음 방지 — universe_capabilities가 애초에 ETF엔 재무 조건을 허용하지
        # 않으므로 이 데이터는 어차피 쓰이지 않는다). 미국 종목도 건너뛴다 — KIS는
        # 한국 전용이고, 미국 재무는 EDGAR 백필이 파케이에 이미 담았다.
        if ("roe_or_gpa" not in df.columns or df["roe_or_gpa"].is_null().all()) \
                and not from_us and not self._is_etf(symbol):
            df = self._enrich_fundamentals(symbol, df)

        self._cache[symbol] = df
        return df

    @staticmethod
    def _is_etf(symbol: str) -> bool:
        from .universe_pit import is_etf_symbol
        return is_etf_symbol(symbol)

    @staticmethod
    def _is_us(symbol: str) -> bool:
        from .universe_pit import is_us_symbol
        return is_us_symbol(symbol)

    def _enrich_fundamentals(self, symbol: str, df: pl.DataFrame) -> pl.DataFrame:
        """ROE/EPS/BPS 미보유 종목을 캐시 → API 순으로 enrichment."""
        try:
            fundamentals = fetch_fundamentals(symbol)
            if not fundamentals:
                return df
            pdf = df.to_pandas()
            pdf = enrich_ohlcv_with_fundamentals(pdf, fundamentals)
            return pl.from_pandas(pdf)
        except Exception as e:
            logger.debug("[%s] fundamental enrichment skipped: %s", symbol, e)
            return df

    def clear_cache(self):
        """Clear the in-memory data cache."""
        self._cache.clear()

    def preprocess_data(self, df_pl: pl.DataFrame, apply_dividends: bool = False,
                        sanitize_corporate_actions: bool = True,
                        dividend_tax_rate: float = 0.0) -> pd.DataFrame:
        """OHLCV basic alignment and adjusting prices if needed.

        ``apply_dividends`` opt-in: when a ``dividends`` column is present, fold
        reinvested cash dividends into the OHLC series (total-return). No-op when
        the column is absent, so default behaviour is unchanged.

        ``dividend_tax_rate``(0~1): 배당소득 원천징수세율. 실제로 재투자되는 돈은 세후 배당이므로
        세전 전액을 재투자하면 장기 결과가 실제보다 유리해진다(v16.33). 0이면 종전과 동일.
        """
        pdf = df_pl.to_pandas()

        # 0. 시간순 정렬 + 중복 날짜 제거 가드 (감사 M10). 소스가 이미 정렬돼
        # 있으면 no-op이며, 중복/비정렬 데이터가 지표·사유 매핑을 깨뜨리는 것을 막는다.
        if 'date' in pdf.columns and len(pdf) > 1:
            pdf = pdf.sort_values('date', kind='stable').drop_duplicates(
                subset='date', keep='last').reset_index(drop=True)

        # 1. Handle Adjustment
        if 'adj_close' in pdf.columns:
            factor = pdf['adj_close'] / pdf['close']
            pdf['open'] *= factor
            pdf['high'] *= factor
            pdf['low'] *= factor
            pdf['close'] = pdf['adj_close']

        # 1.5 Dividend total-return adjustment (prototype, opt-in & data-driven).
        if apply_dividends and 'dividends' in pdf.columns:
            from .dividends import dividend_adjust_factor
            _net = pdf['dividends']
            if dividend_tax_rate:
                _net = _net * (1.0 - float(dividend_tax_rate))
            div_factor = dividend_adjust_factor(pdf['close'], _net)
            for c in ('open', 'high', 'low', 'close'):
                if c in pdf.columns:
                    pdf[c] = pdf[c] * div_factor.to_numpy()

        # 2. Robust Price Sanitization (vectorized across all price columns at once)
        price_cols = [c for c in ['open', 'high', 'low', 'close'] if c in pdf.columns]
        if price_cols:
            vals = pdf[price_cols].astype(float).values  # ensure NaN-safe dtype
            vals[(vals <= 0) | ~np.isfinite(vals)] = np.nan
            prices = pd.DataFrame(vals, columns=price_cols, index=pdf.index).ffill()
            # Never borrow a future bar: leading close gaps must remain unavailable.
            # Partial leading OHLC gaps may use the same bar's close without look-ahead.
            if 'close' in prices.columns:
                for c in ('open', 'high', 'low'):
                    if c in prices.columns:
                        prices[c] = prices[c].fillna(prices['close'])
            pdf[price_cols] = prices

        # 3. Corporate-action / bad-print guard (수정주가 robustness).
        # The source close is only partially adjusted: forward splits are adjusted, but
        # reverse splits / 감자 / stale-suspension resumptions are not, and the feed has the
        # odd one-day bad print. Those create impossible single-day jumps (>±30% price limit)
        # that fake out stop-losses and returns. Neutralise them so the engine sees a
        # continuous adjusted series regardless of source quality.
        # 한국 전용 — 임계(±30% 가격제한)가 한국 시장 전제이고, 미국 소스(yfinance)는
        # 역분할까지 조정된 시계열이라 여기서의 역보정은 실제 갭(실적·인수·급락)을
        # 미래 봉의 비율로 과거에서 지우는 룩어헤드가 된다. 호출자가 미국 종목이면 끈다.
        if sanitize_corporate_actions:
            pdf = self._sanitize_corporate_actions(pdf)

        pdf.set_index('date', inplace=True)
        pdf.index = pd.to_datetime(pdf.index)
        return pdf

    # Korean daily price limit is ±30%; only resumption/new-listing/정리매매 can exceed it.
    # Anything past these (generous) bounds is a corporate action or bad print, not real trade.
    _CA_JUMP_UP = 1.6     # +60%
    _CA_JUMP_DN = 0.55    # -45%
    _CA_TAIL_GUARD = 8    # never back-adjust within the final N bars (protects 정리매매 loss)

    @staticmethod
    def _sanitize_corporate_actions(pdf: pd.DataFrame) -> pd.DataFrame:
        """Ratio back-adjust split/level-shifts; neutralise transient bad prints.

        Real trades can't move a stock past the ±30% daily limit, so any larger single-day
        jump is a corporate action (reverse split / 감자 / suspension resumption) or a feed
        error, not a price the strategy could have traded.

        - Transient spike (1-day print that reverts next bar): replace the bar with neighbours.
        - Persistent level shift (price stays on the new side): scale all *prior* bars by the
          jump ratio so the discontinuity disappears (standard back-adjustment).
        - The final _CA_TAIL_GUARD bars are never back-adjusted: a 정리매매 delisting crash sits
          there and must remain a real loss on the equity curve (back-adjusting would erase it
          by rescaling the entry alongside the exit).
        """
        cols = [c for c in ['open', 'high', 'low', 'close'] if c in pdf.columns]
        if 'close' not in cols:
            return pdf
        n = len(pdf)
        if n < 6:
            return pdf

        arr = {c: pdf[c].to_numpy(dtype=float).copy() for c in cols}
        close = arr['close']
        up, dn, tail = DataLoader._CA_JUMP_UP, DataLoader._CA_JUMP_DN, DataLoader._CA_TAIL_GUARD

        # Multiple passes resolve compound / adjacent corporate actions.
        for _ in range(4):
            changed = False
            i = 1
            while i < n - 1:
                prev = close[i - 1]
                cur = close[i]
                if prev <= 0 or cur <= 0:
                    i += 1
                    continue
                r = cur / prev
                if dn <= r <= up:
                    i += 1
                    continue

                # transient bad print: jumps then reverts toward the prior level next bar
                nxt = close[i + 1]
                rev = (nxt / cur) if cur > 0 else 1.0
                if (r > up and rev < 0.7) or (r < dn and rev > 1.43):
                    for c in cols:
                        arr[c][i] = (arr[c][i - 1] + arr[c][i + 1]) / 2.0
                    changed = True
                    i += 1
                    continue

                # protect the delisting (정리매매) crash at the very end of the series.
                # 정리매매 is always a DOWN crash, so only down-jumps in the tail are shielded;
                # an up-jump (reverse split / 감자) is still adjusted even near the end.
                if r < dn and i >= n - tail:
                    i += 1
                    continue

                # persistent level shift: next bar stays on the new side (not a brief excursion)
                mid = (prev + cur) / 2.0
                persists = (cur > prev and nxt > mid) or (cur < prev and nxt < mid)
                if persists:
                    for c in cols:
                        arr[c][:i] *= r       # back-adjust the whole history before the jump
                    changed = True
                i += 1
            if not changed:
                break

        for c in cols:
            pdf[c] = arr[c]
        return pdf

    def check_liquidity(self, pdf: pd.DataFrame, target_amount: float, limit_pct: float) -> np.ndarray:
        """Check if trading volume is enough to cover the target amount."""
        data_len = len(pdf)
        if limit_pct <= 0:
            return np.ones(data_len, dtype=bool)

        vol_val = (pdf['close'] * pdf['volume']).values
        liquidity_ok = np.zeros(data_len, dtype=bool)
        # 전일 거래대금 * limit_pct% >= target_amount (벡터화)
        liquidity_ok[1:] = vol_val[:-1] * (limit_pct / 100.0) >= target_amount
        return liquidity_ok
