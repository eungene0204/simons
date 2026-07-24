import { describe, it, expect } from "vitest";
import { formatFundamentalFilter } from "./strategy-summary";

// '작년도 흑자종목' 파싱이 eps 부호 필터(eps>0)로 승격되면서, 배지가 원시 표기
// ("eps > 0") 대신 사용자 어휘("흑자 기업")로 읽히는지 확인하는 회귀 테스트.
describe("formatFundamentalFilter eps sign badge", () => {
  it("renders eps>0 as 흑자 기업", () => {
    expect(formatFundamentalFilter({ metric: "eps", operator: ">", value: 0 })).toBe(
      "흑자 기업 (EPS > 0)",
    );
  });

  it("renders eps<0 as 적자 기업", () => {
    expect(formatFundamentalFilter({ metric: "eps", operator: "<", value: 0 })).toBe(
      "적자 기업 (EPS < 0)",
    );
  });

  it("keeps generic rendering for non-zero eps thresholds", () => {
    expect(formatFundamentalFilter({ metric: "eps", operator: ">=", value: 1000 })).toBe(
      "EPS >= 1000",
    );
  });

  // '영업이익 흑자'도 ebit 부호 필터로 승격 — 수학식("영업이익 > 0") 대신 사용자 어휘.
  it("renders ebit>0 as 영업이익 흑자 기업", () => {
    expect(formatFundamentalFilter({ metric: "ebit", operator: ">", value: 0 })).toBe(
      "영업이익 흑자 기업",
    );
  });

  it("renders ebit<0 as 영업이익 적자 기업", () => {
    expect(formatFundamentalFilter({ metric: "ebit", operator: "<", value: 0 })).toBe(
      "영업이익 적자 기업",
    );
  });
});
