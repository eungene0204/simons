import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  getNextMissingBacktestCondition,
  hasExplicitInitialCapital,
  isBacktestReady,
} from "./backtestReadiness";

const base: ParsedSummary = {
  description: "x",
  universe: ["KOSPI200"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: "5y",
  initial_capital: 10_000_000,
};

describe("isBacktestReady", () => {
  it("유니버스 전략은 리밸런싱까지 있어야 실행 가능", () => {
    const withoutRebal = {
      ...base,
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 10,
      take_profit_pct: 20,
    };
    // 리밸런싱(none)이 없으면 유니버스 전략은 실행 불가
    expect(isBacktestReady(withoutRebal)).toBe(false);
    expect(isBacktestReady({ ...withoutRebal, rebalancing_period: "monthly" })).toBe(true);
  });

  it("리밸런싱 누락 안내에서 안 함을 선택할 수 있고 명시적 선택으로 인정한다", () => {
    const withoutRebal = {
      ...base,
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 10,
      take_profit_pct: 20,
    };

    expect(getNextMissingBacktestCondition(withoutRebal)).toMatchObject({
      field: "rebalancing",
      suggestions: [
        "매주 리밸런싱",
        "매월 리밸런싱",
        "분기마다 리밸런싱",
        "안 함",
      ],
    });
    expect(
      isBacktestReady(withoutRebal, { allowNoRebalancing: true }),
    ).toBe(true);
  });

  it("단독 종목은 리밸런싱 없이도(나머지 충족 시) 실행 가능", () => {
    expect(
      isBacktestReady({
        ...base,
        target_symbols: ["005930"],
        entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
        exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
        stop_loss_pct: 10,
        take_profit_pct: 20,
      }),
    ).toBe(true);
  });

  it("지정 종목(테마 자동 적용)이라도 매수 조건이 없으면 완성으로 판정하지 않는다", () => {
    // [버그 2026-07-25] 테마 유니버스가 target_symbols를 채우면 진입으로 인정돼 매수 조건
    // 질문이 생략되고 "모든 조건을 정했습니다"가 뜨던 사고 — 빈 진입은 엔진에서 0거래다.
    const themeParsed: ParsedSummary = {
      ...base,
      target_symbols: ["352820", "035900", "041510"],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 15,
      take_profit_pct: 30,
      initial_capital: 50_000_000,
    };
    const options = {
      requireExplicitConfiguration: true,
      prompt: "bts 관련주로 백테스트, 손절 15%, 익절 30%, 최근 5년 데이터, 5,000만원",
    };
    expect(getNextMissingBacktestCondition(themeParsed, options)).toMatchObject({
      field: "entry",
    });
    expect(isBacktestReady(themeParsed, options)).toBe(false);
    expect(
      isBacktestReady(
        {
          ...themeParsed,
          entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
          rebalancing_period: "monthly",
        },
        { ...options, prompt: `${options.prompt}, 매월 리밸런싱` },
      ),
    ).toBe(true);
  });

  it("지정 종목이 여러 개(테마 유니버스)면 리밸런싱을 묻는다 — 기본값 확정 금지", () => {
    // [회귀 2026-07-28 '모바일솔루션 관련주' 사고] '지정 종목 존재=단독 종목'으로 판정해
    // 리밸런싱 질문이 생략되고 기본값 '설정 안 함'으로 조용히 확정되던 버그.
    const themeParsed: ParsedSummary = {
      ...base,
      target_symbols: ["108860", "139670", "051160"],
      entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
      exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      stop_loss_pct: 10,
      take_profit_pct: 20,
    };
    const options = {
      requireExplicitConfiguration: true,
      prompt: "모바일솔루션 관련주 투자 전략, 손절 10%, 익절 20%, 최근 5년 데이터, 1,000만원",
    };
    expect(getNextMissingBacktestCondition(themeParsed, options)).toMatchObject({
      field: "rebalancing",
    });
    // '안 함' 선택(allowNoRebalancing)도 사용자의 결정으로 인정한다.
    expect(
      isBacktestReady(themeParsed, {
        ...options,
        allowNoRebalancing: true,
        prompt: `${options.prompt}\n리밸런싱 안 함`,
      }),
    ).toBe(true);
    // 단독 종목(1개)은 교체가 없어 기존대로 묻지 않는다.
    expect(
      isBacktestReady({ ...themeParsed, target_symbols: ["005930"] }, options),
    ).toBe(true);
  });

  it("손절·익절이 없으면 실행 불가(버튼 숨김)", () => {
    expect(
      isBacktestReady({
        ...base,
        entry_signals: [{ indicator: "ma_crossover", signal_type: "buy" }],
        exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
      }),
    ).toBe(false);
  });

  it("단일 종목만 지정하고 나머지 조건이 없으면 실행 불가", () => {
    expect(isBacktestReady({ ...base, target_symbols: ["005930"] })).toBe(false);
  });

  it("모멘텀 랭킹+정기 리밸런싱은 진입·청산으로 인정하되 손절·익절이 있어야 실행 가능", () => {
    const momentum: ParsedSummary = {
      ...base,
      ranking_metric: "return",
      rebalancing_period: "monthly",
    };
    expect(isBacktestReady(momentum)).toBe(false);
    expect(isBacktestReady({ ...momentum, stop_loss_pct: 10, take_profit_pct: 20 })).toBe(true);
  });

  it("parsed가 없으면 실행 불가", () => {
    expect(isBacktestReady(undefined)).toBe(false);
  });
});

describe("hasExplicitInitialCapital", () => {
  it("거래대금·시가총액 필터의 금액은 초기 자본 명시로 인정하지 않는다", () => {
    // [회귀 2026-07-29 '원자력 관련주' 사고] '일평균 거래대금이 20억 원 이상'의 '20억 원'이
    // 자본금 명시로 오인돼 초기 자금 되묻기가 생략되고 기본값 1,000만원이 확정 표시됐다.
    expect(
      hasExplicitInitialCapital("일평균 거래대금이 20억 원 이상인 종목만 대상으로"),
    ).toBe(false);
    expect(hasExplicitInitialCapital("시가총액 1조 원 이상 대형주")).toBe(false);
    expect(hasExplicitInitialCapital("시총 5000억 원 이상")).toBe(false);
  });

  it("자본금 cue·맨 금액(칩 답변 포함)은 명시로 인정한다", () => {
    expect(hasExplicitInitialCapital("초기 자금 500만원")).toBe(true);
    expect(hasExplicitInitialCapital("투자 금액은 1억 원으로")).toBe(true);
    // 되묻기 칩 답변("1,000만원")은 cue 없이 금액만 온다 — 명시로 인정해야 재질문이 없다.
    expect(hasExplicitInitialCapital("1,000만원")).toBe(true);
    // 필터 금액과 자본금 금액이 함께 있으면 자본금 쪽만 근거가 된다.
    expect(
      hasExplicitInitialCapital("거래대금 20억 원 이상, 초기 자금 3,000만원"),
    ).toBe(true);
  });

  it("거래대금 필터만 있는 전략은 초기 자금 되묻기까지 진행된다", () => {
    // 스크린샷 시나리오 재현: 테마 유니버스(지정 다종목)+거래대금 필터+랭킹+매월 리밸런싱.
    const themeParsed: ParsedSummary = {
      ...base,
      target_symbols: ["015760", "052690", "034020"],
      fundamental_filters: [{ metric: "trading_value", operator: ">=", value: 20 }],
      ranking_metric: "return",
      rebalancing_period: "monthly",
      max_positions: 5,
      stop_loss_pct: 9,
      take_profit_pct: 20,
    };
    const prompt =
      "원자력 관련주 중 일평균 거래대금이 20억 원 이상인 종목만 대상으로, " +
      "최근 60거래일 수익률이 높은 상위 5종목만 동일 비중으로 보유하고 매월 순위를 " +
      "다시 산정해 주세요. 손절 -9%, 익절 20%, 최근 5년 데이터";
    const options = { requireExplicitConfiguration: true, prompt };
    expect(getNextMissingBacktestCondition(themeParsed, options)).toMatchObject({
      field: "initial_capital",
    });
    // 칩 답변이 프롬프트 맥락에 더해지면 완성으로 판정한다.
    expect(
      isBacktestReady(themeParsed, { ...options, prompt: `${prompt}\n1,000만원` }),
    ).toBe(true);
  });
});
