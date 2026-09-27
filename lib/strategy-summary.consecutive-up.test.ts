import { describe, expect, it } from "vitest";

import { getSignalLabel } from "./strategy-summary";

describe("consecutive-up strategy badge", () => {
  it("shows the actual streak length", () => {
    expect(getSignalLabel({ indicator: "consecutive_up", period: 5 }, "entry"))
      .toBe("종가 5거래일 연속 상승");
  });
});
