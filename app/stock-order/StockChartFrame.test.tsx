import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StockChartFrame from "./StockChartFrame";

describe("StockChartFrame", () => {
  it("uses responsive chart heights and preserves the supplied desktop span", () => {
    render(
      <StockChartFrame className="lg:col-span-10">
        <div>캔들차트</div>
      </StockChartFrame>
    );

    expect(screen.getByTestId("stock-chart-frame")).toHaveClass(
      "h-[420px]",
      "sm:h-[480px]",
      "lg:h-[560px]",
      "lg:col-span-10"
    );
    expect(screen.getByText("캔들차트")).toBeInTheDocument();
  });
});
