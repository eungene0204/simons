// '이 전략으로 확정'은 대화 전체를 LLM에 재파싱시키지 않고, 누적된 parsed를 그대로
// /api/strategy/compile로 컴파일한다 — 재해석이 규칙 파서가 표현 못 하는 조건
// ('영업이익 흑자' → operating_income_growth 필터)을 비결정적으로 잃어 완성 전략의
// 매수 조건을 다시 되묻던 사고의 회귀 테스트.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { resetGraphMetaForTests } from "@/lib/strategy-graph/meta";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

const push = vi.fn();
const fetchMock = vi.fn();

// LLM 해석으로만 얻는 진입 필터를 포함하고, 익절만 비어 있는 전략 — 결정적 칩 한 번으로
// 완성돼 확정 단계에 도달한다. 프롬프트에 유니버스·종목 수·리밸런싱·기간·자본이 명시돼
// 있어야 requireExplicitConfiguration 게이트를 통과한다.
const parsedWithLlmOnlyFilter = {
  description: "영업이익 흑자인 기업 투자 전략",
  universe: ["KOSPI"],
  fundamental_filters: [
    { metric: "operating_income_growth", operator: ">=", value: 0 },
  ],
  entry_signals: [],
  exit_signals: [],
  max_positions: 5,
  hold_period_days: null,
  rebalancing_period: "monthly",
  rebalance_method: "reconstitute",
  stop_loss_pct: 10,
  take_profit_pct: null,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

const backtestRequest = {
  symbols: ["005930", "000660"],
  universe_id: "kospi",
  entry: {
    conditions: [
      { type: "filter", id: "operating_income_growth", params: { operator: ">=", value: 0 } },
    ],
  },
  exit: { conditions: [] },
  risk: {
    max_positions: 5,
    init_cash: 10000000,
    stop_loss_pct: 10,
    take_profit_pct: 30,
  },
  period: "5y",
  options: { fee_rate: 0.015, slippage_rate: 0.05 },
};

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

vi.mock("@/components/strategy/backtest/BacktestDashboard", () => ({
  default: ({ strategyGraphInput }: { strategyGraphInput?: { origin: string; sourceRef: string; request?: { risk?: { take_profit_pct?: number } } } }) => (
    <div data-testid="backtest-dashboard">
      <span data-testid="dash-graph-origin">{strategyGraphInput?.origin}</span>
      <span data-testid="dash-graph-tp">{String(strategyGraphInput?.request?.risk?.take_profit_pct)}</span>
    </div>
  ),
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth: vi.fn(),
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  }),
}));

const isDraftPreview = (init?: RequestInit) => (init?.headers as Record<string, string> | undefined)?.["X-Graph-Draft"] === "1";

function createJsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function createParseStreamResponse() {
  const encoder = new TextEncoder();
  const payload = [
    // 프롬프트가 다섯 설정을 모두 말했으므로 백엔드 provenance도 전부를 명시로 보고한다.
    `data: ${JSON.stringify({
      type: "parsed_final",
      parsed: parsedWithLlmOnlyFilter,
      explicit_fields: [
        "universe",
        "max_positions",
        "rebalancing",
        "rebalance_method",
        "backtest_period",
        "initial_capital",
      ],
    })}\n\n`,
    `data: ${JSON.stringify({ type: "dsl_ready", backtest_request: backtestRequest, symbol_count: 2 })}\n\n`,
    "data: [DONE]\n\n",
  ].join("");

  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(payload));
        controller.close();
      },
    }),
    { status: 200 },
  );
}

describe("deterministic strategy confirmation", () => {
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

  it("확정 시 재파싱 없이 누적 전략을 컴파일해 LLM 전용 매수 필터를 보존한다", async () => {
    let parseCallCount = 0;
    const compileBodies: Array<{ parsed: Record<string, unknown> }> = [];

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      }
      if (url === "/api/strategy/parse/stream") {
        parseCallCount += 1;
        return Promise.resolve(createParseStreamResponse());
      }
      if (url === "/api/strategy/compile") {
        const body = JSON.parse(String(init?.body ?? "{}"));
        if (!isDraftPreview(init)) compileBodies.push(body);
        return Promise.resolve(
          createJsonResponse({
            parsed: body.parsed,
            backtest_request: backtestRequest,
            notices: [],
          }),
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    fireEvent.change(await screen.findByRole("textbox"), {
      target: {
        value:
          "영업이익 흑자인 기업을 코스피에서 최대 5종목, 매월 리밸런싱, 손절 10%, " +
          "최근 5년 데이터, 1,000만원으로 백테스트",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 익절만 비어 있으므로 익절 질문 → 칩 선택으로 완성한다.
    fireEvent.click(await screen.findByRole("button", { name: "익절 30%" }));

    fireEvent.click(await screen.findByRole("button", { name: "이 전략으로 확정" }));

    await waitFor(() => {
      expect(compileBodies).toHaveLength(1);
    });

    // 누적 parsed가 그대로 컴파일 요청에 실린다 — LLM 전용 필터·칩으로 채운 익절 포함.
    expect(compileBodies[0].parsed.fundamental_filters).toEqual([
      { metric: "operating_income_growth", operator: ">=", value: 0 },
    ]);
    expect(compileBodies[0].parsed.take_profit_pct).toBe(30);

    // 확정은 대화 전체를 재파싱하지 않는다(최초 1회만).
    expect(parseCallCount).toBe(1);

    // 매수 조건이 사라져 다시 묻는 사고가 없어야 한다.
    expect(screen.queryByText(/어떤 조건에서 매수할지/)).not.toBeInTheDocument();
    expect(screen.queryByText(/매수 조건이 빠져 있습니다/)).not.toBeInTheDocument();
  });
});

// ── 확정 직후 전략 그래프 자동 표시 ─────────────────────────────────────────────
describe("confirmed strategy graph card", () => {
  const META = { version: "t", indicators: {}, bindings: {}, classes: [], concepts: [] };
  const PROMPT =
    "영업이익 흑자인 기업을 코스피에서 최대 5종목, 매월 리밸런싱, 손절 10%, " +
    "최근 5년 데이터, 1,000만원으로 백테스트";

  type Opts = {
    compile?: (body: { parsed: Record<string, unknown> }, call: number) => Response | Promise<Response>;
    meta?: () => Response;
  };
  const calls = { parse: 0, compile: 0, draftCompile: 0, meta: 0, backtest: 0, urls: [] as string[] };

  const install = (opts: Opts = {}) => {
    calls.parse = 0; calls.compile = 0; calls.draftCompile = 0; calls.meta = 0; calls.backtest = 0; calls.urls = [];
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.urls.push(url);
      if (url === "/api/model/status") return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      if (url === "/api/user") return Promise.resolve(createJsonResponse({ user: { name: "Tester" } }));
      if (url === "/api/query/classify") return Promise.resolve(createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] }));
      if (url === "/api/strategy/parse/stream") {
        calls.parse += 1;
        return Promise.resolve(createParseStreamResponse());
      }
      if (url === "/api/strategy/graph-meta") {
        calls.meta += 1;
        return Promise.resolve(opts.meta ? opts.meta() : createJsonResponse(META));
      }
      if (url === "/api/strategy/compile") {
        const draft = isDraftPreview(init);
        if (draft) calls.draftCompile += 1;
        else calls.compile += 1;
        const body = JSON.parse(String(init?.body ?? "{}"));
        if (opts.compile && !draft) return Promise.resolve(opts.compile(body, calls.compile));
        return Promise.resolve(createJsonResponse(compiled(body.parsed)));
      }
      if (url === "/api/strategy/backtest-stream") {
        calls.backtest += 1;
        const payload = `data: ${JSON.stringify({ type: "result", data: { metrics: { total_return: 1 }, equity_curve: [], trades: [] } })}\n\ndata: [DONE]\n\n`;
        return Promise.resolve(new Response(payload, { status: 200 }));
      }
      return Promise.resolve(createJsonResponse({}));
    });
  };

  // The compile response mirrors the parsed it received, so a normalized value is visible in the request.
  const compiled = (parsed: Record<string, unknown>) => ({
    parsed,
    backtest_request: { ...backtestRequest, risk: { ...backtestRequest.risk, take_profit_pct: parsed.take_profit_pct } },
    notices: [],
  });

  const reachConfirmation = async (chip = "익절 30%") => {
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: PROMPT } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    fireEvent.click(await screen.findByRole("button", { name: chip }));
    return screen.findByRole("button", { name: "이 전략으로 확정" });
  };

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => { cb(0); return 1; });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());
    Element.prototype.scrollTo = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the graph automatically after a successful confirm, using only the public metadata endpoint", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    const confirm = await reachConfirmation();
    // Nothing is shown before the confirm succeeds.
    expect(screen.queryByTestId("confirmed-strategy-graph")).not.toBeInTheDocument();
    fireEvent.click(confirm);

    const card = await screen.findByTestId("confirmed-strategy-graph");
    expect(within(card).getByRole("heading", { name: "확정된 전략" })).toBeInTheDocument();
    expect(await within(card).findByTestId("strategy-graph-canvas")).toBeInTheDocument();
    expect(calls.compile).toBe(1);
    expect(calls.urls.filter((u) => u.includes("ontology") || u.includes("admin"))).toEqual([]);
    // The graph adds exactly one request (public metadata); the existing post-confirm coach call is unchanged.
    expect(calls.urls.filter((u) => u.includes("graph"))).toEqual(["/api/strategy/graph-meta"]);
    expect(calls.urls.filter((u) => u === "/api/strategy/parse/stream")).toHaveLength(1);
    // The existing run button still follows the confirmed card.
    expect(screen.getByRole("button", { name: "백테스트 시작하기" })).toBeEnabled();
  });

  it("draws the understood-so-far strategy as a graph instead of the text summary while questions are open", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: PROMPT } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    // The take-profit question is still open: the card is a draft graph, not the text list.
    const draft = await screen.findByTestId("draft-strategy-graph");
    expect(within(draft).getByRole("heading", { name: "현재까지 이해한 전략입니다" })).toBeInTheDocument();
    expect(await within(draft).findByTestId("strategy-graph-canvas")).toBeInTheDocument();
    expect(screen.queryByTestId("builder-strategy-summary")).not.toBeInTheDocument();
    // The graph is built from this turn's structured data only (no confirmed graph yet).
    expect(screen.queryByTestId("confirmed-strategy-graph")).not.toBeInTheDocument();
    // Only the draft preview compile ran — the real confirm call has not been made.
    expect(calls.compile).toBe(0);
    expect(calls.draftCompile).toBeGreaterThan(0);
    // Next step: answering moves the same flow forward and the confirmed graph appears.
    fireEvent.click(await screen.findByRole("button", { name: "익절 30%" }));
    fireEvent.click(await screen.findByRole("button", { name: "이 전략으로 확정" }));
    const confirmed = await screen.findByTestId("confirmed-strategy-graph");
    await within(confirmed).findByTestId("strategy-graph-canvas");
    // The confirmed graph continues the draft: the root the draft already drew is not replayed.
    expect(confirmed.querySelector('[data-item-key="node:strategy"] .sg-enter')).toBeNull();
  });

  it("shows the confirmed summary as horizontal chips instead of a vertical list", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation());
    const summary = await screen.findByTestId("confirmed-strategy-summary");
    const chips = within(summary).getByTestId("builder-strategy-chips");
    expect(chips.tagName).toBe("UL");
    expect(chips.className).toContain("flex-wrap");
    expect(chips.querySelectorAll("li").length).toBeGreaterThan(3);
    expect(summary.querySelector("dl")).toBeNull();
    // each chip carries its label and its value together
    expect(within(chips).getByText("유니버스").closest("li")).toHaveTextContent("KOSPI");
  });

  it("titles the confirmed block '확정된 전략' with the view menu beside the title and no draft heading", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation());
    const card = await screen.findByTestId("confirmed-strategy-graph");
    await within(card).findByTestId("strategy-graph-canvas");
    const header = within(card).getByRole("heading", { name: "확정된 전략" }).parentElement as HTMLElement;
    // the graph/text menu sits in the same header row as the title
    expect(within(header).getByRole("button", { name: /그래프/ })).toBeInTheDocument();
    expect(within(header).getByRole("button", { name: /텍스트로 보기/ })).toBeInTheDocument();
    // the summary chips live inside the same block, and the draft heading is gone
    expect(within(card).getByTestId("builder-strategy-chips")).toBeInTheDocument();
    expect(within(card).queryByText("현재까지 이해한 전략입니다")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("confirmed-strategy-summary")).toHaveLength(1);
  });

  it("shows the normalized values of the confirm response, not the draft the user clicked on", async () => {
    install({
      compile: (body) =>
        createJsonResponse(compiled({ ...body.parsed, take_profit_pct: 25 })),
    });
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    const card = await screen.findByTestId("confirmed-strategy-graph");
    await within(card).findByTestId("strategy-graph-canvas");
    expect(within(card).getByText("익절 +25%")).toBeInTheDocument();
    expect(within(card).queryByText("익절 +30%")).not.toBeInTheDocument();
  });

  it("shows no confirmed graph when the confirm fails", async () => {
    install({ compile: () => new Response(JSON.stringify({ detail: "검증 실패" }), { status: 422 }) });
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation());
    await waitFor(() => expect(calls.compile).toBe(1));
    await screen.findByText(/검증 실패/);
    expect(screen.queryByTestId("confirmed-strategy-graph")).not.toBeInTheDocument();
  });

  it("does not show a confirmed graph when the confirm response still needs an answer", async () => {
    install({
      compile: (body) => createJsonResponse(compiled({ ...body.parsed, rebalancing_period: null, rebalance_method: null, take_profit_pct: null })),
    });
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation());
    await waitFor(() => expect(calls.compile).toBe(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: "이 전략으로 확정" })).not.toBeInTheDocument());
    expect(screen.queryByTestId("confirmed-strategy-graph")).not.toBeInTheDocument();
  });

  it("creates one graph for rapid repeated clicks", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    const confirm = await reachConfirmation();
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await screen.findByTestId("confirmed-strategy-graph");
    await waitFor(() => expect(calls.compile).toBe(1));
    expect(screen.getAllByTestId("confirmed-strategy-graph")).toHaveLength(1);
  });

  it("retries only the metadata after a graph failure and never repeats confirm or parse", async () => {
    let metaOk = false;
    install({
      meta: () => (metaOk ? createJsonResponse(META) : new Response("{}", { status: 502 })),
    });
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation());
    const banner = await screen.findByTestId("graph-meta-error");
    // The confirmation itself stays successful: structure is shown and the run button remains.
    expect(screen.getByTestId("strategy-graph-canvas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "백테스트 시작하기" })).toBeEnabled();
    const parseBefore = calls.parse;
    metaOk = true;
    fireEvent.click(within(banner).getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.queryByTestId("graph-meta-error")).not.toBeInTheDocument());
    expect(calls.compile).toBe(1);
    expect(calls.parse).toBe(parseBefore);
  });

  it("keeps the confirmed graph unchanged when the strategy is later confirmed again as B", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    const first = await screen.findByTestId("confirmed-strategy-graph");
    await within(first).findByTestId("strategy-graph-canvas");
    expect(within(first).getByText("익절 +30%")).toBeInTheDocument();

    // A modified draft B (take profit 20) arrives through the normal conversation, then is confirmed.
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "익절 20%로 바꿔줘" } });
    fireEvent.click(screen.getByRole("button", { name: /전략 생성|전송/ }));
    fireEvent.click(await screen.findByRole("button", { name: "익절 20%" }));
    fireEvent.click(await screen.findByRole("button", { name: "이 전략으로 확정" }));

    await waitFor(() => expect(screen.getAllByTestId("confirmed-strategy-graph")).toHaveLength(2));
    const [a, b] = screen.getAllByTestId("confirmed-strategy-graph");
    await within(b).findByTestId("strategy-graph-canvas");
    expect(within(a).getByText("익절 +30%")).toBeInTheDocument();
    expect(within(a).queryByText("익절 +20%")).not.toBeInTheDocument();
    expect(within(b).getByText("익절 +20%")).toBeInTheDocument();
    expect(calls.compile).toBe(2);
  });

  it("gives the result screen the executed request, separate from the confirmed snapshot", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await screen.findByTestId("confirmed-strategy-graph");
    fireEvent.click(await screen.findByRole("button", { name: "백테스트 시작하기" }));
    expect(await screen.findByTestId("backtest-dashboard")).toBeInTheDocument();
    expect(calls.backtest).toBe(1);
    expect(screen.getByTestId("dash-graph-origin")).toHaveTextContent("executed");
    expect(screen.getByTestId("dash-graph-tp")).toHaveTextContent("30");
  });
});
