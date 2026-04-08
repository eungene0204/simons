import { describe, expect, it } from "vitest";
import { formatMarketCap } from "@/lib/format-market-cap";

describe("formatMarketCap", () => {
  it("억 단위는 정수 억으로 표시한다", () => {
    expect(formatMarketCap(10_000_000_000)).toBe("100억");
  });

  it("조 단위는 조와 천억을 조합해서 표시한다", () => {
    expect(formatMarketCap(2_300_000_000_000)).toBe("2조3천억");
  });

  it("천억으로 딱 나누어지지 않으면 억 단위 remainder를 그대로 표시한다", () => {
    expect(formatMarketCap(2_345_600_000_000)).toBe("2조3,456억");
  });
});
