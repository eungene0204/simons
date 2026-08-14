import type { AnchorHTMLAttributes } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";
import {
  clearVirtualAccountOverviewCache,
  setCachedVirtualAccounts,
} from "@/components/virtual-account/virtualAccountOverviewCache";
import { deleteAccount } from "@/lib/portfolio";
import type { VirtualAccount } from "@/types/portfolio";

const assignMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    onClick,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} onClick={onClick} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/strategy/StrategyWaveBackground", () => ({
  StrategyWaveBackground: () => <div data-testid="strategy-wave-background" />,
}));

vi.mock("@/components/ui/CreateAccountModal", () => ({
  default: () => null,
}));

vi.mock("@/lib/portfolio", async () => {
  const actual = await vi.importActual<typeof import("@/lib/portfolio")>(
    "@/lib/portfolio"
  );

  return {
    ...actual,
    createAccount: vi.fn(),
    deleteAccount: vi.fn(),
    getAccount: vi.fn(),
  };
});

const mockedDeleteAccount = vi.mocked(deleteAccount);

const cachedAccount: VirtualAccount = {
  id: "cached-account",
  name: "캐시 계좌",
  initialAmount: 10_000_000,
  currentBalance: 9_000_000,
  totalValue: 10_500_000,
  strategyName: "캐시 전략",
  tradingMode: "manual",
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

describe("VirtualAccountOverview navigation", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    window.sessionStorage.clear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...originalLocation,
        assign: assignMock,
      },
    });
  });

  afterEach(() => {
    clearVirtualAccountOverviewCache();
    assignMock.mockReset();
    mockedDeleteAccount.mockReset();
    vi.unstubAllGlobals();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("shows a centered indicator with a loading message while loading the initial account list", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));

    render(<VirtualAccountOverview />);

    const loadingIndicator = screen.getByRole("status", {
      name: "가상계좌 불러오는 중",
    });
    expect(loadingIndicator).toHaveClass(
      "min-h-[calc(100vh-var(--top-menu-bar-height,76px))]",
      "items-center",
      "justify-center"
    );
    expect(screen.getByText("불러오는 중...")).toBeInTheDocument();
    expect(screen.queryByTestId("virtual-account-overview-root")).not.toBeInTheDocument();
    expect(screen.queryByTestId("virtual-account-simulation-notice")).not.toBeInTheDocument();
  });

  it("fills the available page height when there are no virtual accounts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      })
    );

    render(<VirtualAccountOverview />);

    const emptyBackground = await screen.findByTestId("virtual-account-empty-background");
    const root = screen.getByTestId("virtual-account-overview-root");

    expect(screen.getByTestId("virtual-account-empty-state")).toHaveClass("flex-1");
    expect(screen.getByTestId("virtual-account-overview-content")).toHaveClass(
      "flex",
      "flex-1",
      "flex-col"
    );
    expect(emptyBackground.parentElement).toBe(root);
    expect(root.className).not.toContain("px-");
    expect(root.className).not.toContain("pb-");
    expect(screen.getByTestId("virtual-account-simulation-notice")).toHaveClass(
      "relative",
      "z-10",
      "mt-auto"
    );
  });

  it("renders the add account prompt as two fixed text lines", async () => {
    setCachedVirtualAccounts([cachedAccount]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [cachedAccount],
      })
    );

    render(<VirtualAccountOverview />);

    const firstLine = await screen.findByText("전략과 가상계좌를 연결해");
    const secondLine = screen.getByText("실시간 시장 데이터로 전략을 시뮬레이션해 보세요");

    expect(firstLine).toHaveClass("block", "whitespace-nowrap");
    expect(secondLine).toHaveClass("block", "whitespace-nowrap");
    expect(firstLine.parentElement).toBe(secondLine.parentElement);
  });

  it("renders auto accounts with the strategy simulation badge", async () => {
    const autoAccount = { ...cachedAccount, tradingMode: "auto" as const };
    setCachedVirtualAccounts([autoAccount]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [autoAccount],
      })
    );

    render(<VirtualAccountOverview />);

    const badge = await screen.findByText("전략 시뮬레이션 중");
    expect(badge).toHaveClass(
      "border-amber-400/25",
      "bg-[#1a1208]/90",
      "text-amber-300",
      "text-[11px]"
    );
    expect(screen.queryByText("자동")).not.toBeInTheDocument();
  });

  it("does not render the strategy simulation badge for manual accounts", async () => {
    setCachedVirtualAccounts([cachedAccount]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [cachedAccount],
      })
    );

    render(<VirtualAccountOverview />);

    expect(await screen.findByText("캐시 계좌")).toBeInTheDocument();
    expect(screen.queryByText("전략 시뮬레이션 중")).not.toBeInTheDocument();
  });

  it("navigates to the account detail page when the selected account link is clicked", async () => {
    setCachedVirtualAccounts([cachedAccount]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [cachedAccount],
      })
    );

    render(<VirtualAccountOverview />);

    fireEvent.click(await screen.findByRole("link", { name: "캐시 계좌 상세 보기" }));

    expect(assignMock).toHaveBeenCalledWith("/virtual-account/cached-account");
    expect(
      JSON.parse(
        window.sessionStorage.getItem("virtual-account-detail:cached-account") || "{}"
      )
    ).toMatchObject({
      account: cachedAccount,
      holdings: [],
      transactions: [],
      trackedSymbols: [],
    });

    expect(
      screen.getByText(
        "가상계좌의 자산과 거래 내역은 시뮬레이션 결과입니다. 실제 주문은 발생하지 않으며, 전략 검증 목적으로 제공됩니다."
      )
    ).toBeInTheDocument();
    expect(screen.getByTestId("virtual-account-overview-root")).toHaveClass("flex", "flex-col");
    expect(screen.getByTestId("virtual-account-simulation-notice")).toHaveClass("mt-auto");
  });

  it("navigates when clicking the account card body", async () => {
    setCachedVirtualAccounts([cachedAccount]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [cachedAccount],
      })
    );

    render(<VirtualAccountOverview />);

    fireEvent.click(screen.getByTestId("virtual-account-card-cached-account"));

    expect(assignMock).toHaveBeenCalledWith("/virtual-account/cached-account");
    expect(
      JSON.parse(
        window.sessionStorage.getItem("virtual-account-detail:cached-account") || "{}"
      )
    ).toMatchObject({
      account: cachedAccount,
      holdings: [],
      transactions: [],
      trackedSymbols: [],
    });
  });

  it("opens a liquidation warning modal from the x button and deletes after confirmation", async () => {
    setCachedVirtualAccounts([cachedAccount]);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [cachedAccount],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });
    vi.stubGlobal("fetch", fetchMock);
    mockedDeleteAccount.mockResolvedValue(undefined);

    render(<VirtualAccountOverview />);

    fireEvent.click(screen.getByRole("button", { name: "캐시 계좌 계좌 해지" }));

    expect(await screen.findByRole("dialog", { name: "계좌 해지" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "계좌 해지" })).toBeInTheDocument();
    expect(
      screen.getByText(/남은 현금과 보유 종목은 다른 계좌로 이전되지 않습니다/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/회원님 자산으로 반환됩니다/)).not.toBeInTheDocument();
    expect(screen.queryByText(/사용자 자산으로 반환/)).not.toBeInTheDocument();
    expect(assignMock).not.toHaveBeenCalled();

    const confirmDeleteButton = screen.getByRole("button", { name: "계좌 해지" });
    expect(confirmDeleteButton).toHaveClass("border", "border-white/[0.08]", "text-[var(--main-red)]");
    expect(confirmDeleteButton.className).not.toContain("bg-black");

    fireEvent.click(confirmDeleteButton);

    await waitFor(() => {
      expect(mockedDeleteAccount).toHaveBeenCalledWith("cached-account");
      expect(screen.queryByText("캐시 계좌")).not.toBeInTheDocument();
    });
    expect(assignMock).not.toHaveBeenCalled();
  });
});
