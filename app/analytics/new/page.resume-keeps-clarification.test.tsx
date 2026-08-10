// [회귀] 되묻기(익절 등)가 열려 있는 상태에서 대화를 재개(RESUME)하면, 일반 안내
// ("다음으로 정할 조건을 말씀해 주세요")만 나가고 열려 있던 질문이 화면에서 사라졌다.
// pending_ask는 상태에 그대로 살아 있으므로, 재개 후 첫 발화("리스크 관리")가 보이지
// 않는 질문의 답으로 해석돼 말한 적 없는 값이 확정됐다(2026-08-10 익절 8% 사고).
// RESUME 턴은 열려 있던 되묻기를 선택지와 함께 그대로 다시 세워야 한다.
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

const TAKE_PROFIT_QUESTION = "익절 — 목표 수익 비율을 정해주세요 (예: 익절 20%, 익절 10%)";
const TAKE_PROFIT_CHIPS = ["익절 20%", "익절 10%"];

function minimalParsed() {
  return {
    description: "거래대금 50억 이상, 60일 수익률 상위 15종목",
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
        clarification_question: TAKE_PROFIT_QUESTION,
        clarification_suggestions: TAKE_PROFIT_CHIPS,
        clarification_priority: "dag_planner",
        pending_ask: {
          topic: "리스크 관리",
          question: TAKE_PROFIT_QUESTION,
          chips: TAKE_PROFIT_CHIPS,
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

describe("재개(RESUME) 턴은 열려 있는 되묻기를 다시 세운다", () => {
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

  it("'계속 이어서 하자' 뒤에도 익절 되묻기가 선택지와 함께 남는다", async () => {
    mockFetch((query) =>
      query === "계속 이어서 하자"
        ? { intent: "STRATEGY_ADVICE", symbols: [], workflow_effect: "RESUME" }
        : { intent: "STRATEGY_ADVICE", symbols: [], workflow_effect: "NONE" }
    );

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, {
      target: { value: "거래대금 50억 이상, 60일 수익률 상위 15종목" },
    });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    await screen.findByText(new RegExp("목표 수익 비율을 정해주세요"), undefined, {
      timeout: 5000,
    });

    await sendFreeText("계속 이어서 하자");

    // 재개 안내가 나가고, 열려 있던 되묻기는 선택지와 함께 그대로 남는다 —
    // 질문 없이 "다음으로 정할 조건을 말씀해 주세요"만 나가면 다음 발화가
    // 보이지 않는 질문의 답으로 해석된다.
    await screen.findByText(new RegExp("이어서 진행할게요"), undefined, { timeout: 5000 });
    await waitFor(() => {
      expect(
        screen.getByText(new RegExp("목표 수익 비율을 정해주세요")),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "익절 20%" })).toBeInTheDocument();
    }, { timeout: 5000 });
    expect(
      screen.queryByText(new RegExp("다음으로 정할 조건을 말씀해 주세요")),
    ).not.toBeInTheDocument();

    // 재개가 전략 파싱을 다시 돌리지 않는다(질문 복원은 화면 상태만 되살린다).
    const parseCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/strategy/parse/stream"
    );
    expect(parseCalls).toHaveLength(1);
  });
});
