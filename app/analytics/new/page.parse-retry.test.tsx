// [회귀] LLM 콜드스타트(scale-to-zero)로 파싱 SSE 스트림이 결과(parsed_final) 없이 끊기면
// 조용한 로딩 방치가 아니라 오류 + '다시 시도' 버튼을 보여주고, 클릭 시 같은 프롬프트로
// 파싱을 재실행한다(2026-07-26 prod primary 전환 — 첫 파스 타임아웃 UX).
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

// 결과(parsed_final) 없이 끊긴 SSE 스트림 — 프록시 타임아웃으로 잘린 콜드스타트 재현.
function createCutStreamResponse() {
  return new Response('data: {"type":"stage","stage":"thinking"}\n\n', {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("파싱 스트림 타임아웃 '다시 시도'", () => {
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

  it("결과 없이 끊긴 스트림은 오류+다시 시도 버튼을 보여주고, 클릭 시 파싱을 재실행한다", async () => {
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
        return Promise.resolve(createCutStreamResponse());
      }
      return Promise.resolve(createJsonResponse({}));
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "골든크로스에 사고 데드크로스에 파는 전략" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 타임아웃 안내 + 다시 시도 버튼이 표시된다.
    expect(
      await screen.findByText(/시간 안에 도착하지 않았어요/, undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    const retryButton = await screen.findByTestId("parse-retry");

    const parseCallsBefore = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes("/api/strategy/parse/stream")
    ).length;
    expect(parseCallsBefore).toBe(1);

    // 재시도 클릭 → 같은 턴이 다시 파싱된다(사용자 버블 중복 없이).
    fireEvent.click(retryButton);
    await waitFor(() => {
      const parseCalls = fetchMock.mock.calls.filter(([input]) =>
        String(input).includes("/api/strategy/parse/stream")
      );
      expect(parseCalls).toHaveLength(2);
    });

    // 재시도도 끊기면 다시 같은 안내+버튼으로 돌아온다(무한 재시도 가능).
    expect(
      await screen.findByText(/시간 안에 도착하지 않았어요/, undefined, { timeout: 5000 })
    ).toBeInTheDocument();
    expect(await screen.findByTestId("parse-retry")).toBeInTheDocument();

    // 재시도 요청 본문은 실패한 원래 프롬프트를 그대로 담는다.
    const retryCall = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes("/api/strategy/parse/stream")
    )[1];
    const retryBody = JSON.parse(String(retryCall[1]?.body));
    expect(retryBody.prompt).toContain("골든크로스");
  });
});
