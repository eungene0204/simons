import { describe, expect, it } from "vitest";

import { getSignalLabel } from "./strategy-summary";

describe("market index change strategy badge", () => {
  it("shows the index, the period and the threshold like the trade reason", () => {
    expect(getSignalLabel({ indicator: "market_index_return", signal_type: "buy", index: "KOSPI", period: 1, operator: "<=", value: -5 }, "entry"))
      .toBe("코스피 1거래일 등락률 -5% 이하");
    expect(getSignalLabel({ indicator: "market_index_return", signal_type: "sell", index: "KOSDAQ", period: 5, operator: ">", value: 3 }, "exit"))
      .toBe("코스닥 5거래일 등락률 3% 초과");
  });
});
