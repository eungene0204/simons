import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VirtualAccountList from "./VirtualAccountList";
import type { VirtualAccountListData } from "@/app/api/dashboard/virtual-account-list/route";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

function makeAccount(
  overrides: Partial<VirtualAccountListData["accounts"][number]> = {}
): VirtualAccountListData["accounts"][number] {
  return {
    id: "account-1",
    name: "계좌 A",
    status: "ACTIVE",
    strategyName: "골드 크로스",
    initialAmount: 10_000_000,
    totalValue: 11_000_000,
    profit: 1_000_000,
    returnPct: 10,
    createdAt: "2026-06-15T00:00:00.000Z",
    closedAt: null,
    ...overrides,
  };
}

function makeData(accounts: VirtualAccountListData["accounts"]): VirtualAccountListData {
  return { accounts };
}

describe("VirtualAccountList", () => {
  beforeEach(() => {
    pushMock.mockReset();
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("navigates to the account detail page when a row is clicked", () => {
    render(<VirtualAccountList initialData={makeData([makeAccount()])} />);

    fireEvent.click(screen.getByRole("button", { name: /계좌 A/i }));

    expect(pushMock).toHaveBeenCalledWith("/virtual-account/account-1");
  });

  it("opens the full account list from the header action", () => {
    render(<VirtualAccountList initialData={makeData([makeAccount()])} />);

    fireEvent.click(screen.getByRole("button", { name: "전체 보기" }));

    expect(pushMock).toHaveBeenCalledWith("/virtual-account");
  });

  it("shows a 운용중 badge for active accounts and 삭제됨 for closed accounts", () => {
    render(
      <VirtualAccountList
        initialData={makeData([
          makeAccount({ id: "active-1", name: "활성 계좌", status: "ACTIVE" }),
          makeAccount({ id: "closed-1", name: "삭제 계좌", status: "CLOSED" }),
        ])}
      />
    );

    expect(screen.getByText("운용중")).toBeInTheDocument();
    expect(screen.getByText("삭제됨")).toBeInTheDocument();
  });

  it("renders an empty state when there are no accounts", () => {
    render(<VirtualAccountList initialData={makeData([])} />);

    expect(screen.getByText("등록된 가상계좌가 없습니다")).toBeInTheDocument();
  });

  it("refreshes empty initial data and renders newly created accounts", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => makeData([makeAccount({ name: "신규 계좌" })]),
    } as Response);

    render(<VirtualAccountList initialData={makeData([])} />);

    expect(await screen.findByText("신규 계좌")).toBeInTheDocument();
    expect(screen.queryByText("등록된 가상계좌가 없습니다")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/dashboard/virtual-account-list", {
      cache: "no-store",
    });
  });

  it("renders positive values in red and negative values in blue", () => {
    render(
      <VirtualAccountList
        initialData={makeData([
          makeAccount({ id: "positive", name: "양수 계좌", returnPct: 1.5, profit: 12000 }),
          makeAccount({ id: "negative", name: "음수 계좌", returnPct: -1.5, profit: -12000 }),
        ])}
      />
    );

    expect(screen.getByText("+1.5%")).toHaveClass("text-[var(--main-red)]");
    expect(screen.getByText("+1만원")).toHaveClass("text-[var(--main-red)]");
    expect(screen.getByText("-1.5%")).toHaveClass("text-[var(--main-blue)]");
    expect(screen.getByText("-1만원")).toHaveClass("text-[var(--main-blue)]");
  });
});
