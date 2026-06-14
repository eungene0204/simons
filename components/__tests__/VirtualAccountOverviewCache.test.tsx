import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";
import {
  clearVirtualAccountOverviewCache,
  setCachedVirtualAccounts,
} from "@/components/virtual-account/virtualAccountOverviewCache";
import type { VirtualAccount } from "@/types/portfolio";

vi.mock("@/components/strategy/StrategyWaveBackground", () => ({
  StrategyWaveBackground: () => <div data-testid="strategy-wave-background" />,
}));

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

afterEach(() => {
  clearVirtualAccountOverviewCache();
  vi.unstubAllGlobals();
});

describe("VirtualAccountOverview cache", () => {
  it("renders cached accounts immediately while refreshing in the background", () => {
    setCachedVirtualAccounts([cachedAccount]);
    const fetchMock = vi.fn(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetchMock);

    render(<VirtualAccountOverview />);

    expect(screen.queryByText("계좌를 불러오는 중입니다.")).not.toBeInTheDocument();
    expect(screen.getByText("캐시 계좌")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/virtual-account");
  });
});
