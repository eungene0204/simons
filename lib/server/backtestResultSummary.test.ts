/**
 * 저장된 백테스트 요약(BacktestResult.summary) 필드 회귀 테스트.
 *
 * 승률(winRate)은 BacktestHistory.metrics 에만 들어가고 summary 에서는 빠져 있어,
 * 저장 전략 상세 화면(/analytics/[id])의 승률이 0으로 보였다.
 */
import { describe, it, expect } from "vitest";
import { buildBacktestResultSummary } from "@/lib/server/backtestResultSummary";

const RESULT = {
  totalReturn: 12.5,
  cagr: 8.1,
  maxDrawdown: -18,
  winRate: 61.2,
  profitFactor: null,
  trades: 53,
  perAssetStats: {},
};

describe("buildBacktestResultSummary", () => {
  it("승률을 요약에 담는다", () => {
    expect(buildBacktestResultSummary(RESULT).winRate).toBe(61.2);
  });

  it("손실 0건이라 정의 불가인 손익비는 null 을 그대로 둔다", () => {
    expect(buildBacktestResultSummary(RESULT).profitFactor).toBeNull();
  });

  it("AI 리포트를 함께 받으면 그 값을, 없으면 기본값을 채운다", () => {
    expect(buildBacktestResultSummary(RESULT, { aiScore: 72 }).aiScore).toBe(72);

    const withoutReport = buildBacktestResultSummary(RESULT);
    expect(withoutReport.aiScore).toBeNull();
    expect(withoutReport.aiStrengths).toEqual([]);
  });
});
