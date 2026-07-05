import { describe, it, expect } from "vitest";
import {
  buildStrategySummary,
  buildStrategySummaryFromRequest,
  buildStrategySummaryFromDsl,
  type ParsedSummary,
} from "./strategy-summary";

// 결과 화면(BacktestDashboard) 요약 카드에 리밸런싱 배지가 빠지던 버그의 회귀 방지.
// 세 빌더 모두 rebalancing_period가 "none"이 아니면 rebalancingText를 내보내야 한다.
const baseParsed: ParsedSummary = {
  description: "저PBR 고ROE 분기 리밸런싱",
  universe: ["kospi"],
  fundamental_filters: [
    { metric: "pbr", operator: "<=", value: 1.5 },
    { metric: "roe_or_gpa", operator: ">=", value: 8 },
  ],
  entry_signals: [],
  exit_signals: [],
  max_positions: 12,
  hold_period_days: null,
  rebalancing_period: "quarterly",
  stop_loss_pct: 12,
  take_profit_pct: null,
  backtest_period: "full",
  initial_capital: 10000000,
};

describe("리밸런싱 배지 — 요약 빌더", () => {
  it("buildStrategySummary(파싱)는 분기 리밸런싱을 rebalancingText로 노출한다", () => {
    const summary = buildStrategySummary(baseParsed);
    expect(summary?.rebalancingText).toBe("분기 리밸런싱");
  });

  it("rebalancing_period가 none이면 rebalancingText는 undefined다", () => {
    const summary = buildStrategySummary({ ...baseParsed, rebalancing_period: "none" });
    expect(summary?.rebalancingText).toBeUndefined();
  });

  it("buildStrategySummaryFromRequest(실행 요청)도 리밸런싱을 노출한다", () => {
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kospi",
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: { max_positions: 12, stop_loss_pct: 12, rebalancing_period: "quarterly" },
    });
    expect(summary?.rebalancingText).toBe("분기 리밸런싱");
  });

  it("buildStrategySummaryFromDsl(DSL)도 리밸런싱을 노출한다", () => {
    const summary = buildStrategySummaryFromDsl({
      description: "저PBR",
      universe: "kospi",
      entry: { conditions: [] },
      exit: { conditions: [] },
      risk: { max_positions: 12, stop_loss_pct: 12, rebalancing_period: "quarterly" },
    } as never);
    expect(summary?.rebalancingText).toBe("분기 리밸런싱");
  });
});
