import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccountProfitChart from "./AccountProfitChart";
import type { AccountMonthlyData } from "@/app/api/dashboard/account-monthly/route";

describe("AccountProfitChart", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      }
    );
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows an empty-state message instead of an empty chart when no accounts exist", () => {
    const initialData: AccountMonthlyData = {
      months: [],
      accounts: [],
    };

    render(<AccountProfitChart initialData={initialData} />);

    expect(screen.getByText("계좌별 수익률")).toBeInTheDocument();
    expect(screen.getByText("개설된 계좌가 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("계좌를 개설하면 여기서 수익률을 확인할 수 있습니다")).toBeInTheDocument();
    expect(screen.getByTestId("account-profit-empty-state").className).not.toContain("border");
    expect(screen.getByTestId("account-profit-card")).toHaveClass(
      "p-3",
      "sm:p-4",
      "lg:p-5"
    );
  });

  it("refreshes empty initial data and renders newly created accounts", async () => {
    const refreshedData: AccountMonthlyData = {
      months: ["2026/07"],
      accounts: [
        {
          id: "account-1",
          name: "신규 계좌",
          initialCash: 10_000_000,
          createdAt: "2026-07-01T00:00:00.000Z",
          monthlyProfitPct: [0],
        },
      ],
    };
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => refreshedData,
    } as Response);

    render(<AccountProfitChart initialData={{ months: [], accounts: [] }} />);

    expect(await screen.findByText("신규 계좌")).toBeInTheDocument();
    expect(screen.queryByText("개설된 계좌가 없습니다.")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/dashboard/account-monthly", {
      cache: "no-store",
    });
  });

  it("renders visible zero-return bars even before chart width is measured", async () => {
    const initialData: AccountMonthlyData = {
      months: ["2026/07"],
      accounts: [
        {
          id: "account-1",
          name: "첫전략",
          initialCash: 10_000_000,
          createdAt: "2026-07-10T00:00:00.000Z",
          monthlyProfitPct: [0],
        },
        {
          id: "account-2",
          name: "내계좌",
          initialCash: 10_000_000,
          createdAt: "2026-07-11T00:00:00.000Z",
          monthlyProfitPct: [0],
        },
      ],
    };

    render(<AccountProfitChart initialData={initialData} />);

    expect(screen.getByText("7월")).toBeInTheDocument();
    const bars = screen.getAllByTestId("account-profit-bar");
    expect(bars).toHaveLength(2);
    for (const bar of bars) {
      expect(bar).toHaveStyle({ height: "10px" });
    }
  });

  it("shows invested-weighted portfolio return instead of a plain sum of percentages", async () => {
    // A: 1천만 원 +20%, B: 9천만 원 0% → 단순합 +20%, 투자금 가중 +2%
    const initialData: AccountMonthlyData = {
      months: ["2026/07"],
      accounts: [
        { id: "account-1", name: "계좌A", initialCash: 10_000_000, createdAt: "2026-01-01T00:00:00.000Z", monthlyProfitPct: [20] },
        { id: "account-2", name: "계좌B", initialCash: 90_000_000, createdAt: "2026-01-01T00:00:00.000Z", monthlyProfitPct: [0] },
      ],
    };

    render(<AccountProfitChart initialData={initialData} />);

    expect(screen.getAllByText("+2.0%").length).toBeGreaterThan(0);
    expect(screen.queryByText("+20.0%")).not.toBeInTheDocument();
    expect(screen.getByText(/투자금 가중/)).toBeInTheDocument();
  });

  it("renders loss accounts with a striped bar and a legend hint", async () => {
    const initialData: AccountMonthlyData = {
      months: ["2026/07"],
      accounts: [
        { id: "account-1", name: "이익계좌", initialCash: 10_000_000, createdAt: "2026-01-01T00:00:00.000Z", monthlyProfitPct: [5] },
        { id: "account-2", name: "손실계좌", initialCash: 10_000_000, createdAt: "2026-01-01T00:00:00.000Z", monthlyProfitPct: [-5] },
      ],
    };

    render(<AccountProfitChart initialData={initialData} />);

    const bars = screen.getAllByTestId("account-profit-bar");
    expect(bars).toHaveLength(2);
    const negativeBars = bars.filter((bar) => bar.dataset.negative === "true");
    expect(negativeBars).toHaveLength(1);
    expect(negativeBars[0].style.background).toContain("repeating-linear-gradient");
    expect(screen.getByText("빗금 = 손실")).toBeInTheDocument();
  });

  it("keeps months visible but hides account bars before account creation month", () => {
    const initialData: AccountMonthlyData = {
      months: ["2026/02", "2026/03", "2026/04", "2026/05", "2026/06", "2026/07"],
      accounts: [
        {
          id: "account-1",
          name: "첫전략",
          initialCash: 10_000_000,
          createdAt: "2026-06-10T00:00:00.000Z",
          monthlyProfitPct: [0, 0, 0, 0, 0, 0],
        },
        {
          id: "account-2",
          name: "내계좌",
          initialCash: 10_000_000,
          createdAt: "2026-07-11T00:00:00.000Z",
          monthlyProfitPct: [0, 0, 0, 0, 0, 0],
        },
      ],
    };

    render(<AccountProfitChart initialData={initialData} />);

    // 6월: account-1만, 7월: 둘 다 → 총 3개
    expect(screen.getAllByTestId("account-profit-bar")).toHaveLength(3);
    for (const month of ["2월", "3월", "4월", "5월", "6월", "7월"]) {
      expect(screen.getByText(month)).toBeInTheDocument();
    }
  });

  it("renders bars from server-provided data immediately without waiting for any client fetch", () => {
    // 회귀: 개설 월을 얻으려고 /virtual-account-list 응답을 기다리는 동안 막대가 전부 비어 있었다.
    // fetch는 beforeEach에서 영원히 pending → 서버 데이터만으로 첫 렌더에 막대가 있어야 한다.
    const initialData: AccountMonthlyData = {
      months: ["2026/06", "2026/07"],
      accounts: [
        { id: "account-1", name: "계좌A", initialCash: 10_000_000, createdAt: "2026-01-01T00:00:00.000Z", monthlyProfitPct: [1, 2] },
      ],
    };

    render(<AccountProfitChart initialData={initialData} />);

    expect(screen.getAllByTestId("account-profit-bar")).toHaveLength(2);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).not.toHaveBeenCalledWith("/api/dashboard/virtual-account-list", expect.anything());
  });
});
