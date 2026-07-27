import { describe, expect, it } from "vitest";

import { CATEGORY_STYLE, EXAMPLES, type ExampleCategory } from "./StrategyExampleTabs";

// ETF는 여러 기업을 묶은 상품이라 기업 재무제표 지표를 조건으로 쓸 수 없다
// (backend/engine/universe_capabilities.py). 예시 문구에 재무 지표가 섞이면
// 파싱 단계에서 "ETF에선 쓸 수 없다"는 되묻기로 빠지므로 데이터 단계에서 막는다.
const FUNDAMENTAL_TERMS = ["PER", "PBR", "ROE", "ROA", "부채비율", "시가총액", "영업이익", "현금흐름", "매출"];

// 국내 주식·국내 상장 ETF만 지원 — 해외 지수/시장 언급은 nl_parser의 overseas
// 미지원 안내(backend/engine/nl_parser.py _UNSUPPORTED_CONCEPT_PATTERNS)에 걸린다.
// "나스닥100 ETF" 예시가 미지원 안내로 빠지던 사고(2026-07-27) 재발 방지.
const OVERSEAS_TERMS = ["나스닥", "S&P", "다우", "QQQ", "SPY", "미국", "해외"];

describe("EXAMPLES", () => {
  it("카드 key로 쓰이는 제목이 중복되지 않는다", () => {
    const titles = EXAMPLES.map((example) => example.title);
    expect(new Set(titles).size).toBe(titles.length);
  });

  it("모든 예시 카테고리에 배지 스타일이 정의돼 있다", () => {
    for (const example of EXAMPLES) {
      expect(CATEGORY_STYLE[example.category]).toBeDefined();
    }
  });

  it("ETF·테마 예시가 각각 존재한다", () => {
    const countOf = (category: ExampleCategory) =>
      EXAMPLES.filter((example) => example.category === category).length;

    expect(countOf("ETF")).toBeGreaterThan(0);
    expect(countOf("테마")).toBeGreaterThan(0);
  });

  it("예시는 미지원 해외 시장/지수 키워드를 쓰지 않는다", () => {
    const violations = EXAMPLES.filter((example) =>
      OVERSEAS_TERMS.some((term) =>
        example.prompt.toUpperCase().includes(term.toUpperCase())
      )
    ).map((example) => example.title);

    expect(violations).toEqual([]);
  });

  it("ETF 예시는 기업 재무 지표를 조건으로 쓰지 않는다", () => {
    const violations = EXAMPLES.filter(
      (example) =>
        example.category === "ETF" &&
        FUNDAMENTAL_TERMS.some((term) => example.prompt.includes(term))
    ).map((example) => example.title);

    expect(violations).toEqual([]);
  });
});
