import { render, screen, within } from "@testing-library/react";
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

const autoAccount: VirtualAccount = {
  ...cachedAccount,
  id: "auto-account",
  name: "자동 계좌",
  tradingMode: "auto",
};

beforeEach(() => {
  clearVirtualAccountOverviewCache();
});

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

  it("shows a load error instead of the empty account state when the account request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
      })
    );

    render(<VirtualAccountOverview />);

    expect(await screen.findByText("가상계좌를 불러오지 못했습니다")).toBeInTheDocument();
    expect(screen.queryByText("가상계좌를 만들고")).not.toBeInTheDocument();
  });

  it("keeps the initial amount box size while positioning the trading mode badge above it", () => {
    setCachedVirtualAccounts([autoAccount]);
    const fetchMock = vi.fn(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetchMock);

    render(<VirtualAccountOverview />);

    const initialAmountLabel = screen.getByText("초기 투자금");
    const initialAmountCard = initialAmountLabel.parentElement;
    expect(initialAmountCard).not.toBeNull();
    expect(initialAmountCard).toHaveClass("relative", "rounded-md", "p-3");

    const badge = within(initialAmountCard as HTMLDivElement).getByText("자동");
    expect(badge).toHaveClass("absolute", "-top-8");
    expect(badge.compareDocumentPosition(initialAmountLabel)).toBeTruthy();
    expect(badge.compareDocumentPosition(initialAmountLabel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders an account delete button in the account card header with a red hover state", () => {
    setCachedVirtualAccounts([autoAccount]);
    const fetchMock = vi.fn(() => new Promise<Response>(() => undefined));
    vi.stubGlobal("fetch", fetchMock);

    render(<VirtualAccountOverview />);

    const deleteButton = screen.getByRole("button", { name: "자동 계좌 계좌 삭제" });
    expect(deleteButton).toHaveClass(
      "bg-white/[0.06]",
      "text-gray-500",
      "hover:bg-[var(--main-red)]/15",
      "hover:text-[var(--main-red)]"
    );
  });
});
