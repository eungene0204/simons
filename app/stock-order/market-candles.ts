import type { OHLCV } from "@/components/stock/CandlestickChart";
import type { StockPriceSnapshot } from "@/lib/stock-prices";

const NXT_SESSION_START_MINUTES = 8 * 60;

type SeoulClock = {
  date: string;
  weekday: string;
  minutes: number;
};

function getSeoulClock(now: Date): SeoulClock {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));

  return {
    date: `${values.year}-${values.month}-${values.day}`,
    weekday: values.weekday,
    minutes: Number(values.hour) * 60 + Number(values.minute),
  };
}

function canAppendRealtimeCandle(quoteDate: string, now: Date): boolean {
  const seoulClock = getSeoulClock(now);
  const isWeekday = seoulClock.weekday !== "Sat" && seoulClock.weekday !== "Sun";

  return (
    quoteDate === seoulClock.date &&
    isWeekday &&
    seoulClock.minutes >= NXT_SESSION_START_MINUTES
  );
}

export function applyRealtimeToLatestCandle(
  candles: OHLCV[] | null,
  quote?: StockPriceSnapshot | null,
  now = new Date()
): OHLCV[] {
  if (!candles || candles.length === 0) return [];
  if (!quote?.price || quote.price <= 0 || !quote.date) return candles;

  const last = candles[candles.length - 1];

  // Completed Parquet candles are immutable, even if a quote reports the same date.
  if (
    quote.date <= last.time ||
    quote.source !== "kis_ws_total" ||
    !canAppendRealtimeCandle(quote.date, now)
  ) {
    return candles;
  }

  const realtimeOpen = quote.open && quote.open > 0 ? quote.open : last.close;
  const realtimeHigh = quote.high && quote.high > 0
    ? quote.high
    : Math.max(realtimeOpen, quote.price);
  const realtimeLow = quote.low && quote.low > 0
    ? quote.low
    : Math.min(realtimeOpen, quote.price);

  return [
    ...candles,
    {
      time: quote.date,
      open: realtimeOpen,
      high: realtimeHigh,
      low: realtimeLow,
      close: quote.price,
      volume: quote.volume ?? 0,
    },
  ];
}
