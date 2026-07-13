// [회귀] 후속 질문("다른 예는 없어?")이 대화 맥락 없이 분류돼 OFF_TOPIC 거절로 새던 사고
// (2026-07-12). 분류·일반 답변 호출에 최근 대화 턴(history)을 함께 보내, 백엔드 LLM이
// 직전 답변의 주제에 이어 판단하게 한다.
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

const REDIRECT_REPLY =
  "삼성전자에 대한 매수·매도 판단이나 종목 추천은 제공하지 않아요.\n" +
  "예를 들어 이렇게 시작해볼 수 있어요:\n" +
  "• RSI가 30 이하로 떨어지면 매수하고 70 이상에서 파는 과매도 반등 전략";

function bodyOf(call: unknown[]): any {
  return JSON.parse((call[1] as RequestInit).body as string);
}

describe("후속 질문 분류에 대화 맥락 전달", () => {
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

  it("classify·general 호출 body에 직전 턴들이 history로 실린다", async () => {
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
        const body = JSON.parse(String(init?.body ?? "{}"));
        // 첫 질문은 종목 전환 안내, 후속 질문은(맥락 덕에) 일반 투자 답변으로 분류된다.
        if (body.query === "삼성전자 어때?") {
          return Promise.resolve(
            createJsonResponse({
              intent: "STOCK_ANALYSIS",
              symbols: [{ symbol: "005930", name: "삼성전자", overseas: false }],
              suggested_reply: REDIRECT_REPLY,
            })
          );
        }
        return Promise.resolve(createJsonResponse({ intent: "GENERAL_INVESTMENT" }));
      }
      if (url === "/api/query/general") {
        return Promise.resolve(
          createJsonResponse({ answer: "볼린저 밴드 하단 반등 전략도 있어요." })
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "삼성전자 어때?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    await screen.findByText(/과매도 반등 전략/, undefined, { timeout: 5000 });

    // 후속 질문 전송(대화 시작 후에는 전송 버튼 라벨이 "전송"이다).
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "다른 예는 없어?" } });
    fireEvent.click(screen.getByRole("button", { name: "전송" }));

    await screen.findByText(/볼린저 밴드 하단 반등 전략도 있어요/, undefined, {
      timeout: 5000,
    });

    const classifyCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/query/classify"
    );
    expect(classifyCalls).toHaveLength(2);

    // 첫 호출: 대화가 없으므로 history는 빈 배열.
    expect(bodyOf(classifyCalls[0]).history).toEqual([]);

    // 후속 호출: 직전 사용자 질문과 전환 안내가 history로 실린다.
    const followUpBody = bodyOf(classifyCalls[1]);
    expect(followUpBody.query).toBe("다른 예는 없어?");
    expect(followUpBody.history).toEqual([
      { role: "user", text: "삼성전자 어때?" },
      { role: "assistant", text: REDIRECT_REPLY },
    ]);

    // 일반 답변 호출에도 같은 맥락이 실린다(직전 답변에 이어 답하도록).
    const generalCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/query/general"
    );
    expect(generalCalls).toHaveLength(1);
    expect(bodyOf(generalCalls[0]).history).toEqual(followUpBody.history);
  });
});
