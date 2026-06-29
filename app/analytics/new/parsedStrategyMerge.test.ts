import { describe, expect, it } from "vitest";
import type { ParsedSummary } from "./strategySummary";
import {
  buildAdvisorEvaluationContextFromWalkForward,
  buildCandidateBacktestRequest,
  buildWalkForwardParameterRanges,
  buildWalkForwardRequest,
  hasWalkForwardParameterRanges,
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

  it("명시적 연도 범위 후속 요청은 백테스트 시작/종료일을 전략과 요청에 반영한다", () => {
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        backtest_start_date: "2002-01-01",
        backtest_end_date: "2005-12-31",
      },
      previousBacktestRequest: {
        symbols: ["005930", "000660"],
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [{ id: "ai_drop_model" }] },
        risk: { max_positions: 5, position_size_pct: 20, init_cash: 10000000 },
        period: "5y",
        options: { fee_rate: 0.015, slippage_rate: 0.05 },
      },
      nextBacktestRequest: {
        symbols: ["005930", "000660"],
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [{ id: "ai_drop_model" }] },
        risk: { max_positions: 5, position_size_pct: 20, init_cash: 10000000 },
        period: "5y",
        startDate: "2002-01-01",
        endDate: "2005-12-31",
        options: { fee_rate: 0.015, slippage_rate: 0.05 },
      },
      userPrompt: "2002년부터 2005년까지만 테스트 해줘",
    });

    expect(result.parsed.backtest_start_date).toBe("2002-01-01");
    expect(result.parsed.backtest_end_date).toBe("2005-12-31");
    expect(result.backtestRequest?.startDate).toBe("2002-01-01");
    expect(result.backtestRequest?.endDate).toBe("2005-12-31");
  });

  it("날짜와 무관한 후속 수정(초기자금)에서는 기존 명시 기간을 유지한다", () => {
    const dated: ParsedSummary = {
      ...previousParsed,
      backtest_start_date: "2002-01-01",
      backtest_end_date: "2005-12-31",
    };
    const result = mergeStrategyModification({
      previousParsed: dated,
      nextParsed: { ...dated, initial_capital: 20000000 },
      previousBacktestRequest: {
        symbols: ["005930"],
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [] },
        risk: { max_positions: 5, position_size_pct: 20, init_cash: 10000000 },
        period: "5y",
        startDate: "2002-01-01",
        endDate: "2005-12-31",
        options: {},
      },
      nextBacktestRequest: {
        symbols: ["005930"],
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [] },
        risk: { max_positions: 5, position_size_pct: 20, init_cash: 20000000 },
        period: "5y",
        startDate: "2002-01-01",
        endDate: "2005-12-31",
        options: {},
      },
      userPrompt: "초기자금 2천만원으로 바꿔줘",
    });

    expect(result.parsed.backtest_start_date).toBe("2002-01-01");
    expect(result.parsed.backtest_end_date).toBe("2005-12-31");
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

  it("'수익 실현' 표현으로 익절을 설정하면 risk 도메인으로 인식해 반영한다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: null,
      },
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: 30,
      },
      previousBacktestRequest: {
        universe_id: "kospi",
        risk: { max_positions: 5, stop_loss_pct: 12, take_profit_pct: null, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kospi",
        risk: { max_positions: 5, stop_loss_pct: 12, take_profit_pct: 30, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "30% 상승시 수익 실현 하게 설정해",
      previousCoachText: "익절 비율 설정을 추천드립니다. 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다.",
    });

    expect(result.requestedDomains.has("risk")).toBe(true);
    expect(result.parsed.take_profit_pct).toBe(30);
    expect(result.parsed.stop_loss_pct).toBe(12);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(30);
  });

  it("'수익 실현' 설정 요청은 후속 질문이 아니라 전략 수정으로 분류된다", () => {
    expect(isAdvisorFollowUpPrompt("30% 상승시 수익 실현 하게 설정해")).toBe(false);
  });

  it("'30% 수익시 매도'를 익절(risk)로 인식해 백엔드 추출값을 반영한다", () => {
    const result = mergeStrategyModification({
      previousParsed: { ...previousParsed, stop_loss_pct: 10, take_profit_pct: null },
      nextParsed: { ...previousParsed, stop_loss_pct: 10, take_profit_pct: 30 },
      previousBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: 10, take_profit_pct: null, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: 10, take_profit_pct: 30, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "30% 수익시 매도",
      previousCoachText: "수익 실현 비율 설정을 추천드립니다. 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다.",
    });

    expect(result.requestedDomains.has("risk")).toBe(true);
    expect(result.parsed.take_profit_pct).toBe(30);
    expect(result.parsed.stop_loss_pct).toBe(10);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(30);
  });

  it("백엔드 riskOverrides는 프론트가 프롬프트에서 risk를 못 읽어도 그대로 신뢰해 반영한다", () => {
    // 프론트 정규식이 'risk'로 분류하지 못하는 임의 문구라도, 백엔드가 결정적으로 뽑은 값이면 적용.
    const result = mergeStrategyModification({
      previousParsed: { ...previousParsed, stop_loss_pct: 10, take_profit_pct: null },
      nextParsed: { ...previousParsed, stop_loss_pct: 10, take_profit_pct: null },
      previousBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: 10, take_profit_pct: null, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: 10, take_profit_pct: null, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "그러면 그렇게 해줘",
      riskOverrides: { take_profit_pct: 30 },
    });

    expect(result.requestedDomains.has("risk")).toBe(true);
    expect(result.parsed.take_profit_pct).toBe(30);
    expect(result.parsed.stop_loss_pct).toBe(10);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(30);
  });

  it("백엔드 riskOverrides의 null은 해당 리스크 필드 삭제로 반영한다", () => {
    const result = mergeStrategyModification({
      previousParsed: { ...previousParsed, stop_loss_pct: 10, take_profit_pct: 30 },
      nextParsed: { ...previousParsed, stop_loss_pct: 10, take_profit_pct: 30 },
      previousBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: 10, take_profit_pct: 30, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: 10, take_profit_pct: 30, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "익절 빼줘",
      riskOverrides: { take_profit_pct: null },
    });

    expect(result.parsed.take_profit_pct).toBeNull();
    expect(result.parsed.stop_loss_pct).toBe(10);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBeNull();
  });

  it("'10% 하락시 매도'를 손절(risk)로 인식해 백엔드 추출값을 반영한다", () => {
    const result = mergeStrategyModification({
      previousParsed: { ...previousParsed, stop_loss_pct: null, take_profit_pct: null },
      nextParsed: { ...previousParsed, stop_loss_pct: 10, take_profit_pct: null },
      previousBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: null, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kosdaq",
        risk: { max_positions: 6, stop_loss_pct: 10, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "10% 하락시 매도",
      previousCoachText: "손절 조건을 추가해 보세요.",
    });

    expect(result.requestedDomains.has("risk")).toBe(true);
    expect(result.parsed.stop_loss_pct).toBe(10);
  });

  it("코치가 손절을 맥락으로 언급하며 익절을 물은 뒤 '30%로 설정해줘'라고 답하면 익절에 반영한다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: null,
      },
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: null,
      },
      previousBacktestRequest: {
        universe_id: "kospi",
        risk: { max_positions: 8, stop_loss_pct: 12, take_profit_pct: null, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        universe_id: "kospi",
        risk: { max_positions: 8, stop_loss_pct: 12, take_profit_pct: null, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "30%로 설정해줘",
      previousCoachText:
        "손절 12%는 매수가 대비 12% 하락 시 매도하는 조건으로 설정하셨으니, 큰 손실 방지에는 도움이 됩니다. 익절 비율 설정을 추천드립니다. 몇 %로 설정할까요?",
    });

    expect(result.parsed.take_profit_pct).toBe(30);
    expect(result.parsed.stop_loss_pct).toBe(12);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(30);
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

  it("이전 코치가 익절만 언급한 뒤 퍼센트로 다시 조정하면 익절 문맥으로 해석한다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: 30,
        hold_period_days: 126,
        max_positions: 8,
      },
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: 30,
        hold_period_days: 126,
        max_positions: 8,
      },
      previousBacktestRequest: {
        universe_id: "kospi",
        risk: {
          max_positions: 8,
          stop_loss_pct: 12,
          take_profit_pct: 30,
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
          max_holding_days: 126,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "20%로 다시 조정",
      previousCoachText:
        "익절 비율(매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건)을 30%로 조정해 주신 요청을 반영하여, 현재 조건과 비교 테스트를 진행해 보시겠어요?",
    });

    expect(result.requestedDomains.has("risk")).toBe(true);
    expect(result.parsed.stop_loss_pct).toBe(12);
    expect(result.parsed.take_profit_pct).toBe(20);
    expect(result.backtestRequest?.risk?.stop_loss_pct).toBe(12);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(20);
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
      entry: {
        conditions: [
          { id: "rsi", params: { period: 14, value: 30, threshold: 30, operator: "<=" } },
          { id: "ma_crossover", params: { shortMA: 5, longMA: 20 } },
          { type: "filter", id: "pbr", params: { value: 1, operator: "<=" } },
        ],
      },
      exit: {
        conditions: [
          { id: "ai_drop_model", params: { threshold: 70, value: 70, signalType: "sell" } },
        ],
      },
      risk: { init_cash: 10000000, stop_loss_pct: 10, take_profit_pct: 20 },
      period: "5Y",
    };
    const settings = {
      n_splits: 5,
      train_pct: 0.7,
      anchor: false,
      target_metric: "cagr",
      n_trials: 30,
    };

    const ranges = buildWalkForwardParameterRanges(baseStrategy);
    expect(hasWalkForwardParameterRanges(ranges)).toBe(true);

    expect(ranges).toMatchObject({
      "risk.stop_loss_pct": [6, 10, 14],
      "risk.take_profit_pct": [12, 20, 28],
      "entry.conditions.0.params.period": [9, 14, 19],
      "entry.conditions.0.params.value": [18, 30, 42],
      "entry.conditions.1.params.shortMA": [3, 5, 7],
      "entry.conditions.1.params.longMA": [13, 20, 27],
      "entry.conditions.2.params.value": [0.8, 1, 1.2],
      "exit.conditions.0.params.threshold": [42, 70, 80],
    });
    expect(ranges).not.toHaveProperty("entry.conditions.0.params.threshold");
    expect(ranges).not.toHaveProperty("exit.conditions.0.params.value");

    expect(buildWalkForwardRequest(baseStrategy, settings, ranges)).toEqual({
      base_strategy: baseStrategy,
      ranges,
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

  it("Walk-forward 튜닝 범위가 없는 전략을 식별한다", () => {
    const ranges = buildWalkForwardParameterRanges({
      symbols: ["005930"],
      risk: { init_cash: 10000000 },
      period: "1Y",
    });

    expect(ranges).toEqual({});
    expect(hasWalkForwardParameterRanges(ranges)).toBe(false);
    expect(hasWalkForwardParameterRanges({ "risk.stop_loss_pct": [6, 10] })).toBe(true);
    expect(hasWalkForwardParameterRanges({ "risk.stop_loss_pct": [10] })).toBe(false);
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
