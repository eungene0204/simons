import { describe, it, expect } from "vitest";

import {
  buildStrategySummary,
  buildStrategySummaryFromRequest,
  formatSeasonalLabel,
  formatVolTargetLabel,
  type ParsedSummary,
} from "./strategy-summary";

// 계절 필터·목표 변동성(엔진 v16.25) — 요약 카드에 드러내지 않으면 설정이 조용히 사라진 것처럼 보인다.

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

describe("계절 필터·목표 변동성 라벨", () => {
  it("투자하는 달과 목표 변동성을 리스크 문구에 싣는다", () => {
    const s = buildStrategySummary({ ...base, seasonal_months: [11, 12, 1, 2, 3, 4], volatility_target: { target_pct: 10 } });
    expect(s?.riskText).toContain("11·12·1·2·3·4월에만 투자");
    expect(s?.riskText).toContain("목표 연변동성 10%");
  });

  it("목표 값이 비면 값 미정으로 적는다(조용한 확정 금지)", () => {
    expect(formatVolTargetLabel({ target_pct: null })).toBe("목표 변동성(값 미정)");
    expect(formatVolTargetLabel(null)).toBeNull();
    expect(formatSeasonalLabel([])).toBeNull();
  });

  it("실행된 요청(risk.seasonal_months·target_volatility_pct)에서도 같은 문구", () => {
    const s = buildStrategySummaryFromRequest({
      universe_id: "kospi",
      risk: { max_positions: 10, seasonal_months: [5, 6], target_volatility_pct: 8 },
    });
    expect(s?.riskText).toContain("5·6월에만 투자");
    expect(s?.riskText).toContain("목표 연변동성 8%");
  });
});
