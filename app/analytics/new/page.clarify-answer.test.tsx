// [회귀] "초기자금을 얼마로 변경할까요?"에 사용자가 '직접 입력'으로 "3억원"이라고 답하면
// 같은 질문이 다시 나오는 무한 되묻기(2026-07-31 사용자 신고). 되묻기 답변은 필드를 밝히지
// 않으므로 분류 LLM의 clarify_target이 그대로 다시 나오는데(그 축은 '값이 함께 왔는가'를
// 알지 못한다), 되묻기 레인이 그걸 근거로 또 가로챈 것이 원인이다.
// 계약: 답을 기다리는 질문이 떠 있으면 그 턴의 입력은 답이다 — 되묻기 레인은 개입하지 않고
// 파스 레인(LLM)이 해석하며, 어떤 질문에 대한 답인지는 pending_question 에코가 알려준다.
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StrategyLabPage from "./page";

const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
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

const CAPITAL_QUESTION = "초기자금을 얼마로 변경할까요?";

function createJsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

// 진행 골격 8칸이 모두 채워진 전략 — 이래야 파스 뒤에 최소 조건 되묻기가 열리지 않아
// 이 테스트가 보려는 '수정 되묻기'만 남는다.
function completeParsed(initialCapital: number) {
  return {
    description: "20일 고점 돌파 전략",
    universe: ["KOSPI200"],
    sector: null,
    target_symbols: [],
    entry_signals: [{ indicator: "breakout", signal_type: "buy", lookback_period: 20 }],
    exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
    fundamental_filters: [],
    max_positions: 3,
    rebalancing_period: "monthly",
    stop_loss_pct: 6,
    take_profit_pct: 30,
    backtest_period: "5y",
    initial_capital: initialCapital,
  };
}

const EXPLICIT_FIELDS = [
  "universe", "max_positions", "rebalancing", "backtest_period", "initial_capital",
];

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

function bodiesFor(url: string) {
  return fetchMock.mock.calls
    .filter(([input]) => String(input) === url)
    .map((call) => JSON.parse((call[1] as RequestInit).body as string));
}

async function send(text: string) {
  // 칩이 떠 있는 동안 입력창은 숨겨진다 — 사용자는 '직접 입력'으로 다시 연다.
  const freeInput = screen.queryByRole("button", { name: "직접 입력" });
  if (freeInput) fireEvent.click(freeInput);
  const textarea = await screen.findByRole("textbox");
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /전략 생성|전송/ }));
}

describe("되묻기 답변은 파스 레인이 해석한다", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
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
        const body = JSON.parse((init?.body as string) ?? "{}");
        // 값을 말해도 대상은 그대로 나온다 — 실측(9B): "3억원" → initial_capital.
        const clarify = /초기자금|억원/.test(String(body.query)) ? "initial_capital" : null;
        return Promise.resolve(createJsonResponse({
          intent: "STRATEGY_ADVICE",
          symbols: [],
          workflow_effect: "UPDATE",
          workflow_status: "ACTIVE",
          clarify_target: clarify,
        }));
      }
      if (url === "/api/strategy/parse/stream") {
        const body = JSON.parse((init?.body as string) ?? "{}");
        const capital = body.pending_question ? 300_000_000 : 10_000_000;
        return Promise.resolve(sseResultResponse({
          parsed: completeParsed(capital),
          explicit_fields: EXPLICIT_FIELDS,
          notices: [],
        }));
      }
      if (url === "/api/strategy/coach") {
        return Promise.resolve(createJsonResponse({ message: "검증 결과입니다." }));
      }
      return Promise.resolve(createJsonResponse({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("'3억원' 답변을 같은 질문으로 되받지 않고 파스 레인에 질문과 함께 넘긴다", async () => {
    render(<StrategyLabPage />);
    await send("코스피200에서 20일 고점 돌파 시 매수, 데드크로스 매도, 최대 3종목, 매월 리밸런싱, 손절 -6%, 익절 30%, 최근 5년, 초기자금 1000만원");
    await waitFor(() => expect(bodiesFor("/api/strategy/parse/stream")).toHaveLength(1));

    // ① 값 없는 수정 요청에는 되묻는다(기존 동작).
    await send("초기자금 바꿔줘");
    expect(await screen.findByText(new RegExp(CAPITAL_QUESTION))).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "초기자금 1억원으로 변경" })).toBeInTheDocument();

    // ② 그 질문의 답은 파스 레인으로 간다 — 되묻기가 다시 가로채지 않는다.
    await send("3억원");
    await waitFor(() => expect(bodiesFor("/api/strategy/parse/stream")).toHaveLength(2));

    const answerBody = bodiesFor("/api/strategy/parse/stream")[1];
    expect(answerBody.prompt).toBe("3억원");
    // 어느 필드의 답인지는 질문이 정한다(백엔드 인터프리터가 이 문맥으로 귀속한다).
    expect(answerBody.pending_question).toContain("초기자금을 얼마로");
    expect(answerBody.previous_parsed).toBeTruthy();
  });
});
