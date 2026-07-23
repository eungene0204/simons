import { describe, expect, it } from "vitest";
import { applyParsedValueStrategySeed } from "./builderSeed";

describe("applyParsedValueStrategySeed", () => {
  it("hydrates the screenshot request as a complete value selection method", () => {
    const state = {
      universe: "KOSPI",
      holding_count: 12,
      rebalance_cycle: "quarterly",
      stop_loss_pct: 12,
      risk_done: true,
    };

    expect(
      applyParsedValueStrategySeed(state, {
        fundamental_filters: [
          { metric: "pbr", operator: "<=", value: 1.5 },
          { metric: "roe_or_gpa", operator: ">=", value: 8 },
        ],
      }),
    ).toEqual({
      ...state,
      strategy_type: "value",
      value_pbr: 1.5,
      value_roe: 8,
    });
  });

  it("does not infer a value strategy when either financial condition is missing", () => {
    const state = { universe: "KOSPI" };

    expect(
      applyParsedValueStrategySeed(state, {
        fundamental_filters: [{ metric: "roe_or_gpa", operator: ">=", value: 8 }],
      }),
    ).toBe(state);
  });

  it("does not replace an explicitly recognized strategy type", () => {
    const state = { universe: "KOSPI", strategy_type: "momentum" };

    expect(
      applyParsedValueStrategySeed(state, {
        fundamental_filters: [
          { metric: "pbr", operator: "<=", value: 1.5 },
          { metric: "roe_or_gpa", operator: ">=", value: 8 },
        ],
      }),
    ).toBe(state);
  });
});
