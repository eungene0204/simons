import { describe, expect, it } from "vitest";
import { explainFactorEstimate, interpretFactor, summarizeFactorPattern, summarizeFactorStatistics } from "./factorInterpretation";

const exposure = {
  available: true,
  loadings: [
    { factor: "MKT", beta: 0.46, tStat: 6.6 },
    { factor: "SMB", beta: 0.29, tStat: 1.3 },
    { factor: "HML", beta: -1.11, tStat: -5.2 },
    { factor: "MOM", beta: 0.51, tStat: 3.6 },
  ],
  alphaAnnualPct: -5.35,
  alphaTStat: -0.3,
  r2: 0.5,
};

describe("factor exposure interpretation", () => {
  it("explains each loading from its sign and t-statistic", () => {
    expect(interpretFactor(exposure.loadings[0], false)).toContain("시장 수익률이 1%p 높을 때");
    expect(interpretFactor(exposure.loadings[1], false)).toContain("분명하다고 보기 어렵습니다");
    expect(interpretFactor(exposure.loadings[2], false)).toContain("1.11%p 낮게 추정");
    expect(interpretFactor(exposure.loadings[3], false)).toContain("모멘텀 상위−하위 수익률 차이");
  });

  it("summarizes the supplied result without treating an insignificant alpha as evidence", () => {
    const pattern = summarizeFactorPattern(exposure, false);
    const numbers = summarizeFactorStatistics(exposure, false);
    expect(pattern).toContain("저PBR−고PBR 수익률 차이");
    expect(pattern).toContain("소형주−대형주 수익률 차이");
    expect(pattern).not.toContain("따라");
    expect(numbers).toContain("약 50%");
    expect(numbers).toContain("나머지가 모두 알파라는 뜻은 아닙니다");
    expect(numbers).toContain("연환산 알파 -5.35%");
    expect(numbers).toContain("t값이 -0.3");
    expect(numbers).toContain("별도의 추가 수익이나 손실이 있었다고 말하기 어렵습니다");
  });

  it("explains beta and t using the observed market estimate", () => {
    const explanation = explainFactorEstimate(exposure, false);
    expect(explanation).toContain("시장 수익률 β +0.46");
    expect(explanation).toContain("0.46%p 높게 추정");
    expect(explanation).toContain("t값은 그 관계가 이번 과거 자료에서 얼마나 뚜렷한지");
  });

  it("updates the interpretation when significance and direction change", () => {
    const changed = {
      ...exposure,
      loadings: [{ factor: "HML", beta: 0.4, tStat: 2.1 }],
      alphaAnnualPct: 4,
      alphaTStat: 2.3,
      r2: 0.25,
    };
    expect(interpretFactor(changed.loadings[0], true)).toContain("low-minus-high PBR return spread");
    const numbers = summarizeFactorStatistics(changed, true);
    expect(numbers).toContain("about 25%");
    expect(numbers).toContain("clear positive alpha estimate");
    expect(numbers).not.toContain("does not clearly show extra gains or losses");
    expect(explainFactorEstimate(changed, false)).toContain("저PBR−고PBR 수익률 차이 β +0.40");
  });

  it("does not infer a direction from missing estimates", () => {
    expect(interpretFactor({ factor: "MKT", beta: null, tStat: null }, false)).toContain("자료가 부족합니다");
    expect(summarizeFactorPattern({ available: true, loadings: [], r2: null, alphaTStat: null }, false)).toContain("자료가 부족합니다");
    expect(summarizeFactorStatistics({ available: true, loadings: [], r2: null, alphaTStat: null }, false)).toContain("자료가 부족합니다");
    expect(explainFactorEstimate({ available: true, loadings: [] }, false)).not.toContain("예를 들어");
  });

  it("does not classify the large-cap production strategy from its positive SMB loading", () => {
    const largeCapResult = {
      available: true, symbols: 871, observations: 1137,
      loadings: [{ factor: "SMB", beta: 0.197952, tStat: 5.389427 }],
    };
    const row = interpretFactor(largeCapResult.loadings[0], false);
    expect(row).toContain("다른 팩터의 영향을 통제");
    expect(row).toContain("소형주−대형주 수익률 차이가 1%p 높을 때");
    expect(row).toContain("0.20%p 높게 추정");
    expect(row).not.toContain("소형주의 움직임");
    expect(row).not.toContain("대형주의 움직임");
    expect(summarizeFactorPattern(largeCapResult, false)).toContain(row);
    expect(explainFactorEstimate(largeCapResult, false)).toContain("소형주−대형주 수익률 차이 β +0.20");
  });

  it.each([
    ["MKT", "시장 수익률", "market return"],
    ["SMB", "소형주−대형주 수익률 차이", "small-minus-large return spread"],
    ["HML", "저PBR−고PBR 수익률 차이", "low-minus-high PBR return spread"],
    ["MOM", "모멘텀 상위−하위 수익률 차이", "high-minus-low momentum return spread"],
  ])("preserves the %s factor definition for both coefficient signs and languages", (factor, ko, en) => {
    for (const beta of [0.2, -0.2]) {
      for (const english of [false, true]) {
        const loading = { factor, beta, tStat: beta > 0 ? 5.4 : -5.4 };
        const single = { available: true, loadings: [loading] };
        const row = interpretFactor(loading, english);
        expect(row).toContain(english ? en : ko);
        expect(row).toContain(english ? (beta > 0 ? "0.20 percentage points higher" : "0.20 percentage points lower") : (beta > 0 ? "0.20%p 높게" : "0.20%p 낮게"));
        expect(summarizeFactorPattern(single, english)).toContain(row);
        expect(explainFactorEstimate(single, english)).toContain(english ? en : ko);
      }
    }
  });

  it.each([null, NaN, Infinity])("does not interpret non-finite estimates (%s)", (value) => {
    for (const loading of [{ factor: "SMB", beta: value, tStat: 5.4 }, { factor: "SMB", beta: 0.2, tStat: value }]) {
      expect(interpretFactor(loading, false)).toContain("자료가 부족합니다");
      expect(summarizeFactorPattern({ available: true, loadings: [loading] }, true)).toContain("not enough data");
    }
  });

  it.each([1.95, -1.95, 1.96, -1.96])("applies the stated absolute t-value threshold (%s)", (tStat) => {
    const row = interpretFactor({ factor: "SMB", beta: 0.2, tStat }, false);
    expect(row).toContain("0.20%p 높게 추정");
    expect(row.includes("t값 기준을 충족")).toBe(Math.abs(tStat) >= 1.96);
  });

  it.each([{ factor: "SMB", beta: 0, tStat: 0 }, { factor: "unknown", beta: 0.2, tStat: 5.4 }])("does not invent a relationship for %j", (loading) => {
    expect(interpretFactor(loading, false)).toContain("자료가 부족합니다");
    expect(summarizeFactorPattern({ available: true, loadings: [loading] }, false)).toContain("자료가 부족합니다");
  });
});
