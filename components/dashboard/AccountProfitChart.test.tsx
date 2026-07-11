import { render, screen, waitFor } from "@testing-library/react";
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
  });

  it("refreshes empty initial data and renders newly created accounts", async () => {
    const refreshedData: AccountMonthlyData = {
      months: ["2026/07"],
      accounts: [
        {
          id: "account-1",
          name: "신규 계좌",
          initialCash: 10_000_000,
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
          monthlyProfitPct: [0],
        },
        {
          id: "account-2",
          name: "내계좌",
          initialCash: 10_000_000,
          monthlyProfitPct: [0],
        },
      ],
    };
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => initialData,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          accounts: [
            { id: "account-1", createdAt: "2026-07-10T00:00:00.000Z" },
            { id: "account-2", createdAt: "2026-07-11T00:00:00.000Z" },
          ],
        }),
      } as Response);

    render(<AccountProfitChart initialData={initialData} />);

    expect(screen.getByText("7월")).toBeInTheDocument();
    const bars = await screen.findAllByTestId("account-profit-bar");
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
        { id: "account-1", name: "계좌A", initialCash: 10_000_000, monthlyProfitPct: [20] },
        { id: "account-2", name: "계좌B", initialCash: 90_000_000, monthlyProfitPct: [0] },
      ],
    };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => initialData } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          accounts: [
            { id: "account-1", createdAt: "2026-01-01T00:00:00.000Z" },
            { id: "account-2", createdAt: "2026-01-01T00:00:00.000Z" },
          ],
        }),
      } as Response);

    render(<AccountProfitChart initialData={initialData} />);

    await waitFor(() => {
      expect(screen.getAllByText("+2.0%").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("+20.0%")).not.toBeInTheDocument();
    expect(screen.getByText(/투자금 가중/)).toBeInTheDocument();
  });

  it("renders loss accounts with a striped bar and a legend hint", async () => {
    const initialData: AccountMonthlyData = {
      months: ["2026/07"],
      accounts: [
        { id: "account-1", name: "이익계좌", initialCash: 10_000_000, monthlyProfitPct: [5] },
        { id: "account-2", name: "손실계좌", initialCash: 10_000_000, monthlyProfitPct: [-5] },
      ],
    };
    vi.mocked(fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => initialData } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          accounts: [
            { id: "account-1", createdAt: "2026-01-01T00:00:00.000Z" },
            { id: "account-2", createdAt: "2026-01-01T00:00:00.000Z" },
          ],
        }),
      } as Response);

    render(<AccountProfitChart initialData={initialData} />);

    const bars = await screen.findAllByTestId("account-profit-bar");
    expect(bars).toHaveLength(2);
    const negativeBars = bars.filter((bar) => bar.dataset.negative === "true");
    expect(negativeBars).toHaveLength(1);
    expect(negativeBars[0].style.background).toContain("repeating-linear-gradient");
    expect(screen.getByText("빗금 = 손실")).toBeInTheDocument();
  });

  it("keeps months visible but hides account bars before account creation month", async () => {
    const initialData: AccountMonthlyData = {
      months: ["2026/02", "2026/03", "2026/04", "2026/05", "2026/06", "2026/07"],
      accounts: [
        {
          id: "account-1",
          name: "첫전략",
          initialCash: 10_000_000,
          monthlyProfitPct: [0, 0, 0, 0, 0, 0],
        },
        {
          id: "account-2",
          name: "내계좌",
          initialCash: 10_000_000,
          monthlyProfitPct: [0, 0, 0, 0, 0, 0],
        },
      ],
    };
    let resolveAccountList!: (response: Response) => void;
    const accountListPromise = new Promise<Response>((resolve) => {
      resolveAccountList = resolve;
    });
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => initialData,
      } as Response)
      .mockReturnValueOnce(accountListPromise);

    render(<AccountProfitChart initialData={initialData} />);

    expect(screen.queryAllByTestId("account-profit-bar")).toHaveLength(0);
    resolveAccountList({
      ok: true,
      json: async () => ({
        accounts: [
          { id: "account-1", createdAt: "2026-07-10T00:00:00.000Z" },
          { id: "account-2", createdAt: "2026-07-11T00:00:00.000Z" },
        ],
      }),
    } as Response);

    await waitFor(() => {
      expect(screen.getAllByTestId("account-profit-bar")).toHaveLength(2);
    });
    expect(screen.getByText("2월")).toBeInTheDocument();
    expect(screen.getByText("3월")).toBeInTheDocument();
    expect(screen.getByText("4월")).toBeInTheDocument();
    expect(screen.getByText("5월")).toBeInTheDocument();
    expect(screen.getByText("6월")).toBeInTheDocument();
    expect(screen.getByText("7월")).toBeInTheDocument();
  });
});
