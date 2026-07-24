import { describe, expect, it } from "vitest";
import type { ParsedSummary } from "./strategySummary";
import {
  buildAdvisorEvaluationContextFromWalkForward,
  buildCandidateBacktestRequest,
  buildFundamentalFactorPrompt,
  buildStrategyHorizonComparisonResponse,
  buildTakeProfitPercentagePrompt,
  buildWalkForwardParameterDescriptors,
  buildWalkForwardParameterRanges,
  buildWalkForwardRequest,
  correctCountTypo,
  hasWalkForwardParameterRanges,
  isAdvisorFollowUpPrompt,
  MA_CROSSOVER_PERIOD_VALUES,
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
  it("작년도 흑자종목은 EPS 양수 조건만 남기고 순이익증가율 환각을 제거한다", () => {
    const result = mergeStrategyModification({
      previousParsed: null,
      nextParsed: {
        ...previousParsed,
        description: "작년도 흑자종목을 매수 하는 전략",
        fundamental_filters: [
          { metric: "net_income_growth", operator: ">=", value: 100 },
          { metric: "eps", operator: ">", value: 0 },
        ],
      },
      nextBacktestRequest: {
        universe_id: "kospi200",
        entry: {
          conditions: [
            {
              type: "filter",
              id: "net_income_growth",
              params: { operator: ">=", value: 100 },
            },
            {
              type: "filter",
              id: "eps",
              params: { operator: ">", value: 0 },
            },
          ],
        },
        risk: { max_positions: 10, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "작년도 흑자종목을 매수 하는 전략",
    });

    expect(result.parsed.fundamental_filters).toEqual([
      { metric: "eps", operator: ">", value: 0 },
    ]);
    expect(result.backtestRequest?.entry?.conditions).toEqual([
      {
        type: "filter",
        id: "eps",
        params: { operator: ">", value: 0 },
      },
    ]);
  });

  it("사용자가 흑자와 순이익증가율을 모두 명시하면 두 조건을 유지한다", () => {
    const filters = [
      { metric: "net_income_growth", operator: ">=", value: 100 },
      { metric: "eps", operator: ">", value: 0 },
    ];
    const result = mergeStrategyModification({
      previousParsed: null,
      nextParsed: {
        ...previousParsed,
        fundamental_filters: filters,
      },
      userPrompt: "흑자 기업 중 순이익증가율 100% 이상인 종목",
    });

    expect(result.parsed.fundamental_filters).toEqual(filters);
  });

  it("백테스트 기간만 바꾸는 요청에서는 기존 진입/청산 조건을 유지한다", () => {
    // 백엔드가 권위 있게 병합해 내려주므로(요청 안 된 진입/청산·손절은 이전 값 그대로),
    // next는 기간만 바뀐 완전한 전략이다. 프론트는 그대로 신뢰한다.
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 7,
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
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [{ id: "ai_drop_model" }] },
        risk: {
          max_positions: 5,
          position_size_pct: 20,
          stop_loss_pct: 7,
          init_cash: 10000000,
        },
        period: "1y",
        options: { fee_rate: 0.015, slippage_rate: 0.05 },
      },
      userPrompt: "백테스트 1년만",
    });

    // 백엔드가 병합해 내려준 전략을 프론트가 그대로 신뢰한다(진입/청산/리스크/기간 보존).
    expect(result.parsed.entry_signals).toEqual(previousParsed.entry_signals);
    expect(result.parsed.exit_signals).toEqual(previousParsed.exit_signals);
    expect(result.parsed.stop_loss_pct).toBe(7);
    expect(result.parsed.backtest_period).toBe("1y");
    expect(result.backtestRequest?.entry?.conditions).toEqual([{ id: "ai_model" }]);
    expect(result.backtestRequest?.exit?.conditions).toEqual([{ id: "ai_drop_model" }]);
    expect(result.backtestRequest?.risk?.stop_loss_pct).toBe(7);
    expect(result.backtestRequest?.period).toBe("1y");
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

  it("'종목을 10개로 늘려줘'는 포트폴리오 변경으로 인식해 최대 종목 수를 반영한다", () => {
    // 백엔드가 권위 있게 병합해 내려주므로(요청 안 된 진입/청산 신호는 이전 값 유지),
    // next는 max_positions만 바뀐 완전한 전략이다. 프론트는 그대로 신뢰한다.
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        max_positions: 10,
      },
      previousBacktestRequest: {
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [{ id: "ai_drop_model" }] },
        risk: { max_positions: 5, position_size_pct: 20, init_cash: 10000000 },
        period: "5y",
      },
      nextBacktestRequest: {
        entry: { conditions: [{ id: "ai_model" }] },
        exit: { conditions: [{ id: "ai_drop_model" }] },
        risk: { max_positions: 10, position_size_pct: 10, init_cash: 10000000 },
        period: "5y",
      },
      userPrompt: "종목을 10개로 늘려줘",
    });
    expect(result.parsed.max_positions).toBe(10);
    // 진입/청산 조건은 이전 전략에서 그대로 유지(버려지지 않음).
    expect(result.parsed.entry_signals).toEqual(previousParsed.entry_signals);
    expect(result.parsed.exit_signals).toEqual(previousParsed.exit_signals);
    expect(result.backtestRequest?.entry?.conditions).toEqual([{ id: "ai_model" }]);
    expect(result.backtestRequest?.risk?.max_positions).toBe(10);
  });

  it("'최대 종목을 10게로 해줘'(개→게 오타)도 포트폴리오 변경으로 인식해 max_positions를 반영한다", () => {
    // 회귀: 백엔드는 max_positions=10을 올바로 추출하는데, 프론트 도메인 게이트가 '게' 오타를
    // 인식 못 해(portfolio 미감지) 백엔드 값을 버리고 이전 8을 유지하던 버그.
    const result = mergeStrategyModification({
      previousParsed: { ...previousParsed, max_positions: 8 },
      nextParsed: { ...previousParsed, max_positions: 10 },
      userPrompt: "최대 종목을 10게로 해줘",
    });
    expect(result.parsed.max_positions).toBe(10);
  });

  it("correctCountTypo는 숫자 뒤 '게'만 '개'로 보정하고 게임/게시 같은 단어는 보존한다", () => {
    expect(correctCountTypo("최대 종목을 10게로 해줘")).toBe("최대 종목을 10개로 해줘");
    expect(correctCountTypo("종목은 5게")).toBe("종목은 5개");
    expect(correctCountTypo("120게임 만들기")).toBe("120게임 만들기");
  });

  it("리스크 후속 수정은 백엔드 권위 병합 결과(기존 유니버스·손절 유지 + 트레일링 추가)를 반영한다", () => {
    // 백엔드가 요청 안 된 유니버스·손절·진입 신호를 이전 값으로 보존하고 트레일링만 추가해
    // 내려주므로, next가 이미 완전한 전략이다. 프론트는 그대로 신뢰한다.
    const result = mergeStrategyModification({
      previousParsed,
      nextParsed: {
        ...previousParsed,
        universe: ["KOSPI"],
        stop_loss_pct: 7,
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
        universe_id: "kospi",
        symbols: ["005930", "000660"],
        entry: { conditions: [{ id: "pbr" }] },
        exit: { conditions: [] },
        risk: {
          max_positions: 5,
          position_size_pct: 20,
          stop_loss_pct: 7,
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

  // 코치 맥락 답변("15%")→트레일링 귀속, "30%로 설정해줘"→익절 귀속 등 코치맥락 리스크 해석은
  // 백엔드로 이관했다(resolve_coach_context_risk, FR-STR-019e). 검증은 백엔드 유닛테스트
  // (test_nl_parser_overrides.test_resolve_coach_context_risk_*)가 담당한다.

  it("익절 비율만 명시한 요청은 이전 코치 문장에 트레일링 스탑이 있어도 트레일링 스탑을 설정하지 않는다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: null,
        trailing_stop_pct: null,
        hold_period_days: 126,
      },
      // 백엔드 환각 게이트가 요청 안 된 트레일링(LLM 환각)을 이전 값(null)으로 되돌려 내려준다.
      nextParsed: {
        ...previousParsed,
        stop_loss_pct: 12,
        take_profit_pct: 30,
        trailing_stop_pct: null,
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
          trailing_stop_pct: null,
          max_holding_days: 126,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "익절 비율을 30%로 설정해줘",
    });

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
    });
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
    });
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
    });
    expect(result.parsed.stop_loss_pct).toBe(10);
  });

  it("기존 트레일링 스탑이 있는 전략에서 익절만 바꾸면 기존 트레일링 스탑 값을 유지한다", () => {
    const result = mergeStrategyModification({
      previousParsed: {
        ...previousParsed,
        take_profit_pct: 20,
        trailing_stop_pct: 15,
      },
      // 백엔드 환각 게이트가 요청 안 된 트레일링을 이전 값(15)으로 되돌려 내려준다.
      nextParsed: {
        ...previousParsed,
        take_profit_pct: 30,
        trailing_stop_pct: 15,
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
          trailing_stop_pct: 15,
          init_cash: 10000000,
        },
        period: "5y",
      },
      userPrompt: "익절 30%로 바꿔줘",
    });

    expect(result.parsed.take_profit_pct).toBe(30);
    expect(result.parsed.trailing_stop_pct).toBe(15);
    expect(result.backtestRequest?.risk?.take_profit_pct).toBe(30);
    expect(result.backtestRequest?.risk?.trailing_stop_pct).toBe(15);
  });

  // "후속 개선 질문(수정 domain 없음)은 기존 전략 유지" 테스트는 제거했다 — 그런 프롬프트는
  // 상위 isAdvisorFollowUpPrompt가 병합 이전에 코치로 라우팅하므로 mergeStrategyModification에
  // 도달하지 않는다(아래 isAdvisorFollowUpPrompt describe에서 '어디를 개선 해볼까?'를 검증).

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
      risk: { init_cash: 10000000, stop_loss_pct: 10, take_profit_pct: 20, max_positions: 8 },
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
      "risk.stop_loss_pct": [2, 10, 25],
      "risk.take_profit_pct": [5, 20, 60],
      "risk.max_positions": [5, 8, 11],
      "entry.conditions.0.params.period": [9, 14, 19],
      "entry.conditions.0.params.value": [18, 30, 42],
      "entry.conditions.1.params.shortMA": [5, 10, 20, 60, 120],
      "entry.conditions.1.params.longMA": [5, 10, 20, 60, 120],
      "entry.conditions.2.params.value": [0.8, 1, 1.2],
      "exit.conditions.0.params.threshold": [42, 70, 80],
    });
    expect(ranges).not.toHaveProperty("entry.conditions.0.params.threshold");
    expect(ranges).not.toHaveProperty("exit.conditions.0.params.value");
    // 이동평균 단기/장기는 임의 정수가 아니라 실전 표준 일선(5/10/20/60/120)만 탐색한다.
    expect(ranges["entry.conditions.1.params.shortMA"]).toEqual(MA_CROSSOVER_PERIOD_VALUES);
    expect(ranges["entry.conditions.1.params.longMA"]).toEqual(MA_CROSSOVER_PERIOD_VALUES);

    expect(buildWalkForwardRequest(baseStrategy, settings, ranges)).toEqual({
      base_strategy: baseStrategy,
      ranges,
      ...settings,
      method: "bayesian",
    });

    expect(
      buildWalkForwardRequest(
        baseStrategy,
        {
          ...settings,
          parameter_steps: {
            PBR: 0.1,
            손절라인: 2,
            익절라인: 5,
            보유종목수: 1,
          },
          parameter_ranges: {
            PBR: {
              min: 0.9,
              max: 1.1,
              step: 0.2,
            },
          },
        },
        ranges
      )
    ).toEqual({
      base_strategy: baseStrategy,
      ranges: {
        ...ranges,
        "entry.conditions.2.params.value": { type: "number", min: 0.9, max: 1.1, step: 0.2 },
        "risk.stop_loss_pct": { type: "number", min: 2, max: 25, step: 2 },
        "risk.take_profit_pct": { type: "number", min: 5, max: 60, step: 5 },
        "risk.max_positions": { type: "number", min: 5, max: 11, step: 1 },
      },
      ...settings,
      method: "bayesian",
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

  it("이동평균 파라미터의 values 오버라이드는 min/max/step 스펙이 아니라 고정 리스트로 전달된다", () => {
    const baseStrategy = {
      symbols: ["005930"],
      entry: {
        conditions: [{ id: "ma_crossover", params: { shortMA: 5, longMA: 20 } }],
      },
      risk: {},
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

    const request = buildWalkForwardRequest(
      baseStrategy,
      {
        ...settings,
        parameter_ranges: {
          "entry.conditions.0.params.longMA": { min: 5, max: 120, step: 0, values: [20, 60, 120] },
        },
      },
      ranges
    );

    expect(request.ranges["entry.conditions.0.params.longMA"]).toEqual([20, 60, 120]);
    // 오버라이드 없는 shortMA는 자동 생성 기본값(전체 5개)이 그대로 유지된다.
    expect(request.ranges["entry.conditions.0.params.shortMA"]).toEqual(MA_CROSSOVER_PERIOD_VALUES);
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

  it("백테스트 결과 해석·평가 요청은 재파싱이 아니라 follow-up으로 분류한다", () => {
    // [회귀] '백테스트' 도메인 단어가 있어도 결과 질문은 전략 수정이 아니다.
    expect(isAdvisorFollowUpPrompt("백테스트 결과가 왜 이렇게 나빠?")).toBe(true);
    expect(isAdvisorFollowUpPrompt("결과 해석해줘")).toBe(true);
    expect(isAdvisorFollowUpPrompt("성과 평가해줘")).toBe(true);
    expect(isAdvisorFollowUpPrompt("MDD가 큰 원인이 뭐야")).toBe(true);
  });

  it("결과 질문 어휘가 있어도 수정 동사가 붙으면 수정 흐름으로 남는다", () => {
    expect(isAdvisorFollowUpPrompt("분석해 보게 손절 10% 추가해줘")).toBe(false);
  });
});

describe("buildStrategyHorizonComparisonResponse", () => {
  it.each([
    "단기 전략 장기 전략 뭐가 좋을까?",
    "단타와 장투의 차이를 설명해줘",
    "짧게 거래하는 것과 오래 보유하는 것을 비교해줘",
  ])("단기·장기 비교 질문에는 객관적인 차이를 설명한다: %s", (prompt) => {
    const response = buildStrategyHorizonComparisonResponse(prompt);

    expect(response).toContain("연구할 보유기간과 거래 빈도 가정이 다릅니다");
    expect(response).toContain("수수료·슬리피지");
    expect(response).toContain("장기간의 변동성과 최대 낙폭");
    expect(response).toContain("보유기간(며칠 또는 몇 개월)과 진입 조건");
  });

  it("비교가 아닌 구체적인 전략 생성 요청은 기존 흐름을 유지한다", () => {
    expect(buildStrategyHorizonComparisonResponse("단기 전략을 만들어줘")).toBeNull();
    expect(buildStrategyHorizonComparisonResponse("장기 전략을 만들어줘")).toBeNull();
    expect(buildStrategyHorizonComparisonResponse("단기와 장기 전략을 각각 만들어줘")).toBeNull();
  });
});

describe("buildTakeProfitPercentagePrompt", () => {
  const percentagePrompt = {
    message: "익절 기준은 매수가 대비 수익률로 설정합니다. 예시 값은 5%, 10%, 15%입니다. 적용할 익절 기준을 몇 %로 할까요?",
    suggestions: ["익절 5%", "익절 10%", "익절 15%"],
  };

  it.each([
    "익절을 추가해 볼까?",
    "익절도 해볼까?",
    "익절 기준은 어떻게 잡지?",
    "목표 수익률을 정해보자",
    "익절 조건이 필요할 것 같아",
    "이익이 나면 일정 비율에서 팔고 싶어",
  ])("표현 방식과 무관하게 비율 없는 익절 설정 의도에 질문을 반환한다: %s", (prompt) => {
    expect(buildTakeProfitPercentagePrompt(prompt)).toEqual(percentagePrompt);
  });

  it.each([
    "익절 10%를 추가해줘",
    "익절을 빼줘",
    "익절이 뭐야?",
    "현재 전략에 익절이 있어?",
    "익절이 왜 적용 안 돼?",
    "익절 결과를 분석해줘",
  ])("숫자 지정·삭제·정보 요청은 기존 흐름을 유지한다: %s", (prompt) => {
    expect(buildTakeProfitPercentagePrompt(prompt)).toBeNull();
  });
});

describe("buildFundamentalFactorPrompt", () => {
  it.each([
    ["영업이익률을 추가해 볼까?", "영업이익률 몇% 이상일 때 진입할까요?", "영업이익률 15% 이상"],
    ["PER도 넣자", "PER 몇배 이하일 때 진입할까요?", "PER 10배 이하"],
    ["배당수익률도 추가해줘", "배당수익률 몇% 이상일 때 진입할까요?", "배당수익률 3% 이상"],
    ["시가총액 조건 넣어줘", "시가총액 몇억 이상일 때 진입할까요?", "시가총액 1조 이상"],
  ])("값 없는 재무 팩터 추가에 추천 칩과 함께 되묻는다: %s", (prompt, message, chip) => {
    const result = buildFundamentalFactorPrompt(prompt);
    expect(result?.message).toBe(message);
    expect(result?.suggestions).toContain(chip);
  });

  it("배당성향/배당성장률을 배당수익률보다 먼저 잡는다", () => {
    expect(buildFundamentalFactorPrompt("배당성향도 추가")?.message).toContain("배당성향");
    expect(buildFundamentalFactorPrompt("배당성장률도 넣자")?.message).toContain("배당성장률");
  });

  it.each([
    "영업이익률 15% 이상 추가해줘", // 값이 이미 있음 → 수정 파싱으로
    "영업이익률이 뭐야?", // 정의 질문
    "영업이익률을 빼줘", // 제거
    "영업이익률이 왜 반영 안 돼?", // 분석 질문
    "손절을 추가해 볼까?", // 재무 팩터 아님
  ])("숫자 지정·정의·제거·비재무는 null을 반환한다: %s", (prompt) => {
    expect(buildFundamentalFactorPrompt(prompt)).toBeNull();
  });
});

describe("buildWalkForwardParameterRanges — 엔진 파라미터 화이트리스트", () => {
  it("MACD·볼린저·스토캐스틱의 엔진 파라미터를 탐색 공간에 포함한다", () => {
    const ranges = buildWalkForwardParameterRanges({
      symbols: ["005930"],
      entry: {
        conditions: [
          { id: "bollinger_bands", params: { period: 20, stdDev: 2 } },
          { id: "macd", params: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 } },
          { id: "stochastic", params: { period: 9, value: 20 } }, // crossover 모드 → value 미사용
        ],
      },
      risk: { init_cash: 10000000 },
    });

    expect(Object.keys(ranges).sort()).toEqual([
      "entry.conditions.0.params.period",
      "entry.conditions.0.params.stdDev",
      "entry.conditions.1.params.fastPeriod",
      "entry.conditions.1.params.signalPeriod",
      "entry.conditions.1.params.slowPeriod",
      "entry.conditions.2.params.period",
    ]);
    expect(ranges["entry.conditions.0.params.stdDev"]).toEqual([1.5, 2, 2.5]);
    // crossover 모드 스토캐스틱의 value(엔진 미사용)는 여전히 제외
    expect(ranges).not.toHaveProperty("entry.conditions.2.params.value");
  });

  it("전략에 실제 포함된 지표의 엔진 파라미터만 추출한다 (EMA 듀얼·브레이크아웃·스토캐스틱 level)", () => {
    const ranges = buildWalkForwardParameterRanges({
      symbols: ["005930"],
      entry: {
        conditions: [
          { id: "ema", params: { shortPeriod: 10, longPeriod: 50 } },
          { id: "breakout", params: { lookbackPeriod: 20 } },
          { id: "stochastic", params: { mode: "level", value: 20 } },
        ],
      },
      exit: {
        conditions: [{ id: "ema", params: { period: 20, signalType: "sell" } }],
      },
      risk: { init_cash: 10000000 },
    });

    expect(Object.keys(ranges).sort()).toEqual([
      "entry.conditions.0.params.longPeriod",
      "entry.conditions.0.params.shortPeriod",
      "entry.conditions.1.params.lookbackPeriod",
      "entry.conditions.2.params.value",
      "exit.conditions.0.params.period",
    ]);
  });

  it("알 수 없는 조건 id는 탐색 공간에 넣지 않는다", () => {
    const ranges = buildWalkForwardParameterRanges({
      symbols: ["005930"],
      entry: { conditions: [{ id: "unknown_indicator", params: { period: 14, value: 30 } }] },
      risk: { init_cash: 10000000 },
    });

    expect(ranges).toEqual({});
  });
});

describe("buildWalkForwardRequest — 사용자 범위·제외·명시적 분할", () => {
  const baseStrategy = {
    symbols: ["005930"],
    entry: {
      conditions: [{ type: "filter", id: "pbr", params: { value: 1, operator: "<=" } }],
    },
    risk: { init_cash: 10000000, stop_loss_pct: 10 },
  };
  const settings = {
    n_splits: 4,
    train_pct: 0.7,
    anchor: false,
    target_metric: "cagr",
    n_trials: 30,
  };

  it("symbols가 없는 저장 DSL은 빈 배열로 채운다 (백엔드 필수 필드 — 422 회귀 방지)", () => {
    // 저장된 전략 DSL(Strategy.settings)에는 symbols가 없어(universe_id만 저장)
    // 그대로 보내면 pydantic 422("base_strategy.symbols: Field required")가 나던 회귀 케이스.
    const { symbols: _symbols, ...withoutSymbols } = baseStrategy;
    const ranges = buildWalkForwardParameterRanges(withoutSymbols);

    const request = buildWalkForwardRequest(withoutSymbols, settings, ranges);

    expect(request.base_strategy.symbols).toEqual([]);
    // symbols가 이미 있으면 그대로 유지한다.
    expect(buildWalkForwardRequest(baseStrategy, settings, ranges).base_strategy.symbols).toEqual(["005930"]);
  });

  it("자동 생성 범위를 벗어난 사용자 오버라이드도 그대로 반영한다 (클램프 없음)", () => {
    const ranges = buildWalkForwardParameterRanges(baseStrategy);
    // 자동 범위는 PBR=1 주변 [0.8, 1, 1.2]지만 사용자는 0.5~3.0을 원한다
    const request = buildWalkForwardRequest(
      baseStrategy,
      { ...settings, parameter_ranges: { PBR: { min: 0.5, max: 3.0, step: 0.25 } } },
      ranges
    );

    expect(request.ranges["entry.conditions.0.params.value"]).toEqual({
      type: "number",
      min: 0.5,
      max: 3.0,
      step: 0.25,
    });
  });

  it("excluded_parameters로 지정한 라벨의 범위는 요청에서 제거된다", () => {
    const ranges = buildWalkForwardParameterRanges(baseStrategy);
    expect(ranges).toHaveProperty("risk.stop_loss_pct");

    const request = buildWalkForwardRequest(
      baseStrategy,
      { ...settings, excluded_parameters: ["손절라인"] },
      ranges
    );

    expect(request.ranges).not.toHaveProperty("risk.stop_loss_pct");
    expect(request.ranges).toHaveProperty("entry.conditions.0.params.value");
  });

  it("is_bars/oos_bars 설정을 백엔드 요청에 그대로 전달한다", () => {
    const ranges = buildWalkForwardParameterRanges(baseStrategy);
    const request = buildWalkForwardRequest(
      baseStrategy,
      { ...settings, is_bars: 504, oos_bars: 126 },
      ranges
    );

    expect(request.is_bars).toBe(504);
    expect(request.oos_bars).toBe(126);
  });
});

describe("buildWalkForwardParameterDescriptors — path 기반 파라미터 칩", () => {
  it("MACD·볼린저·리스크 파라미터를 한글 라벨과 경로로 노출한다", () => {
    const baseStrategy = {
      symbols: ["005930"],
      entry: {
        conditions: [
          { id: "macd", params: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 } },
          { id: "bollinger_bands", params: { period: 20, stdDev: 2 } },
          { type: "filter", id: "pbr", params: { value: 1 } },
        ],
      },
      risk: { init_cash: 10000000, stop_loss_pct: 10 },
    };

    const descriptors = buildWalkForwardParameterDescriptors(baseStrategy);
    const byPath = Object.fromEntries(descriptors.map((d) => [d.path, d.label]));

    expect(byPath).toEqual({
      "risk.stop_loss_pct": "손절라인",
      "entry.conditions.0.params.fastPeriod": "MACD 단기",
      "entry.conditions.0.params.slowPeriod": "MACD 장기",
      "entry.conditions.0.params.signalPeriod": "MACD 시그널",
      "entry.conditions.1.params.period": "볼린저 기간",
      "entry.conditions.1.params.stdDev": "볼린저 표준편차",
      "entry.conditions.2.params.value": "PBR",
    });
  });

  it("진입/청산에 같은 지표가 있으면 라벨에 구간을 붙여 구분한다", () => {
    const baseStrategy = {
      symbols: ["005930"],
      entry: { conditions: [{ id: "rsi", params: { period: 14, value: 30 } }] },
      exit: { conditions: [{ id: "rsi", params: { period: 14, value: 70, signalType: "sell" } }] },
      risk: { init_cash: 10000000 },
    };

    const labels = buildWalkForwardParameterDescriptors(baseStrategy).map((d) => d.label);
    expect(labels).toContain("RSI 기간 (진입)");
    expect(labels).toContain("RSI 기간 (청산)");
    expect(labels).toContain("RSI 기준값 (진입)");
    expect(labels).toContain("RSI 기준값 (청산)");
  });

  it("path 키 오버라이드·제외가 정확히 해당 경로에만 적용된다", () => {
    const baseStrategy = {
      symbols: ["005930"],
      entry: {
        conditions: [{ id: "macd", params: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 } }],
      },
      risk: { init_cash: 10000000, stop_loss_pct: 10 },
    };
    const ranges = buildWalkForwardParameterRanges(baseStrategy);
    const settings = {
      n_splits: 4,
      train_pct: 0.7,
      anchor: false,
      target_metric: "cagr",
      n_trials: 30,
      parameter_ranges: {
        "entry.conditions.0.params.fastPeriod": { min: 5, max: 20, step: 1 },
      },
      excluded_parameters: ["risk.stop_loss_pct"],
    };

    const request = buildWalkForwardRequest(baseStrategy, settings, ranges);

    expect(request.ranges["entry.conditions.0.params.fastPeriod"]).toEqual({
      type: "number",
      min: 5,
      max: 20,
      step: 1,
    });
    // 다른 MACD 경로는 오버라이드의 영향을 받지 않는다
    expect(Array.isArray(request.ranges["entry.conditions.0.params.slowPeriod"])).toBe(true);
    expect(request.ranges).not.toHaveProperty("risk.stop_loss_pct");
  });
});
