import { describe, expect, it } from "vitest";
import { formatProfitFactor, profitFactorForRanking } from "./format-profit-factor";

describe("formatProfitFactor", () => {
  it("손실 거래가 0건이면(null) 0이 아니라 ∞로 표시한다", () => {
    // 회귀: 엔진이 무한대를 0.0으로 뭉개던 시절 전승한 전략이 손익비 0(최악)으로 표시됐다
    expect(formatProfitFactor(null)).toBe("∞");
  });

  it("값이 없으면 —, 있으면 소수 둘째 자리", () => {
    expect(formatProfitFactor(undefined)).toBe("—");
    expect(formatProfitFactor(1.4567)).toBe("1.46");
    expect(formatProfitFactor(0)).toBe("0.00");
  });
});

describe("profitFactorForRanking", () => {
  it("null(=∞)은 점수·정렬에서 상한값으로 접는다", () => {
    expect(profitFactorForRanking(null)).toBe(999);
  });

  it("undefined(값 없음)는 상한이 아니라 '모름'으로 남긴다", () => {
    expect(profitFactorForRanking(undefined)).toBeUndefined();
  });

  it("유한값은 그대로 통과시킨다", () => {
    expect(profitFactorForRanking(1.8)).toBe(1.8);
    expect(profitFactorForRanking(0)).toBe(0);
  });
});
