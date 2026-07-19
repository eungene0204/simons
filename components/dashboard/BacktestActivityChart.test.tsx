import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import BacktestActivityChart from "./BacktestActivityChart";

describe("BacktestActivityChart", () => {
  it("uses compact mobile spacing and restores the desktop chart layout", () => {
    render(<BacktestActivityChart initialRecords={[]} />);

    expect(screen.getByTestId("backtest-activity-card")).toHaveClass(
      "p-3",
      "sm:p-4",
      "lg:p-5"
    );
    expect(screen.getByTestId("backtest-activity-bars")).toHaveClass(
      "gap-1",
      "lg:gap-1.5"
    );
    expect(screen.getAllByTestId("backtest-activity-date")).toHaveLength(7);
    expect(screen.getAllByTestId("backtest-activity-date")[0]).toHaveClass(
      "text-[10px]",
      "lg:text-xs"
    );
  });
});
