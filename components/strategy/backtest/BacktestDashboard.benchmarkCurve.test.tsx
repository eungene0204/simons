// @ts-nocheck
/**
 * 자산곡선 차트에 벤치마크 라인을 함께 그리는지 고정하는 테스트.
 *
 * 대시보드는 result.benchmarkEquity를 차트에 넘기지 않아 벤치마크 라인이 아예
 * 그려지지 않았다. 배선하면서 주의할 점: 벤치마크 지수가 존재하지 않는 구간은
 * null로 내려오는데(엔진 v11.0), 차트의 필터는 isFinite(null)===true라 null을
 * 0원으로 그려 가짜 폭락 구간을 만든다 → undefined로 변환해 건너뛰게 한다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, cleanup } from "@testing-library/react";

const chartCalls: any[] = [];

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({
  default: (props: any) => {
    chartCalls.push(props);
    return null;
  },
}));
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
  totalReturn: 12.3,
  cagr: 5.1,
  buyAndHoldReturn: 8.4,
  maxDrawdown: -10.2,
  winRate: 55,
  profitFactor: 1.4,
  sharpe: 0.9,
  sortino: 1.1,
  trades: 12,
  finalEquity: 11230000,
  initialCapital: 10000000,
  equity: [10000000, 10500000, 11230000],
  // 첫 날은 벤치마크 지수 미상장 구간 → null
  benchmarkEquity: [null, 10200000, 10840000],
  benchmarkLabel: "KODEX 200 (069500)",
  dates: ["2024-01-02", "2024-06-03", "2024-12-30"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

function equityChartProps() {
  return chartCalls.find((c) => c.type === "equity");
}

describe("BacktestDashboard 벤치마크 곡선", () => {
  beforeEach(() => {
    cleanup();
    chartCalls.length = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("benchmarkEquity를 차트의 buyHold 시리즈로 넘긴다", () => {
    render(
      <BacktestDashboard result={baseResult} onRestart={() => {}} disableHistorySave />
    );

    const props = equityChartProps();
    expect(props).toBeTruthy();
    expect(props.equityData.map((p: any) => p.buyHold)).toEqual([
      undefined,
      10200000,
      10840000,
    ]);
  });

  it("벤치마크가 없는 결과에서는 buyHold를 채우지 않는다", () => {
    render(
      <BacktestDashboard
        result={{ ...baseResult, benchmarkEquity: undefined }}
        onRestart={() => {}}
        disableHistorySave
      />
    );

    const props = equityChartProps();
    expect(props).toBeTruthy();
    expect(props.equityData.every((p: any) => p.buyHold === undefined)).toBe(true);
  });
});
