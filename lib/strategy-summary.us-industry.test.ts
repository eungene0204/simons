/**
 * 미국 업종 필터 배지(FR-STR-074 ⑩) — 유니버스가 조용히 좁혀지지 않게 드러낸다.
 *
 * 분류(GICS)는 한국 섹터와 체계가 달라 필드가 따로다(us_industry). 배지에 싣지 않으면
 * 사용자에게는 "미국 전체"로 보이는데 실제로는 업종 교집합으로 돌아간다.
 */
import { describe, expect, it } from "vitest";

import { getDisplayUniverseLabels } from "./strategy-summary";

const base = {
  universe: ["US"],
  fundamental_filters: [],
  entry_signals: [],
  exit_signals: [],
  max_positions: 10,
  backtest_period: "5y",
  initial_capital: 10000,
  rebalancing_period: "none",
  hold_period_days: null,
  stop_loss_pct: null,
  take_profit_pct: null,
  trailing_stop_pct: null,
};

describe("미국 업종 필터 배지", () => {
  it("업종 필터를 유니버스 옆 배지로 드러낸다", () => {
    const labels = getDisplayUniverseLabels({ ...base, us_industry: "Airlines" } as never);
    expect(labels.some((l) => l.includes("Airlines"))).toBe(true);
  });

  it("지수 유니버스와 함께 쓰면 둘 다 보인다(교집합임이 드러나야 한다)", () => {
    const labels = getDisplayUniverseLabels({
      ...base,
      universe: ["SP500"],
      us_industry: "Health Care",
    } as never);
    expect(labels.length).toBeGreaterThanOrEqual(2);
    expect(labels.some((l) => l.includes("Health Care"))).toBe(true);
  });

  it("업종 필터가 없으면 배지도 없다", () => {
    const labels = getDisplayUniverseLabels({ ...base } as never);
    expect(labels.some((l) => l.includes("업종"))).toBe(false);
  });
});
