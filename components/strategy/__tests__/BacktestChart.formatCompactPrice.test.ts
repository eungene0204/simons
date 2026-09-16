import { describe, expect, it } from "vitest";
import { formatCompactPrice } from "../BacktestChart";

describe("formatCompactPrice (자산곡선 축·툴팁 원화 축약)", () => {
  it("양수는 기존 억/만/천 축약을 유지한다", () => {
    expect(formatCompactPrice(123_000_000)).toBe("1.2억");
    expect(formatCompactPrice(48_380_000)).toBe("4838만");
    expect(formatCompactPrice(1_500)).toBe("1.5천");
    expect(formatCompactPrice(0)).toBe("0");
  });

  it("음수 눈금도 같은 축약으로 표기한다", () => {
    // [회귀 2026-09-17] 자동 스케일 여백으로 생긴 음수 눈금이 "-10000000" 생숫자로 찍혔다.
    expect(formatCompactPrice(-10_000_000)).toBe("-1000만");
    expect(formatCompactPrice(-250_000_000)).toBe("-2.5억");
    expect(formatCompactPrice(-2_000)).toBe("-2.0천");
    expect(formatCompactPrice(-10_000_000)).not.toMatch(/^-\d{5,}$/);
  });
});
