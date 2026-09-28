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
    expect(interpretFactor(exposure.loadings[0], false)).toContain("시장과 같은 방향으로 움직이는 편");
    expect(interpretFactor(exposure.loadings[1], false)).toContain("분명하다고 보기 어렵습니다");
    expect(interpretFactor(exposure.loadings[2], false)).toContain("PBR이 높은 종목의 움직임");
    expect(interpretFactor(exposure.loadings[3], false)).toContain("최근 상대적으로 오른 종목의 움직임");
  });

  it("summarizes the supplied result without treating an insignificant alpha as evidence", () => {
    const pattern = summarizeFactorPattern(exposure, false);
    const numbers = summarizeFactorStatistics(exposure, false);
    expect(pattern).toContain("PBR이 높은 종목의 움직임과 최근 상대적으로 오른 종목의 움직임");
    expect(pattern).toContain("소형주 쪽 성향도 수치상 보이지만");
    expect(numbers).toContain("약 50%");
    expect(numbers).toContain("나머지가 모두 알파라는 뜻은 아닙니다");
    expect(numbers).toContain("연환산 알파 -5.35%");
    expect(numbers).toContain("t값이 -0.3");
    expect(numbers).toContain("별도의 추가 수익이나 손실이 있었다고 말하기 어렵습니다");
  });

  it("explains beta and t using the observed market estimate", () => {
    const explanation = explainFactorEstimate(exposure, false);
    expect(explanation).toContain("시장 β +0.46");
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
    expect(interpretFactor(changed.loadings[0], true)).toContain("lower-PBR stocks");
    const numbers = summarizeFactorStatistics(changed, true);
    expect(numbers).toContain("about 25%");
    expect(numbers).toContain("clear positive alpha estimate");
    expect(numbers).not.toContain("does not clearly show extra gains or losses");
    expect(explainFactorEstimate(changed, false)).toContain("가치 β +0.40");
  });

  it("does not infer a direction from missing estimates", () => {
    expect(interpretFactor({ factor: "MKT", beta: null, tStat: null }, false)).toContain("자료가 부족합니다");
    expect(summarizeFactorPattern({ available: true, loadings: [], r2: null, alphaTStat: null }, false)).toContain("자료가 부족합니다");
    expect(summarizeFactorStatistics({ available: true, loadings: [], r2: null, alphaTStat: null }, false)).toContain("자료가 부족합니다");
    expect(explainFactorEstimate({ available: true, loadings: [] }, false)).not.toContain("예를 들어");
  });
});
