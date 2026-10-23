import { describe, expect, it } from "vitest";

import { getSignalLabel } from "./strategy-summary";

describe("consecutive-down strategy badge", () => {
  it("shows the actual streak length", () => {
    expect(getSignalLabel({ indicator: "consecutive_down", period: 3 }, "entry"))
      .toBe("종가 3거래일 연속 하락");
  });
});
