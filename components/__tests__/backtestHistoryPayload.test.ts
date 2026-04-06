// @ts-nocheck
import { describe, expect, it } from "vitest";
import { buildAutoSaveHistoryPayload } from "@/lib/backtest-history";

const baseResult = {
  executionId: "exec-1",
  strategyId: "strategy-1",
  totalReturn: 12.3,
  cagr: 7.8,
  buyAndHoldReturn: 3.4,
  maxDrawdown: -5.6,
  winRate: 52,
  profitFactor: 1.4,
  sharpe: 1.1,
  sortino: 1.2,
  kelly: 0.1,
  trades: 14,
  finalEquity: 11230000,
  initialCapital: 10000000,
  equity: [10000000, 11230000],
  dates: ["2025-01-01", "2025-12-31"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
};

const summary = {
  strategyName: "테스트 전략",
  universeName: "KOSPI",
  entryBlocks: ["MACD"],
  exitBlocks: ["RSI"],
};

describe("buildAutoSaveHistoryPayload", () => {
  it("cacheKey가 없으면 상세 result를 함께 저장해야 함", () => {
    const payload = buildAutoSaveHistoryPayload(baseResult, summary);
    expect(payload.result).toEqual(baseResult);
    expect(payload.cacheKey).toBeUndefined();
    expect(payload.isAutoSave).toBe(true);
  });

  it("cacheKey가 있으면 기존 캐시 레코드를 사용하고 result는 중복 저장하지 않아야 함", () => {
    const payload = buildAutoSaveHistoryPayload(
      { ...baseResult, cacheKey: "cache-123" },
      summary
    );
    expect(payload.cacheKey).toBe("cache-123");
    expect(payload.result).toBeUndefined();
  });
});
