// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: () =>
      ({ children, layoutId: _layoutId, ...props }: any) => <div {...props}>{children}</div>,
  }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({
  default: () => null,
  WalkForwardPanel: ({ optimizationTargets = [] }: any) => (
    <div>
      <button type="button">워크포워드 분석 시작</button>
      {optimizationTargets.map((target: any) => (
        <span key={target.id}>{target.label}</span>
      ))}
    </div>
  ),
}));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

import BacktestDashboard from "./BacktestDashboard";

function buildDates(length: number) {
  return Array.from({ length }, (_, index) => {
    const date = new Date(Date.UTC(2024, 0, 1 + index));
    return date.toISOString().slice(0, 10);
  });
}

function buildEquity(length: number) {
  let value = 10_000_000;
  return Array.from({ length }, (_, index) => {
    value *= index % 9 === 0 ? 0.992 : 1.006;
    return Math.round(value);
  });
}

const equity = buildEquity(120);
const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
  symbols: ["005930"],
  totalReturn: 12.4,
  cagr: 8.2,
  buyAndHoldReturn: 6.1,
  maxDrawdown: -9.8,
  winRate: 54.3,
  profitFactor: 1.44,
  sharpe: 1.12,
  sortino: 1.38,
  trades: 18,
  finalEquity: equity[equity.length - 1],
  initialCapital: 10_000_000,
  equity,
  dates: buildDates(equity.length),
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

async function renderDashboard(planId: "FREE" | "PREMIUM", props: Record<string, any> = {}) {
  const fetchMock = vi.fn((url: string) => {
    if (url === "/api/user/plan") {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            plan: {
              planId,
              name: planId,
            },
          }),
      });
    }

    if (url === "/api/stocks/names") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }

    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });

  vi.stubGlobal("fetch", fetchMock);

  let view: ReturnType<typeof render> | undefined;
  await act(async () => {
    view = render(
      <BacktestDashboard
        result={baseResult}
        onRestart={() => {}}
        disableHistorySave
        aiSummary="과거 데이터 기준 요약"
        aiScore={61}
        {...props}
      />
    );
  });
  return view;
}

describe("BacktestDashboard 전략 최적화 페이지", () => {
  beforeEach(() => {
    cleanup();
  });

  it("FREE 플랜에서는 몬테카를로 모델에 프리미엄 잠금 안내를 표시한다", async () => {
    await renderDashboard("FREE");
    const user = userEvent.setup();

    expect(screen.getByTestId("backtest-tab-content")).not.toHaveClass("flex-1");
    expect(screen.getByTestId("backtest-dashboard-footer")).toHaveClass("px-0", "py-3", "mt-auto");

    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    expect(await screen.findByTestId("backtest-optimization-page")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "몬테카를로" }));

    expect(await screen.findByText("프리미엄 전용 검증 기능입니다.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "요금제 보기" })).toHaveAttribute("href", "/pricing");
  });

  it("PREMIUM 플랜에서는 전략 최적화 페이지에서 워크포워드 CTA와 몬테카를로 결과를 노출한다", async () => {
    await renderDashboard("PREMIUM", {
      onWalkForward: vi.fn(),
      strategySummary: {
        strategyName: "저PBR 장기보유",
        universeName: "KOSPI 200",
        blockNames: ["PBR <= 1"],
        entryBlocks: ["PBR <= 1"],
        exitBlocks: ["손절 -12% 하락시 매도", "익절 30% 이상 수익시 매도", "최대 126일 보유 후 매도"],
        positionText: "최대 8종목 · 126일 보유",
        riskText: "손절 12%, 익절 30%",
      },
    });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    expect(await screen.findByTestId("backtest-optimization-page")).toBeInTheDocument();

    // 기본 선택은 워크포워드
    expect(screen.getByRole("button", { name: "워크포워드" })).toHaveClass("border-sky-400/40");
    expect(screen.getByRole("button", { name: "워크포워드" })).toHaveClass("bg-transparent");
    expect(screen.getByRole("button", { name: "워크포워드" })).not.toHaveClass("bg-sky-500/10");
    expect(await screen.findByRole("button", { name: "워크포워드 분석 시작" })).toBeInTheDocument();
    expect(screen.getByTestId("backtest-walk-forward-section")).not.toHaveClass("py-4");
    expect(screen.getByTestId("backtest-walk-forward-section")).not.toHaveClass("flex-1");
    expect(screen.getByText("PBR")).toBeInTheDocument();
    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(screen.getByText("익절라인")).toBeInTheDocument();
    expect(screen.getByText("보유기간")).toBeInTheDocument();
    expect(screen.getByText("보유종목수")).toBeInTheDocument();
    expect(screen.queryByText("PBR <= 1")).not.toBeInTheDocument();
    expect(screen.queryByText("손절 -12% 하락시 매도")).not.toBeInTheDocument();
    expect(screen.queryByText("익절 30% 이상 수익시 매도")).not.toBeInTheDocument();
    expect(screen.queryByText("최대 126일 보유 후 매도")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "몬테카를로" }));
    await user.click(await screen.findByRole("button", { name: "몬테카를로 실행" }));

    await waitFor(() => {
      expect(screen.getByText("양수 CAGR 확률")).toBeInTheDocument();
      expect(screen.getByText(/최대낙폭이 30%를 초과할 확률은/)).toBeInTheDocument();
    });
  });

  it("일반 탭을 클릭하면 전략 최적화 페이지를 닫는다", async () => {
    await renderDashboard("PREMIUM");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "전략 최적화" }));
    expect(await screen.findByTestId("backtest-optimization-page")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "종목 분석" }));
    expect(screen.queryByTestId("backtest-optimization-page")).not.toBeInTheDocument();
    expect(screen.getByTestId("backtest-tab-content")).toBeInTheDocument();
  });
});
