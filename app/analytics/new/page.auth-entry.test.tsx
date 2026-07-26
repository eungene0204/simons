import type { ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  StrategyExampleTabs: ({
    onPreviewOpenChange,
  }: {
    onPreviewOpenChange?: (isOpen: boolean) => void;
  }) => (
    <div>
      예시 전략
      <button type="button" onClick={() => onPreviewOpenChange?.(true)}>
        미리보기 열기
      </button>
      <button type="button" onClick={() => onPreviewOpenChange?.(false)}>
        미리보기 닫기
      </button>
    </div>
  ),
}));

vi.mock("@/components/strategy/StrategyWaveBackground", () => ({
  StrategyWaveBackground: () => <div>배경</div>,
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
    vi.useRealTimers();
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  // 글자 진입 연출은 CSS animation-delay 캐스케이드가 만든다(.chat-headline-char).
  // 이전에는 38ms setInterval + 인라인 opacity였고, 이 테스트도 그 타이머를 전제로
  // opacity 0 -> 1을 검증했다. 타이머 구현은 글자마다 페이지 전체를 리렌더링했고
  // prefers-reduced-motion으로 끌 수도 없어 CSS로 옮겼다.
  it("staggers the headline letters through the CSS delay cascade", async () => {
    render(<StrategyLabPage />);

    await act(async () => {
      await Promise.resolve();
    });

    const headline = screen.getByTestId("strategy-lab-headline");
    expect(headline).toHaveTextContent(
      "투자 아이디어를 전략으로 만들고전략을 시뮬레이션 하세요"
    );
    expect(headline).toHaveClass("text-[27px]", "sm:text-5xl", "lg:text-7xl");
    expect(screen.getByTestId("strategy-lab-headline-stack")).toHaveClass(
      "w-full",
      "lg:w-auto"
    );
    expect(headline.querySelector(":scope > span")).toHaveClass(
      "whitespace-normal",
      "lg:whitespace-nowrap"
    );
    expect(screen.getByTestId("strategy-lab-background")).toHaveClass(
      "pt-10",
      "sm:pt-14",
      "lg:pt-20"
    );

    const animatedChars = Array.from(headline.querySelectorAll("span span"));
    expect(animatedChars).toHaveLength(
      "투자 아이디어를 전략으로 만들고전략을 시뮬레이션 하세요".length
    );
    expect(animatedChars[0]).toHaveClass("chat-headline-char");
    // 지연 순서는 --char-index가 줄 경계를 넘어 이어져야 한다.
    expect(animatedChars[0].getAttribute("style")).toContain("--char-index: 0");
    expect(animatedChars[animatedChars.length - 1].getAttribute("style")).toContain(
      `--char-index: ${animatedChars.length - 1}`
    );
  });

  it("opens a Google start modal when an anonymous user tries to generate a strategy", async () => {
    render(<StrategyLabPage />);

    expect(await screen.findByTestId("strategy-lab-headline")).toHaveTextContent(
      "투자 아이디어를 전략으로 만들고전략을 시뮬레이션 하세요"
    );

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

  // 리로드 직후 /api/user 왕복이 끝나기 전(authState=loading)에 전략 프롬프트를 보내면
  // 로그인된 사용자에게도 로그인 모달이 뜨던 회귀 — 하이드레이션 완료까지 보관 후 자동 전송.
  it("does not show the login modal when sending while auth is still hydrating and the user turns out to be logged in", async () => {
    let resolveUser!: (value: { ok: boolean; json: () => Promise<unknown> }) => void;
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "ready", error: null }),
        });
      }
      if (url === "/api/user") {
        return new Promise((resolve) => {
          resolveUser = resolve;
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 종목 전략 만들어줘" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    // 하이드레이션 완료 전에는 모달을 띄우지 않는다.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await act(async () => {
      resolveUser({ ok: true, json: async () => ({ user: { id: "u1" } }) });
      await Promise.resolve();
    });

    // 로그인 확인 후 보관했던 프롬프트가 자동 전송된다(인트로 페이지 → 채팅 소프트 내비게이션).
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/analytics?chat=1");
    });
    expect(window.sessionStorage.getItem("simons.pendingStrategyPrompt")).toBe(
      "PER 10 이하 종목 전략 만들어줘"
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the login modal after hydration resolves to anonymous for a prompt sent while loading", async () => {
    let resolveUser!: (value: { ok: boolean; json: () => Promise<unknown> }) => void;
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/model/status") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "ready", error: null }),
        });
      }
      if (url === "/api/user") {
        return new Promise((resolve) => {
          resolveUser = resolve;
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 종목 전략 만들어줘" } });
    fireEvent.click(screen.getByRole("button", { name: "전략 생성" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await act(async () => {
      resolveUser({ ok: true, json: async () => ({ user: null }) });
      await Promise.resolve();
    });

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("simons.pendingStrategyPrompt")).toBe(
      "PER 10 이하 종목 전략 만들어줘"
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("blurs the strategy lab background while a template preview is open", async () => {
    render(<StrategyLabPage />);

    const background = await screen.findByTestId("strategy-lab-background");
    expect(background.className).not.toContain("blur-[6px]");

    fireEvent.click(screen.getByRole("button", { name: "미리보기 열기" }));

    expect(background.className).toContain("blur-[6px]");
    expect(background.className).toContain("pointer-events-none");

    fireEvent.click(screen.getByRole("button", { name: "미리보기 닫기" }));

    expect(background.className).not.toContain("blur-[6px]");
  });
});
