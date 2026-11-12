import { describe, expect, it } from "vitest";

import { listStrategyItems, clearStrategyItems } from "@/app/analytics/new/strategyItems";
import {
  buildStrategySummary,
  buildStrategySummaryFromRequest,
  getSignalExitLabels,
  type ParsedSummary,
} from "./strategy-summary";

// 재무 지표 매도 조건(엔진 v16.51) — "PER 10 이하·ROE 10% 이상 매수, PER 15 초과 또는 ROE 10% 미만이면
// 매도"(2026-11-12 사용자 예시). 대화 카드·요약 카드·결과 화면 배지가 매도 조건을 빠뜨리거나
// 내부 식별자(per·roe_or_gpa)로 내보내지 않아야 한다.
const parsed: ParsedSummary = {
  description: "저평가 우량주",
  universe: ["KOSPI"],
  fundamental_filters: [
    { metric: "per", operator: "<=", value: 10 },
    { metric: "roe_or_gpa", operator: ">=", value: 10 },
  ],
  entry_signals: [],
  exit_signals: [],
  exit_fundamental_filters: [
    { metric: "per", operator: ">", value: 15 },
    { metric: "roe_or_gpa", operator: "<", value: 10 },
  ],
  max_positions: 10,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: null,
  take_profit_pct: null,
  backtest_period: "5y",
  initial_capital: 10_000_000,
};

describe("fundamental exit conditions", () => {
  it("labels them as sell conditions on the summary card", () => {
    const labels = getSignalExitLabels(parsed);
    expect(labels).toHaveLength(2);
    expect(labels.join(" ")).toContain("PER");
    expect(labels.join(" ")).toContain("ROE");
    expect(labels.join(" ")).not.toMatch(/roe_or_gpa|\bper\b/);
    expect(buildStrategySummary(parsed)?.exitBlocks).toEqual(labels);
  });

  it("reads them back from the executed request (no signalType = fundamental)", () => {
    const summary = buildStrategySummaryFromRequest({
      universe_id: "kospi",
      entry: { conditions: [{ type: "filter", id: "per", params: { operator: "<=", value: 10 } }] },
      exit: {
        conditions: [
          { type: "indicator", id: "rsi", params: { period: 14, operator: ">", value: 70, signalType: "sell" } },
          { type: "indicator", id: "per", params: { operator: ">", value: 15 } },
        ],
      },
      risk: { max_positions: 10 },
    });
    expect(summary?.exitBlocks).toHaveLength(2);
    expect(summary?.exitBlocks).toContain(getSignalExitLabels({ exit_signals: [], exit_fundamental_filters: [{ metric: "per", operator: ">", value: 15 }] })[0]);
  });

  it("lists them as clearable sell-condition rows in the chat card", () => {
    const items = listStrategyItems(parsed).filter((item) => item.slot === "exit");
    expect(items.map((item) => item.id)).toEqual(["exit_fundamental.0", "exit_fundamental.1"]);
    const cleared = clearStrategyItems(parsed, ["exit_fundamental.0"]).parsed;
    expect(cleared.exit_fundamental_filters).toEqual([{ metric: "roe_or_gpa", operator: "<", value: 10 }]);
  });
});
