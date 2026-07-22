import { describe, expect, it } from "vitest";

import type { ParsedSummary } from "@/lib/strategy-summary";

import { isBacktestReady } from "./backtestReadiness";

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

  it("단독 종목은 리밸런싱 없이도(나머지 충족 시) 실행 가능", () => {
    expect(
      isBacktestReady({
        ...base,
        target_symbols: ["005930"],
        exit_signals: [{ indicator: "ma_crossover", signal_type: "sell" }],
        stop_loss_pct: 10,
        take_profit_pct: 20,
      }),
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
