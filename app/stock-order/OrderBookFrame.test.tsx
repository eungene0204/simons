import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OrderBookFrame from "./OrderBookFrame";

describe("OrderBookFrame", () => {
  it("uses responsive heights and preserves the desktop grid span", () => {
    render(
      <OrderBookFrame className="lg:col-span-4">
        <div>호가창</div>
      </OrderBookFrame>
    );

    expect(screen.getByTestId("order-book-frame")).toHaveClass(
      "h-[420px]",
      "sm:h-[480px]",
      "lg:h-[560px]",
      "overflow-hidden",
      "lg:col-span-4"
    );
    expect(screen.getByText("호가창")).toBeInTheDocument();
  });
});
