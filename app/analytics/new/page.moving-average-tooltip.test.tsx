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

describe("StrategyLab moving average help", () => {
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
          createJsonResponse({ user: { name: "Tester", email: "tester@example.com" } })
        );
      }

      if (url === "/api/query/classify") {
        return Promise.resolve(createJsonResponse({ intent: "ONBOARDING" }));
      }

      if (url === "/api/strategy/builder/step") {
        return Promise.resolve(
          createJsonResponse({
            state: { step: "ma_type" },
            reply: "어떤 이동평균을 쓸까요?",
            suggestions: ["단순(SMA)", "지수(EMA)"],
          })
        );
      }

      return Promise.resolve(createJsonResponse({}));
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it("shows SMA and EMA tooltip help next to the moving average choices", async () => {
    render(<StrategyLabPage />);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input) === "/api/user")).toBe(true);
    });

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "처음부터 전략 만들래" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(await screen.findByText("어떤 이동평균을 쓸까요?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "SMA와 EMA 설명" })).toBeInTheDocument();

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("SMA는 단순 이동평균");
    expect(tooltip).toHaveTextContent("EMA는 지수 이동평균");
  });
});
