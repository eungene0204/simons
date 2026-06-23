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

/**
 * 전일 종가를 결정한다.
 *
 * 비-WS 라이브 소스(kis_total 등)는 applyRealtimeToLatestCandle가 오늘 봉을 캔들에
 * 추가하지 않는다. 그래서 라이브 시세 날짜가 마지막 캔들보다 최신이면(= 오늘 봉이 아직
 * OHLCV에 없음) 마지막 캔들이 직전 거래일이고 그 종가가 전일 종가다. 이때 직전 캔들
 * (= 이틀 전)을 전일 종가로 쓰면 안 된다. KIS가 내려준 previousClose가 있으면 우선한다.
 *
 * 그 외(오늘 봉이 이미 캔들에 있거나 라이브 시세가 없음)에는 직전 캔들 종가를 쓴다.
 */
export function resolveMarketPreviousClose(
  candles: OHLCV[],
  quote?: StockPriceSnapshot | null
): number | undefined {
  if (candles.length === 0) return undefined;
  const last = candles[candles.length - 1];
  const liveIsNewerThanLastCandle = !!quote?.date && quote.date > last.time;
  if (liveIsNewerThanLastCandle) {
    return quote?.previousClose && quote.previousClose > 0
      ? quote.previousClose
      : last.close;
  }
  const prev = candles[candles.length - 2];
  return prev ? prev.close : last.close;
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
