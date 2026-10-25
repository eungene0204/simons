import { describe, expect, it } from "vitest";

import { getSignalLabel } from "./strategy-summary";

describe("disparity strategy badge", () => {
  it("shows the moving-average period and threshold", () => {
    expect(getSignalLabel({ indicator: "disparity", period: 20, operator: ">=", value: 115 }, "exit"))
      .toBe("20일선 이격도 115 이상");
  });
});
