// [회귀] planner 유니버스 ask 칩("보안주(정보)") 클릭이 의도 분류를 거쳐 OFF_TOPIC 거절로
// 새던 사고(2026-07-28). pending_ask 칩과 정확히 일치하는 입력은 시스템 생성 열거형
// 선택지의 '답'이므로 분류 없이 곧장 파스 레인으로 보낸다 — 백엔드 결정론 칩 귀속
// (run_chip_answer)이 pending_ask 에코로 처리한다.
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

const UNIVERSE_QUESTION = "'보안주'의 범위를 어떻게 정할까요?";
const UNIVERSE_CHIPS = ["보안주(정보)", "보안주(물리)"];

function minimalParsed(overrides: Record<string, unknown> = {}) {
  return {
    description: "보안주 관련 투자 전략",
    universe: ["KOSPI", "KOSDAQ"],
    sector: null,
    target_symbols: [],
    entry_signals: [],
    exit_signals: [],
    fundamental_filters: [],
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

function bodyOf(call: unknown[]): any {
  return JSON.parse((call[1] as RequestInit).body as string);
}

describe("planner 유니버스 ask 칩 — 분류 우회 결정론 귀속", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it("pending_ask 칩 클릭은 분류를 거치지 않고 pending_ask 에코와 함께 파스로 간다", async () => {
    let parseCalls = 0;
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
        return Promise.resolve(
          createJsonResponse({ intent: "STRATEGY_ADVICE", symbols: [] })
        );
      }
      if (url === "/api/strategy/parse/stream") {
        parseCalls += 1;
        if (parseCalls === 1) {
          // 턴 1: planner-first 유니버스 범위 되묻기 + pending_ask 에코 컨텍스트
          return Promise.resolve(sseResultResponse({
            parsed: minimalParsed(),
            clarification_question: UNIVERSE_QUESTION,
            clarification_suggestions: UNIVERSE_CHIPS,
            clarification_priority: "dag_planner",
            pending_ask: {
              topic: "유니버스",
              question: UNIVERSE_QUESTION,
              chips: UNIVERSE_CHIPS,
            },
            notices: [],
          }));
        }
        // 턴 2: 칩 결정론 귀속 결과 — 테마 상장사 반영
        return Promise.resolve(sseResultResponse({
          parsed: minimalParsed({ target_symbols: ["012345"] }),
          clarification_question: null,
          clarification_suggestions: null,
          clarification_priority: null,
          pending_ask: null,
          notices: ["'보안주(정보)' 관련 상장사 1곳을 대상 종목으로 설정했어요."],
        }));
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "보안주 관련 투자 전략" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 턴 1: 유니버스 범위 질문과 범위 칩이 표시된다.
    await screen.findByText(new RegExp("보안주'의 범위를 어떻게"), undefined, {
      timeout: 5000,
    });
    const chipButton = await screen.findByRole("button", { name: "보안주(정보)" });

    fireEvent.click(chipButton);

    // 턴 2: 칩 입력이 파스 레인으로 직행한다(분류 우회).
    await waitFor(() => {
      const parseStreamCalls = fetchMock.mock.calls.filter(
        ([input]) => String(input) === "/api/strategy/parse/stream"
      );
      expect(parseStreamCalls).toHaveLength(2);
    }, { timeout: 5000 });

    const parseStreamCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/strategy/parse/stream"
    );
    const chipTurnBody = bodyOf(parseStreamCalls[1]);
    expect(chipTurnBody.prompt).toBe("보안주(정보)");
    expect(chipTurnBody.previous_parsed).toBeTruthy();
    // pending_ask 에코 — 백엔드 결정론 칩 귀속(run_chip_answer)의 판정 근거
    expect(chipTurnBody.pending_ask).toEqual({
      topic: "유니버스",
      question: UNIVERSE_QUESTION,
      chips: UNIVERSE_CHIPS,
    });

    // 칩 텍스트가 의도 분류로 새지 않았다 — OFF_TOPIC 거절 사고의 재발 방지 핵심
    const classifyCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/query/classify"
    );
    for (const call of classifyCalls) {
      expect(bodyOf(call).query).not.toBe("보안주(정보)");
    }
    expect(
      screen.queryByText(/투자 전략 및 투자 분석 전용 모델/)
    ).not.toBeInTheDocument();
  });
});
