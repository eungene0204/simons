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

/**
 * '거래 비용' 행 — 결과가 실제로 적용한 수수료·슬리피지·거래세(result.tradingCosts).
 * 2026-09-14: 결과 로그에 비용이 보이지 않던 공백 수리. 동봉이 없으면(구버전 결과) 행을 만들지 않는다.
 */
import { buildTradingCostRow } from "@/components/strategy/backtest/promptSummaryRows";

describe("buildTradingCostRow", () => {
  it("대칭 수수료·슬리피지·고정 거래세를 한 줄씩 보인다(작은 비율도 0으로 뭉개지 않음)", () => {
    const row = buildTradingCostRow({
      buyFeeRate: 0.00015, sellFeeRate: 0.00015, slippageRate: 0.0005, sellTaxRate: 0.0018,
    });
    expect(row).toEqual({ label: "거래 비용", values: ["수수료 0.015%", "슬리피지 0.05%", "거래세 0.18%"] });
  });

  it("법정 세율 스케줄 구간은 최고→최저 범위로, 매수·매도 수수료가 다르면 나눠 보인다", () => {
    const row = buildTradingCostRow({
      buyFeeRate: 0.0002, sellFeeRate: 0.0003, slippageRate: 0.002,
      sellTaxRate: null, sellTaxRateRange: [0.0015, 0.0023],
    });
    expect(row?.values).toEqual([
      "수수료 매수 0.02% · 매도 0.03%",
      "슬리피지 0.2%",
      "거래세 0.23% → 0.15% (시행일 기준)",
    ]);
  });

  it("거래세 0(미국·ETF)은 0%로 보이고, 동봉이 없으면 행을 만들지 않는다", () => {
    expect(
      buildTradingCostRow({ buyFeeRate: 0.0015, sellFeeRate: 0.0015, slippageRate: 0.002, sellTaxRate: 0 })?.values
    ).toEqual(["수수료 0.15%", "슬리피지 0.2%", "거래세 0%"]);
    expect(buildTradingCostRow(undefined)).toBeNull();
    expect(buildTradingCostRow(null)).toBeNull();
  });
});
