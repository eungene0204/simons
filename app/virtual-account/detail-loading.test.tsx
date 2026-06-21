import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VirtualAccountDetailPage from "@/app/virtual-account/[id]/page";

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
  getAccount: vi.fn(() => new Promise(() => undefined)),
  getTransactionsByAccount: vi.fn().mockResolvedValue([]),
  refreshAccountValue: vi.fn(),
  updateAccountStrategy: vi.fn(),
  updateTradingMode: vi.fn(),
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
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
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
});
