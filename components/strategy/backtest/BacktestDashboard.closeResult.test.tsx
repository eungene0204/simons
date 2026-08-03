// @ts-nocheck
/**
 * 백테스트 결과 화면 "결과 닫기" 배지 회귀 테스트.
 *
 * 버그: 전략연구소에서 백테스트를 실행한 뒤 다른 페이지로 이동했다가 돌아오면
 * 결과 화면이 사라졌고(세션 스냅샷이 nav 클릭 시 삭제됨), 결과 화면 자체에는
 * 이를 닫고 전략연구소 초기 화면으로 돌아갈 방법이 없었다. onRestart prop이
 * 컴포넌트에 실제로 배선되지 않아 "결과 닫기" 동작이 불가능했던 문제를 수정 →
 * 배지 클릭 시 onRestart가 호출되는지로 회귀 고정.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";

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
  finalEquity: 15148259.47,
  initialCapital: 5000000,
  totalProfit: 10148259.47,
  equity: [5000000, 6000000, 15148259.47],
  dates: ["2024-01-02", "2024-06-01", "2025-12-30"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

describe("BacktestDashboard 결과 닫기 배지", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("결과 닫기 배지를 클릭하면 onRestart가 호출된다", () => {
    const onRestart = vi.fn();
    render(
      <BacktestDashboard
        result={baseResult}
        onRestart={onRestart}
        disableHistorySave
      />
    );

    fireEvent.click(screen.getByText("결과 닫기"));

    expect(onRestart).toHaveBeenCalledTimes(1);
  });
});
