// @ts-nocheck
/**
 * BacktestDashboard AI 리포트 플랜 게이트 회귀 테스트.
 *
 * AI 리포트는 프로/프리미엄 전용 기능이다.
 * - 무료 플랜: "AI 리포트" 탭을 누르면 리포트 대신 "플랜 변경" 안내가 나오고,
 *   백그라운드에서 /api/backtest/summarize (유료 LLM) 를 호출하지 않는다.
 * - 유료 플랜: 리포트 카드를 렌더링한다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({
  default: () => <div data-testid="ai-report-card" />,
}));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("@/components/ui/CreateAccountModal", () => ({ default: () => null }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import BacktestDashboard from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
  cacheKey: "ck-1",
  symbols: [],
  totalReturn: 0,
  cagr: 0,
  buyAndHoldReturn: 0,
  maxDrawdown: 0,
  winRate: 0,
  profitFactor: 0,
  sharpe: 0,
  sortino: 0,
  trades: 0,
  finalEquity: 10000000,
  initialCapital: 10000000,
  equity: [],
  dates: [],
  tradesList: [],
  monthlyReturns: {},
  yearlyReturns: {},
  signals: [],
} as any;

function renderWith(planId: string) {
  let summarizeCalls = 0;
  const fetchMock = vi.fn((url: string) => {
    if (typeof url === "string" && url.includes("/api/backtest/summarize")) {
      summarizeCalls += 1;
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    if (typeof url === "string" && url.includes("/api/user/plan")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ plan: { planId } }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <BacktestDashboard
      result={baseResult}
      onRestart={() => {}}
      disableHistorySave
      promptText="pbr 전략"
      backtestDsl={{ universe: { id: "KOSPI" }, entry: {}, exit: {} }}
      strategySummary={{ strategyName: "pbr 전략", universeName: "KOSPI" }}
    />
  );
  return () => summarizeCalls;
}

describe("BacktestDashboard AI 리포트 플랜 게이트", () => {
  beforeEach(() => {
    cleanup();
  });

  it("무료 플랜은 AI 리포트 탭에서 플랜 변경 안내를 보이고 summarize 를 호출하지 않는다", async () => {
    const getCalls = renderWith("FREE");
    const user = userEvent.setup();

    // 플랜 로드 완료를 기다린 뒤 AI 리포트 탭 진입.
    await user.click(screen.getByRole("button", { name: "AI 리포트" }));

    const upgrade = await screen.findByRole("link", { name: "플랜 변경" });
    expect(upgrade).toHaveAttribute("href", "/pricing");
    expect(screen.queryByTestId("ai-report-card")).toBeNull();

    // 무료 플랜은 백그라운드 유료 LLM 생성을 트리거하지 않는다.
    await new Promise((r) => setTimeout(r, 0));
    expect(getCalls()).toBe(0);
  });

  it("프로 플랜은 AI 리포트 카드를 렌더링한다", async () => {
    renderWith("PRO");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "AI 리포트" }));

    expect(await screen.findByTestId("ai-report-card")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "플랜 변경" })).toBeNull();
  });
});
