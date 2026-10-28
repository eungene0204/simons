// '이 전략으로 확정'은 대화 전체를 LLM에 재파싱시키지 않고, 누적된 parsed를 그대로
// /api/strategy/compile로 컴파일한다 — 재해석이 규칙 파서가 표현 못 하는 조건
// ('영업이익 흑자' → operating_income_growth 필터)을 비결정적으로 잃어 완성 전략의
// 매수 조건을 다시 되묻던 사고의 회귀 테스트.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { resetGraphMetaForTests } from "@/lib/strategy-graph/meta";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

// 실행은 상단 툴바 버튼 하나다 — 준비가 끝나(활성) 누를 수 있을 때까지 기다린다.
const findRunButton = async (timeout = 5_000) => {
  await waitFor(() => expect(screen.getByTestId("lab-run-button")).toBeEnabled(), { timeout });
  return screen.getByTestId("lab-run-button");
};

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
describe("confirmed strategy graph on the canvas", () => {
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

  // 캔버스 레이아웃(2026-10-28): 전략 구조 그래프는 대화 카드가 아니라 가운데 캔버스가 그린다. 입력 규칙은
  // 같다 — 확정 뒤에는 확정 응답의 스냅샷, 확정 전에는 이 턴 parsed의 초안 컴파일 한 쌍.
  const canvas = () => screen.getByTestId("lab-canvas");
  const waitOrigin = (origin: string) => waitFor(() => expect(canvas()).toHaveAttribute("data-origin", origin));

  // 캔버스 블록은 올리는 즉시 전략에 포함된다 — 해석 요청 없이 화면의 전략이 바뀌고, 캔버스가 그 전략으로 다시 그려진다.
  it("includes a picked canvas block directly in the strategy and redraws the canvas without a parse call", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    await screen.findByRole("textbox");

    fireEvent.click(screen.getByRole("button", { name: "블록 추가" }));
    const tray = screen.getByTestId("lab-block-tray");
    fireEvent.click(within(tray).getByRole("tab", { name: "투자 대상" }));
    fireEvent.click(within(tray).getByRole("button", { name: "코스닥" }));

    // 초안 컴파일(LLM 없음)이 바뀐 전략을 받아 캔버스를 그린다.
    await waitFor(() => expect(calls.draftCompile).toBeGreaterThan(0));
    const draftCall = fetchMock.mock.calls.find(([input, init]) => String(input) === "/api/strategy/compile" && isDraftPreview(init as RequestInit));
    expect(JSON.parse(String((draftCall?.[1] as RequestInit).body)).parsed.universe).toEqual(["KOSDAQ"]);
    await waitOrigin("draft");
    expect(calls.parse).toBe(0);
    expect(await screen.findByTestId("clarification-card")).toBeInTheDocument();
  });

  it("shows the confirmed snapshot on the canvas after a successful confirm, using only the public metadata endpoint", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    const confirm = await reachConfirmation();
    // Before the confirm succeeds the canvas shows the draft, never a confirmed graph.
    expect(canvas()).not.toHaveAttribute("data-origin", "confirmed");
    fireEvent.click(confirm);

    await waitOrigin("confirmed");
    expect(await within(canvas()).findByTestId("lab-node-risk")).toBeInTheDocument();
    expect(calls.compile).toBe(1);
    expect(calls.urls.filter((u) => u.includes("ontology") || u.includes("admin"))).toEqual([]);
    // The graph adds exactly one request (public metadata); the existing post-confirm coach call is unchanged.
    expect(calls.urls.filter((u) => u.includes("graph"))).toEqual(["/api/strategy/graph-meta"]);
    expect(calls.urls.filter((u) => u === "/api/strategy/parse/stream")).toHaveLength(1);
    // Both run entry points are ready: the chat button after the confirmed card and the toolbar button.
    expect(screen.getByTestId("lab-run-button")).toBeEnabled();
    expect(screen.getByTestId("lab-run-button")).toBeEnabled();
  });

  it("draws the understood-so-far strategy on the canvas while questions are open", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: PROMPT } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    // The take-profit question is still open: the canvas shows the draft structure.
    await waitOrigin("draft");
    expect(await within(canvas()).findByTestId("lab-node-universe")).toBeInTheDocument();
    // An open question blocks the toolbar run button and says why.
    expect(screen.getByTestId("lab-run-button")).toBeDisabled();
    expect(screen.getByText("채팅의 질문에 먼저 답해 주세요.")).toBeInTheDocument();
    // Only the draft preview compile ran — the real confirm call has not been made.
    expect(calls.compile).toBe(0);
    expect(calls.draftCompile).toBeGreaterThan(0);
    // Next step: answering moves the same flow forward and the canvas switches to the confirmed snapshot.
    fireEvent.click(await screen.findByRole("button", { name: "익절 30%" }));
    fireEvent.click(await screen.findByRole("button", { name: "이 전략으로 확정" }));
    await waitOrigin("confirmed");
  });

  it("does not draw a summary card or a chat start button after confirm — the toolbar runs the backtest", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation());
    await waitOrigin("confirmed");
    expect(screen.queryByTestId("confirmed-strategy-summary")).not.toBeInTheDocument();
    expect(screen.queryByTestId("backtest-action")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "백테스트 시작하기" })).not.toBeInTheDocument();
    expect(screen.getByTestId("lab-run-button")).toBeEnabled();
    // 확정 뒤에도 지난 대화(사용자 말풍선)는 그대로 남는다 — 확정 응답 말풍선만 그리지 않는다.
    expect(screen.getByTestId("lab-chat-scroll")).toBeInTheDocument();
    expect(screen.getAllByTestId("user-chat-bubble").length).toBeGreaterThan(0);
  });

  it("shows the normalized values of the confirm response, not the draft the user clicked on", async () => {
    install({
      compile: (body) =>
        createJsonResponse(compiled({ ...body.parsed, take_profit_pct: 25 })),
    });
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await waitOrigin("confirmed");
    // 노드 내용은 그래프 계산 다음 effect에서 갱신된다 — 값이 그려질 때까지 기다린다.
    expect(await within(canvas()).findByText("익절 +25%")).toBeInTheDocument();
    expect(within(canvas()).queryByText("익절 +30%")).not.toBeInTheDocument();
  });

  it("shows no confirmed graph when the confirm fails", async () => {
    install({ compile: () => new Response(JSON.stringify({ detail: "검증 실패" }), { status: 422 }) });
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation());
    await waitFor(() => expect(calls.compile).toBe(1));
    await screen.findByText(/검증 실패/);
    expect(canvas()).not.toHaveAttribute("data-origin", "confirmed");
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
    expect(canvas()).not.toHaveAttribute("data-origin", "confirmed");
  });

  it("confirms once for rapid repeated clicks", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    const confirm = await reachConfirmation();
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitOrigin("confirmed");
    await waitFor(() => expect(calls.compile).toBe(1));
    expect(screen.queryByTestId("confirmed-strategy-summary")).not.toBeInTheDocument();
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
    await waitOrigin("confirmed");
    expect(await within(canvas()).findByTestId("lab-node-universe")).toBeInTheDocument();
    expect(screen.getByTestId("lab-run-button")).toBeEnabled();
    const parseBefore = calls.parse;
    metaOk = true;
    fireEvent.click(within(banner).getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.queryByTestId("graph-meta-error")).not.toBeInTheDocument());
    expect(calls.compile).toBe(1);
    expect(calls.parse).toBe(parseBefore);
  });

  it("switches the canvas to the new snapshot when the strategy is later confirmed again as B", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await waitOrigin("confirmed");
    expect(await within(canvas()).findByText("익절 +30%")).toBeInTheDocument();

    // A modified draft B (take profit 20) arrives through the normal conversation, then is confirmed.
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "익절 20%로 바꿔줘" } });
    fireEvent.click(screen.getByRole("button", { name: /전략 생성|전송/ }));
    fireEvent.click(await screen.findByRole("button", { name: "익절 20%" }));
    fireEvent.click(await screen.findByRole("button", { name: "이 전략으로 확정" }));

    await waitFor(() => expect(calls.compile).toBe(2));
    await waitFor(() => expect(within(canvas()).getByText("익절 +20%")).toBeInTheDocument());
    expect(canvas()).toHaveAttribute("data-origin", "confirmed");
    expect(within(canvas()).queryByText("익절 +30%")).not.toBeInTheDocument();
  });

  it("runs the backtest from the toolbar button", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await waitOrigin("confirmed");
    const run = screen.getByTestId("lab-run-button");
    expect(run).toHaveTextContent("백테스트 실행");
    fireEvent.click(run);
    expect(await screen.findByTestId("backtest-dashboard")).toBeInTheDocument();
    expect(calls.backtest).toBe(1);
  });

  // 캔버스의 지우기는 화면 상태만 지우지 않는다 — 대화의 '다시 정하기'와 같은 경로(항목 비우기 → 되묻기)다.
  it("removes a strategy item from the canvas through the re-decide conversation flow", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await waitOrigin("confirmed");

    fireEvent.doubleClick(await within(canvas()).findByTestId("lab-node-risk"));
    fireEvent.click(await screen.findByRole("button", { name: "지우기" }));
    const dialog = await screen.findByRole("dialog", { name: "위험 관리에서 지울 항목" });
    const takeProfit = within(dialog).getByText("+30%").closest("li") as HTMLElement;
    fireEvent.click(within(takeProfit).getByRole("button", { name: "지우기" }));

    expect(await screen.findByText(/익절 \+30% 다시 정하기/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "익절 20%" })).toBeInTheDocument();
    expect(calls.parse).toBe(1);
  });

  // 조건 노드를 선택하고 Backspace를 누르면 "지울까요?" 확인을 받고, 확인하면 대화의 '다시 정하기' 경로로 지운다.
  it("asks for confirmation when Backspace is pressed on a selected condition node, then removes it", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await waitOrigin("confirmed");

    const nodes = await within(canvas()).findAllByTestId("lab-condition-node");
    const takeProfit = nodes.find((n) => n.textContent?.includes("익절"))!;
    fireEvent.click(takeProfit);
    fireEvent.keyDown(canvas(), { key: "Backspace" });

    const alert = await screen.findByRole("alertdialog");
    expect(within(alert).getByText(/지울까요\?/)).toBeInTheDocument();
    fireEvent.click(within(alert).getByRole("button", { name: "확인" }));

    expect(await screen.findByText(/익절 \+30% 다시 정하기/)).toBeInTheDocument();
  });

  // 노드를 더블클릭하면 상세 패널에서 그 칸의 값을 바로 바꾼다 — 해석 요청 없이 전략에 반영되고 다시 확정을 묻는다.
  it("edits a condition value from the double-click panel and applies it to the strategy without a parse call", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await waitOrigin("confirmed");

    fireEvent.doubleClick(await within(canvas()).findByTestId("lab-node-risk"));
    const editors = await screen.findAllByTestId("lab-item-editor");
    // 상세 패널은 설정만 보여 준다 — 입력·출력 칸은 없다.
    expect(screen.queryByText("입력")).not.toBeInTheDocument();
    expect(screen.queryByText("출력")).not.toBeInTheDocument();
    const stopLoss = editors.find((e) => e.textContent?.includes("손절"))!;
    const input = within(stopLoss).getByRole("spinbutton");
    expect(input).toHaveValue(10);
    const apply = within(stopLoss).getByRole("button", { name: "적용" });
    expect(apply).toBeDisabled();
    // 범위를 벗어난 값은 적용할 수 없다.
    fireEvent.change(input, { target: { value: "150" } });
    expect(apply).toBeDisabled();
    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.click(apply);

    // 바뀐 전략은 초안 컴파일로 다시 그려지고(확정 스냅샷과 달라짐), 채팅은 다시 확정을 묻는다.
    await waitOrigin("draft");
    const draftCall = [...fetchMock.mock.calls].reverse().find(([u, init]) => String(u) === "/api/strategy/compile" && isDraftPreview(init as RequestInit));
    expect(JSON.parse(String((draftCall?.[1] as RequestInit).body)).parsed.stop_loss_pct).toBe(7);
    expect(await screen.findByRole("button", { name: "이 전략으로 확정" })).toBeInTheDocument();
    expect(calls.parse).toBe(1);
  });

  it("gives the result screen the executed request, separate from the confirmed snapshot", async () => {
    install();
    resetGraphMetaForTests();
    render(<StrategyLabPage />);
    fireEvent.click(await reachConfirmation("익절 30%"));
    await waitOrigin("confirmed");
    fireEvent.click(await findRunButton());
    expect(await screen.findByTestId("backtest-dashboard")).toBeInTheDocument();
    expect(calls.backtest).toBe(1);
    expect(screen.getByTestId("dash-graph-origin")).toHaveTextContent("executed");
    expect(screen.getByTestId("dash-graph-tp")).toHaveTextContent("30");
  });
});
