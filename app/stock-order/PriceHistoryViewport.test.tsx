import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PriceHistoryViewport from "./PriceHistoryViewport";

describe("PriceHistoryViewport", () => {
  it("keeps fixed price columns inside a mobile-only horizontal scroll area", () => {
    render(
      <PriceHistoryViewport>
        <div>시세 표</div>
      </PriceHistoryViewport>
    );

    expect(screen.getByTestId("price-history-scroll")).toHaveClass(
      "overflow-x-auto",
      "lg:overflow-x-hidden"
    );
    expect(screen.getByTestId("price-history-table")).toHaveClass(
      "min-w-[696px]",
      "lg:min-w-0"
    );
    expect(screen.getByText("시세 표")).toBeInTheDocument();
  });
});
