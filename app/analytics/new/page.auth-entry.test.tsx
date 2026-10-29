import type { ReactNode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StrategyLabPage from "./page";

const push = vi.fn();
const signInWithOAuth = vi.fn();
const fetchMock = vi.fn();
let chatQuery = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/analytics",
  useSearchParams: () => new URLSearchParams(chatQuery),
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
    chatQuery = "";
    window.sessionStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  // 캔버스 레이아웃(2026-10-28)은 화면 제목 자리에 툴바의 전략 이름을 둔다. 페이지 유일 h1은 검색엔진이
  // 본문 제목으로 읽도록 보이지 않게(sr-only) 남긴다(SEO 2026-09-13).
  it("keeps the single page h1 and shows the five lab areas", async () => {
    render(<StrategyLabPage />);

    await act(async () => {
      await Promise.resolve();
    });

    const headline = screen.getByTestId("strategy-lab-headline");
    expect(headline.tagName).toBe("H1");
    expect(headline).toHaveTextContent("퀀트 전략을 입력하세요");
    expect(headline).toHaveClass("sr-only");
    expect(document.querySelectorAll("h1")).toHaveLength(1);

    expect(screen.getByTestId("lab-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("lab-left-drawer")).toBeInTheDocument();
    expect(screen.getByTestId("lab-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("lab-chat-panel")).toBeInTheDocument();
    // 왼쪽 서랍은 전략 예시 탭이 첫 번째이고 처음부터 열려 있다.
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs.indexOf("전략 예시")).toBeLessThan(tabs.indexOf("대화 기록"));
    expect(screen.getByRole("tab", { name: "전략 예시" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "대화 기록" })).toHaveAttribute("aria-selected", "false");
    // 빈 캔버스는 채팅으로 안내하고, 전략이 없으니 실행 버튼은 막혀 있다.
    expect(screen.getByTestId("lab-canvas-empty")).toHaveTextContent("아래 채팅창에 전략을 설명해 보세요");
    expect(screen.getByTestId("lab-run-button")).toBeDisabled();
  });

  it("opens a Google start modal when an anonymous user tries to generate a strategy", async () => {
    render(<StrategyLabPage />);

    expect(await screen.findByTestId("strategy-lab-headline")).toHaveTextContent(
      "퀀트 전략을 입력하세요"
    );

    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "PER 10 이하 종목 전략 만들어줘" } });
    fireEvent.keyDown(textarea, { key: "Enter" });

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("아이디어를 전략으로 만들어 드립니다")).toBeInTheDocument();
    expect(screen.getByText("Google 또는 이메일로 시작하세요")).toBeInTheDocument();
    expect(screen.getByText("카드 등록 불필요")).toBeInTheDocument();
    expect(textarea).toHaveValue("PER 10 이하 종목 전략 만들어줘");

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

  it("continues the saved strategy after login returns to the intro page", async () => {
    window.sessionStorage.setItem("simons.pendingStrategyPrompt", "PER 10 이하 종목 전략 만들어줘");
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/user") {
        return Promise.resolve({ ok: true, json: async () => ({ user: { id: 1 } }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ status: "ready", error: null }) });
    });

    const view = render(<StrategyLabPage />);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/analytics?chat=1"));
    expect(window.sessionStorage.getItem("simons.pendingStrategyPrompt")).toBe(
      "PER 10 이하 종목 전략 만들어줘"
    );

    chatQuery = "chat=1";
    view.rerender(<StrategyLabPage />);

    await waitFor(() => {
      expect(window.sessionStorage.getItem("simons.pendingStrategyPrompt")).toBeNull();
      expect(screen.getByText("PER 10 이하 종목 전략 만들어줘")).toBeInTheDocument();
    });
    expect(push).toHaveBeenCalledTimes(1);
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

  // 예시 카드는 문장을 입력창에 채우기만 한다 — 자동 전송하지 않는다(로그인 대화상자도 뜨지 않는다).
  it("fills the chat input from an example card without sending it", async () => {
    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    fireEvent.click(screen.getByRole("tab", { name: "전략 예시" }));
    const [firstCard] = screen.getAllByTestId("lab-example-card");
    fireEvent.click(firstCard);

    expect((textarea as HTMLTextAreaElement).value.length).toBeGreaterThan(0);
    expect(firstCard).toHaveTextContent((textarea as HTMLTextAreaElement).value.slice(0, 20));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/query/classify"))).toBe(false);
  });
  // "+"는 캔버스 위에서 블록 트레이를 내린다. 블록은 값이 정해진 되묻기 칩이고, 올리는 즉시 전략에 포함된다 —
  // 채팅 턴(해석 요청)도 로그인 대화상자도 없다. 다음에 정할 조건은 채팅이 이어서 묻는다.
  it("includes a picked block in the strategy immediately without a chat turn, then asks the next condition", async () => {
    render(<StrategyLabPage />);

    const textarea = (await screen.findByRole("textbox")) as HTMLTextAreaElement;
    const tray = screen.getByTestId("lab-block-tray");
    expect(tray).toHaveAttribute("data-open", "false");
    fireEvent.click(screen.getByRole("button", { name: "블록 추가" }));
    expect(tray).toHaveAttribute("data-open", "true");

    fireEvent.click(within(tray).getByRole("tab", { name: "위험 관리" }));
    const options = within(tray).getAllByTestId("lab-block-option").map((o) => o.textContent);
    expect(options).toEqual(["손절 -5%", "손절 -10%", "손절 -15%", "익절 10%", "익절 20%", "익절 30%"]);

    fireEvent.click(within(tray).getByRole("tab", { name: "투자 대상" }));
    fireEvent.click(within(tray).getByRole("button", { name: "코스피" }));

    expect(tray).toHaveAttribute("data-open", "false");
    expect(textarea.value).toBe("");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/strategy/parse"))).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/query/classify"))).toBe(false);
    // 투자 대상이 정해졌으니 채팅은 다음 조건(매수 조건)을 묻는다.
    const card = await screen.findByTestId("clarification-card");
    expect(card).toHaveTextContent("매수");
    expect(screen.queryByText("어떤 시장을 대상으로 할까요?")).not.toBeInTheDocument();
  });

  // 트레이가 내려와 있을 때 다른 곳(캔버스 바탕·채팅 입력창)을 누르면 접힌다. 여는 "+" 버튼은 토글로 남는다.
  it("collapses the block tray when something outside it is pressed", async () => {
    render(<StrategyLabPage />);

    const textarea = await screen.findByRole("textbox");
    const tray = screen.getByTestId("lab-block-tray");
    const toggle = screen.getByRole("button", { name: "블록 추가" });

    fireEvent.click(toggle);
    expect(tray).toHaveAttribute("data-open", "true");
    // 트레이 안(칸 탭)을 눌러도 열려 있다.
    fireEvent.pointerDown(within(tray).getByRole("tab", { name: "위험 관리" }));
    expect(tray).toHaveAttribute("data-open", "true");
    // 바깥(채팅 입력창)을 누르면 접힌다.
    fireEvent.pointerDown(textarea);
    expect(tray).toHaveAttribute("data-open", "false");

    // "+" 버튼은 누르는 순간 접었다 다시 열지 않고 토글로 동작한다.
    fireEvent.pointerDown(toggle);
    fireEvent.click(toggle);
    expect(tray).toHaveAttribute("data-open", "true");
    fireEvent.pointerDown(toggle);
    fireEvent.click(toggle);
    expect(tray).toHaveAttribute("data-open", "false");
  });
});
