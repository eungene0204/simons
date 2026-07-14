// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: () => ({ children, layoutId: _layoutId, ...props }: any) => <div {...props}>{children}</div>,
  }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

import BacktestDashboard, { metricTooltip } from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-trade-stats",
  strategyId: "strat-trade-stats",
  symbols: ["005930"],
  totalReturn: 14.2,
  cagr: 9.1,
  buyAndHoldReturn: 6.8,
  maxDrawdown: -8.4,
  winRate: 57.1,
  profitFactor: 1.53,
  sharpe: 1.24,
  sortino: 1.41,
  trades: 101,
  avgProfit: 3.21,
  avgLoss: 1.76,
  maxConsecutiveWins: 6,
  maxConsecutiveLosses: 3,
  finalEquity: 11_420_000,
  initialCapital: 10_000_000,
  equity: [10_000_000, 10_650_000, 11_420_000],
  dates: ["2024-01-02", "2024-06-03", "2024-12-30"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

describe("BacktestDashboard 매매 통계", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  it("중복된 총 매매 횟수 카드를 표시하지 않는다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={baseResult}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    expect(screen.queryByText("총 매매 횟수")).not.toBeInTheDocument();
    expect(screen.getByText("평균 수익")).toBeInTheDocument();
    expect(screen.getByText("평균 손실")).toBeInTheDocument();
    expect(screen.getByText("최대 연속 수익")).toBeInTheDocument();
    expect(screen.getByText("최대 연속 손실")).toBeInTheDocument();
  });

  it("초기 자본과 최종 자산으로 계산한 ROI를 CAGR 아래에 표시한다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={{ ...baseResult, totalReturn: 0 }}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    const roiLabel = screen.getByText("투자 수익률");
    const roiCard = roiLabel.parentElement?.parentElement?.parentElement;
    expect(roiCard).not.toBeNull();
    expect(within(roiCard!).getByText("ROI")).toBeInTheDocument();
    expect(within(roiCard!).getByText("+14.20%")).toBeInTheDocument();

    const metricGrid = roiCard?.parentElement;
    const metricLabels = Array.from(metricGrid?.children ?? []).map((card) => card.textContent ?? "");
    expect(metricLabels.findIndex((text) => text.includes("투자 수익률"))).toBe(
      metricLabels.findIndex((text) => text.includes("연평균수익률")) + 2
    );
  });

  it("엔진 변동성이 없으면 최종 자산 오른쪽에 연환산 변동성을 표시한다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={{ ...baseResult, volatility: undefined }}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    const volatilityLabel = screen.getByText("변동성");
    const volatilityCard = volatilityLabel.parentElement?.parentElement;
    expect(volatilityCard).not.toBeNull();
    expect(volatilityCard).toHaveTextContent("5.79%");

    const performanceRow = volatilityCard?.parentElement;
    const metricLabels = Array.from(performanceRow?.children ?? []).map((card) => card.textContent ?? "");
    expect(metricLabels.findIndex((text) => text.includes("변동성"))).toBe(
      metricLabels.findIndex((text) => text.includes("최종 자산")) + 1
    );
  });

  it("시장 노출도 오른쪽에 왕복거래 기준 회전율을 표시한다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={{
            ...baseResult,
            equity: [10_000_000, 11_000_000],
            tradesList: [
              { date: "2024-01-02", symbol: "005930", type: "buy", price: 10_000, quantity: 100, amount: 1_000_000, reason: "진입" },
              { date: "2024-06-03", symbol: "005930", type: "sell", price: 12_000, quantity: 100, amount: 0, reason: "청산" },
            ],
          }}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    const turnoverLabel = screen.getByText("회전율");
    const turnoverCard = turnoverLabel.parentElement?.parentElement;
    expect(turnoverCard).not.toBeNull();
    expect(turnoverCard).toHaveTextContent("10.5%");

    const performanceRow = turnoverCard?.parentElement;
    const metricLabels = Array.from(performanceRow?.children ?? []).map((card) => card.textContent ?? "");
    expect(metricLabels.findIndex((text) => text.includes("회전율"))).toBe(
      metricLabels.findIndex((text) => text.includes("시장 노출도")) + 1
    );
  });

  it("소티노 지수를 샤프 비율 바로 오른쪽에 표시한다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={baseResult}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    const sortinoLabel = screen.getByText("소티노 지수");
    const sortinoCard = sortinoLabel.parentElement?.parentElement?.parentElement;
    expect(sortinoCard).not.toBeNull();
    expect(within(sortinoCard!).getByText("Sortino")).toBeInTheDocument();
    expect(within(sortinoCard!).getByText("1.41")).toBeInTheDocument();

    const metricGrid = sortinoCard?.parentElement;
    const metricLabels = Array.from(metricGrid?.children ?? []).map((card) => card.textContent ?? "");
    expect(metricLabels.findIndex((text) => text.includes("소티노 지수"))).toBe(
      metricLabels.findIndex((text) => text.includes("샤프 비율")) + 1
    );
  });

  it("소티노 지수 툴팁에 신호등 가이드라인을 표시한다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={baseResult}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    const sortinoLabel = screen.getByText("소티노 지수");
    const sortinoCard = sortinoLabel.parentElement?.parentElement?.parentElement;
    const infoIcon = sortinoCard?.querySelector("svg");
    expect(infoIcon).not.toBeNull();

    fireEvent.mouseEnter(infoIcon!);

    expect(screen.queryByText(/과거 백테스트 결과 해석용/)).not.toBeInTheDocument();
    expect(screen.getByText(/🟢 높음: 2.0 이상/)).toBeInTheDocument();
    expect(screen.getByText(/🟡 중간: 1.0 ~ 2.0/)).toBeInTheDocument();
    expect(screen.getByText(/🔴 낮음: 1.0 미만/)).toBeInTheDocument();
  });

  it("지표 툴팁 형식에 공식과 신호등 가이드라인을 포함한다", () => {
    const tooltip = metricTooltip("지표 정의", "지표 공식", "🟢 양호\n🟡 중간\n🔴 주의");

    expect(tooltip).toContain("[ 공식 ]");
    expect(tooltip).toContain("지표 공식");
    expect(tooltip).not.toContain("[ 가이드라인 - 과거 백테스트 결과 해석용 ]");
    expect(tooltip).toContain("🟢 양호");
    expect(tooltip).toContain("🟡 중간");
    expect(tooltip).toContain("🔴 주의");
  });

  it("엔진 소티노 지수가 없으면 자산곡선으로 계산한다", async () => {
    await act(async () => {
      render(
        <BacktestDashboard
          result={{ ...baseResult, sortino: undefined, equity: [100, 110, 100] }}
          onRestart={() => {}}
          disableHistorySave
        />
      );
    });

    const sortinoLabel = screen.getByText("소티노 지수");
    const sortinoCard = sortinoLabel.parentElement?.parentElement?.parentElement;
    expect(sortinoCard).not.toBeNull();
    expect(within(sortinoCard!).getByText("1.12")).toBeInTheDocument();
  });
});
