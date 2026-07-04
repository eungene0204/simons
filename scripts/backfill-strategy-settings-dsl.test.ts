import { describe, expect, it } from "vitest";
import { buildDslFromCanonical, needsBackfill } from "./backfill-strategy-settings-dsl";

describe("needsBackfill", () => {
  it("entry.conditions가 이미 있으면 backfill 대상이 아니다", () => {
    expect(needsBackfill({ entry: { conditions: [{ id: "rsi" }] } })).toBe(false);
  });

  it("risk 객체가 이미 있으면 backfill 대상이 아니다", () => {
    expect(needsBackfill({ risk: { stop_loss_pct: 10 } })).toBe(false);
  });

  it("canonical 요약 필드만 있으면 backfill 대상이다", () => {
    expect(
      needsBackfill({
        entry_signals: [{ indicator: "rsi", signal_type: "buy" }],
        stop_loss_pct: 10,
        take_profit_pct: 20,
      })
    ).toBe(true);
  });

  it("아무 신호/리스크 필드도 없으면 backfill 대상이 아니다", () => {
    expect(needsBackfill({ universe: ["KOSPI200"] })).toBe(false);
  });

  it("null/비객체는 backfill 대상이 아니다", () => {
    expect(needsBackfill(null)).toBe(false);
    expect(needsBackfill(undefined)).toBe(false);
  });
});

describe("buildDslFromCanonical", () => {
  it("entry_signals/exit_signals를 entry.conditions/exit.conditions로 복원한다", () => {
    const settings = {
      entry_signals: [
        { indicator: "rsi", signal_type: "buy", period: 14, operator: "<", value: 30 },
      ],
      exit_signals: [{ indicator: "rsi", signal_type: "sell", period: 14, operator: ">", value: 70 }],
      fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
      stop_loss_pct: 10,
      take_profit_pct: 20,
      max_positions: 8,
      universe: ["KOSPI"],
    };

    const patch = buildDslFromCanonical(settings);

    expect(patch.entry).toEqual({
      conditions: [
        { type: "filter", id: "pbr", params: { operator: "<=", value: 1 }, weight: 1.0 },
        {
          type: "indicator",
          id: "rsi",
          params: { signalType: "buy", period: 14, operator: "<", value: 30 },
          weight: 1.0,
        },
      ],
    });
    expect(patch.exit).toEqual({
      conditions: [
        {
          type: "indicator",
          id: "rsi",
          params: { signalType: "sell", period: 14, operator: ">", value: 70 },
          weight: 1.0,
        },
      ],
    });
    expect((patch.risk as any).stop_loss_pct).toBe(10);
    expect((patch.risk as any).take_profit_pct).toBe(20);
    expect((patch.risk as any).max_positions).toBe(8);
    expect((patch.risk as any).position_size_pct).toBe(12.5);
    expect(patch.universe_id).toBe("kospi");
  });

  it("ma_crossover 신호의 shortMA/longMA를 복원한다", () => {
    const settings = {
      entry_signals: [
        { indicator: "ma_crossover", signal_type: "buy", short_period: 5, long_period: 20 },
      ],
    };

    const patch: any = buildDslFromCanonical(settings);
    expect(patch.entry.conditions[0]).toEqual({
      type: "indicator",
      id: "ma_crossover",
      params: { signalType: "buy", shortMA: 5, longMA: 20 },
      weight: 1.0,
    });
  });

  it("rebalancing_period이 있으면 max_holding_days를 끈다", () => {
    const settings = {
      hold_period_days: 30,
      rebalancing_period: "month",
    };

    const patch: any = buildDslFromCanonical(settings);
    expect(patch.risk.max_holding_days).toBeNull();
    expect(patch.risk.rebalancing_period).toBe("month");
  });

  it("universe가 없으면 kospi200을 기본값으로 사용한다", () => {
    const patch: any = buildDslFromCanonical({});
    expect(patch.universe_id).toBe("kospi200");
  });

  it("fee_rate/slippage_rate를 퍼센트에서 비율로 변환한다", () => {
    const patch: any = buildDslFromCanonical({ fee_rate: 0.015, slippage_rate: 0.05 });
    expect(patch.options.fee_rate).toBeCloseTo(0.00015);
    expect(patch.options.slippage_rate).toBeCloseTo(0.0005);
  });

  it("backtest_period/start_date/end_date가 있으면 period/startDate/endDate를 채운다", () => {
    const patch: any = buildDslFromCanonical({
      backtest_period: "5y",
      backtest_start_date: "2020-01-01",
      backtest_end_date: "2024-01-01",
    });
    expect(patch.period).toBe("5y");
    expect(patch.startDate).toBe("2020-01-01");
    expect(patch.endDate).toBe("2024-01-01");
  });
});
