import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MarketDataPanelFrame from "./MarketDataPanelFrame";

describe("MarketDataPanelFrame", () => {
  it("uses responsive panel heights and restores the desktop height", () => {
    render(
      <MarketDataPanelFrame>
        <div>시세 패널</div>
      </MarketDataPanelFrame>
    );

    expect(screen.getByTestId("market-data-panel-frame")).toHaveClass(
      "flex-col",
      "overflow-hidden",
      "h-[420px]",
      "sm:h-[480px]",
      "lg:h-[560px]"
    );
    expect(screen.getByText("시세 패널")).toBeInTheDocument();
  });
});
