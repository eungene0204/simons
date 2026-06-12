import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StrategyLabPage from "./page";

const push = vi.fn();
const signInWithOAuth = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/analytics",
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

vi.mock("@/components/strategy/StockAnalysisPanel", () => ({
  default: () => <div>종목 분석</div>,
}));

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth,
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  }),
}));

describe("StrategyLab auth entry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/model/status") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "ready", error: null }),
        });
      }

      if (url === "/api/user") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ user: null }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      });
    });

    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://example.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key";
    signInWithOAuth.mockResolvedValue({ error: null });
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it("opens a Google start modal when an anonymous user tries to generate a strategy", async () => {
    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 종목 전략 만들어줘" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("아이디어를 전략으로 만들어 드립니다")).toBeInTheDocument();
    expect(screen.getByText("Google로 3초만에 시작하세요")).toBeInTheDocument();
    expect(screen.getByText("카드 등록 불필요")).toBeInTheDocument();
    expect(screen.queryByText("PER 10 이하 종목 전략 만들어줘")).not.toBeInTheDocument();

    const ctaButton = screen.getByRole("button", { name: "Google로 시작하기" });
    fireEvent.click(ctaButton);

    await waitFor(() => {
      expect(signInWithOAuth).toHaveBeenCalledWith({
        provider: "google",
        options: {
          redirectTo: window.location.href,
          queryParams: {
            access_type: "offline",
            prompt: "select_account",
          },
        },
      });
    });

    expect(window.sessionStorage.getItem("simons.pendingStrategyPrompt")).toBe(
      "PER 10 이하 종목 전략 만들어줘"
    );
  });
});
