// [회귀] "어떻게 해야 할까?" 같은 후속 질문(answer_follow_up)의 답은 **진행 골격 순서**에서
// 나와야 한다 — 질문·선택지·진행률이 한 판정(getNextMissingBacktestCondition)에서 나온다.
// 2026-07-31 사고 2건:
//  ① 검증 문구만 말풍선으로 띄워 진행률도 선택지도 없었다.
//  ② 그 문구를 질문 자리에 넣었더니 질문("익절 조건을 입력해 주세요")과 선택지(리밸런싱 칩)가
//     서로 다른 출처라 어긋났고, 검증 agent가 자기 순서대로 답하는 탓에 매번 같은 항목만 물었다.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/analytics/chat",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/strategy/StrategyExampleTabs", () => ({
  StrategyExampleTabs: () => <div>예시 전략</div>,
}));

vi.mock("@/components/strategy/StrategyWaveBackground", () => ({
  StrategyWaveBackground: () => <div>배경</div>,
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth: vi.fn(),
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  }),
}));

function createJsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

// 검증 agent는 미완성 전략이면 자기 순서대로 이 문구만 돌려준다 — 진행 순서와 무관하다.
const VALIDATION_REPLY = "익절 조건을 입력해 주세요.";

function baseParsed(overrides: Record<string, unknown> = {}) {
  return {
    description: "인공지능 ETF 20일 신고가 돌파 전략",
    universe: ["ETF"],
    etf_theme: "인공지능",
    sector: null,
    target_symbols: [],
    entry_signals: [{ type: "breakout", lookback_days: 20 }],
    exit_signals: [{ type: "ma_crossover", direction: "dead_cross" }],
    fundamental_filters: [],
    max_positions: 3,
    backtest_period: "5y",
    initial_capital: 10000000,
    stop_loss_pct: 6,
    hold_period_days: 40,
    take_profit_pct: null,
    ...overrides,
  };
}

function sseResultResponse(data: Record<string, unknown>) {
  const parsedFinal = JSON.stringify({ type: "parsed_final", ...data });
  const dslReady = JSON.stringify({
    type: "dsl_ready",
    backtest_request: { symbols: [], period: "5y", risk: {} },
    symbol_count: 0,
  });
  return new Response(
    `data: ${parsedFinal}\n\ndata: ${dslReady}\n\ndata: [DONE]\n\n`,
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

function mockFetch(parsed: Record<string, unknown>, explicitFields: string[]) {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);

    if (url === "/api/model/status") {
      return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
    }
    if (url === "/api/user") {
      return Promise.resolve(
        createJsonResponse({ user: { name: "Tester", email: "tester@example.com" } })
      );
    }
    if (url === "/api/query/classify") {
      return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
    }
    if (url === "/api/strategy/parse/stream") {
      return Promise.resolve(sseResultResponse({
        parsed,
        clarification_question: null,
        clarification_suggestions: null,
        clarification_priority: null,
        pending_ask: null,
        explicit_fields: explicitFields,
        notices: [],
      }));
    }
    if (url === "/api/strategy/coach") {
      return Promise.resolve(createJsonResponse({ message: VALIDATION_REPLY }));
    }
    return Promise.resolve(createJsonResponse({}));
  });
}

async function startStrategy() {
  render(<StrategyLabPage />);
  const textarea = await screen.findByRole("textbox");
  fireEvent.change(textarea, {
    target: { value: "인공지능 ETF 중 20일 신고가를 돌파하면 매수, 최대 3종목" },
  });
  fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
}

async function askHowToProceed() {
  // 되묻기 칩이 떠 있는 동안에는 입력창이 숨겨진다 — '직접 입력'으로 다시 연다.
  fireEvent.click(await screen.findByRole("button", { name: "직접 입력" }, { timeout: 5000 }));
  const input = await screen.findByRole("textbox");
  fireEvent.change(input, { target: { value: "어떻게 해야 할까?" } });
  fireEvent.click(screen.getByRole("button", { name: /전략 생성|전송/ }));
}

describe("후속 질문 턴 — 진행 골격 순서대로 되묻는다", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("리밸런싱 차례면 리밸런싱을 묻는다 — 검증 agent가 익절이라고 답해도 끌려가지 않는다", async () => {
    // 리밸런싱이 비어 있는 상태(익절보다 진행 순서가 앞선다).
    mockFetch(baseParsed(), [
      "universe", "max_positions", "backtest_period", "initial_capital",
    ]);

    await startStrategy();
    await screen.findByText(/포트폴리오를 얼마나 자주/, undefined, { timeout: 5000 });

    await askHowToProceed();

    await waitFor(() => {
      // 질문과 선택지가 같은 항목이다 — 어긋난 조합(익절 질문 + 리밸런싱 칩)이 사고였다.
      expect(screen.getByText(/포트폴리오를 얼마나 자주/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "매월 리밸런싱" })).toBeInTheDocument();
    }, { timeout: 5000 });
    expect(screen.queryByText(VALIDATION_REPLY)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "익절 10%" })).not.toBeInTheDocument();

    // 정할 것이 남아 있으면 검증 agent를 부르지 않는다(LLM 왕복 0, 파스 재실행 0).
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/coach")
    ).toHaveLength(0);
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/strategy/parse/stream")
    ).toHaveLength(1);
  });

  it("익절 차례면 익절을 묻는다 — 선택지·진행률이 함께 선다", async () => {
    mockFetch(baseParsed({ rebalancing_period: "monthly" }), [
      "universe", "max_positions", "rebalancing", "backtest_period", "initial_capital",
    ]);

    await startStrategy();
    await screen.findByText(/익절 기준을 몇 %로/, undefined, { timeout: 5000 });

    await askHowToProceed();

    await waitFor(() => {
      expect(screen.getByText(/익절 기준을 몇 %로/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "익절 10%" })).toBeInTheDocument();
      expect(screen.getByTestId("strategy-progress-panel")).toBeInTheDocument();
    }, { timeout: 5000 });
  });
});
