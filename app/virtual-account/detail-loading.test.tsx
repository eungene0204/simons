import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VirtualAccountDetailPage from "@/app/virtual-account/[id]/page";

const { fetchMock, getAccountMock } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  getAccountMock: vi.fn(),
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
  updateTradingMode: vi.fn(),
}));

vi.mock("@/components/stock/StockSearchModal", () => ({
  default: ({
    isOpen,
    onClose,
    onSelect,
  }: {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (symbols: { symbol: string; name: string }[]) => void;
  }) =>
    isOpen ? (
      <button
        type="button"
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

  it("adds selected stocks to the tracked symbol list without duplicates", async () => {
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
        trackedSymbols: [{ symbol: "000660", name: "SK하이닉스" }],
      })
    );
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/stocks/names") {
        return Promise.resolve({
          ok: true,
          json: async () => ({}),
        } as Response);
      }

      if (
        String(input) === "/api/virtual-market/account-123" &&
        init?.method === "POST"
      ) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ symbols: ["000660", "005930"] }),
        } as Response);
      }

      return new Promise<Response>(() => undefined);
    });

    render(<VirtualAccountDetailPage />);

    expect(
      await screen.findByText("전략 조건을 만족하면 자동으로 거래가 실행됩니다.")
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
    expect(screen.queryByRole("button", { name: "자동매매" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "삭제" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "계좌닫기" })).toBeInTheDocument();
    expect(screen.getByText(/해지 2026\.\s?06\.\s?20\.?/)).toBeInTheDocument();
  });
});
