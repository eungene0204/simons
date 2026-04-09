import { describe, expect, it } from "vitest";
import { formatMarketCap } from "@/lib/format-market-cap";

describe("formatMarketCap", () => {
  it("억 단위는 억원 표기로 표시한다", () => {
    expect(formatMarketCap(10_000_000_000)).toBe("100억원");
  });

  it("조 단위는 조와 억원으로 표기한다", () => {
    expect(formatMarketCap(2_300_000_000_000)).toBe("2조 3,000억원");
  });

  it("조 단위 나머지는 콤마 포함 억원으로 표시한다", () => {
    expect(formatMarketCap(2_345_600_000_000)).toBe("2조 3,456억원");
  });

  it("사진과 같은 대형 시가총액 형식으로 표시한다", () => {
    expect(formatMarketCap(1_247_525_300_000_000)).toBe("1,247조 5,253억원");
  });

  it("KIS 억원 단위 원본값도 조/억원 형식으로 보정해서 표시한다", () => {
    expect(formatMarketCap(12_475_253)).toBe("1,247조 5,253억원");
  });
});
