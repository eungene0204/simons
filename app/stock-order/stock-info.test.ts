import { describe, expect, it } from "vitest";
import {
  mergeStockInfo,
  pickPositiveNumber,
  pickStockName,
} from "@/app/stock-order/stock-info";

describe("stock-info helpers", () => {
  it("prefers the first positive number", () => {
    expect(pickPositiveNumber(undefined, 0, -1, 125)).toBe(125);
  });

  it("ignores the stock code when resolving a display name", () => {
    expect(pickStockName("005930", "005930", "", "삼성전자")).toBe("삼성전자");
  });

  it("keeps existing market cap and volume when a refresh returns zero", () => {
    expect(
      mergeStockInfo(
        { marketCap: 418_474_470_500_000, volume: 12_345_678, previousClose: 69_000 },
        { marketCap: 0, volume: 0, previousClose: 0, currentPrice: 70_100 }
      )
    ).toMatchObject({
      marketCap: 418_474_470_500_000,
      volume: 12_345_678,
      previousClose: 69_000,
      currentPrice: 70_100,
    });
  });

  it("uses fresher positive values when they arrive", () => {
    expect(
      mergeStockInfo(
        { marketCap: 300_000_000_000_000, volume: 8_000_000 },
        { marketCap: 418_474_470_500_000, volume: 12_345_678 }
      )
    ).toMatchObject({
      marketCap: 418_474_470_500_000,
      volume: 12_345_678,
    });
  });
});
