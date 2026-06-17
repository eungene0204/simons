import type { AnchorHTMLAttributes } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";
import {
  clearVirtualAccountOverviewCache,
  setCachedVirtualAccounts,
} from "@/components/virtual-account/virtualAccountOverviewCache";
import { getAccount } from "@/lib/portfolio";
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
    getAccount: vi.fn(),
  };
});

const mockedGetAccount = vi.mocked(getAccount);

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
    vi.unstubAllGlobals();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
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
});
