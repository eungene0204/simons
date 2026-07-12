// [회귀] 뉴스 분석처럼 제공하지 않는 기능 기반 요청("최근 뉴스가 좋은 종목을 사는 전략")은
// 전략 빌더 모드로 자동 진입하지 않고 미제공 안내(UNSUPPORTED_FEATURE)만 보여준 뒤
// 사용자의 다른 아이디어를 기다려야 한다(2026-07-12).
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

const UNSUPPORTED_REPLY =
  "죄송합니다. 뉴스·공시 같은 재료 분석 기능은 현재 제공하고 있지 않아요. " +
  "다른 투자 아이디어를 알려주시면 전략으로 만들어 백테스트해 드릴 수 있어요.";

describe("미제공 기능(뉴스 분석) 기반 요청 안내", () => {
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

  it("미제공 안내를 보여주고 전략 빌더 모드로 진입하지 않는다", async () => {
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
            intent: "UNSUPPORTED_FEATURE",
            symbols: [],
            suggested_reply: UNSUPPORTED_REPLY,
          })
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "최근 뉴스가 좋은 종목을 사는 전략을 만들어줘" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 미제공 안내가 표시된다.
    expect(
      await screen.findByText(/재료 분석 기능은 현재 제공하고 있지 않아요/, undefined, {
        timeout: 5000,
      })
    ).toBeInTheDocument();

    // 빌더 스텝 호출도, 전략 파싱 호출도 없어야 한다 — 빌더 첫 질문("어떤 시장을 대상으로
    // 할까요?")으로 넘어가지 않고 사용자의 다른 아이디어를 기다린다.
    await waitFor(() => {
      const blockedCalls = fetchMock.mock.calls.filter(
        ([input]) =>
          String(input).includes("/api/strategy/builder/step") ||
          String(input).includes("/api/strategy/parse/stream")
      );
      expect(blockedCalls).toHaveLength(0);
    });

    // 후속 입력을 받을 수 있도록 입력창이 유지된다.
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });
});
