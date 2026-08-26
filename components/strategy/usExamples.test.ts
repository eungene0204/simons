import { describe, expect, it } from "vitest";

import { CATEGORY_STYLE } from "./StrategyExampleTabs";
import { US_EXAMPLES } from "./usExamples";

// 한국 시장 어휘 — US 예시에 섞이면 파서가 한국 유니버스로 해석하거나 혼합 되묻기가 난다
// (StrategyExampleTabs.examples.test.ts의 해외 키워드 금지 가드와 대칭).
const KR_MARKET_TERMS = ["KOSPI", "KOSDAQ", "코스피", "코스닥", "억 원", "억원"];

// ETF는 기업 재무제표가 없다 — 재무 지표가 섞이면 파싱 단계 되묻기로 빠진다(KR 가드와 동일).
const FUNDAMENTAL_TERMS = ["PER", "PBR", "ROE", "ROA", "부채비율", "영업이익", "현금흐름", "매출"];

describe("US_EXAMPLES", () => {
  it("100개(테마 18 포함)이고 카드 key로 쓰이는 제목이 중복되지 않는다", () => {
    expect(US_EXAMPLES.length).toBe(100);
    const titles = US_EXAMPLES.map((example) => example.title);
    expect(new Set(titles).size).toBe(titles.length);
  });

  it("모든 카테고리에 배지 스타일이 있고, 테마는 카탈로그 기반 18개다", () => {
    for (const example of US_EXAMPLES) {
      expect(CATEGORY_STYLE[example.category]).toBeDefined();
    }
    expect(US_EXAMPLES.filter((example) => example.category === "테마").length).toBe(18);
  });

  it("예시는 한국 시장 어휘를 쓰지 않는다", () => {
    const violations = US_EXAMPLES.filter((example) =>
      KR_MARKET_TERMS.some((term) => example.prompt.toUpperCase().includes(term.toUpperCase()))
    ).map((example) => example.title);
    expect(violations).toEqual([]);
  });

  it("ETF 예시는 기업 재무 지표를 조건으로 쓰지 않는다", () => {
    const violations = US_EXAMPLES.filter(
      (example) =>
        example.category === "ETF" &&
        FUNDAMENTAL_TERMS.some((term) => example.prompt.includes(term))
    ).map((example) => example.title);
    expect(violations).toEqual([]);
  });

  it("KR 예시와 제목이 겹치지 않는다(전면 새 구성)", async () => {
    const { EXAMPLES } = await import("./StrategyExampleTabs");
    const krTitles = new Set(EXAMPLES.map((example) => example.title));
    const overlap = US_EXAMPLES.filter((example) => krTitles.has(example.title));
    expect(overlap).toEqual([]);
  });
});
