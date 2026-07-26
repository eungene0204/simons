import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  getNextMissingBacktestCondition,
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
        },
        options,
      ),
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
