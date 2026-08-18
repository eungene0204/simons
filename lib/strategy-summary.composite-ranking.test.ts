import { describe, it, expect } from "vitest";

import { getRankingLabel, type ParsedSummary } from "./strategy-summary";

// 복합 순위 합산(FR-BT-063) — 요약 라벨은 내부 식별자('composite')가 아니라 구성 지표의
// 정본 라벨과 방향으로 표시한다. 산정 기간 미정인 가격 지표는 일수를 붙이지 않는다.

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

describe("getRankingLabel — 복합 순위 합산", () => {
  it("구성 지표 라벨+방향을 나열하고 내부명을 노출하지 않는다", () => {
    const label = getRankingLabel({
      ...base,
      ranking_metric: "composite",
      ranking_components: [
        { metric: "roe_or_gpa", direction: "top" },
        { metric: "current_ratio", direction: "top" },
        { metric: "per", direction: "bottom" },
        { metric: "pcr", direction: "bottom" },
      ],
    });
    expect(label).toBe(
      "복합 순위 상위 (ROE 높은 순 + 유동비율 높은 순 + PER 낮은 순 + PCR 낮은 순 순위 합산)",
    );
    expect(label).not.toContain("composite");
  });

  it("가격 지표 구성은 산정 기간(전략 공통값 상속)을 붙이고, 미정이면 미정으로 표시", () => {
    const comps = [
      { metric: "per", direction: "bottom" as const },
      { metric: "return", direction: "top" as const },
    ];
    expect(
      getRankingLabel({ ...base, ranking_metric: "composite", ranking_components: comps, ranking_lookback_days: 20 }),
    ).toBe("복합 순위 상위 (PER 낮은 순 + 20일 수익률 높은 순 순위 합산)");
    expect(
      getRankingLabel({ ...base, ranking_metric: "composite", ranking_components: comps }),
    ).toBe("복합 순위 상위 (PER 낮은 순 + 수익률(산정 기간 미정) 높은 순 순위 합산)");
  });

  it("단일 랭킹 라벨은 그대로다", () => {
    expect(getRankingLabel({ ...base, ranking_metric: "per", ranking_direction: "bottom" })).toBe(
      "PER 낮은 순 상위",
    );
  });
});
