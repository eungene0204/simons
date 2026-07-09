import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import BacktestSummaryCard from "./BacktestSummaryCard";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

const baseResult = {
  cacheKey: "ck-1",
  cagr: 12,
  profitFactor: 1.8,
  maxDrawdown: 14,
  sharpe: 1.1,
  calmar: 0.9,
  equity: [100, 101, 102, 103],
} as any;

describe("BacktestSummaryCard", () => {
  it("AI 리포트에서 advisor 평가 점수 문구를 숨기고 리스크 진단은 유지한다", () => {
    render(
      <BacktestSummaryCard
        result={baseResult}
        initialSummary="요약"
        initialScore={80}
        initialStrengths={["장점"]}
        initialWeaknesses={["단점"]}
        initialImprovements={["개선점"]}
        initialAdvisorScore={80}
        initialRiskScore={35}
        initialOverfitRisk="low"
      />
    );

    expect(screen.getByText("리스크 점수")).toBeInTheDocument();
    expect(screen.getByText("과적합 위험")).toBeInTheDocument();
    expect(screen.queryByText(/Advisor 전략 평가 점수/)).toBeNull();
  });
});
