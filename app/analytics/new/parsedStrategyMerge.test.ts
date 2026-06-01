import { describe, expect, it } from "vitest";
import type { ParsedSummary } from "./strategySummary";
import {
  buildAdvisorEvaluationContextFromWalkForward,
  buildCandidateBacktestRequest,
  buildWalkForwardRequest,
  isAdvisorFollowUpPrompt,
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

  it("리스크 후속 수정은 파서 기본 KOSPI200으로 기존 유니버스를 덮어쓰지 않는다", () => {
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        universe: ["KOSPI200"],
        entry_signals: [],
        exit_signals: [],
        stop_loss_pct: null,
        take_profit_pct: null,
        trailing_stop_pct: 15,
      },
      previousBacktestRequest: {
        universe_id: "kospi",
        symbols: ["005930", "000660"],
        entry: { conditions: [{ id: "pbr" }] },
        exit: { conditions: [] },
        risk: {
          max_positions: 5,
          position_size_pct: 20,
          stop_loss_pct: 7,
          init_cash: 10000000,
        },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kospi200",
        symbols: ["069500"],
        entry: { conditions: [] },
        exit: { conditions: [] },
        risk: {
          max_positions: null,
          stop_loss_pct: null,
          take_profit_pct: null,
          trailing_stop_pct: 15,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "트레일링 15% 추가해줘",
    });

    expect(result.parsed.universe).toEqual(["KOSPI"]);
    expect(result.parsed.stop_loss_pct).toBe(7);
    expect(result.parsed.trailing_stop_pct).toBe(15);
    expect(result.backtestRequest?.universe_id).toBe("kospi");
    expect(result.backtestRequest?.symbols).toEqual(["005930", "000660"]);
    expect(result.backtestRequest?.risk?.stop_loss_pct).toBe(7);
    expect(result.backtestRequest?.risk?.trailing_stop_pct).toBe(15);
  });

  it("코치가 트레일링 스탑 비율을 물은 뒤 숫자만 답해도 전략 요약에 반영한다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        trailing_stop_pct: null,
      },
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        trailing_stop_pct: null,
      },
      previousBacktestRequest: {
        universe_id: "kospi",
        symbols: ["005930", "000660"],
        risk: {
          max_positions: 8,
          stop_loss_pct: 12,
          max_holding_days: 126,
          init_cash: 10000000,
        },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kospi",
        symbols: ["005930", "000660"],
        risk: {
          max_positions: 8,
          stop_loss_pct: 12,
          max_holding_days: 126,
          trailing_stop_pct: null,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "15%로 정해줘",
      previousCoachText:
        "트레일링 스탑이라는 조건을 추가할 때, 최고가에서 몇 % 내려오면 팔지 정할까요?",
    });

    expect(result.requestedDomains.has("risk")).toBe(true);
    expect(result.parsed.trailing_stop_pct).toBe(15);
    expect(result.parsed.stop_loss_pct).toBe(12);
    expect(result.backtestRequest?.risk?.trailing_stop_pct).toBe(15);
    expect(result.backtestRequest?.risk?.stop_loss_pct).toBe(12);
  });

  it("익절 비율만 명시한 요청은 이전 코치 문장에 트레일링 스탑이 있어도 트레일링 스탑을 설정하지 않는다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: null,
        trailing_stop_pct: null,
        hold_period_days: 126,
      },
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: 30,
        trailing_stop_pct: 30,
        hold_period_days: 126,
      },
      previousBacktestRequest: {
        universe_id: "kospi",
        risk: {
          max_positions: 8,
          stop_loss_pct: 12,
          take_profit_pct: null,
          trailing_stop_pct: null,
          max_holding_days: 126,
          init_cash: 10000000,
        },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kospi",
        risk: {
          max_positions: 8,
          stop_loss_pct: 12,
          take_profit_pct: 30,
          trailing_stop_pct: 30,
          max_holding_days: 126,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "익절 비율을 30%로 설정해줘",
      previousCoachText:
        "익절 비율을 추가해 보시겠어요? 아니면 트레일링 스탑을 추가해 보시겠어요? 예를 들면 '트레일링 스탑 15% 설정'이라고 말씀해주세요.",
    });

    expect(result.requestedDomains.has("risk")).toBe(true);
    expect(result.parsed.take_profit_pct).toBe(30);
    expect(result.parsed.trailing_stop_pct).toBeNull();
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(30);
    expect(result.backtestRequest?.risk?.trailing_stop_pct).toBeNull();
  });

  it("기존 트레일링 스탑이 있는 전략에서 익절만 바꾸면 기존 트레일링 스탑 값을 유지한다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        take_profit_pct: 20,
        trailing_stop_pct: 15,
      },
      nextParsed: {
        ...previousParsed,
        take_profit_pct: 30,
        trailing_stop_pct: 30,
      },
      previousBacktestRequest: {
        risk: {
          stop_loss_pct: 7,
          take_profit_pct: 20,
          trailing_stop_pct: 15,
          init_cash: 10000000,
        },
        period: "5y",
      },
      nextBacktestRequest: {
        risk: {
          stop_loss_pct: 7,
          take_profit_pct: 30,
          trailing_stop_pct: 30,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "익절 30%로 바꿔줘",
      previousCoachText:
        "트레일링 스탑이라는 조건을 추가할 때, 최고가에서 몇 % 내려오면 팔지 정할까요?",
    });

    expect(result.parsed.take_profit_pct).toBe(30);
    expect(result.parsed.trailing_stop_pct).toBe(15);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(30);
    expect(result.backtestRequest?.risk?.trailing_stop_pct).toBe(15);
  });

  it("후속 개선 질문처럼 수정 domain이 없는 요청은 기존 전략을 유지한다", () => {
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        entry_signals: [],
        exit_signals: [],
        stop_loss_pct: null,
        max_positions: null,
      },
      previousBacktestRequest: {
        symbols: ["005930", "000660"],
        entry: { conditions: [{ id: "breakout_52w" }, { id: "volume_spike" }] },
        exit: { conditions: [] },
        risk: {
          max_positions: 6,
          position_size_pct: 16.67,
          stop_loss_pct: 10,
          max_holding_days: 20,
          init_cash: 10000000,
        },
        period: "5y",
      },
      nextBacktestRequest: {
        symbols: [],
        entry: { conditions: [] },
        exit: { conditions: [] },
        risk: {
          max_positions: null,
          stop_loss_pct: null,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "어디를 개선 해볼까?",
    });

    expect(result.requestedDomains.size).toBe(0);
    expect(result.parsed.entry_signals).toEqual(previousParsed.entry_signals);
    expect(result.parsed.exit_signals).toEqual(previousParsed.exit_signals);
    expect(result.parsed.stop_loss_pct).toBe(7);
    expect(result.parsed.max_positions).toBe(5);
    expect(result.backtestRequest?.entry?.conditions).toEqual([
      { id: "breakout_52w" },
      { id: "volume_spike" },
    ]);
    expect(result.backtestRequest?.risk?.stop_loss_pct).toBe(10);
    expect(result.backtestRequest?.risk?.max_holding_days).toBe(20);
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

describe("isAdvisorFollowUpPrompt", () => {
  it("전략 수정 domain이 없는 개선 질문을 advisor follow-up으로 분류한다", () => {
    expect(isAdvisorFollowUpPrompt("어떻게 개선해 볼까?")).toBe(true);
    expect(isAdvisorFollowUpPrompt("어디를 개선 해볼까?")).toBe(true);
  });

  it("매도 시점 질문은 기존 전략을 바꾸지 않는 follow-up으로 분류한다", () => {
    expect(isAdvisorFollowUpPrompt("만약 저 두 종목만 산다면 언제 팔아야 할까?")).toBe(true);
    expect(isAdvisorFollowUpPrompt("익절은 어느 정도가 좋을까?")).toBe(true);
  });

  it("명시적인 전략 수정 요청은 follow-up으로 분류하지 않는다", () => {
    expect(isAdvisorFollowUpPrompt("손절 12%로 바꿔줘")).toBe(false);
    expect(isAdvisorFollowUpPrompt("KOSPI200으로 바꿔줘")).toBe(false);
  });
});
