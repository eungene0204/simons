// @ts-nocheck
import { describe, expect, it } from "vitest";
import {
  buildAutoSaveHistoryPayload,
  buildHistorySummary,
  historySummaryHasContent,
} from "@/lib/backtest-history";

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

  it("프롬프트 원문을 스냅샷으로 함께 저장한다(trim, 빈 값은 undefined)", () => {
    expect(
      buildAutoSaveHistoryPayload(baseResult, summary, "  KOSPI 골든크로스 전략  ").prompt
    ).toBe("KOSPI 골든크로스 전략");
    expect(buildAutoSaveHistoryPayload(baseResult, summary, "   ").prompt).toBeUndefined();
    expect(buildAutoSaveHistoryPayload(baseResult, summary).prompt).toBeUndefined();
  });
});

describe("buildHistorySummary", () => {
  it("표시용 names 스키마를 진입/청산/포지션/리스크 배지로 변환한다", () => {
    const summary = buildHistorySummary({
      conditions: {
        entry: { logic: "AND", names: ["MA 크로스"] },
        exit: { logic: "AND", names: ["MA 크로스", "손절 -8% 하락시 매도"] },
        position: "최대 10종목",
        risk: "손절 8%, 익절 30%",
      },
      universeName: "KOSPI",
      strategyName: "골드 크로스",
    });

    expect(summary.entryBlocks).toEqual(["MA 크로스"]);
    expect(summary.exitBlocks).toEqual(["MA 크로스", "손절 -8% 하락시 매도"]);
    expect(summary.blockNames).toEqual(["MA 크로스", "MA 크로스", "손절 -8% 하락시 매도"]);
    expect(summary.positionText).toBe("최대 10종목");
    expect(summary.riskText).toBe("손절 8%, 익절 30%");
    expect(historySummaryHasContent(summary)).toBe(true);
  });

  it("raw DSL conditions만(표시용 names 없음) 가진 행은 빈 요약 → SOT 미채택 판정", () => {
    const summary = buildHistorySummary({
      conditions: {
        entry: { conditions: [{ type: "indicator", id: "ma_crossover" }] },
        exit: { conditions: [{ type: "indicator", id: "ma_crossover" }] },
      },
      universeName: "KOSPI",
      strategyName: "골드 크로스",
    });

    expect(summary.entryBlocks).toEqual([]);
    expect(summary.exitBlocks).toEqual([]);
    expect(historySummaryHasContent(summary)).toBe(false);
  });

  it("레거시 평면 conditions(배열/{logic,names})도 진입 배지로 처리한다", () => {
    expect(buildHistorySummary({ conditions: ["MACD", "RSI"] }).entryBlocks).toEqual(["MACD", "RSI"]);
    expect(
      buildHistorySummary({ conditions: { logic: "OR", names: ["거래량 급증"] } }).entryBlocks
    ).toEqual(["거래량 급증"]);
  });
});
