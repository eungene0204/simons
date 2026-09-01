// @ts-nocheck
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, within } from "@testing-library/react";

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

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/us" }));

import BacktestDashboard from "./BacktestDashboard";
import { setLanguage, __resetLanguageForTests } from "@/lib/i18n";

const baseResult = {
  executionId: "exec-en-labels",
  strategyId: "strat-en-labels",
  symbols: ["AAPL"],
  universeId: "nasdaq100",
  totalReturn: 108.79,
  cagr: 17.16,
  buyAndHoldReturn: 80.94,
  maxDrawdown: -12.3,
  winRate: 56.5,
  profitFactor: 1.95,
  sharpe: 1.0,
  sortino: 1.51,
  trades: 115,
  finalEquity: 104_396,
  initialCapital: 50_000,
  equity: [50_000, 80_000, 104_396],
  dates: ["2024-01-02", "2024-06-03", "2024-12-30"],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

async function renderDashboard() {
  await act(async () => {
    render(<BacktestDashboard result={baseResult} onRestart={() => {}} disableHistorySave />);
  });
}

describe("BacktestDashboard 지표 카드 영문 병기", () => {
  beforeEach(() => {
    cleanup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }))
    );
  });

  afterEach(() => {
    __resetLanguageForTests();
  });

  it("영어 화면에서는 영문 병기 줄을 감춘다", async () => {
    setLanguage("en");
    await renderDashboard();

    const roiCard = screen.getByText("ROI").closest("div.min-h-\\[110px\\]");
    expect(roiCard).not.toBeNull();
    // 카드에 남는 텍스트는 라벨 한 줄과 값뿐이다 — "ROI"가 두 번 나오지 않는다.
    expect(within(roiCard!).getAllByText("ROI")).toHaveLength(1);
    expect(screen.queryByText("Sortino")).not.toBeInTheDocument();
    expect(screen.queryByText("Profit Factor")).not.toBeInTheDocument();
    expect(screen.queryByText("Win Rate")).not.toBeInTheDocument();
  });

  it("영어 화면에서도 벤치마크 이름 줄은 남긴다", async () => {
    setLanguage("en");
    await renderDashboard();

    expect(screen.getByText("Invesco QQQ (QQQ)")).toBeInTheDocument();
  });

  it("한국어 화면에서는 영문 병기 줄을 그대로 표시한다", async () => {
    setLanguage("ko");
    await renderDashboard();

    expect(screen.getByText("소티노 지수")).toBeInTheDocument();
    expect(screen.getByText("Sortino")).toBeInTheDocument();
    expect(screen.getByText("Profit Factor")).toBeInTheDocument();
  });
});
