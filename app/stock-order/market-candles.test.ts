import { describe, expect, it } from "vitest";
import type { OHLCV } from "@/components/stock/CandlestickChart";
import type { StockPriceSnapshot } from "@/lib/stock-prices";
import {
  applyRealtimeToLatestCandle,
  resolveMarketPreviousClose,
} from "@/app/stock-order/market-candles";

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

describe("resolveMarketPreviousClose", () => {
  it("uses the last candle (직전 거래일) when a REST live quote is newer than the last candle", () => {
    // kis_total 라이브: 오늘 봉이 캔들에 추가되지 않음 → 마지막 캔들(월) 종가가 전일 종가.
    // 직전 캔들(금, 353_500)을 쓰면 안 된다.
    const restQuote = { ...realtimeQuote, source: "kis_total", previousClose: undefined };
    expect(resolveMarketPreviousClose(parquetCandles, restQuote)).toBe(356_500);
  });

  it("prefers the KIS previousClose when the live quote provides it", () => {
    const restQuote = { ...realtimeQuote, source: "kis_total", previousClose: 356_500 };
    expect(resolveMarketPreviousClose(parquetCandles, restQuote)).toBe(356_500);
  });

  it("uses the prior candle when today's candle is already appended (WS)", () => {
    const appended = applyRealtimeToLatestCandle(
      parquetCandles,
      realtimeQuote,
      new Date("2026-06-22T23:05:00.000Z")
    );
    // 캔들 = [금, 월, 화(오늘)]. 오늘(화) 기준 전일 종가는 월(356_500).
    expect(resolveMarketPreviousClose(appended, realtimeQuote)).toBe(356_500);
  });

  it("falls back to the prior candle when there is no live quote", () => {
    expect(resolveMarketPreviousClose(parquetCandles, null)).toBe(353_500);
  });
});
