import { describe, expect, it } from "vitest";
import type { OHLCV } from "@/components/stock/CandlestickChart";
import type { StockPriceSnapshot } from "@/lib/stock-prices";
import { applyRealtimeToLatestCandle } from "@/app/stock-order/market-candles";

const parquetCandles: OHLCV[] = [
  {
    time: "2026-06-19",
    open: 350_000,
    high: 355_000,
    low: 348_000,
    close: 353_500,
    volume: 800_000,
  },
  {
    time: "2026-06-22",
    open: 354_000,
    high: 358_000,
    low: 352_500,
    close: 356_500,
    volume: 1_100_000,
  },
];

const realtimeQuote: StockPriceSnapshot = {
  date: "2026-06-23",
  price: 357_000,
  changePercent: 0.14,
  source: "kis_ws_total",
  open: 356_500,
  high: 358_000,
  low: 355_500,
  volume: 120_000,
};

describe("applyRealtimeToLatestCandle", () => {
  it("does not overwrite a completed Parquet candle", () => {
    const sameDateQuote = { ...realtimeQuote, date: "2026-06-22" };
    const result = applyRealtimeToLatestCandle(
      parquetCandles,
      sameDateQuote,
      new Date("2026-06-23T00:30:00.000Z")
    );

    expect(result).toBe(parquetCandles);
    expect(result.at(-1)?.close).toBe(356_500);
  });

  it("does not add today's candle before the NXT session starts", () => {
    const result = applyRealtimeToLatestCandle(
      parquetCandles,
      realtimeQuote,
      new Date("2026-06-22T20:57:00.000Z")
    );

    expect(result).toBe(parquetCandles);
    expect(result.at(-1)?.time).toBe("2026-06-22");
  });

  it("adds today's realtime candle after the NXT session starts", () => {
    const result = applyRealtimeToLatestCandle(
      parquetCandles,
      realtimeQuote,
      new Date("2026-06-22T23:05:00.000Z")
    );

    expect(result).toHaveLength(3);
    expect(result.at(-1)).toMatchObject({
      time: "2026-06-23",
      close: 357_000,
      volume: 120_000,
    });
    expect(parquetCandles.at(-1)?.close).toBe(356_500);
  });

  it("does not create a candle from a REST snapshot with a synthetic date", () => {
    const restQuote = { ...realtimeQuote, source: "kis_total" };
    const result = applyRealtimeToLatestCandle(
      parquetCandles,
      restQuote,
      new Date("2026-06-23T00:05:00.000Z")
    );

    expect(result).toBe(parquetCandles);
  });

  it("does not add a realtime candle on weekends", () => {
    const weekendQuote = { ...realtimeQuote, date: "2026-06-27" };
    const result = applyRealtimeToLatestCandle(
      parquetCandles,
      weekendQuote,
      new Date("2026-06-27T03:00:00.000Z")
    );

    expect(result).toBe(parquetCandles);
  });
});
