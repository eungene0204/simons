// [회귀] '대화 종료'로 새 대화를 시작한 뒤 인사("안녕 뭘 만들어 볼까?")를 보냈는데, 해석 실패
// 안내와 함께 **직전 대화의 전략 카드**가 되살아났다(2026-09-06 프로덕션 신고).
// 채팅 진입은 같은 라우트의 ?chat=1 소프트 내비게이션이라 컴포넌트(ref)가 그대로 살아 있고,
// 새 대화 초기화가 '열린 되묻기'(openClarificationRef)를 비우지 않아 실패 안내 턴
// (preservesOpenQuestion)이 그 되묻기에 저장된 옛 전략 카드를 다시 세웠다.
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
const FIRST_STRATEGY = "코스피 PBR 0.8 이하 10종목 분기 리밸런싱";
const GREETING = "안녕 뭘 만들어 볼까?";
const INTERPRETATION_FAILED_NOTICE =
  "죄송해요, 방금 입력을 해석하지 못했어요. 잠시 후 다시 시도하시거나 조금 다르게 표현해 주시겠어요?";

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

function mockFetch() {
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
      // 인사는 LLM 미가용으로 해석 실패(프로덕션 재현) — 전략 발화는 파스 레인으로.
      return Promise.resolve(createJsonResponse(
        body.query === GREETING
          ? { intent: "UNKNOWN", interpretation_failed: true }
          : { intent: "STRATEGY_ADVICE", symbols: [], workflow_effect: "NONE" },
      ));
    }
    if (url === "/api/strategy/parse/stream") {
      return Promise.resolve(sseResultResponse({
        parsed: {
          description: FIRST_STRATEGY,
          universe: ["KOSPI"],
          sector: null,
          target_symbols: [],
          entry_signals: [],
          exit_signals: [],
          fundamental_filters: [{ metric: "pbr", operator: "<=", value: 0.8 }],
          max_positions: 10,
          rebalancing_period: "quarterly",
        },
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

describe("'대화 종료' 뒤 새 대화에는 직전 대화의 전략·되묻기가 남지 않는다", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
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

  it("해석 실패 안내에 옛 전략 카드와 옛 되묻기가 되살아나지 않는다", async () => {
    mockFetch();
    render(<StrategyLabPage />);

    // 1) 첫 대화: 전략 파싱 → 익절 되묻기가 열린 채로 끝난다(카드 표시).
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: FIRST_STRATEGY } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    await screen.findByText(/목표 수익 비율을 정해주세요/, undefined, { timeout: 5000 });
    expect(screen.getByTestId("builder-strategy-summary")).toBeInTheDocument();

    // 2) '대화 종료' — 같은 컴포넌트가 유지된 채 새 대화가 시작된다(?chat=1 소프트 내비).
    fireEvent.click(screen.getByRole("button", { name: "대화 종료" }));
    await waitFor(() => {
      expect(screen.queryByTestId("builder-strategy-summary")).not.toBeInTheDocument();
    });

    // 3) 새 대화의 첫 발화가 해석 실패로 끝나도 옛 전략은 어디에도 남아 있지 않아야 한다.
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: GREETING } });
    fireEvent.click(screen.getByRole("button", { name: /전략 생성|전송/ }));
    await screen.findByText(INTERPRETATION_FAILED_NOTICE, undefined, { timeout: 5000 });

    expect(screen.queryByTestId("builder-strategy-summary")).not.toBeInTheDocument();
    // 카드 값(PBR <= 0.8)이 없어야 한다 — 왼쪽 대화 로그에 남는 이전 대화 제목은 의도된 기록이다.
    expect(screen.queryByText(/PBR <= 0\.8/)).not.toBeInTheDocument();
    expect(screen.queryByText(/목표 수익 비율을 정해주세요/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "익절 20%" })).not.toBeInTheDocument();
    // 해석 실패 턴은 분류 LLM 실패 보고 그대로 끝난다 — 파싱을 다시 돌리지 않는다.
    const parseCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/strategy/parse/stream"
    );
    expect(parseCalls).toHaveLength(1);
  });
});
