import { describe, expect, it } from "vitest";
import {
  regionFromPathname,
  stripRegionPrefix,
  withRegionPath,
} from "@/lib/geo/region";

describe("regionFromPathname", () => {
  it("/us 트리만 us다", () => {
    expect(regionFromPathname("/us")).toBe("us");
    expect(regionFromPathname("/us/backtest")).toBe("us");
    expect(regionFromPathname("/")).toBe("kr");
    expect(regionFromPathname("/backtest")).toBe("kr");
    // 프리픽스가 낱말 경계로 끝나야 한다 — /user는 한국 트리
    expect(regionFromPathname("/user")).toBe("kr");
    expect(regionFromPathname(null)).toBe("kr");
  });
});

describe("stripRegionPrefix", () => {
  it("us 프리픽스를 벗긴다", () => {
    expect(stripRegionPrefix("/us")).toBe("/");
    expect(stripRegionPrefix("/us/pricing")).toBe("/pricing");
    expect(stripRegionPrefix("/pricing")).toBe("/pricing");
    expect(stripRegionPrefix("/user")).toBe("/user");
  });
});

describe("withRegionPath", () => {
  it("kr은 경로를 그대로 둔다", () => {
    expect(withRegionPath("kr", "/pricing")).toBe("/pricing");
  });

  it("us는 /us 프리픽스를 붙인다", () => {
    expect(withRegionPath("us", "/pricing")).toBe("/us/pricing");
    expect(withRegionPath("us", "/")).toBe("/us");
  });

  it("쿼리·해시를 보존한다", () => {
    expect(withRegionPath("us", "/?legal=terms")).toBe("/us?legal=terms");
    expect(withRegionPath("us", "/stock-order?symbol=AAPL")).toBe(
      "/us/stock-order?symbol=AAPL"
    );
    expect(withRegionPath("us", "/pricing#plans")).toBe("/us/pricing#plans");
  });

  it("이미 프리픽스된 경로·외부 URL은 그대로 둔다(이중 프리픽스 금지)", () => {
    expect(withRegionPath("us", "/us/pricing")).toBe("/us/pricing");
    expect(withRegionPath("us", "https://example.com/a")).toBe("https://example.com/a");
    expect(withRegionPath("us", "#section")).toBe("#section");
  });
});
