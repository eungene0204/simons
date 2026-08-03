// @ts-nocheck
/**
 * BacktestDashboard "총 수익" 0원 표시 회귀 테스트.
 *
 * 버그: 전략모음에서 저장된 백테스트를 다시 열면 총 수익이 0원으로 보였다.
 * 백엔드 엔진 응답(및 DB에 저장된 과거 기록)에는 finalEquity/initialCapital이 비어
 * 있고 totalProfit과 equity[] 배열로만 자산 규모가 전달되는데, 프론트는
 * (finalEquity||0)-(initialCapital||0)만 계산해 항상 0이 나왔다. totalProfit을
 * 우선 사용하고, finalEquity/initialCapital이 없으면 equity[]의 양끝값으로
 * 보완하도록 수정 → 회귀 고정.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import BacktestDashboard from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
  symbols: [],
  totalReturn: 202.96,
  cagr: 28.93,
  buyAndHoldReturn: 312.7,
  maxDrawdown: -32.54,
  winRate: 33.93,
  profitFactor: 1.68,
  sharpe: 1.06,
  sortino: 1.2,
  trades: 221,
  // 저장된 기록 재조회 시 실제로 관측된 형태: finalEquity/initialCapital은 undefined.
  finalEquity: undefined,
  initialCapital: undefined,
  totalProfit: 10148259.47,
  equity: [5000000, 6000000, 15148259.47],
  dates: ["2024-01-02", "2024-06-01", "2025-12-30"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

describe("BacktestDashboard 총 수익 폴백", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("finalEquity/initialCapital이 비어 있어도 totalProfit으로 총 수익을 표시한다", () => {
    render(
      <BacktestDashboard
        result={baseResult}
        onRestart={() => {}}
        disableHistorySave
        promptText="PBR 3배 이상 매수"
      />
    );

    expect(screen.getByText("총 수익")).toBeInTheDocument();
    expect(screen.getByText("10,148,259원")).toBeInTheDocument();
    expect(screen.queryByText("0원")).not.toBeInTheDocument();
  });
});
