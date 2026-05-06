import { describe, expect, it } from "vitest";
import type { ParsedSummary } from "./strategySummary";
import {
  buildAdvisorEvaluationContextFromWalkForward,
  buildCandidateBacktestRequest,
  buildWalkForwardRequest,
  mergeStrategyModification,
} from "./parsedStrategyMerge";

const previousParsed: ParsedSummary = {
  description: "AI 추세 추종 전략",
  universe: ["KOSPI"],
  fundamental_filters: [],
  entry_signals: [{ indicator: "ai_model", signal_type: "buy" }],
  exit_signals: [{ indicator: "ai_drop_model", signal_type: "sell" }],
  max_positions: 5,
  hold_period_days: null,
  rebalancing_period: "none",
  stop_loss_pct: 7,
  take_profit_pct: null,
  backtest_period: "5y",
  initial_capital: 10000000,
};

describe("mergeStrategyModification", () => {
  it("백테스트 기간만 바꾸는 요청에서는 기존 진입/청산 조건을 유지한다", () => {
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        entry_signals: [],
        exit_signals: [],
        stop_loss_pct: null,
        backtest_period: "1y",
      },
      previousBacktestRequest: {
        symbols: ["005930", "000660"],
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [{ id: "ai_drop_model" }] },
        risk: {
          max_positions: 5,
          position_size_pct: 20,
          stop_loss_pct: 7,
          init_cash: 10000000,
        },
        period: "5y",
        options: { fee_rate: 0.015, slippage_rate: 0.05 },
      },
      nextBacktestRequest: {
        symbols: ["005930", "000660"],
        entry: { conditions: [] },
        exit: { conditions: [] },
        risk: {
          max_positions: 5,
          position_size_pct: 20,
          stop_loss_pct: null,
          init_cash: 10000000,
        },
        period: "1y",
        options: { fee_rate: 0.015, slippage_rate: 0.05 },
      },
      userPrompt: "백테스트 1년만",
      clarificationQuestion: "어떤 조건으로 종목을 선택할까요? 진입 조건을 알려주세요.",
    });

    expect(result.parsed.entry_signals).toEqual(previousParsed.entry_signals);
    expect(result.parsed.exit_signals).toEqual(previousParsed.exit_signals);
    expect(result.parsed.stop_loss_pct).toBe(7);
    expect(result.parsed.backtest_period).toBe("1y");
    expect(result.backtestRequest?.entry?.conditions).toEqual([{ id: "ai_model" }]);
    expect(result.backtestRequest?.exit?.conditions).toEqual([{ id: "ai_drop_model" }]);
    expect(result.backtestRequest?.risk?.stop_loss_pct).toBe(7);
    expect(result.backtestRequest?.period).toBe("1y");
    expect(result.shouldReusePreviousClarification).toBe(true);
  });

  it("리스크 수정 요청은 새로운 손절 값을 적용한다", () => {
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 10,
      },
      previousBacktestRequest: {
        risk: { stop_loss_pct: 7, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        risk: { stop_loss_pct: 10, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "손절 10%로 바꿔줘",
    });

    expect(result.parsed.entry_signals).toEqual(previousParsed.entry_signals);
    expect(result.parsed.stop_loss_pct).toBe(10);
    expect(result.backtestRequest?.risk?.stop_loss_pct).toBe(10);
  });

  it("Advisor 후보 전략을 기존 백테스트 요청에 반영한다", () => {
    const candidate = buildCandidateBacktestRequest(
      {
        symbols: ["005930", "000660"],
        entry: { conditions: [{ id: "old", type: "indicator" }] },
        exit: { conditions: [] },
        risk: {
          max_positions: 5,
          position_size_pct: 20,
          stop_loss_pct: null,
          init_cash: 10000000,
        },
        period: "5Y",
        options: { fee_rate: 0.00015, slippage_rate: 0.0005 },
      },
      {
        fundamental_filters: [{ metric: "pbr", operator: "<=", value: 1 }],
        entry_signals: [{ indicator: "rsi", operator: "<=", threshold: 30 }] as any,
        exit_signals: [{ indicator: "rsi", operator: ">=", threshold: 70 }] as any,
        max_positions: 10,
        stop_loss_pct: 10,
        take_profit_pct: 20,
        backtest_period: "3y",
        initial_capital: 12000000,
      }
    );

    expect(candidate.symbols).toEqual(["005930", "000660"]);
    expect(candidate.entry?.conditions).toHaveLength(2);
    expect(candidate.entry?.conditions?.[0]).toMatchObject({
      type: "filter",
      id: "pbr",
      params: { operator: "<=", value: 1 },
    });
    expect(candidate.exit?.conditions?.[0]).toMatchObject({
      type: "indicator",
      id: "rsi",
      params: { signalType: "sell", value: 70 },
    });
    expect(candidate.risk?.max_positions).toBe(10);
    expect(candidate.risk?.position_size_pct).toBe(10);
    expect(candidate.risk?.stop_loss_pct).toBe(10);
    expect(candidate.risk?.take_profit_pct).toBe(20);
    expect(candidate.risk?.init_cash).toBe(12000000);
    expect(candidate.period).toBe("3Y");
  });

  it("Walk-forward 요청과 Advisor OOS 평가 context를 생성한다", () => {
    const baseStrategy = {
      symbols: ["005930"],
      risk: { init_cash: 10000000 },
      period: "5Y",
    };
    const settings = {
      n_splits: 5,
      train_pct: 0.7,
      anchor: false,
      target_metric: "cagr",
      n_trials: 30,
    };

    expect(buildWalkForwardRequest(baseStrategy, settings, { "risk.stop_loss_pct": [5, 10] })).toEqual({
      base_strategy: baseStrategy,
      ranges: { "risk.stop_loss_pct": [5, 10] },
      ...settings,
    });

    const context = buildAdvisorEvaluationContextFromWalkForward(
      {
        aggregate: { avg_oos_cagr: 4 },
        walk_forward_efficiency: 0.45,
      },
      {
        aggregate: { avg_oos_cagr: 8 },
        walk_forward_efficiency: 0.62,
      }
    );

    expect(context).toMatchObject({
      oos_available: true,
      oos_delta: 0.04,
      before_oos_cagr: 0.04,
      after_oos_cagr: 0.08,
      before_walk_forward_efficiency: 0.45,
      after_walk_forward_efficiency: 0.62,
    });
  });

  it("OOS 결과가 부족하면 Advisor context를 unavailable로 표시한다", () => {
    expect(buildAdvisorEvaluationContextFromWalkForward(null, { aggregate: { avg_oos_cagr: 8 } })).toEqual({
      oos_available: false,
    });
  });
});
