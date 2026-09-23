import { describe, it, expect } from "vitest";

import {
  formatUniverseFilterLabels,
  getDisplayUniverseLabels,
  type ParsedSummary,
} from "./strategy-summary";

// 유니버스 사전 필터 확장(엔진 v16.32) — 적자기업 제외·시가총액 하위 분위 제외.
// 배지에 드러나지 않으면 대상이 좁혀졌다는 사실이 화면에서 사라진다(업종 제외와 같은 계약).

const base: ParsedSummary = {
  description: "테스트",
  universe: ["kospi"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "monthly",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: "full",
  initial_capital: 10000000,
};

describe("유니버스 사전 필터 배지", () => {
  it("시가총액 하위 분위 제외를 상위 N·거래대금 필터와 함께 적는다", () => {
    const labels = formatUniverseFilterLabels({
      universe_market_cap_top_n: 500,
      universe_market_cap_exclude_bottom_pct: 20,
      universe_liquidity_exclude_bottom_pct: 10,
      universe_liquidity_lookback_days: 20,
    });

    expect(labels).toEqual([
      "시가총액 상위 500종목",
      "시가총액 하위 20% 제외",
      "20일 평균 거래대금 하위 10% 제외",
    ]);
  });

  it("적자기업 제외는 기준별로 다른 문구를 쓴다", () => {
    expect(formatUniverseFilterLabels({ universe_exclude_loss_making: "net" }))
      .toEqual(["당기순손실 기업 제외"]);
    expect(formatUniverseFilterLabels({ universe_exclude_loss_making: "operating" }))
      .toEqual(["영업손실 기업 제외"]);
    expect(formatUniverseFilterLabels({ universe_exclude_loss_making: "both" }))
      .toEqual(["당기순손실·영업손실 기업 제외"]);
  });

  it("모르는 기준 값은 배지를 만들지 않는다(없는 필터를 있는 것처럼 적지 않는다)", () => {
    expect(formatUniverseFilterLabels({ universe_exclude_loss_making: "yes" })).toEqual([]);
    expect(formatUniverseFilterLabels({})).toEqual([]);
  });

  it("유니버스 배지에 필터가 함께 나온다", () => {
    const labels = getDisplayUniverseLabels({
      ...base,
      universe_market_cap_exclude_bottom_pct: 20,
      universe_exclude_loss_making: "net",
    });

    expect(labels).toContain("시가총액 하위 20% 제외");
    expect(labels).toContain("당기순손실 기업 제외");
  });
});
