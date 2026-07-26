import { describe, expect, it } from "vitest";

import {
  decideConversationTurn,
  getModificationClarification,
  needsEntrySignalClarification,
  parseHoldingPeriodDays,
  parseMetricOptimizationRange,
  resolveStrategyAssumptions,
  type ConversationContext,
} from "./conversationDecision";

const baseContext: ConversationContext = {
  stage: "idle",
  hasBacktestRequest: false,
  hasCurrentStrategy: false,
  builderMode: false,
  lastCoachText: null,
};

describe("decideConversationTurn", () => {
  it("parses conversational optimization ranges", () => {
    expect(parseMetricOptimizationRange("5 ~ 20")).toEqual({
      type: "number",
      min: 5,
      max: 20,
      step: 2,
    });
    expect(parseMetricOptimizationRange("0.5부터 2.5")).toEqual({
      type: "number",
      min: 0.5,
      max: 2.5,
      step: 0.2,
    });
    expect(parseMetricOptimizationRange("20 ~ 5")).toBeNull();
    expect(parseMetricOptimizationRange("범위를 모르겠어")).toBeNull();
  });

  it("starts the builder with an explicit Sharpe research objective", () => {
    expect(decideConversationTurn("샤프지수를 최대화할 수 있는 전략을 만들어줘", baseContext)).toMatchObject({
      action: "start_builder",
      reason: "research_metric_selected",
      researchMetric: "sharpe",
      seedPrompt: expect.stringContaining("과거 데이터 연구 목표: 샤프 지수"),
    });
  });

  it("asks for one objective before starting broad metric research", () => {
    const prompt = "위험 조정 성과 지표를 기준으로 전략을 만들고 싶어";
    expect(decideConversationTurn(prompt, baseContext)).toMatchObject({
      action: "ask_research_metric",
      reason: "research_metric_required",
      strategyPrompt: prompt,
      suggestions: ["샤프 지수", "소르티노 지수", "칼마 비율", "트레이너 지수 (현재 계산 불가)"],
    });

    expect(decideConversationTurn("소르티노 지수", {
      ...baseContext,
      pendingResearchMetricPrompt: prompt,
    })).toMatchObject({
      action: "start_builder",
      researchMetric: "sortino",
      seedPrompt: expect.stringContaining("과거 데이터 연구 목표: 소르티노 지수"),
    });
  });

  it("explains why Treynor is unavailable and keeps the metric step open", () => {
    expect(decideConversationTurn("트레이너 지수를 최대화하는 전략을 만들어줘", baseContext)).toMatchObject({
      action: "ask_research_metric",
      reason: "treynor_metric_unavailable",
      message: expect.stringContaining("시장 벤치마크와 전략 베타 데이터가 필요"),
      suggestions: ["샤프 지수", "소르티노 지수", "칼마 비율"],
    });
  });

  it("does not intercept a metric definition question", () => {
    expect(decideConversationTurn("샤프 지수가 뭐야?", baseContext)).toMatchObject({
      action: "classify",
    });
  });

  it("responds to an invalid backtest period before semantic routing", () => {
    const decision = decideConversationTurn("백테스트를 6개월로 돌려줘", baseContext);

    expect(decision).toMatchObject({
      action: "respond",
      speechAct: "modify",
      topic: "backtest",
      confidence: 1,
      reason: "backtest_period_below_minimum",
    });
  });

  it("runs a ready backtest only after a matching confirmation prompt", () => {
    const decision = decideConversationTurn("네", {
      ...baseContext,
      stage: "ready",
      hasBacktestRequest: true,
      lastCoachText: "현재 상태로도 백테스트를 실행할 수 있습니다. 백테스트를 시작할까요?",
    });

    expect(decision).toMatchObject({
      action: "run_backtest",
      speechAct: "confirm",
      topic: "backtest",
      reason: "confirmed_backtest_prompt",
    });
  });

  it("answers a strategy-horizon comparison instead of starting the builder", () => {
    const decision = decideConversationTurn("단타와 장투 중 뭐가 나아?", baseContext);

    expect(decision).toMatchObject({
      action: "respond",
      speechAct: "compare",
      topic: "strategy",
      reason: "strategy_horizon_comparison",
    });
  });

  it("classifies a long-horizon request before choosing a strategy action", () => {
    const decision = decideConversationTurn("장기전략으로 만들어 볼까?", baseContext);

    expect(decision).toMatchObject({
      action: "classify",
      reason: "requires_semantic_classification",
    });
  });

  it("asks for a long holding period before parsing", () => {
    const decision = decideConversationTurn("장기전략으로 만들어 볼까?", baseContext, {
      intent: "STRATEGY_ADVICE",
    });

    expect(decision).toEqual({
      action: "ask_holding_period",
      speechAct: "ask",
      topic: "risk",
      confidence: 1,
      reason: "long_holding_period_required",
      message: "바이 앤 홀드 전략으로 이해했어요. 얼마나 오래 보유할까요?",
      suggestions: [
        "252거래일 (1년)",
        "504거래일 (2년)",
        "756거래일 (3년)",
        "1,260거래일 (5년)",
        "직접 입력",
      ],
      strategyPrompt: "장기전략으로 만들어 볼까?",
      holdingHorizon: "long",
    });
  });

  it("asks for a short holding period before parsing", () => {
    const decision = decideConversationTurn("단기 투자 전략을 만들어보자", baseContext, {
      intent: "STRATEGY_ADVICE",
    });

    expect(decision).toEqual({
      action: "ask_holding_period",
      speechAct: "ask",
      topic: "risk",
      confidence: 1,
      reason: "short_holding_period_required",
      message: "단기 매매 전략으로 이해했어요. 얼마나 오래 보유할까요?",
      suggestions: [
        "1거래일 (당일)",
        "5거래일 (1주)",
        "10거래일 (2주)",
        "20거래일 (약 1개월)",
        "60거래일 (약 3개월)",
        "직접 입력",
      ],
      strategyPrompt: "단기 투자 전략을 만들어보자",
      holdingHorizon: "short",
    });
  });

  it("parses a named-stock strategy even when classification returns STOCK_PICK", () => {
    const decision = decideConversationTurn(
      "삼성전자에 투자 하는 전략",
      baseContext,
      {
        intent: "STOCK_PICK",
        symbol: "005930",
      },
    );

    expect(decision).toMatchObject({
      action: "parse_strategy",
      reason: "named_stock_strategy_request",
      strategyPrompt: "삼성전자에 투자 하는 전략",
    });
  });

  it("preserves an active strategy when semantic classification is ambiguous", () => {
    const decision = decideConversationTurn("장기전략으로 만들어 볼까?", {
      ...baseContext,
      hasCurrentStrategy: true,
    }, {
      intent: "STRATEGY_PICK",
    });

    expect(decision).toMatchObject({
      action: "ask_holding_period",
      reason: "long_holding_period_required",
    });
  });

  it("continues the original strategy after a holding period is selected", () => {
    const decision = decideConversationTurn("504거래일 (2년)", {
      ...baseContext,
      pendingHoldingPeriodPrompt: "장기전략으로 만들어 볼까?",
      pendingHoldingPeriodHorizon: "long",
    });

    expect(decision).toEqual({
      action: "start_builder",
      speechAct: "create",
      topic: "strategy",
      confidence: 1,
      reason: "holding_period_selected",
      seedPrompt: "장기전략으로 만들어 볼까?",
      strategyAssumptions: { holdingPeriodDays: 504 },
    });
  });

  it("keeps asking when a long holding period is below one year", () => {
    const decision = decideConversationTurn("126거래일", {
      ...baseContext,
      pendingHoldingPeriodPrompt: "장기전략으로 만들어 볼까?",
      pendingHoldingPeriodHorizon: "long",
    });

    expect(decision).toMatchObject({
      action: "ask_holding_period",
      reason: "long_holding_period_still_missing",
      message: "장기 보유기간은 252거래일 이상으로 입력해 주세요. 얼마나 오래 보유할까요?",
    });
  });

  it("continues the original short strategy after a valid holding period is selected", () => {
    const decision = decideConversationTurn("10거래일 (2주)", {
      ...baseContext,
      pendingHoldingPeriodPrompt: "단기 투자 전략을 만들어보자",
      pendingHoldingPeriodHorizon: "short",
    });

    expect(decision).toEqual({
      action: "start_builder",
      speechAct: "create",
      topic: "strategy",
      confidence: 1,
      reason: "holding_period_selected",
      seedPrompt: "단기 투자 전략을 만들어보자",
      strategyAssumptions: { holdingPeriodDays: 10 },
    });
  });

  it("keeps asking when a short holding period is outside the short range", () => {
    const decision = decideConversationTurn("252거래일", {
      ...baseContext,
      pendingHoldingPeriodPrompt: "단기 투자 전략을 만들어보자",
      pendingHoldingPeriodHorizon: "short",
    });

    expect(decision).toMatchObject({
      action: "ask_holding_period",
      reason: "short_holding_period_still_missing",
      message: "단기 보유기간은 1~251거래일로 입력해 주세요. 얼마나 오래 보유할까요?",
      holdingHorizon: "short",
    });
  });

  it("continues an active builder instead of resetting it for a long-horizon request", () => {
    const decision = decideConversationTurn("장기 전략으로 해줘", {
      ...baseContext,
      builderMode: true,
    });

    expect(decision).toMatchObject({
      action: "continue_builder",
      reason: "active_builder_session",
    });
  });

  it("does not infer a builder action from a long-horizon knowledge question", () => {
    const decision = decideConversationTurn("장기 전략이 뭐야?", baseContext);

    expect(decision).toMatchObject({
      action: "classify",
      reason: "requires_semantic_classification",
    });
  });

  it("keeps an active builder session ahead of modification clarification", () => {
    const decision = decideConversationTurn("익절도 해볼까?", {
      ...baseContext,
      hasCurrentStrategy: true,
      builderMode: true,
    });

    expect(decision).toMatchObject({
      action: "continue_builder",
      reason: "active_builder_session",
    });
  });

  it("asks which entry signal to use instead of reparsing an underspecified change", () => {
    const decision = decideConversationTurn("진입 신호를 바꾸고 싶어", {
      ...baseContext,
      hasCurrentStrategy: true,
    });

    expect(decision).toEqual({
      action: "respond",
      speechAct: "modify",
      topic: "strategy",
      confidence: 1,
      reason: "missing_entry_signal_definition",
      message: "어떤 진입 신호로 변경할까요? 아래 옵션을 선택하거나 원하는 조건을 직접 입력해 주세요.",
      suggestions: [
        "진입 신호를 5일·20일 이동평균 골든크로스로 변경",
        "진입 신호를 RSI 30 이하 반등으로 변경",
        "진입 신호를 20일 신고가 돌파로 변경",
        "진입 신호를 MACD 골든크로스로 변경",
        "직접 입력",
      ],
    });
  });

  it("clarifies a value-less fundamental factor add instead of a coach follow-up", () => {
    // 스크린샷 회귀: "영업이익률을 추가해 볼까?"가 물음표 때문에 answer_follow_up으로 새어
    // 조용히 넘어가던 것 — 이제 그 지표 기준을 추천 칩으로 되묻는다.
    const decision = decideConversationTurn("영업이익률을 추가해 볼까?", {
      ...baseContext,
      hasCurrentStrategy: true,
    });
    expect(decision).toMatchObject({
      action: "respond",
      speechAct: "modify",
      reason: "missing_fundamental_threshold",
    });
    expect(decision.action === "respond" ? decision.suggestions : []).toEqual(
      expect.arrayContaining(["영업이익률 15% 이상", "직접 입력"]),
    );
  });

  it("does not re-clarify a fundamental factor add that already has a threshold", () => {
    // 추천 칩("영업이익률 15% 이상") 클릭 시 값이 붙어 오므로 되묻지 않고 수정 파싱으로 흐른다.
    const decision = decideConversationTurn("영업이익률 15% 이상", {
      ...baseContext,
      hasCurrentStrategy: true,
    });
    expect(decision.reason).not.toBe("missing_fundamental_threshold");
  });

  it("keeps the active builder ahead of entry-signal clarification", () => {
    expect(decideConversationTurn("매수 조건을 변경해줘", {
      ...baseContext,
      hasCurrentStrategy: true,
      builderMode: true,
    })).toMatchObject({
      action: "continue_builder",
      reason: "active_builder_session",
    });
  });

  it.each([
    ["유니버스를 바꾸고 싶어", "missing_universe_definition", "유니버스를 KOSPI200으로 변경"],
    ["청산 신호를 변경해줘", "missing_exit_signal_definition", "청산 신호를 RSI 70 이상으로 변경"],
    ["포트폴리오를 수정하고 싶어", "missing_portfolio_definition", "최대 5종목으로 변경"],
    ["리스크 옵션을 보여줘", "missing_risk_definition", "손절을 10%로 변경"],
    ["리스트를 바꾸고 싶어", "missing_risk_definition", "MDD 20% 한도로 변경"],
  ])("clarifies an underspecified strategy section: %s", (prompt, reason, suggestion) => {
    const decision = decideConversationTurn(prompt, {
      ...baseContext,
      hasCurrentStrategy: true,
    });
    expect(decision).toMatchObject({ action: "respond", speechAct: "modify", reason });
    expect(decision.action === "respond" ? decision.suggestions : []).toEqual(
      expect.arrayContaining([suggestion, "직접 입력"]),
    );
  });

  it("clarifies a missing take-profit percentage for an active strategy", () => {
    const decision = decideConversationTurn("이익이 나면 일정 비율에서 팔고 싶어", {
      ...baseContext,
      hasCurrentStrategy: true,
    });

    expect(decision).toMatchObject({
      action: "respond",
      speechAct: "modify",
      topic: "risk",
      reason: "missing_take_profit_percentage",
      suggestions: ["익절 5%", "익절 10%", "익절 15%", "직접 입력"],
    });
  });

  it("delegates unresolved input to semantic classification", () => {
    expect(decideConversationTurn("PER 10 이하 전략을 만들어줘", baseContext)).toEqual({
      action: "classify",
      speechAct: "unknown",
      topic: "unknown",
      confidence: 0,
      reason: "requires_semantic_classification",
    });
  });

  it("routes an open onboarding request to the builder after classification", () => {
    expect(decideConversationTurn("어떻게 시작하지?", baseContext, {
      intent: "ONBOARDING",
    })).toMatchObject({
      action: "start_builder",
      reason: "classified_onboarding",
      seedPrompt: "어떻게 시작하지?",
    });
  });

  it("routes general knowledge to the general answer path", () => {
    expect(decideConversationTurn("RSI가 뭐야?", baseContext, {
      intent: "GENERAL_INVESTMENT",
    })).toMatchObject({
      action: "answer_general",
      reason: "classified_general_investment",
    });
  });

  it("uses entry and exit examples only for a single-stock analysis request", () => {
    const decision = decideConversationTurn("삼성전자 언제 사야 하지?", baseContext, {
      intent: "STOCK_ANALYSIS",
      symbol: "005930",
      suggestedReply:
        "PBR은 낮고 ROE는 높은 저평가 우량주를 고르는 가치 전략",
    });

    expect(decision).toMatchObject({
      action: "respond_stock",
      reason: "classified_stock_analysis",
      message: expect.stringContaining("5일 이동평균이 20일 이동평균을 상향 돌파"),
    });
    const message = decision.action === "respond_stock" ? decision.message : "";
    expect(message).toContain("RSI가 30 이하");
    expect(message).not.toContain("저평가 우량주를 고르는");
    expect(message).not.toContain("상위 5종목");
  });

  // 회귀(2026-07-26): 테마 유니버스 전략 진행 중 "제주반도체도 추가해줘"가 STOCK_ANALYSIS로
  // 분류돼 종목 추천 불가 canned 안내에 삼켜졌다 — 전략이 활성이면 종목명이 있어도 백엔드
  // 파싱(LLM 해석)으로 보내야 한다.
  it("routes STOCK_ANALYSIS with a symbol to strategy parsing during an active strategy", () => {
    const decision = decideConversationTurn("제주반도체도 추가해줘", {
      ...baseContext,
      hasCurrentStrategy: true,
    }, {
      intent: "STOCK_ANALYSIS",
      symbol: "080220",
    });

    expect(decision).toMatchObject({
      action: "parse_strategy",
      speechAct: "modify",
      reason: "preserve_active_strategy",
      strategyPrompt: "제주반도체도 추가해줘",
    });
  });

  // 회귀: 전략이 이미 있어도 정의형 질문("pbr이 뭐야?")은 수정 파싱이 아니라 지식 답변
  // 경로로 가야 한다 — 수정 파싱으로 흘리면 무변경 전략 요약만 다시 렌더링됐다.
  it("routes general knowledge to the general answer path even with an active strategy", () => {
    expect(decideConversationTurn("pbr이 뭐야?", {
      ...baseContext,
      hasCurrentStrategy: true,
    }, {
      intent: "GENERAL_INVESTMENT",
    })).toMatchObject({
      action: "answer_general",
      reason: "classified_general_investment",
    });
  });

  it("keeps UNKNOWN with an active strategy on the strategy parse path", () => {
    expect(decideConversationTurn("손절은 그냥 두고 진행해줘", {
      ...baseContext,
      hasCurrentStrategy: true,
    }, {
      intent: "UNKNOWN",
    })).toMatchObject({
      action: "parse_strategy",
      reason: "classified_strategy_input",
    });
  });

  it("answers active-strategy follow-up questions without classification", () => {
    expect(decideConversationTurn("어디를 개선해 볼까?", {
      ...baseContext,
      hasCurrentStrategy: true,
    })).toMatchObject({
      action: "answer_follow_up",
      reason: "active_strategy_follow_up",
    });
  });
});

describe("resolveStrategyAssumptions", () => {
  it.each([
    ["단기 전략으로 구성해줘", { holdingHorizon: "short" }],
    ["중기 투자 전략을 만들자", { holdingHorizon: "medium", holdingPeriodDays: 63 }],
    ["오래 보유하는 전략으로 해줘", { holdingHorizon: "long" }],
  ])("normalizes qualitative holding horizons: %s", (prompt, assumptions) => {
    expect(resolveStrategyAssumptions(prompt)).toEqual(assumptions);
  });

  it("does not override an explicit holding period", () => {
    const prompt = "장기 전략으로 2년 동안 보유해줘";
    expect(resolveStrategyAssumptions(prompt)).toEqual({});
  });

  it("does not choose a holding period when multiple horizons are compared", () => {
    const prompt = "단기와 장기 전략을 비교해줘";
    expect(resolveStrategyAssumptions(prompt)).toEqual({});
  });

  it("does not treat moving-average terminology as a holding horizon", () => {
    const prompt = "장기 이동평균선 위에서 매수하는 전략을 만들어줘";
    expect(resolveStrategyAssumptions(prompt)).toEqual({});
  });
});

describe("needsEntrySignalClarification", () => {
  it.each([
    "진입 신호를 바꾸고 싶어",
    "매수 조건을 변경해줘",
    "엔트리 옵션을 보여줘",
  ])("detects an underspecified entry-signal change: %s", (prompt) => {
    expect(needsEntrySignalClarification(prompt)).toBe(true);
  });

  it.each([
    "진입 신호를 RSI 30 이하 반등으로 바꿔줘",
    "매수 조건은 20일 신고가 돌파로 변경",
    "진입 신호는 그대로 유지해줘",
    "진입 신호를 삭제해줘",
  ])("does not intercept a concrete or explicit entry-signal request: %s", (prompt) => {
    expect(needsEntrySignalClarification(prompt)).toBe(false);
  });
});

describe("getModificationClarification", () => {
  it.each([
    "유니버스를 KOSDAQ으로 변경",
    "청산 신호를 RSI 70 이상으로 변경",
    "포트폴리오를 최대 8종목으로 변경",
    "리스크 손절을 12%로 변경",
    "청산 신호는 그대로 유지",
  ])("does not intercept a concrete section change: %s", (prompt) => {
    expect(getModificationClarification(prompt)).toBeNull();
  });

  it("does not clarify a vague section change before a strategy exists", () => {
    expect(decideConversationTurn("유니버스를 바꾸고 싶어", baseContext)).toMatchObject({
      action: "classify",
    });
  });

  it.each([
    "조건을 변경 할 수 있어?",
    "조건을 변경 하고 싶어",
    "설정을 바꿀 수 있나요?",
  ])("asks which condition to change when no target is named: %s", (prompt) => {
    expect(getModificationClarification(prompt)).toMatchObject({
      area: "condition",
      reason: "missing_condition_target",
    });
  });

  it("routes an area-scoped condition change to that area's clarification", () => {
    expect(getModificationClarification("청산 조건을 바꾸고 싶어")).toMatchObject({
      area: "exit_signal",
    });
  });

  // [사용자 결정 2026-07-26] 구체 종목명 없는 종목 교체 의향은 칩 없이 채팅 입력만
  // 안내한다 — 수정 파싱으로 흘리면 무변경 재렌더링+다음 조건 질문으로 흐름이 끊긴다.
  it.each([
    "종목을 변경 할 수 있나?",
    "종목을 교체 할 수 있나?",
    "종목 바꿀 수 있어?",
    "다른 종목으로 하고 싶어",
  ])("invites a chat reply for a symbols-change intent without a target: %s", (prompt) => {
    const clarification = getModificationClarification(prompt);
    expect(clarification).toMatchObject({
      area: "universe",
      reason: "missing_target_symbols_change",
    });
    expect(clarification!.suggestions).toEqual([]);
  });

  it.each([
    "종목을 삼성전자로 바꿔줘", // 구체 종목명 — 어미 인접성이 깨져 수정 파싱으로 통과
    "종목을 코스닥 걸로 바꿔줘", // 시장 언급 — 수정 파싱이 유니버스 전환 처리
    "현대약품은 빼줘", // 제거 발화 — keep/remove 게이트로 수정 파싱 통과
    "최대 8종목으로 변경", // 종목 수 값 칩 — 백엔드 결정론 fast-path 도달
  ])("does not intercept a concrete symbols change: %s", (prompt) => {
    expect(getModificationClarification(prompt)).toBeNull();
  });

  // 백엔드 계약(test_nl_parser_overrides.py)의 전제: 영역 선택 칩은 재전송 시 여기서
  // 다시 가로채져 백엔드 수정 파싱에 도달하지 않는다.
  it.each([
    ["진입 신호 변경", "entry_signal"],
    ["청산 신호 변경", "exit_signal"],
    ["유니버스 변경", "universe"],
    ["포트폴리오 설정 변경", "portfolio"],
    ["리스크 설정 변경", "risk"],
  ])("re-intercepts the area chip %s into the %s clarification", (chip, area) => {
    expect(getModificationClarification(chip)).toMatchObject({ area });
  });

  it.each([
    ["손절 바꿔줘", "missing_stop_loss_value"],
    ["트레일링 스탑을 바꾸고 싶어", "missing_trailing_stop_value"],
    ["MDD 한도 변경할 수 있어?", "missing_mdd_limit_value"],
    ["종목 수를 바꿀 수 있나요?", "missing_max_positions_value"],
    ["보유 기간을 변경하고 싶어", "missing_hold_period_value"],
    ["리밸런싱 주기 바꿔줘", "missing_rebalancing_value"],
    ["초기자금을 바꾸고 싶어", "missing_initial_capital_value"],
    ["백테스트 기간 변경해줘", "missing_backtest_period_value"],
  ])("asks for the value when a field is named without one: %s", (prompt, reason) => {
    expect(getModificationClarification(prompt)).toMatchObject({ reason });
  });

  it.each([
    "손절을 12%로 바꿔줘",
    "리밸런싱을 매주로 바꿔줘",
    "백테스트 전체 기간으로 변경",
    "손절 없애줘",
  ])("does not intercept a field change that already carries a value: %s", (prompt) => {
    expect(getModificationClarification(prompt)).toBeNull();
  });

  // 백엔드 계약의 전제: 필드 값 칩은 재전송 시 가로채지지 않고 백엔드 결정론
  // fast-path에 도달해야 한다(각 칩의 추출 계약은 test_nl_parser_overrides.py가 검증).
  it.each([
    "손절을 5%로 변경",
    "트레일링 스탑을 5%로 변경",
    "MDD 30% 한도로 변경",
    "최대 20종목으로 변경",
    "60일 보유로 변경",
    "매월 리밸런싱으로 변경",
    "초기자금 1억원으로 변경",
    "백테스트 기간을 3년으로 변경",
  ])("lets the value chip %s pass through to backend parsing", (chip) => {
    expect(getModificationClarification(chip)).toBeNull();
  });

  it.each([
    "손절 조건을 10%로 변경",
    "조건은 그대로 유지해줘",
  ])("does not intercept a concrete or keep request as a vague change: %s", (prompt) => {
    expect(getModificationClarification(prompt)).toBeNull();
  });

  it("responds with condition options when a strategy exists", () => {
    expect(
      decideConversationTurn("조건을 변경 할 수 있어?", {
        ...baseContext,
        hasCurrentStrategy: true,
      }),
    ).toMatchObject({
      action: "respond",
      reason: "missing_condition_target",
      suggestions: expect.arrayContaining(["리스크 설정 변경", "직접 입력"]),
    });
  });
});

describe("parseHoldingPeriodDays", () => {
  it.each([
    ["252거래일 (1년)", 252],
    ["1,260거래일 (5년)", 1260],
    ["1000일", 1000],
    ["3년", 756],
    ["18개월", 378],
    ["1년 6개월", 378],
    ["60주", 300],
  ])("parses holding period input: %s", (prompt, days) => {
    expect(parseHoldingPeriodDays(prompt)).toBe(days);
  });

  it("returns null for an unrelated answer", () => {
    expect(parseHoldingPeriodDays("코스피")).toBeNull();
  });
});
