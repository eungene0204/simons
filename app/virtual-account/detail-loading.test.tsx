import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VirtualAccountDetailPage from "@/app/virtual-account/[id]/page";

const {
  fetchMock,
  getAccountMock,
  refreshOverviewCacheMock,
  updateTradingModeMock,
} = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  getAccountMock: vi.fn(),
  refreshOverviewCacheMock: vi.fn(),
  updateTradingModeMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "account-123" }),
  useRouter: () => ({
    prefetch: vi.fn(),
    push: vi.fn(),
  }),
}));

vi.mock("@/components/layout/DashboardLayout", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/portfolio", () => ({
  deleteAccount: vi.fn(),
  executeTrade: vi.fn(),
  getAccount: getAccountMock,
  getTransactionsByAccount: vi.fn().mockResolvedValue([]),
  refreshAccountValue: vi.fn(),
  updateAccountStrategy: vi.fn(),
  updateTradingMode: updateTradingModeMock,
}));

vi.mock("@/components/virtual-account/virtualAccountOverviewCache", () => ({
  refreshVirtualAccountOverviewCache: refreshOverviewCacheMock,
}));

vi.mock("@/components/stock/StockSearchModal", () => ({
  default: ({
    isOpen,
    onClose,
    onSelect,
    universeId,
  }: {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (symbols: { symbol: string; name: string }[]) => void;
    universeId?: string | null;
  }) =>
    isOpen ? (
      <button
        type="button"
        data-universe-id={universeId ?? "all"}
        onClick={() => {
          onSelect([
            { symbol: "000660", name: "SK하이닉스" },
            { symbol: "005930", name: "삼성전자" },
          ]);
          onClose();
        }}
      >
        테스트 종목 선택
      </button>
    ) : null,
}));

vi.mock("@/lib/virtual-market", () => ({
  getMarketLogs: vi.fn(() => new Promise(() => undefined)),
}));

vi.mock("@/lib/hooks/useStockPrices", () => ({
  useStockPrices: () => ({ data: undefined }),
}));

vi.mock("@/lib/hooks/useDelistingStatus", async () => {
  const actual = await vi.importActual<typeof import("@/lib/hooks/useDelistingStatus")>(
    "@/lib/hooks/useDelistingStatus"
  );

  return {
    ...actual,
    useDelistingStatus: () => ({
      delisted: new Set(),
      warning: new Set(),
      tradingSuspended: new Set(),
      delistingScheduled: new Set(),
      delistingReview: new Set(),
      details: {},
      names: {},
    }),
  };
});

describe("VirtualAccountDetailPage loading", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    getAccountMock.mockReset();
    getAccountMock.mockImplementation(() => new Promise(() => undefined));
    refreshOverviewCacheMock.mockReset();
    refreshOverviewCacheMock.mockResolvedValue([]);
    updateTradingModeMock.mockReset();
    fetchMock.mockReset();
    fetchMock.mockImplementation(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetchMock);
  });

  it("shows only a centered indicator while loading the account detail", () => {
    render(<VirtualAccountDetailPage />);

    const loadingIndicator = screen.getByRole("status", {
      name: "가상계좌 상세 불러오는 중",
    });
    expect(loadingIndicator).toHaveClass(
      "min-h-[calc(100vh-var(--top-menu-bar-height,76px))]",
      "items-center",
      "justify-center"
    );
    expect(screen.queryByText("계좌를 불러오는 중...")).not.toBeInTheDocument();
  });

  it("shows the 모니터링 종목 shimmer once the account is ready but tracked symbols haven't arrived yet, then swaps to real content", async () => {
    let resolveAccount: (value: unknown) => void = () => {};
    getAccountMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveAccount = resolve;
        })
    );

    let resolveMarketFetch: (response: Response) => void = () => {};
    const marketFetchPromise = new Promise<Response>((resolve) => {
      resolveMarketFetch = resolve;
    });

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/stocks/names") {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
      }
      if (url === "/api/virtual-market/account-123") {
        return marketFetchPromise;
      }
      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    expect(
      screen.getByRole("status", { name: "가상계좌 상세 불러오는 중" })
    ).toBeInTheDocument();

    resolveAccount({
      id: "account-123",
      name: "테스트 계좌",
      initialAmount: 10_000_000,
      currentBalance: 10_000_000,
      totalValue: 10_000_000,
      tradingMode: "manual",
      createdAt: "2026-06-01T00:00:00.000Z",
      updatedAt: "2026-06-01T00:00:00.000Z",
    });

    // 계정은 이미 렌더되지만 모니터링 종목 fetch는 아직 끝나지 않은 상태 — shimmer가 보여야 한다.
    expect(await screen.findByRole("heading", { name: "테스트 계좌" })).toBeInTheDocument();
    expect(screen.getByTestId("tracked-symbols-skeleton-scroll")).toBeInTheDocument();

    resolveMarketFetch({
      ok: true,
      json: async () => ({ symbols: ["005930"], symbolNames: { "005930": "삼성전자" } }),
    } as Response);

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.queryByTestId("tracked-symbols-skeleton-scroll")).not.toBeInTheDocument();
  });

  it("never shows the '추적 중인 종목이 없습니다' empty state from a stale empty cache when the fresh fetch has real symbols", async () => {
    // 캐시엔 종목이 없다고 저장돼 있지만(오래된 스냅샷), 실제 서버엔 종목이 있는 상황을 재현한다.
    window.sessionStorage.setItem(
      "virtual-account-detail:account-123",
      JSON.stringify({
        account: {
          id: "account-123",
          name: "테스트 계좌",
          initialAmount: 10_000_000,
          currentBalance: 10_000_000,
          totalValue: 10_000_000,
          tradingMode: "manual",
          createdAt: "2026-06-01T00:00:00.000Z",
          updatedAt: "2026-06-01T00:00:00.000Z",
        },
        holdings: [],
        transactions: [],
        trackedSymbols: [],
      })
    );

    getAccountMock.mockResolvedValue({
      id: "account-123",
      name: "테스트 계좌",
      initialAmount: 10_000_000,
      currentBalance: 10_000_000,
      totalValue: 10_000_000,
      tradingMode: "manual",
      createdAt: "2026-06-01T00:00:00.000Z",
      updatedAt: "2026-06-01T00:00:00.000Z",
    });

    let resolveMarketFetch: (response: Response) => void = () => {};
    const marketFetchPromise = new Promise<Response>((resolve) => {
      resolveMarketFetch = resolve;
    });

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/stocks/names") {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
      }
      if (url === "/api/virtual-market/account-123") {
        return marketFetchPromise;
      }
      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    expect(await screen.findByRole("heading", { name: "테스트 계좌" })).toBeInTheDocument();
    // 캐시가 비어 있어도 확정된 응답 전에는 "없습니다" 안내를 보여주지 않고 shimmer만 보여야 한다.
    expect(screen.getByTestId("tracked-symbols-skeleton-scroll")).toBeInTheDocument();
    expect(screen.queryByText("추적 중인 종목이 없습니다")).not.toBeInTheDocument();

    resolveMarketFetch({
      ok: true,
      json: async () => ({ symbols: ["005930"], symbolNames: { "005930": "삼성전자" } }),
    } as Response);

    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.queryByText("추적 중인 종목이 없습니다")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tracked-symbols-skeleton-scroll")).not.toBeInTheDocument();
  });

  it("renders the account detail from a cached overview snapshot while live data is loading", async () => {
    window.sessionStorage.setItem(
      "virtual-account-detail:account-123",
      JSON.stringify({
        account: {
          id: "account-123",
          name: "테스트 계좌",
          initialAmount: 10_000_000,
          currentBalance: 10_000_000,
          totalValue: 10_000_000,
          strategyName: "초보자 전략",
          tradingMode: "auto",
          createdAt: "2026-06-01T00:00:00.000Z",
          updatedAt: "2026-06-01T00:00:00.000Z",
        },
        holdings: [],
        transactions: [],
        trackedSymbols: [],
      })
    );

    render(<VirtualAccountDetailPage />);

    expect(await screen.findByRole("heading", { name: "테스트 계좌" })).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: "가상계좌 상세 불러오는 중" })).not.toBeInTheDocument();
    expect(screen.getByText("총 자산")).toBeInTheDocument();
  });

  it("keeps detail help tooltips inside the mobile viewport and focus-accessible", async () => {
    window.sessionStorage.setItem(
      "virtual-account-detail:account-123",
      JSON.stringify({
        account: {
          id: "account-123",
          name: "테스트 계좌",
          initialAmount: 10_000_000,
          currentBalance: 10_000_000,
          totalValue: 10_000_000,
          tradingMode: "auto",
          createdAt: "2026-06-01T00:00:00.000Z",
          updatedAt: "2026-06-01T00:00:00.000Z",
        },
        holdings: [],
        transactions: [],
        trackedSymbols: [],
      })
    );

    render(<VirtualAccountDetailPage />);

    expect(await screen.findByRole("button", { name: "시뮬레이션 토글 설명" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("button", { name: "모니터링 종목 설명" })).toHaveAttribute("tabindex", "0");

    for (const tooltip of [
      screen.getByTestId("auto-trading-help-tooltip"),
      screen.getByTestId("tracked-symbols-help-tooltip"),
    ]) {
      expect(tooltip).toHaveClass(
        "fixed",
        "inset-x-4",
        "bottom-4",
        "group-focus-within:opacity-100",
        "lg:absolute"
      );
    }
  });

  it("keeps tracked symbols inside a mobile scroll region", async () => {
    getAccountMock.mockResolvedValue({
      id: "account-123",
      name: "테스트 계좌",
      initialAmount: 10_000_000,
      currentBalance: 10_000_000,
      totalValue: 10_000_000,
      tradingMode: "manual",
      createdAt: "2026-06-01T00:00:00.000Z",
      updatedAt: "2026-06-01T00:00:00.000Z",
    });
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/stocks/names") {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
      }
      if (url === "/api/virtual-market/account-123") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ symbols: ["005930"], symbolNames: { "005930": "삼성전자" } }),
        } as Response);
      }
      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    const scrollRegion = await screen.findByTestId("tracked-symbols-table-scroll");
    expect(scrollRegion).toHaveClass("overflow-x-auto", "lg:overflow-x-visible");
    expect(scrollRegion.firstElementChild).toHaveClass(
      "min-w-[520px]",
      "lg:min-w-0"
    );
    expect(screen.getByRole("button", { name: "삼성전자 추적 제거" })).toHaveClass(
      "opacity-100",
      "lg:opacity-0",
      "lg:group-hover:opacity-100"
    );
  });

  it("renders strategy badges from history summary when saved settings lack display conditions", async () => {
    getAccountMock.mockResolvedValue({
      id: "account-123",
      name: "테스트 계좌",
      initialAmount: 10_000_000,
      currentBalance: 10_000_000,
      totalValue: 10_000_000,
      strategyId: "strategy-1",
      strategyName: "저PBR 전략",
      tradingMode: "auto",
      createdAt: "2026-06-01T00:00:00.000Z",
      updatedAt: "2026-06-01T00:00:00.000Z",
    });
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/stocks/names") {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
      }
      if (url === "/api/virtual-market/account-123") {
        return Promise.resolve({ ok: true, json: async () => ({ symbols: [] }) } as Response);
      }
      if (url === "/api/strategy/strategy-1") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            description: "KOSPI 저PBR 종목을 매매합니다.",
            settings: { description: "KOSPI 저PBR 종목을 매매합니다." },
            historySummary: {
              universeName: "KOSPI",
              entryBlocks: ["PBR <= 1"],
              exitBlocks: ["손절 -12% 하락시 매도"],
              positionText: "최대 8종목 · 126일 보유",
              riskText: "손절 12%",
            },
          }),
        } as Response);
      }
      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    expect(await screen.findByText("운용 전략")).toBeInTheDocument();
    expect(await screen.findByText("유니버스")).toBeInTheDocument();
    expect(screen.getByText("KOSPI")).toBeInTheDocument();
    expect(screen.getByText("진입신호")).toBeInTheDocument();
    expect(screen.getByText("PBR <= 1")).toBeInTheDocument();
    expect(screen.getByText("청산신호")).toBeInTheDocument();
    expect(screen.getByText("손절 -12% 하락시 매도")).toBeInTheDocument();
    expect(screen.getByText("리스트")).toBeInTheDocument();
    expect(screen.getByText("최대 8종목 · 126일 보유")).toBeInTheDocument();
    expect(screen.getByText("리스크 관리")).toBeInTheDocument();
    expect(screen.getByText("손절 12%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "종목 추가" }));
    expect(screen.getByRole("button", { name: "테스트 종목 선택" })).toHaveAttribute(
      "data-universe-id",
      "KOSPI"
    );
  });

  it("shows a shimmer skeleton for 운용 전략 while the strategy detail is loading, then swaps to the real content", async () => {
    getAccountMock.mockResolvedValue({
      id: "account-123",
      name: "테스트 계좌",
      initialAmount: 10_000_000,
      currentBalance: 10_000_000,
      totalValue: 10_000_000,
      strategyId: "strategy-1",
      strategyName: "저PBR 전략",
      tradingMode: "auto",
      createdAt: "2026-06-01T00:00:00.000Z",
      updatedAt: "2026-06-01T00:00:00.000Z",
    });

    let resolveStrategyFetch: (response: Response) => void = () => {};
    const strategyFetchPromise = new Promise<Response>((resolve) => {
      resolveStrategyFetch = resolve;
    });

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/stocks/names") {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
      }
      if (url === "/api/virtual-market/account-123") {
        return Promise.resolve({ ok: true, json: async () => ({ symbols: [] }) } as Response);
      }
      if (url === "/api/strategy/strategy-1") {
        return strategyFetchPromise;
      }
      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    expect(await screen.findByTestId("strategy-summary-skeleton")).toBeInTheDocument();
    expect(screen.queryByText("유니버스")).not.toBeInTheDocument();

    resolveStrategyFetch({
      ok: true,
      json: async () => ({
        description: "KOSPI 저PBR 종목을 매매합니다.",
        settings: { description: "KOSPI 저PBR 종목을 매매합니다." },
        historySummary: {
          universeName: "KOSPI",
          entryBlocks: ["PBR <= 1"],
        },
      }),
    } as Response);

    expect(await screen.findByText("유니버스")).toBeInTheDocument();
    expect(screen.queryByTestId("strategy-summary-skeleton")).not.toBeInTheDocument();
  });

  it("adds selected stocks to the tracked symbol list without duplicates", async () => {
    getAccountMock.mockResolvedValue({
      id: "account-123",
      name: "테스트 계좌",
      initialAmount: 10_000_000,
      currentBalance: 10_000_000,
      totalValue: 10_000_000,
      tradingMode: "manual",
      createdAt: "2026-06-01T00:00:00.000Z",
      updatedAt: "2026-06-01T00:00:00.000Z",
    });
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/stocks/names") {
        return Promise.resolve({
          ok: true,
          json: async () => ({}),
        } as Response);
      }

      if (String(input) === "/api/virtual-market/account-123") {
        if (init?.method === "POST") {
          return Promise.resolve({
            ok: true,
            json: async () => ({ symbols: ["000660", "005930"] }),
          } as Response);
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ symbols: ["000660"], symbolNames: { "000660": "SK하이닉스" } }),
        } as Response);
      }

      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    expect(
      await screen.findByText("ON이면 전략 조건을 만족할 때 가상 거래가 실행됩니다.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("연결된 전략의 백테스트에서 성과가 높았던 종목들 입니다.")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "모니터링 종목" })
    ).toBeInTheDocument();
    for (const tabName of ["보유 종목", "거래 내역", "성과 분석"]) {
      expect(screen.getByRole("button", { name: tabName })).toHaveClass("text-sm");
    }
    fireEvent.click(await screen.findByRole("button", { name: "종목 추가" }));
    fireEvent.click(screen.getByRole("button", { name: "테스트 종목 선택" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/virtual-market/account-123",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: ["000660", "005930"] }),
        }
      );
    });
    expect(await screen.findByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("2개")).toBeInTheDocument();

    const cached = JSON.parse(
      window.sessionStorage.getItem("virtual-account-detail:account-123") || "{}"
    );
    expect(cached.trackedSymbols).toEqual([
      { symbol: "000660", name: "SK하이닉스" },
      { symbol: "005930", name: "삼성전자" },
    ]);
  });

  it("turns simulation off and refreshes the overview cache", async () => {
    window.sessionStorage.setItem(
      "virtual-account-detail:account-123",
      JSON.stringify({
        account: {
          id: "account-123",
          name: "테스트 계좌",
          initialAmount: 10_000_000,
          currentBalance: 10_000_000,
          totalValue: 10_000_000,
          strategyName: "초보자 전략",
          tradingMode: "auto",
          createdAt: "2026-06-01T00:00:00.000Z",
          updatedAt: "2026-06-01T00:00:00.000Z",
        },
        holdings: [],
        transactions: [],
        trackedSymbols: [],
      })
    );
    updateTradingModeMock.mockResolvedValue({
      id: "account-123",
      name: "테스트 계좌",
      initialAmount: 10_000_000,
      currentBalance: 10_000_000,
      totalValue: 10_000_000,
      strategyName: "초보자 전략",
      tradingMode: "manual",
      createdAt: "2026-06-01T00:00:00.000Z",
      updatedAt: "2026-06-01T00:00:00.000Z",
    });
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/stocks/names") {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
      }
      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    const toggle = await screen.findByRole("button", { name: "시뮬레이션 ON" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(toggle);

    await waitFor(() => {
      expect(updateTradingModeMock).toHaveBeenCalledWith("account-123", "manual");
    });
    expect(refreshOverviewCacheMock).toHaveBeenCalledWith({ force: true });
    expect(await screen.findByRole("button", { name: "시뮬레이션 OFF" })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
    expect(
      JSON.parse(
        window.sessionStorage.getItem("virtual-account-detail:account-123") || "{}"
      ).account.tradingMode
    ).toBe("manual");
  });

  it("shows a 삭제된 계좌 badge and hides the 삭제 button for a CLOSED account", async () => {
    window.sessionStorage.setItem(
      "virtual-account-detail:account-123",
      JSON.stringify({
        account: {
          id: "account-123",
          name: "테스트 계좌",
          initialAmount: 10_000_000,
          currentBalance: 10_000_000,
          totalValue: 10_000_000,
          tradingMode: "manual",
          status: "CLOSED",
          createdAt: "2026-06-01T00:00:00.000Z",
          updatedAt: "2026-06-01T00:00:00.000Z",
          closedAt: "2026-06-20T00:00:00.000Z",
        },
        holdings: [],
        transactions: [],
        trackedSymbols: [],
      })
    );
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/stocks/names") {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
      }
      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    expect(await screen.findByText("삭제된 계좌")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /시뮬레이션/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "삭제" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "계좌닫기" })).toBeInTheDocument();
    expect(screen.getByText(/해지 2026\.\s?06\.\s?20\.?/)).toBeInTheDocument();
  });
});
