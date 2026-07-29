import { describe, expect, it } from "vitest";
import { buildStrategyRestatement } from "./strategyRestatement";
import type { ParsedSummary } from "./strategySummary";

const baseParsed: ParsedSummary = {
  description: "테스트 전략",
  universe: ["KOSPI", "KOSDAQ"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  trailing_stop_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

describe("buildStrategyRestatement — 자연어 전략 재정리 첫 문장", () => {
  it("흑자 + PER 필터를 '중에서' 어순으로 재정리한다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      fundamental_filters: [
        { metric: "eps", operator: ">", value: 0 },
        { metric: "per", operator: "<=", value: 10 },
      ],
    };
    expect(
      buildStrategyRestatement(parsed),
    ).toBe("순이익이 흑자인 종목 중에서 PER이 10 이하인 종목을 매수하는 전략이군요.");
  });

  it("영업이익 부호 필터를 수학식 없이 사용자 어휘로 재정리한다", () => {
    // 스크린샷 사고 회귀: "영업이익 흑자인 기업 투자 전략"이
    // "영업이익증가율이 0 이상인 종목을 매수하는 전략이군요."로 번역되던 버그.
    const parsed: ParsedSummary = {
      ...baseParsed,
      fundamental_filters: [{ metric: "ebit", operator: ">", value: 0 }],
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "영업이익이 흑자인 종목을 매수하는 전략이군요.",
    );
  });

  it("단일 재무 필터는 곧바로 매수 대상으로 잇는다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "PBR이 1 이하인 종목을 매수하는 전략이군요.",
    );
  });

  it("재무 필터 + 진입 신호는 신호 트리거로 마무리한다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      fundamental_filters: [{ metric: "per", operator: "<=", value: 10 }],
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "PER이 10 이하인 종목 중에서 MA 골든크로스가 발생하면 매수하는 전략이군요.",
    );
  });

  it("임계값 비교 신호는 '일 때'로 잇는다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      entry_signals: [{ indicator: "rsi", operator: "<=", value: 30 }],
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "RSI 30 이하일 때 매수하는 전략이군요.",
    );
  });

  it("시장을 명시하면 유니버스 접두어를 붙인다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      universe: ["KOSDAQ"],
      fundamental_filters: [{ metric: "roe_or_gpa", operator: ">=", value: 15 }],
    };
    expect(buildStrategyRestatement(parsed, ["universe"])).toBe(
      "KOSDAQ에서 ROE가 15 이상인 종목을 매수하는 전략이군요.",
    );
  });

  it("시장 미언급 시 기본 양시장 유니버스는 되풀이하지 않는다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      fundamental_filters: [{ metric: "per", operator: "<=", value: 10 }],
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "PER이 10 이하인 종목을 매수하는 전략이군요.",
    );
  });

  it("업종 제한은 업종 접두어로 재정리한다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      sector: "반도체",
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "반도체 업종에서 MA 골든크로스가 발생하면 매수하는 전략이군요.",
    );
  });

  it("모멘텀 랭킹은 '수익률 상위 종목' 매수로 재정리한다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      ranking_metric: "return",
      ranking_lookback_days: 60,
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "60일 수익률 상위 종목을 매수하는 전략이군요.",
    );
  });

  it("시총 필터는 억/조 단위 한글 값으로 표기한다", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      fundamental_filters: [{ metric: "market_cap", operator: ">=", value: 100_000_000_000 }],
    };
    expect(buildStrategyRestatement(parsed)).toBe(
      "시총이 1,000억 이상인 종목을 매수하는 전략이군요.",
    );
  });

  it("매수 기준이 없으면 재정리하지 않는다", () => {
    expect(buildStrategyRestatement(baseParsed)).toBeNull();
  });

  it("지정 종목 백테스트는 재정리하지 않는다(별도 흐름)", () => {
    const parsed: ParsedSummary = {
      ...baseParsed,
      target_symbols: ["005930"],
      fundamental_filters: [{ metric: "per", operator: "<=", value: 10 }],
    };
    expect(buildStrategyRestatement(parsed)).toBeNull();
  });
});
