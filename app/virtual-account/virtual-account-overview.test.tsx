import type { AnchorHTMLAttributes } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";
import {
  clearVirtualAccountOverviewCache,
  setCachedVirtualAccounts,
} from "@/components/virtual-account/virtualAccountOverviewCache";
import { deleteAccount, getAccount } from "@/lib/portfolio";
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

const mockedGetAccount = vi.mocked(getAccount);
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
    mockedGetAccount.mockReset();
    mockedDeleteAccount.mockReset();
    vi.unstubAllGlobals();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("shows only a centered indicator while loading the initial account list", () => {
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
    expect(screen.queryByText("계좌를 불러오는 중입니다.")).not.toBeInTheDocument();
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

  it("navigates to the account detail page after validating the selected account", async () => {
    setCachedVirtualAccounts([cachedAccount]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [cachedAccount],
      })
    );
    mockedGetAccount.mockResolvedValue(cachedAccount);

    render(<VirtualAccountOverview />);

    fireEvent.click(screen.getByRole("link", { name: /캐시 계좌/i }));

    await waitFor(() => {
      expect(mockedGetAccount).toHaveBeenCalledWith("cached-account");
      expect(assignMock).toHaveBeenCalledWith("/virtual-account/cached-account");
    });

    expect(
      screen.getByText(
        "가상계좌의 자산과 거래 내역은 시뮬레이션 결과입니다. 실제 주문은 발생하지 않으며, 전략 검증 목적으로 제공됩니다."
      )
    ).toBeInTheDocument();
    expect(screen.getByTestId("virtual-account-overview-root")).toHaveClass("flex", "flex-col");
    expect(screen.getByTestId("virtual-account-simulation-notice")).toHaveClass("mt-auto");
  });

  it("refreshes the list instead of navigating when the selected cached account no longer exists", async () => {
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
    mockedGetAccount.mockResolvedValue(null);

    render(<VirtualAccountOverview />);

    fireEvent.click(screen.getByRole("link", { name: /캐시 계좌/i }));

    await waitFor(() => {
      expect(mockedGetAccount).toHaveBeenCalledWith("cached-account");
      expect(assignMock).not.toHaveBeenCalled();
      expect(screen.queryByText("캐시 계좌")).not.toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
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

    fireEvent.click(screen.getByRole("button", { name: "캐시 계좌 계좌 삭제" }));

    expect(await screen.findByRole("dialog", { name: "계좌 삭제" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "계좌 삭제" })).toBeInTheDocument();
    expect(screen.queryByText("가상계좌를 정산하고 삭제할까요?")).not.toBeInTheDocument();
    expect(screen.getByText(/계좌의 보유 종목은 현재가 기준으로 강제 매도됩니다/)).toBeInTheDocument();
    expect(screen.getByText(/회원님 자산으로 반환됩니다/)).toBeInTheDocument();
    expect(screen.queryByText(/삭제 전에 현재가 기준/)).not.toBeInTheDocument();
    expect(screen.queryByText(/사용자 자산으로 반환/)).not.toBeInTheDocument();
    expect(screen.queryByText(/CLOSED 상태로 전환/)).not.toBeInTheDocument();
    expect(screen.queryByText(/이 작업은 일부만 진행될 수 없으며/)).not.toBeInTheDocument();
    expect(assignMock).not.toHaveBeenCalled();

    const confirmDeleteButton = screen.getByRole("button", { name: "계좌 삭제" });
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
