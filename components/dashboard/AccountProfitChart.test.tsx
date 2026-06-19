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
});
