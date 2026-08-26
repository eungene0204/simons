// @ts-nocheck
/**
 * 백테스트 결과 툴바의 "계좌 만들기" 배선 회귀 테스트.
 *
 * 가상계좌는 Strategy 행을 참조해야 추적 종목·자동매매 신호가 붙는다. 그래서 이 버튼은
 * (1) 백테스트 전략을 /api/strategy/ensure 로 확정하고 (2) 그 id 로 계좌를 만들어야 한다.
 * 한 단계라도 빠지면 전략 없는 빈 계좌가 만들어진다.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: any) => <div {...props} /> }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));
vi.mock("@/components/strategy/BacktestChart", () => ({ default: () => null }));
vi.mock("./BacktestSummaryCard", () => ({ default: () => null }));
vi.mock("./XAIModal", () => ({ default: () => null }));
vi.mock("./WalkForwardModal", () => ({ default: () => null }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

import BacktestDashboard from "./BacktestDashboard";

const baseResult = {
  executionId: "exec-1",
  strategyId: "strat-1",
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

const BACKTEST_DSL = { universe: { id: "KOSPI" }, entry: {}, exit: {} };

function stubFetch(overrides: Record<string, any> = {}) {
  const calls: Array<{ url: string; body: any }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: any, init?: any) => {
      const url = String(input);
      calls.push({ url, body: init?.body ? JSON.parse(init.body) : undefined });
      if (url === "/api/user/plan") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            plan: { planId: "FREE", initialInvestmentAmount: 10_000_000 },
            accounts: { used: 0, limit: 1 },
          }),
        });
      }
      if (url === "/api/strategy/ensure") {
        return Promise.resolve(
          overrides.ensure ?? { ok: true, json: async () => ({ id: "7:abc", name: "저PBR 전략", created: true }) }
        );
      }
      if (url === "/api/virtual-account") {
        return Promise.resolve({ ok: true, json: async () => ({ id: "account-1" }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    })
  );
  return calls;
}

function renderDashboard() {
  return render(
    <BacktestDashboard
      result={baseResult}
      onRestart={() => {}}
      disableHistorySave
      promptText="KOSPI 저PBR 종목을 사는 전략"
      backtestDsl={BACKTEST_DSL}
      strategySummary={{
        strategyName: "저PBR 전략",
        universeName: "KOSPI",
        blockNames: ["PBR 1배 이하"],
        entryBlocks: ["PBR 1배 이하"],
        exitBlocks: [],
        positionText: "최대 10종목",
      }}
    />
  );
}

describe("백테스트 결과 → 계좌 만들기", () => {
  beforeEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("전략을 먼저 확정한 뒤 그 전략 id로 가상계좌를 만든다", async () => {
    const calls = stubFetch();
    renderDashboard();

    fireEvent.click(screen.getByRole("button", { name: "계좌 만들기" }));

    expect(await screen.findByTestId("bound-strategy-name")).toHaveTextContent("저PBR 전략");
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));

    await waitFor(() =>
      expect(calls.some((c) => c.url === "/api/virtual-account")).toBe(true)
    );

    const ensure = calls.find((c) => c.url === "/api/strategy/ensure");
    expect(ensure?.body).toMatchObject({
      name: "저PBR 전략",
      description: "KOSPI 저PBR 종목을 사는 전략",
      dsl: BACKTEST_DSL,
    });

    const created = calls.find((c) => c.url === "/api/virtual-account");
    expect(created?.body).toMatchObject({
      name: "저PBR 전략",
      strategyId: "7:abc",
      strategyName: "저PBR 전략",
      // 백테스트 결과에서 여는 계좌는 전략 시뮬레이션을 켠 채로 시작한다.
      tradingMode: "auto",
    });
  });

  it("전략을 결과 화면 '내 전략'과 같은 라벨·값 행으로 보여준다", async () => {
    stubFetch();
    renderDashboard();

    fireEvent.click(screen.getByRole("button", { name: "계좌 만들기" }));

    const rows = await screen.findByTestId("bound-strategy-rows");
    expect(rows).toHaveTextContent("유니버스");
    expect(rows).toHaveTextContent("KOSPI");
    expect(rows).toHaveTextContent("진입 신호");
    expect(rows).toHaveTextContent("PBR 1배 이하");
    expect(rows).toHaveTextContent("리스크");
    expect(rows).toHaveTextContent("최대 10종목");
  });

  it("전략 확정이 실패하면 계좌를 만들지 않고 이유를 보여준다", async () => {
    const calls = stubFetch({
      ensure: {
        ok: false,
        json: async () => ({ code: "PLAN_LIMIT_STRATEGIES", message: "전략 저장 한도에 도달했습니다." }),
      },
    });
    renderDashboard();

    fireEvent.click(screen.getByRole("button", { name: "계좌 만들기" }));
    await screen.findByTestId("bound-strategy-name");
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));

    expect(await screen.findByText("전략 저장 한도에 도달했습니다.")).toBeInTheDocument();
    expect(calls.some((c) => c.url === "/api/virtual-account")).toBe(false);
  });

  it("DSL이 없으면 계좌 만들기 버튼을 내보내지 않는다", () => {
    stubFetch();
    render(
      <BacktestDashboard result={baseResult} onRestart={() => {}} disableHistorySave />
    );

    expect(screen.queryByRole("button", { name: "계좌 만들기" })).not.toBeInTheDocument();
  });
});
