import {
  BACKTEST_MIN_PERIOD_MESSAGE,
  backtestPeriodTooShort,
  isBacktestConfirmation,
  isBacktestPrompt,
} from "./backtestConfirmation";
import {
  buildStrategyHorizonComparisonResponse,
  buildTakeProfitPercentagePrompt,
  isAdvisorFollowUpPrompt,
} from "./parsedStrategyMerge";

type SpeechAct =
  | "ask"
  | "compare"
  | "create"
  | "modify"
  | "confirm"
  | "unknown";
type Topic = "strategy" | "risk" | "backtest" | "stock" | "general" | "unknown";

type DecisionBase = {
  speechAct: SpeechAct;
  topic: Topic;
  confidence: number;
  reason: string;
};

export type SemanticIntent =
  | "GREETING"
  | "OFF_TOPIC"
  | "STOCK_PICK"
  | "STRATEGY_PICK"
  | "ONBOARDING"
  | "UNSUPPORTED_FEATURE"
  | "STOCK_ANALYSIS"
  | "GENERAL_INVESTMENT"
  | "UNKNOWN"
  | "STRATEGY_ADVICE";

export type SemanticClassification = {
  intent: SemanticIntent;
  symbol?: string | null;
  suggestedReply?: string | null;
};

export type StrategyAssumptions = {
  holdingPeriodDays?: number;
  holdingHorizon?: "short" | "medium" | "long";
};

export type HoldingPeriodHorizon = "short" | "long";

export type ConversationDecision =
  | (DecisionBase & {
      action: "respond";
      message: string;
      suggestions?: string[];
    })
  | (DecisionBase & { action: "run_backtest" })
  | (DecisionBase & { action: "continue_builder" })
  | (DecisionBase & { action: "answer_follow_up" })
  | (DecisionBase & { action: "classify" })
  | (DecisionBase & { action: "answer_general" })
  | (DecisionBase & { action: "respond_stock"; message: string; symbol: string | null })
  | (DecisionBase & {
      action: "start_builder";
      message?: string;
      seedPrompt: string;
      strategyAssumptions?: StrategyAssumptions;
    })
  | (DecisionBase & {
      action: "ask_holding_period";
      message: string;
      suggestions: string[];
      strategyPrompt: string;
      holdingHorizon: HoldingPeriodHorizon;
    })
  | (DecisionBase & {
      action: "parse_strategy";
      strategyPrompt: string;
      strategyAssumptions: StrategyAssumptions;
    });

export type ConversationContext = {
  stage: "idle" | "ready" | "running" | "done";
  hasBacktestRequest: boolean;
  hasCurrentStrategy: boolean;
  builderMode: boolean;
  lastCoachText: string | null;
  pendingHoldingPeriodPrompt?: string | null;
  pendingHoldingPeriodHorizon?: HoldingPeriodHorizon | null;
};

const HORIZON_ASSUMPTIONS = [
  {
    horizon: "short",
    pattern: /단기(?!\s*(?:이동\s*평균|이평|sma|ema))(?:\s*(?:전략|투자|보유))?|단타|짧(?:게|은\s*(?:기간|보유|주기))/i,
  },
  {
    days: 63,
    horizon: "medium",
    pattern: /중기(?:\s*(?:전략|투자|보유))?|중간\s*(?:기간|정도)\s*보유/,
  },
  {
    horizon: "long",
    pattern: /장기(?!\s*(?:이동\s*평균|이평|sma|ema))(?:\s*(?:전략|투자|보유))?|장투|오래\s*(?:보유|가져|들고)|긴\s*(?:기간|보유|주기)/i,
  },
] as const;

const EXPLICIT_HOLDING_PERIOD_PATTERN =
  /(?:\d+|한|두|세|반)\s*(?:거래일|일|주|개월|달|년|분기|반기)\s*(?:간|동안|정도)?\s*(?:보유|들고|유지|가져|후\s*청산)/;

export function resolveStrategyAssumptions(prompt: string): StrategyAssumptions {
  if (EXPLICIT_HOLDING_PERIOD_PATTERN.test(prompt)) return {};

  const matchingHorizons = HORIZON_ASSUMPTIONS.filter(({ pattern }) => pattern.test(prompt));
  if (matchingHorizons.length !== 1) return {};

  const [matchingHorizon] = matchingHorizons;
  if (matchingHorizon.horizon !== "medium") {
    return { holdingHorizon: matchingHorizon.horizon };
  }
  return {
    holdingHorizon: matchingHorizon.horizon,
    holdingPeriodDays: matchingHorizon.days,
  };
}

const LONG_HOLDING_PERIOD_QUESTION =
  "바이 앤 홀드 전략으로 이해했어요. 얼마나 오래 보유할까요?";
const LONG_HOLDING_PERIOD_SUGGESTIONS = [
  "252거래일 (1년)",
  "504거래일 (2년)",
  "756거래일 (3년)",
  "1,260거래일 (5년)",
  "직접 입력",
];
const SHORT_HOLDING_PERIOD_QUESTION =
  "단기 매매 전략으로 이해했어요. 얼마나 오래 보유할까요?";
const SHORT_HOLDING_PERIOD_SUGGESTIONS = [
  "1거래일 (당일)",
  "5거래일 (1주)",
  "10거래일 (2주)",
  "20거래일 (약 1개월)",
  "60거래일 (약 3개월)",
  "직접 입력",
];

const HOLDING_PERIOD_PROMPTS = {
  short: {
    question: SHORT_HOLDING_PERIOD_QUESTION,
    suggestions: SHORT_HOLDING_PERIOD_SUGGESTIONS,
    invalidMessage: "단기 보유기간은 1~251거래일로 입력해 주세요. 얼마나 오래 보유할까요?",
    isValid: (days: number) => days >= 1 && days < 252,
  },
  long: {
    question: LONG_HOLDING_PERIOD_QUESTION,
    suggestions: LONG_HOLDING_PERIOD_SUGGESTIONS,
    invalidMessage: "장기 보유기간은 252거래일 이상으로 입력해 주세요. 얼마나 오래 보유할까요?",
    isValid: (days: number) => days >= 252,
  },
} as const;

const MODIFICATION_REQUEST_PATTERN =
  /(?:바꾸|변경|수정|고치|교체|다른|새로|설정|옵션|종류|선택|원하|싶|보여|알려)/i;
const EXPLICIT_KEEP_OR_REMOVE_PATTERN =
  /(?:없애|삭제|제거|해제|빼|그대로|유지|하지\s*마|필요\s*없)/i;
const EXPLICIT_ENTRY_SIGNAL_PATTERN =
  /(?:sma|ema|이동\s*평균|이평|골든\s*크로스|rsi|macd|볼린저|돌파|신고가|거래량|거래대금|모멘텀|상대\s*강도|수익률\s*상위|pbr|per|roe|부채\s*비율|\d+\s*(?:일|주|개월|%|배))/i;
const EXPLICIT_EXIT_SIGNAL_PATTERN =
  /(?:sma|ema|이동\s*평균|이평|데드\s*크로스|rsi|macd|볼린저|이탈|저가|\d+\s*(?:일|주|개월|%))/i;
const EXPLICIT_UNIVERSE_PATTERN =
  /(?:kospi|kosdaq|코스피|코스닥|전체\s*시장|유가\s*증권|반도체|(?:2차|이차)전지|바이오|제약)/i;
const EXPLICIT_PORTFOLIO_PATTERN =
  /(?:\d[\d,]*\s*(?:개|종목|거래일|일|주|개월|년|원|만원|억)|매일|매주|주간|매월|월간|분기|매년|연간|리밸런싱\s*없음)/i;
const EXPLICIT_RISK_PATTERN = /(?:\d+(?:\.\d+)?\s*%)/;

export type ModificationClarification = {
  area: "entry_signal" | "universe" | "exit_signal" | "portfolio" | "risk";
  topic: Topic;
  reason: string;
  message: string;
  suggestions: string[];
};

const MODIFICATION_CLARIFICATIONS: Array<ModificationClarification & {
  topicPattern: RegExp;
  explicitPattern: RegExp;
}> = [
  {
    area: "entry_signal",
    topic: "strategy",
    topicPattern: /(?:(?:진입|매수)\s*(?:신호|조건|기준)|엔트리)/i,
    explicitPattern: EXPLICIT_ENTRY_SIGNAL_PATTERN,
    reason: "missing_entry_signal_definition",
    message: "어떤 진입 신호로 변경할까요? 아래 옵션을 선택하거나 원하는 조건을 직접 입력해 주세요.",
    suggestions: ["진입 신호를 5일·20일 이동평균 골든크로스로 변경", "진입 신호를 RSI 30 이하 반등으로 변경", "진입 신호를 20일 신고가 돌파로 변경", "진입 신호를 MACD 골든크로스로 변경", "직접 입력"],
  },
  {
    area: "universe",
    topic: "strategy",
    topicPattern: /(?:유니버스|투자\s*(?:대상|시장|범위))/i,
    explicitPattern: EXPLICIT_UNIVERSE_PATTERN,
    reason: "missing_universe_definition",
    message: "어떤 유니버스로 변경할까요? 시장 범위를 선택하거나 원하는 시장·업종을 직접 입력해 주세요.",
    suggestions: ["유니버스를 KOSPI200으로 변경", "유니버스를 KOSPI로 변경", "유니버스를 KOSDAQ으로 변경", "유니버스를 KOSPI와 KOSDAQ 전체 시장으로 변경", "직접 입력"],
  },
  {
    area: "exit_signal",
    topic: "strategy",
    topicPattern: /(?:(?:청산|매도)\s*(?:신호|조건|기준))/i,
    explicitPattern: EXPLICIT_EXIT_SIGNAL_PATTERN,
    reason: "missing_exit_signal_definition",
    message: "어떤 청산 신호로 변경할까요? 아래 옵션을 선택하거나 원하는 조건을 직접 입력해 주세요.",
    suggestions: ["청산 신호를 5일·20일 이동평균 데드크로스로 변경", "청산 신호를 RSI 70 이상으로 변경", "청산 신호를 20일 저점 이탈 시 매도로 변경", "20일 보유로 변경", "직접 입력"],
  },
  {
    area: "portfolio",
    topic: "strategy",
    topicPattern: /(?:포트폴리오|포폴)/i,
    explicitPattern: EXPLICIT_PORTFOLIO_PATTERN,
    reason: "missing_portfolio_definition",
    message: "포트폴리오의 어떤 설정을 변경할까요? 아래 옵션을 선택하거나 원하는 설정을 직접 입력해 주세요.",
    suggestions: ["최대 5종목으로 변경", "20일 보유로 변경", "분기 리밸런싱으로 변경", "초기자금 1000만원으로 변경", "직접 입력"],
  },
  {
    area: "risk",
    topic: "risk",
    topicPattern: /(?:리스크|위험\s*(?:관리|조건)?|(?:^|\s)리스트(?:를|의|만|$))/i,
    explicitPattern: EXPLICIT_RISK_PATTERN,
    reason: "missing_risk_definition",
    message: "어떤 리스크 설정을 변경할까요? 아래 옵션을 선택하거나 원하는 기준을 직접 입력해 주세요.",
    suggestions: ["손절을 10%로 변경", "익절을 20%로 변경", "트레일링 스탑을 10%로 변경", "MDD 20% 한도로 변경", "직접 입력"],
  },
];

export function getModificationClarification(prompt: string): ModificationClarification | null {
  if (!MODIFICATION_REQUEST_PATTERN.test(prompt) || EXPLICIT_KEEP_OR_REMOVE_PATTERN.test(prompt)) {
    return null;
  }
  const match = MODIFICATION_CLARIFICATIONS.find(
    ({ topicPattern, explicitPattern }) => topicPattern.test(prompt) && !explicitPattern.test(prompt),
  );
  if (!match) return null;
  return {
    area: match.area,
    topic: match.topic,
    reason: match.reason,
    message: match.message,
    suggestions: match.suggestions,
  };
}

export function needsEntrySignalClarification(prompt: string): boolean {
  return getModificationClarification(prompt)?.area === "entry_signal";
}

export function parseHoldingPeriodDays(prompt: string): number | null {
  const normalized = prompt.replace(/,/g, "").replace(/\s+/g, "");
  const tradingDays = normalized.match(/(\d+)(?:거래)?일/);
  if (tradingDays) return Number(tradingDays[1]);

  const years = normalized.match(/(\d+)년/);
  const months = normalized.match(/(\d+)(?:개월|달)/);
  if (years || months) {
    return Number(years?.[1] ?? 0) * 252 + Number(months?.[1] ?? 0) * 21;
  }

  const weeks = normalized.match(/(\d+)주/);
  if (weeks) return Number(weeks[1]) * 5;
  return null;
}

function buildStrategyInputDecision(
  prompt: string,
  context: ConversationContext,
  reason: string,
): ConversationDecision {
  const assumptions = resolveStrategyAssumptions(prompt);
  if (
    (assumptions.holdingHorizon === "short" || assumptions.holdingHorizon === "long") &&
    !assumptions.holdingPeriodDays
  ) {
    const holdingHorizon = assumptions.holdingHorizon;
    const holdingPrompt = HOLDING_PERIOD_PROMPTS[holdingHorizon];
    return {
      action: "ask_holding_period",
      speechAct: "ask",
      topic: "risk",
      confidence: 1,
      reason: `${holdingHorizon}_holding_period_required`,
      message: holdingPrompt.question,
      suggestions: holdingPrompt.suggestions,
      strategyPrompt: prompt,
      holdingHorizon,
    };
  }

  return {
    action: "parse_strategy",
    speechAct: context.hasCurrentStrategy ? "modify" : "create",
    topic: "strategy",
    confidence: 1,
    reason,
    strategyPrompt: prompt,
    strategyAssumptions: assumptions,
  };
}

function fallbackMessage(intent: SemanticIntent): string {
  if (intent === "GREETING") {
    return "안녕하세요. 오늘은 어떤 전략을 연구해 볼까요?";
  }
  if (intent === "UNSUPPORTED_FEATURE") {
    return "죄송합니다. 요청하신 기능은 현재 제공하고 있지 않아요. 다른 투자 아이디어를 알려주시면 전략으로 만들어 백테스트해 드릴 수 있어요.";
  }
  if (intent === "STOCK_PICK") {
    return "특정 종목을 추천하지는 않지만, 투자 아이디어를 전략으로 만들어 과거 데이터로 검증하도록 도와드릴 수 있어요.\n\n예를 들어 이렇게 시작해볼 수 있어요:\n• RSI가 30 이하로 떨어지면 매수하고 70 이상에서 파는 '과매도 반등' 전략\n• 20일 이동평균이 60일 이동평균을 위로 뚫는 골든크로스에서 매수하는 추세 전략\n• PBR은 낮고 ROE는 높은 저평가 우량주를 고르는 가치 전략\n\n끌리는 아이디어가 있거나 평소 관심 있던 매매 방식이 있다면 말씀해 주세요 — 바로 전략으로 만들어 백테스트해 드릴게요.";
  }
  if (intent === "STRATEGY_PICK") {
    return "어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만, 관심 있는 아이디어를 함께 전략으로 만들어 과거 데이터로 백테스트해 볼 수 있어요. 제가 단계별로 여쭤볼 테니 골라 주시면 바로 백테스트까지 이어집니다.";
  }
  if (intent === "ONBOARDING") {
    return "처음이시거나 어디서부터 시작할지 막막하시면 제가 단계별로 함께 전략을 만들어 드릴게요. 몇 가지만 골라 주시면 바로 백테스트까지 이어집니다.";
  }
  return "저는 투자 전략 및 분석 전용 모델입니다. 현재 질문에는 도움을 드릴 수 없습니다. 대신 투자 전략, 백테스트와 관련된 질문은 도와드릴 수 있습니다.";
}

export function decideConversationTurn(
  prompt: string,
  context: ConversationContext,
  classification?: SemanticClassification,
): ConversationDecision {
  if (backtestPeriodTooShort(prompt)) {
    return {
      action: "respond",
      speechAct: "modify",
      topic: "backtest",
      confidence: 1,
      reason: "backtest_period_below_minimum",
      message: BACKTEST_MIN_PERIOD_MESSAGE,
    };
  }

  if (
    context.stage === "ready" &&
    context.hasBacktestRequest &&
    isBacktestPrompt(context.lastCoachText) &&
    isBacktestConfirmation(prompt)
  ) {
    return {
      action: "run_backtest",
      speechAct: "confirm",
      topic: "backtest",
      confidence: 1,
      reason: "confirmed_backtest_prompt",
    };
  }

  if (context.pendingHoldingPeriodPrompt) {
    // Snapshots created before horizon persistence only contain long-period prompts.
    const holdingHorizon = context.pendingHoldingPeriodHorizon ?? "long";
    const holdingPrompt = HOLDING_PERIOD_PROMPTS[holdingHorizon];
    const holdingPeriodDays = parseHoldingPeriodDays(prompt);
    if (holdingPeriodDays === null || !holdingPrompt.isValid(holdingPeriodDays)) {
      return {
        action: "ask_holding_period",
        speechAct: "ask",
        topic: "risk",
        confidence: 1,
        reason: `${holdingHorizon}_holding_period_still_missing`,
        message: holdingPeriodDays === null
          ? holdingPrompt.question
          : holdingPrompt.invalidMessage,
        suggestions: holdingPrompt.suggestions,
        strategyPrompt: context.pendingHoldingPeriodPrompt,
        holdingHorizon,
      };
    }
    return {
      action: "start_builder",
      speechAct: context.hasCurrentStrategy ? "modify" : "create",
      topic: "strategy",
      confidence: 1,
      reason: "holding_period_selected",
      seedPrompt: context.pendingHoldingPeriodPrompt,
      strategyAssumptions: { holdingPeriodDays },
    };
  }

  const horizonResponse = buildStrategyHorizonComparisonResponse(prompt);
  if (horizonResponse) {
    return {
      action: "respond",
      speechAct: "compare",
      topic: "strategy",
      confidence: 1,
      reason: "strategy_horizon_comparison",
      message: horizonResponse,
    };
  }

  if (context.builderMode) {
    return {
      action: "continue_builder",
      speechAct: "unknown",
      topic: "strategy",
      confidence: 1,
      reason: "active_builder_session",
    };
  }

  const modificationClarification = context.hasCurrentStrategy
    ? getModificationClarification(prompt)
    : null;
  if (modificationClarification) {
    return {
      action: "respond",
      speechAct: "modify",
      topic: modificationClarification.topic,
      confidence: 1,
      reason: modificationClarification.reason,
      message: modificationClarification.message,
      suggestions: modificationClarification.suggestions,
    };
  }

  const takeProfitPrompt = buildTakeProfitPercentagePrompt(prompt);
  if (context.hasCurrentStrategy && takeProfitPrompt) {
    return {
      action: "respond",
      speechAct: "modify",
      topic: "risk",
      confidence: 1,
      reason: "missing_take_profit_percentage",
      message: takeProfitPrompt.message,
      suggestions: [...takeProfitPrompt.suggestions, "직접 입력"],
    };
  }

  if (
    context.hasCurrentStrategy &&
    Object.keys(resolveStrategyAssumptions(prompt)).length === 0 &&
    isAdvisorFollowUpPrompt(prompt)
  ) {
    return {
      action: "answer_follow_up",
      speechAct: "ask",
      topic: "strategy",
      confidence: 1,
      reason: "active_strategy_follow_up",
    };
  }

  if (!classification) {
    return {
      action: "classify",
      speechAct: "unknown",
      topic: "unknown",
      confidence: 0,
      reason: "requires_semantic_classification",
    };
  }

  const { intent, suggestedReply = null, symbol = null } = classification;
  if (
    context.hasCurrentStrategy &&
    (intent === "STOCK_PICK" || intent === "STRATEGY_PICK" || intent === "ONBOARDING")
  ) {
    return buildStrategyInputDecision(prompt, context, "preserve_active_strategy");
  }

  if (
    intent === "GREETING" ||
    intent === "OFF_TOPIC" ||
    intent === "UNSUPPORTED_FEATURE"
  ) {
    return {
      action: "respond",
      speechAct: "unknown",
      topic: "general",
      confidence: 1,
      reason: `classified_${intent.toLowerCase()}`,
      message: suggestedReply ?? fallbackMessage(intent),
    };
  }

  if (intent === "STOCK_PICK" || intent === "STRATEGY_PICK" || intent === "ONBOARDING") {
    return {
      action: "start_builder",
      speechAct: "create",
      topic: "strategy",
      confidence: 1,
      reason: `classified_${intent.toLowerCase()}`,
      message: suggestedReply ?? fallbackMessage(intent),
      seedPrompt: prompt,
    };
  }

  if (intent === "STOCK_ANALYSIS") {
    if (context.hasCurrentStrategy && !symbol) {
      return buildStrategyInputDecision(
        prompt,
        context,
        "stock_analysis_without_symbol_during_strategy",
      );
    }
    return {
      action: "respond_stock",
      speechAct: "ask",
      topic: "stock",
      confidence: 1,
      reason: "classified_stock_analysis",
      symbol,
      message:
        suggestedReply ??
        "특정 종목에 대한 매수·매도 판단이나 종목 추천은 제공하지 않아요. 대신 관심 있는 종목에서 출발한 아이디어를 전략으로 만들어 과거 데이터로 검증할 수 있어요.",
    };
  }

  if ((intent === "GENERAL_INVESTMENT" || intent === "UNKNOWN") && !context.hasCurrentStrategy) {
    return {
      action: "answer_general",
      speechAct: "ask",
      topic: "general",
      confidence: 1,
      reason: `classified_${intent.toLowerCase()}`,
    };
  }

  return buildStrategyInputDecision(prompt, context, "classified_strategy_input");
}
