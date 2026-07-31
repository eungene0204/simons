// [회귀] 전략을 만드는 중 되묻기(리밸런싱)가 열려 있는데 사용자가 "안녕" 같은 부가 발화를
// 하면, 인사 응답이 그 질문을 삼켜 화면에서 질문과 선택지가 통째로 사라졌다(2026-07-31).
// 되묻기 블록은 마지막 assistant 메시지에만 렌더되므로 새 메시지 하나로 질문이 증발한다.
// 부가 발화는 전략 State를 건드리지 않으므로 워크플로를 유지해야 한다(설계 스펙 § 21) —
// 인사에는 인사로 답하되 열려 있던 질문을 그대로 다시 묻는다.
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

const REBALANCE_QUESTION = "리밸런싱은 얼마나 자주 할까요? (매월/분기/매년)";
const REBALANCE_CHIPS = ["매월 리밸런싱", "분기 리밸런싱"];
const GREETING_REPLY = "안녕하세요. 어떤 투자 아이디어를 가지고 계신가요?";

function minimalParsed() {
  return {
    description: "PER 10 이하 저평가주 20종목",
    universe: ["KOSPI", "KOSDAQ"],
    sector: null,
    target_symbols: [],
    entry_signals: [],
    exit_signals: [],
    fundamental_filters: [],
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

function mockFetch(classifyForPrompt: (query: string) => Record<string, unknown>) {
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
      return Promise.resolve(createJsonResponse(classifyForPrompt(body.query ?? "")));
    }
    if (url === "/api/strategy/parse/stream") {
      return Promise.resolve(sseResultResponse({
        parsed: minimalParsed(),
        clarification_question: REBALANCE_QUESTION,
        clarification_suggestions: REBALANCE_CHIPS,
        clarification_priority: "dag_planner",
        pending_ask: {
          topic: "리밸런싱",
          question: REBALANCE_QUESTION,
          chips: REBALANCE_CHIPS,
        },
        notices: [],
      }));
    }
    return Promise.resolve(createJsonResponse({}));
  });
}

async function sendFreeText(text: string) {
  // 되묻기 칩이 떠 있는 동안에는 입력창이 숨겨진다 — '직접 입력'으로 다시 연다.
  fireEvent.click(await screen.findByRole("button", { name: "직접 입력" }));
  const textarea = await screen.findByRole("textbox");
  fireEvent.change(textarea, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /전략 생성|전송/ }));
}

describe("부가 발화는 열려 있는 되묻기를 삼키지 않는다", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // 대화는 sessionStorage에 복원용으로 저장된다 — 앞 케이스의 되묻기가 남으면
    // 다음 케이스가 칩 대기 상태(입력창 숨김)로 시작한다.
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

  it("인사(GREETING)에 답한 뒤에도 리밸런싱 되묻기를 다시 묻는다", async () => {
    mockFetch((query) =>
      query === "안녕"
        ? { intent: "GREETING", symbols: [], suggested_reply: GREETING_REPLY }
        : { intent: "STRATEGY_ADVICE", symbols: [] }
    );

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 저평가주 20종목" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    await screen.findByText(new RegExp("리밸런싱은 얼마나 자주"), undefined, {
      timeout: 5000,
    });

    await sendFreeText("안녕");

    // 인사에는 인사로 답한다.
    await screen.findByText(new RegExp("어떤 투자 아이디어를"), undefined, {
      timeout: 5000,
    });

    // 그리고 열려 있던 되묻기는 선택지와 함께 그대로 남는다.
    await waitFor(() => {
      expect(screen.getByText(new RegExp("리밸런싱은 얼마나 자주"))).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "매월 리밸런싱" })).toBeInTheDocument();
    }, { timeout: 5000 });

    // 인사가 전략 파싱을 다시 돌리지도 않는다(질문 복원은 화면 상태만 되살린다).
    const parseCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/strategy/parse/stream"
    );
    expect(parseCalls).toHaveLength(1);

    // 열린 질문을 분류기에 함께 넘긴다 — 이게 없으면 그 답인 짧은 발화("아니야")가
    // 문맥 없는 잡담으로 보여 인사로 오분류된다(2026-07-31 실측).
    const classifyBodies = fetchMock.mock.calls
      .filter(([input]) => String(input) === "/api/query/classify")
      .map((call) => JSON.parse((call[1] as RequestInit).body as string));
    expect(classifyBodies[classifyBodies.length - 1].pending_question).toContain(
      "리밸런싱은 얼마나 자주",
    );
  });

  it("일반 지식 질문(GENERAL_INVESTMENT)에 답한 뒤에도 되묻기를 다시 묻는다", async () => {
    mockFetch((query) =>
      query === "PBR이 뭐야?"
        ? { intent: "GENERAL_INVESTMENT", symbols: [] }
        : { intent: "STRATEGY_ADVICE", symbols: [] }
    );
    const generalAnswer = "PBR은 주가를 주당순자산으로 나눈 지표입니다.";
    const baseImpl = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/query/general") {
        return Promise.resolve(createJsonResponse({ answer: generalAnswer }));
      }
      return baseImpl(input, init);
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 저평가주 20종목" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    await screen.findByText(new RegExp("리밸런싱은 얼마나 자주"), undefined, {
      timeout: 5000,
    });

    await sendFreeText("PBR이 뭐야?");

    await screen.findByText(new RegExp("주당순자산으로"), undefined, { timeout: 5000 });

    await waitFor(() => {
      expect(screen.getByText(new RegExp("리밸런싱은 얼마나 자주"))).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "매월 리밸런싱" })).toBeInTheDocument();
    }, { timeout: 5000 });
  });
});
