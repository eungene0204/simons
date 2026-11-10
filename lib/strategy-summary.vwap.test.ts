import { describe, expect, it } from "vitest";

import { getSignalLabel } from "./strategy-summary";

describe("vwap strategy badge", () => {
  it("shows the period and the cross direction, independent of role", () => {
    expect(getSignalLabel({ indicator: "vwap", signal_type: "buy", period: 20, cross: "above" }, "entry"))
      .toBe("종가 20일 VWAP 상향 돌파");
    expect(getSignalLabel({ indicator: "vwap", signal_type: "sell", period: 5, cross: "above" }, "exit"))
      .toBe("종가 5일 VWAP 상향 돌파");
    expect(getSignalLabel({ indicator: "vwap", signal_type: "sell", period: 60 }, "exit"))
      .toBe("종가 60일 VWAP 하향 이탈");
  });

  it("shows stay-above / stay-below state conditions", () => {
    expect(getSignalLabel({ indicator: "vwap", signal_type: "buy", period: 20, mode: "above" }, "entry"))
      .toBe("종가가 20일 VWAP 위 유지");
    expect(getSignalLabel({ indicator: "vwap", signal_type: "sell", period: 20, mode: "below" }, "exit"))
      .toBe("종가가 20일 VWAP 아래 유지");
  });
});
