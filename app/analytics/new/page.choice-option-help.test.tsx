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

describe("선택 칩 설명 아이콘", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.stubGlobal("scrollTo", vi.fn());
    window.sessionStorage.clear();

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve(createJsonResponse({ status: "ready", error: null }));
      }
      if (url === "/api/user") {
        return Promise.resolve(
          createJsonResponse({ user: { name: "Tester", email: "tester@example.com" } }),
        );
      }
      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "ONBOARDING" }));
      }
      if (url === "/api/strategy/builder/step") {
        return Promise.resolve(
          createJsonResponse({
            state: { step: "stop_loss" },
            reply: "이제 손절 기준을 몇 %로 정할까요?",
            suggestions: ["손절 -5%", "손절 -10%", "손절 안 함"],
          }),
        );
      }
      return Promise.resolve(createJsonResponse({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  async function openStopLossQuestion() {
    render(<StrategyLabPage />);
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/user")).toBe(true);
    });
    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "처음부터 전략 만들래" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));
    expect(await screen.findByText("이제 손절 기준을 몇 %로 정할까요?")).toBeInTheDocument();
  }

  it("매수 박스가 아닌 질문의 칩에도 설명 아이콘이 붙는다", async () => {
    await openStopLossQuestion();

    for (const chip of ["손절 -5%", "손절 -10%", "손절 안 함"]) {
      expect(screen.getByRole("button", { name: `${chip} 설명` })).toBeInTheDocument();
    }
  });

  it("아이콘에 마우스를 올리면 그 선택지의 설명이 뜨고, 벗어나면 사라진다", async () => {
    await openStopLossQuestion();

    const trigger = screen.getByRole("button", { name: "손절 -10% 설명" });
    fireEvent.mouseEnter(trigger);

    const bubble = await screen.findByTestId("choice-option-help-bubble");
    expect(bubble).toHaveTextContent("매수가보다 10% 내려가면 매도합니다.");

    fireEvent.mouseLeave(trigger);
    expect(screen.queryByTestId("choice-option-help-bubble")).not.toBeInTheDocument();
  });

  // 아이콘은 칩 안에 중첩된 버튼이 아니다 — 눌러도 선택지가 골라지면 안 된다.
  it("아이콘을 눌러도 선택지가 제출되지 않는다", async () => {
    await openStopLossQuestion();

    const before = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "손절 -5% 설명" }));

    expect(await screen.findByTestId("choice-option-help-bubble")).toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBe(before);
  });
});
