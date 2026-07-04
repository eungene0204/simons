import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TopNavigation from "@/components/layout/TopNavigation";
import { mergePopularStocks } from "@/components/layout/QuickSearchModal";

const { pathnameMock, searchParamsMock } = vi.hoisted(() => ({
  pathnameMock: { current: "/" },
  searchParamsMock: { current: "" },
}));

const pushMock = vi.fn();
const replaceMock = vi.fn();
const fetchMock = vi.fn();
const getSessionMock = vi.fn();
const signOutMock = vi.fn();
const signInWithOAuthMock = vi.fn();
const isSupabaseConfiguredMock = vi.fn();

vi.mock("next/image", () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} alt={props.alt || ""} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    onClick,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} onClick={onClick} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameMock.current,
  useSearchParams: () => new URLSearchParams(searchParamsMock.current),
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    refresh: vi.fn(),
  }),
}));

vi.mock("@/lib/firebase", () => ({
  getSupabaseBrowserClient: () => ({
    auth: {
      getSession: getSessionMock,
      signOut: signOutMock,
      signInWithOAuth: signInWithOAuthMock,
    },
  }),
  isSupabaseConfigured: () => isSupabaseConfiguredMock(),
}));

vi.stubGlobal("fetch", fetchMock);

// EventSource mock — popular-stream SSE는 테스트에서 사용하지 않으므로 no-op
class MockEventSource {
  static instances: MockEventSource[] = [];

  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  close() {}
}
vi.stubGlobal("EventSource", MockEventSource);

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe("TopNavigation quick search", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockEventSource.instances = [];
    pathnameMock.current = "/";
    searchParamsMock.current = "";
    isSupabaseConfiguredMock.mockReturnValue(true);
    getSessionMock.mockResolvedValue({ data: { session: null } });
    signOutMock.mockResolvedValue(undefined);
    signInWithOAuthMock.mockResolvedValue({ error: null });

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/user") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ user: null }),
        });
      }

      if (url.startsWith("/api/quick-search")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            stocks: [
              {
                symbol: "005930",
                name: "삼성전자",
                type: "KOSPI",
                region: "KR",
                currency: "KRW",
              },
            ],
            strategies: [
              {
                id: "strategy-1",
                name: "삼성 모멘텀 전략",
                description: "삼성전자 중심 전략",
                strategyType: "모멘텀",
                universe: "KOSPI",
              },
            ],
            virtualAccounts: [
              {
                id: "account-1",
                name: "삼성 테스트 계좌",
                strategyName: "삼성 모멘텀 전략",
                tradingMode: "auto",
              },
            ],
          }),
        });
      }

      if (url === "/api/stock/popular") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            stocks: [
              { rank: 1, symbol: "005930", name: "삼성전자", changePercent: 0.12 },
              { rank: 2, symbol: "000660", name: "SK하이닉스", changePercent: -0.34 },
              { rank: 3, symbol: "373220", name: "LG에너지솔루션", changePercent: 0 },
              { rank: 4, symbol: "005380", name: "현대차", changePercent: 0 },
              { rank: 5, symbol: "068270", name: "셀트리온", changePercent: 0 },
            ],
            updatedAt: "09:00:00",
          }),
        });
      }

      return Promise.resolve({
        ok: false,
        json: async () => ({}),
      });
    });
  });

  it("슬래시 퀵서치에서 종목, 전략, 가상계좌를 검색하고 이동할 수 있다", async () => {
    renderWithQueryClient(<TopNavigation />);

    fireEvent.keyDown(window, { key: "/" });

    const input = await screen.findByPlaceholderText(
      "종목, 전략, 계좌, 백테스트를 검색하세요"
    );
    fireEvent.change(input, { target: { value: "삼성" } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/quick-search?q=%EC%82%BC%EC%84%B1");
    });

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("삼성 모멘텀 전략")).toBeInTheDocument();
    expect(screen.getByText("삼성 테스트 계좌")).toBeInTheDocument();

    fireEvent.click(screen.getByText("삼성 테스트 계좌"));

    expect(pushMock).toHaveBeenCalledWith("/virtual-account/account-1");
  });

  it("루트 경로에서는 전략연구소 메뉴를 활성 상태로 표시한다", async () => {
    pathnameMock.current = "/";

    renderWithQueryClient(<TopNavigation />);

    const analyticsLink = await screen.findByRole("link", { name: /전략연구소/i });
    const dashboardLink = screen.getByRole("link", { name: /대시보드/i });

    expect(analyticsLink.className).toContain("bg-white/10");
    expect(dashboardLink.className).not.toContain("bg-white/10");
  });

  it("상단 로고는 원본 이미지 기반의 투명 NS 마크를 표시한다", async () => {
    renderWithQueryClient(<TopNavigation />);

    const homeLink = await screen.findByRole("link", { name: /널스탁/i });
    const logoMark = screen.getByTestId("nullstock-logo-mark");
    const sourceImage = logoMark.querySelector("image");

    expect(homeLink).toContainElement(logoMark);
    expect(homeLink).toHaveTextContent("OPEN BETA");
    expect(sourceImage).toHaveAttribute("href", "/nullStock.png");
    expect(sourceImage).toHaveAttribute(
      "filter",
      "url(#nullstock-transparent-background)"
    );
    expect(screen.queryByAltText("NullStock Logo")).not.toBeInTheDocument();
  });

  it("데스크톱에서 탑메뉴 묶음을 화면 가운데에 배치한다", async () => {
    renderWithQueryClient(<TopNavigation />);

    const menu = await screen.findByTestId("top-navigation-menu");

    expect(menu).toHaveClass(
      "xl:absolute",
      "xl:left-1/2",
      "xl:-translate-x-1/2"
    );
  });

  it("비로그인 상태에서는 프로필 버튼 대신 Google 로그인 버튼을 보여준다", async () => {
    renderWithQueryClient(<TopNavigation />);

    const loginButton = await screen.findByRole("button", {
      name: "Google 로그인",
    });

    expect(loginButton).toBeInTheDocument();
    expect(screen.queryByLabelText(/사용자 메뉴/)).not.toBeInTheDocument();

    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(signInWithOAuthMock).toHaveBeenCalledWith({
        provider: "google",
        options: {
          redirectTo: window.location.origin,
          queryParams: {
            access_type: "offline",
            prompt: "select_account",
          },
        },
      });
    });
  });

  it("비로그인 상태에서 모의투자, 전략모음, 대시보드 메뉴를 누르면 로그인 모달을 보여준다", async () => {
    renderWithQueryClient(<TopNavigation />);

    await screen.findByRole("button", {
      name: "Google 로그인",
    });

    fireEvent.click(screen.getByRole("link", { name: /모의투자/i }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("로그인 후 이용할 수 있습니다")).toBeInTheDocument();
    expect(screen.getByText("Google로 3초만에 시작하세요")).toBeInTheDocument();
    expect(screen.getByText("카드 등록 불필요")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("link", { name: /전략모음/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "취소" }));

    fireEvent.click(screen.getByRole("link", { name: /대시보드/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Google로 시작하기" }));
    await waitFor(() => {
      expect(signInWithOAuthMock).toHaveBeenCalledWith({
        provider: "google",
        options: {
          redirectTo: window.location.origin,
          queryParams: {
            access_type: "offline",
            prompt: "select_account",
          },
        },
      });
    });
  });

  it("가상계좌 query가 남아 있어도 전략연구소의 정식 경로로 이동한다", async () => {
    pathnameMock.current = "/analytics/chat";
    searchParamsMock.current = "virtualAccount=open";

    renderWithQueryClient(<TopNavigation />);

    fireEvent.click(await screen.findByRole("link", { name: /전략연구소/i }));

    expect(pushMock).toHaveBeenCalledWith("/analytics");
    expect(pushMock).not.toHaveBeenCalledWith("/analytics?virtualAccount=open");
  });

  it("백테스트 결과 화면에서 전략연구소 메뉴를 눌러도 이전 채팅 스냅샷을 유지한 채 이동한다", async () => {
    pathnameMock.current = "/analytics/new";
    const snapshot = JSON.stringify({
      messages: [{ role: "user", content: "PBR 1 이하" }],
      stage: "done",
    });
    sessionStorage.setItem("simons.strategyChatState", snapshot);

    renderWithQueryClient(<TopNavigation />);

    fireEvent.click(await screen.findByRole("link", { name: /전략연구소/i }));

    expect(sessionStorage.getItem("simons.strategyChatState")).toBe(snapshot);
    expect(pushMock).toHaveBeenCalledWith("/analytics");
  });

  it("로그인된 상태에서는 사용자 프로필 버튼과 드롭다운 메뉴를 보여준다", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/user") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            user: {
              name: "홍길동",
              email: "hong@example.com",
              avatarUrl: null,
            },
          }),
        });
      }

      if (url === "/api/stock/popular") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            stocks: [],
            updatedAt: "09:00:00",
          }),
        });
      }

      if (url === "/api/user/plan") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            plan: { planId: "FREE", name: "Free", initialInvestmentAmount: 10_000_000 },
            accounts: { used: 0, limit: 1 },
            strategies: { used: 0, limit: 3, unlimited: false },
            backtests: { used: 0, limit: 30 },
          }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: async () => ({
          stocks: [],
          strategies: [],
          virtualAccounts: [],
        }),
      });
    });

    renderWithQueryClient(<TopNavigation />);

    const profileButton = await screen.findByRole("button", {
      name: "홍길동 사용자 메뉴",
    });

    expect(profileButton).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Google 로그인" })).not.toBeInTheDocument();

    fireEvent.click(profileButton);

    expect(await screen.findByText("hong@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내 플랜" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "내 플랜" }));
    expect(await screen.findByRole("dialog", { name: "내 플랜" })).toBeInTheDocument();
    expect(screen.getByText("현재 플랜")).toBeInTheDocument();
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.getByText("계좌당 초기 모의 투자금")).toBeInTheDocument();
    expect(screen.getByText("10,000,000원")).toBeInTheDocument();
    expect(screen.getByText("사용 중인 계좌")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "내 플랜 모달 닫기" }));
    fireEvent.click(profileButton);
    fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    expect(
      await screen.findByRole("button", { name: "Google 로그인" })
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/사용자 메뉴/)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/logout", {
      method: "POST",
      credentials: "same-origin",
    });
    expect(signOutMock).toHaveBeenCalledOnce();
    expect(replaceMock).toHaveBeenCalledWith("/");
  });

  it("전략연구소 채팅 중 로그아웃하면 채팅 스냅샷을 지우고 랜딩으로 이동한다", async () => {
    pathnameMock.current = "/analytics/chat";
    sessionStorage.setItem(
      "simons.strategyChatState",
      JSON.stringify({ messages: [{ role: "user", content: "PBR 1 이하" }], stage: "done" })
    );
    sessionStorage.setItem("simons.pendingStrategyPrompt", "PBR 1 이하");

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/user") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            user: { name: "홍길동", email: "hong@example.com", avatarUrl: null },
          }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: async () => ({ stocks: [], strategies: [], virtualAccounts: [] }),
      });
    });

    renderWithQueryClient(<TopNavigation />);

    const profileButton = await screen.findByRole("button", {
      name: "홍길동 사용자 메뉴",
    });
    fireEvent.click(profileButton);
    fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    await screen.findByRole("button", { name: "Google 로그인" });

    expect(sessionStorage.getItem("simons.strategyChatState")).toBeNull();
    expect(sessionStorage.getItem("simons.pendingStrategyPrompt")).toBeNull();
    expect(replaceMock).toHaveBeenCalledWith("/");
  });

  it("몇 글자만 입력해도 바로 추천 결과를 보여준다", async () => {
    renderWithQueryClient(<TopNavigation />);

    fireEvent.keyDown(window, { key: "/" });

    const input = await screen.findByPlaceholderText(
      "종목, 전략, 계좌, 백테스트를 검색하세요"
    );
    fireEvent.change(input, { target: { value: "삼" } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/quick-search?q=%EC%82%BC");
    });

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("삼성 모멘텀 전략")).toBeInTheDocument();
    expect(screen.getByText("삼성 테스트 계좌")).toBeInTheDocument();
  });

  it("실시간 시세가 비어도 마지막 정상 등락률을 유지한다", () => {
    const current = [
      { rank: 1, symbol: "005930", name: "삼성전자", changePercent: -1.9 },
      { rank: 2, symbol: "000660", name: "SK하이닉스", changePercent: -1.83 },
      { rank: 3, symbol: "373220", name: "LG에너지솔루션", changePercent: null },
      { rank: 4, symbol: "005380", name: "현대차", changePercent: null },
      { rank: 5, symbol: "068270", name: "셀트리온", changePercent: null },
    ];

    const merged = mergePopularStocks(current, {
      "005930": { price: 0, changePercent: 0, volume: 0 },
      "000660": { price: 0, changePercent: 0, volume: 0 },
    });

    expect(merged[0]?.changePercent).toBe(-1.9);
    expect(merged[1]?.changePercent).toBe(-1.83);
    expect(merged[2]?.changePercent).toBeNull();
  });

  it("인기 검색은 SSE 이벤트를 받으면 즉시 등락률을 갱신한다", async () => {
    renderWithQueryClient(<TopNavigation />);

    fireEvent.keyDown(window, { key: "/" });

    await screen.findByText("인기 검색");
    expect(fetchMock).toHaveBeenCalledWith("/api/stock/popular");
    expect(await screen.findByText("+0.12%")).toBeInTheDocument();

    expect(MockEventSource.instances[0]?.url).toBe("/api/stock/popular-stream");

    await act(async () => {
      MockEventSource.instances[0]?.emitMessage({
        "005930": { close: 61000, change_rate: 1.23, prev_close: 60260, open: 60500 },
        "000660": { close: 210000, change_rate: -1.83, prev_close: 213910, open: 211500 },
      });
    });

    expect(await screen.findByText("+1.23%")).toBeInTheDocument();
    expect(await screen.findByText("1.83%")).toBeInTheDocument();
  });

  it("localStorage에 {title, href} 객체 형식의 레거시 최근 검색이 있어도 안전하게 렌더된다", async () => {
    window.localStorage.setItem(
      "quick-search:recent",
      JSON.stringify([
        { title: "삼성전자", href: "/stock-order?symbol=005930" },
        { title: "SK하이닉스", href: "/stock-order?symbol=000660" },
        "현대차",
      ])
    );

    renderWithQueryClient(<TopNavigation />);

    fireEvent.keyDown(window, { key: "/" });

    expect(await screen.findByText("최근 검색")).toBeInTheDocument();
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("SK하이닉스")).toBeInTheDocument();
    expect(screen.getByText("현대차")).toBeInTheDocument();

    const stored = window.localStorage.getItem("quick-search:recent");
    expect(stored).toBe(JSON.stringify(["삼성전자", "SK하이닉스", "현대차"]));

    window.localStorage.removeItem("quick-search:recent");
  });
});
