/**
 * 결과 화면 "프롬프트" 팝오버의 전략 요약 행 — 대화 카드(ParsedSummaryBubble)와 같은 항목·순서.
 * 2026-08-18: 카드에는 '백테스트 기간'·'초기 자본' 행이 있는데 결과 화면 요약에는 빠져 있던 결함 회귀.
 */
import { describe, it, expect } from "vitest";
import { buildPromptSummaryRows } from "@/components/strategy/backtest/promptSummaryRows";

const SUMMARY = {
  universeName: "KOSPI",
  entryBlocks: ["PBR <= 1.2", "거래대금 >= 30억", "브레이크아웃"],
  exitBlocks: ["손절 -10% 하락시 매도", "익절 20% 이상 수익시 매도"],
  positionText: "최대 12종목",
  rebalancingText: "매월 리밸런싱",
  riskText: "손절 -10%, 익절 20%",
  backtestPeriodText: "3년",
  initialCapitalText: "10,000,000원",
};

describe("buildPromptSummaryRows", () => {
  it("유니버스 → 진입 → 청산 → 백테스트 기간 → 초기 자본 → 리스크 순으로 행을 만든다", () => {
    const rows = buildPromptSummaryRows(SUMMARY, undefined, ["2023-08-18", "2024-01-02", "2026-08-14"]);
    expect(rows.map((r) => r.label)).toEqual(["유니버스", "진입 신호", "청산 신호", "백테스트 기간", "초기 자본", "리스크"]);
    // 상대 기간 라벨 뒤에 실제 실행 구간을 한 줄 더 붙인다
    expect(rows[3].values).toEqual(["3년", "2023-08-18 ~ 2026-08-14"]);
    expect(rows[4].values).toEqual(["10,000,000원"]);
    expect(rows[5].values).toEqual(["최대 12종목", "매월 리밸런싱", "손절 -10%, 익절 20%"]);
  });

  it("직접 지정 창(라벨에 날짜 포함)에는 실행 구간을 다시 붙이지 않는다", () => {
    const rows = buildPromptSummaryRows(
      { ...SUMMARY, backtestPeriodText: "2년 (2020-01-01 ~ 2022-01-01)" },
      undefined,
      ["2020-01-02", "2021-12-30"]
    );
    expect(rows.find((r) => r.label === "백테스트 기간")?.values).toEqual(["2년 (2020-01-01 ~ 2022-01-01)"]);
  });

  it("기간 라벨이 없어도 실행 구간이 있으면 기간 행을 만들고, 자본이 없으면 자본 행을 생략한다", () => {
    const rows = buildPromptSummaryRows(
      { ...SUMMARY, backtestPeriodText: undefined, initialCapitalText: undefined },
      undefined,
      ["2022-01-03", "2026-08-14"]
    );
    expect(rows.find((r) => r.label === "백테스트 기간")?.values).toEqual(["2022-01-03 ~ 2026-08-14"]);
    expect(rows.some((r) => r.label === "초기 자본")).toBe(false);
  });

  it("요약이 없으면 빈 배열", () => {
    expect(buildPromptSummaryRows(null, undefined, [])).toEqual([]);
  });
});
