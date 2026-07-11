// [회귀] 특정 종목 질문("삼성전자 어때?") 전환 안내 후 전략 빌더 모드로 자동 진입하지 않는다.
// 안내가 이미 그 종목 기반의 구체적인 전략 예시를 제시하므로, 빌더의 첫 질문("어떤 시장을
// 대상으로 할까요?")이 예시를 덮지 않도록 사용자의 후속 답변을 기다려야 한다(2026-07-11).
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
  "• 삼성전자가 속한 반도체 업종 종목만 대상으로, 최근 3개월 수익률 상위 5종목을 매수하는 전략";

describe("특정 종목 질문 전환 안내", () => {
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

  it("전환 안내를 보여주고 전략 빌더 모드로 자동 진입하지 않는다", async () => {
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
          createJsonResponse({
            intent: "STOCK_ANALYSIS",
            symbols: [{ symbol: "005930", name: "삼성전자", overseas: false }],
            suggested_reply: REDIRECT_REPLY,
          })
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "삼성전자 어때?" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 전환 안내(종목 기반 전략 예시 포함)가 표시된다.
    expect(
      await screen.findByText(/삼성전자가 속한 반도체 업종 종목만 대상으로/, undefined, {
        timeout: 5000,
      })
    ).toBeInTheDocument();

    // 빌더 스텝 호출이 없어야 한다 — 빌더 첫 질문이 예시를 덮지 않고 후속 답변을 기다린다.
    await waitFor(() => {
      const builderCalls = fetchMock.mock.calls.filter(([input]) =>
        String(input).includes("/api/strategy/builder/step")
      );
      expect(builderCalls).toHaveLength(0);
    });

    // 후속 입력을 받을 수 있도록 입력창이 유지된다.
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });
});
