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
        self._cache: dict[str, pl.DataFrame] = {}

    def load_symbol_data(self, symbol: str) -> pl.DataFrame:
        # Return cached data if available (avoids repeated parquet I/O during optimization)
        if symbol in self._cache:
            return self._cache[symbol]

        file_path = os.path.join(self.data_dir, f"{symbol}.parquet")

        if not os.path.exists(file_path):
            return None

        df = pl.read_parquet(file_path)

        # ROE 미보유 시 캐시에서 빠르게 enrichment 시도
        if "roe_or_gpa" not in df.columns or df["roe_or_gpa"].is_null().all():
            df = self._enrich_fundamentals(symbol, df)

        self._cache[symbol] = df
        return df

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

    def preprocess_data(self, df_pl: pl.DataFrame, apply_dividends: bool = False) -> pd.DataFrame:
        """OHLCV basic alignment and adjusting prices if needed.

        ``apply_dividends`` opt-in: when a ``dividends`` column is present, fold
        reinvested cash dividends into the OHLC series (total-return). No-op when
        the column is absent, so default behaviour is unchanged.
        """
        pdf = df_pl.to_pandas()

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
            div_factor = dividend_adjust_factor(pdf['close'], pdf['dividends'])
            for c in ('open', 'high', 'low', 'close'):
                if c in pdf.columns:
                    pdf[c] = pdf[c] * div_factor.to_numpy()

        # 2. Robust Price Sanitization (vectorized across all price columns at once)
        price_cols = [c for c in ['open', 'high', 'low', 'close'] if c in pdf.columns]
        if price_cols:
            vals = pdf[price_cols].astype(float).values  # ensure NaN-safe dtype
            vals[(vals <= 0) | ~np.isfinite(vals)] = np.nan
            # ffill + bfill via pandas (operates on contiguous block)
            pdf[price_cols] = pd.DataFrame(vals, columns=price_cols, index=pdf.index).ffill().bfill()

        # 3. Corporate-action / bad-print guard (수정주가 robustness).
        # The source close is only partially adjusted: forward splits are adjusted, but
        # reverse splits / 감자 / stale-suspension resumptions are not, and the feed has the
        # odd one-day bad print. Those create impossible single-day jumps (>±30% price limit)
        # that fake out stop-losses and returns. Neutralise them so the engine sees a
        # continuous adjusted series regardless of source quality.
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
