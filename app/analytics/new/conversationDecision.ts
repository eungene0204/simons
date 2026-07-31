import {
  BACKTEST_MIN_PERIOD_MESSAGE,
  backtestPeriodTooShort,
  isBacktestConfirmation,
  isBacktestPrompt,
} from "./backtestConfirmation";
import {
  buildStrategyHorizonComparisonResponse,
  fundamentalFactorPromptFor,
  isAdvisorFollowUpPrompt,
  takeProfitPrompt,
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
  // 이 턴이 전략 State를 건드리지 않는 '부가 발화'인지(인사·역할 밖·미제공 안내·용어 질문).
  // 진행 중인 되묻기가 열려 있으면 답한 뒤 그 질문을 그대로 다시 물어야 한다 — 되묻기 블록은
  // 마지막 assistant 메시지에만 렌더되므로 새 메시지 하나로 질문과 선택지가 증발한다
  // (2026-07-31 "안녕" 사고). 설계 스펙 § 21: 부가 질문은 워크플로를 유지한다.
  // 자기 질문을 던지는 턴(익절 되묻기·보유기간 질문 등)에는 붙이지 않는다 — 질문이 겹친다.
  preservesOpenQuestion?: boolean;
};

export type SemanticIntent =
  | "GREETING"
  | "OFF_TOPIC"
  | "STOCK_PICK"
  | "STRATEGY_PICK"
  | "ONBOARDING"
  | "UNSUPPORTED_FEATURE"
  | "PERSONAL_ADVICE"
  | "LIVE_TRADING"
  | "STOCK_ANALYSIS"
  | "GENERAL_INVESTMENT"
  | "UNKNOWN"
  | "STRATEGY_ADVICE";

// 입력이 진행 중인 전략 작성 워크플로에 일으키는 효과(백엔드 intent/schemas.py와 동일).
// SemanticIntent와 직교하는 축이다 — 라벨은 '무엇에 대한 발화인가', 이 값은 '워크플로를
// 어떻게 제어하는가'를 말한다. 판정은 전적으로 백엔드 분류 LLM이 하며, 프론트는 정규식으로
// 재판정하지 않는다(정규식이 LLM의 의미 판정을 재심하는 구조 금지 — 자연어 해석 계약).
export type WorkflowEffect =
  | "NONE"
  | "UPDATE"
  | "PAUSE"
  | "RESUME"
  | "CANCEL"
  | "RESTART"
  | "ROLLBACK"
  | "CORRECT";

export type WorkflowStatus = "IDLE" | "ACTIVE" | "PAUSED" | "CANCELLED";

// 대화 흐름을 실제로 제어하는 효과 — NONE/UPDATE는 기존 흐름 그대로다.
export type WorkflowControlEffect = Exclude<WorkflowEffect, "NONE" | "UPDATE">;

const WORKFLOW_CONTROL_EFFECTS: readonly WorkflowControlEffect[] = [
  "PAUSE",
  "RESUME",
  "CANCEL",
  "RESTART",
  "ROLLBACK",
  "CORRECT",
];

export type SemanticClassification = {
  intent: SemanticIntent;
  symbol?: string | null;
  suggestedReply?: string | null;
  workflowEffect?: WorkflowEffect;
  workflowStatus?: WorkflowStatus;
  // 값 없이 지목된 수정 대상(백엔드 intent/clarify_targets.py의 닫힌 목록).
  // "무엇을 바꾸려는데 값이 없다"는 의미 판정이므로 LLM이 하고, 무엇을 물을지(문구·선택지)는
  // 이 라벨을 키로 아래 표에서 결정론이 고른다 — 프론트가 원문을 다시 읽지 않는다.
  clarifyTarget?: string | null;
};

export type StrategyAssumptions = {
  holdingPeriodDays?: number;
  holdingHorizon?: "short" | "medium" | "long";
};

export type ResearchMetric = "sharpe" | "sortino" | "calmar";

export type MetricOptimizationRange = {
  type: "number";
  min: number;
  max: number;
  step: number;
};

export type HoldingPeriodHorizon = "short" | "long";

export type ConversationDecision =
  | (DecisionBase & {
      action: "respond";
      message: string;
      suggestions?: string[];
    })
  | (DecisionBase & { action: "run_backtest" })
  | (DecisionBase & {
      action: "control_workflow";
      effect: WorkflowControlEffect;
      message: string | null;
    })
  | (DecisionBase & { action: "continue_builder" })
  | (DecisionBase & { action: "answer_follow_up" })
  | (DecisionBase & { action: "classify" })
  | (DecisionBase & { action: "answer_general" })
  | (DecisionBase & {
      action: "ask_research_metric";
      message: string;
      suggestions: string[];
      strategyPrompt: string;
    })
  | (DecisionBase & { action: "respond_stock"; message: string; symbol: string | null })
  | (DecisionBase & {
      action: "start_builder";
      message?: string;
      seedPrompt: string;
      strategyAssumptions?: StrategyAssumptions;
      researchMetric?: ResearchMetric;
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
    })
  // 상태 기본 액션 — 아직 정하지 않은 조건을 진행 골격 순서대로 묻는다(FR-SA-016).
  // 질문·선택지는 슬롯 판정 하나에서 오고, 화면 조립기가 진행률 카드를 함께 세운다.
  | (DecisionBase & {
      action: "ask_next_condition";
      field: string;
      message: string;
      suggestions: string[];
    })
  // 지금 설정된 항목을 체크박스로 보여주고 "그대로 둘 것"을 고르게 한다(FR-SA-020).
  // 목록은 화면이 상태에서 만든다 — 중재자는 이 화면을 띄우라는 결정만 한다.
  | (DecisionBase & {
      action: "ask_keep_items";
      message: string;
      /** 보여줄 항목이 하나도 없을 때의 대체 선택지(기존 영역 칩). */
      suggestions: string[];
    });

// 진행 골격 슬롯 상태 — 중재자가 "지금 무엇을 할 수 있는가"를 판정하는 유일한 입력이다.
// 계산은 호출부(page.tsx)가 정본 술어(backtestReadiness.isSlotFilled)로 하고 여기엔 결과만
// 실린다 — 중재자를 순수 함수로 유지하고, 같은 판정이 두 곳에서 갈라지지 않게 한다.
export type SlotAsk = { field: string; question: string; suggestions: string[] };

export type StrategySlotState = {
  /** 다음에 정할 조건(없으면 null = 백테스트 실행 가능). */
  next: SlotAsk | null;
};

export type ConversationContext = {
  stage: "idle" | "ready" | "running" | "done";
  hasBacktestRequest: boolean;
  hasCurrentStrategy: boolean;
  builderMode: boolean;
  lastCoachText: string | null;
  pendingHoldingPeriodPrompt?: string | null;
  pendingHoldingPeriodHorizon?: HoldingPeriodHorizon | null;
  pendingResearchMetricPrompt?: string | null;
  /** 진행 골격 상태. 없으면(전략 없음) 상태 기본 액션이 성립하지 않는다. */
  slots?: StrategySlotState | null;
  /** 사용자가 "바꾸겠다"고 고른 항목의 재질문 — 대기열의 머리 하나(문구까지 채워서).
   *  slots와 같은 계약이다: 판정도 문구 조회도 호출부가 하고 중재자는 결과만 본다. */
  reaskNext?: SlotAsk | null;
};

const RESEARCH_METRIC_LABELS: Record<ResearchMetric, string> = {
  sharpe: "샤프 지수",
  sortino: "소르티노 지수",
  calmar: "칼마 비율",
};
const RESEARCH_METRIC_SUGGESTIONS = ["샤프 지수", "소르티노 지수", "칼마 비율"];
const RESEARCH_METRIC_PATTERNS = [
  ["sharpe", /(?:샤프|sharpe)/i],
  ["sortino", /(?:소르티노|sortino)/i],
  ["calmar", /(?:칼마|칼미|calmar)/i],
  ["treynor", /(?:트레이너|treynor)/i],
] as const;

export function getResearchMetricLabel(metric: ResearchMetric): string {
  return RESEARCH_METRIC_LABELS[metric];
}

export function buildResearchMetricIntro(metric: ResearchMetric): string {
  return `${getResearchMetricLabel(metric)}를 과거 데이터 연구 목표로 두고, 사용자가 선택한 조건의 파라미터 조합을 비교할 전략을 함께 구성할게요.`;
}

export function buildResearchMetricSummary(metric: ResearchMetric): string {
  return `${getResearchMetricLabel(metric)}를 과거 데이터 연구 목표로 설정했습니다. 아래 전략은 사용자가 대화에서 선택한 조건으로 구성되었습니다.`;
}

export function parseMetricOptimizationRange(input: string): MetricOptimizationRange | null {
  const pair = input.match(
    /(-?\d+(?:\.\d+)?)\s*(?:~|〜|–|—|-|부터|에서|to)\s*(-?\d+(?:\.\d+)?)/i
  );
  const fallback = input.match(/-?\d+(?:\.\d+)?/g);
  const values = pair ? [pair[1], pair[2]] : fallback?.length === 2 ? fallback : null;
  if (!values) return null;

  const min = Number(values[0]);
  const max = Number(values[1]);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min >= max) return null;

  const span = max - min;
  const step = Number.isInteger(min) && Number.isInteger(max)
    ? Math.max(1, Math.round(span / 10))
    : Number(Math.max(0.01, span / 10).toPrecision(2));

  return { type: "number", min, max, step };
}

function researchMetricDecision(prompt: string, pendingPrompt?: string | null): ConversationDecision | null {
  const mentioned = RESEARCH_METRIC_PATTERNS.filter(([, pattern]) => pattern.test(prompt)).map(([metric]) => metric);
  const strategyPrompt = pendingPrompt ?? prompt;
  const isNewRequest =
    /(?:샤프|sharpe|소르티노|sortino|칼마|칼미|calmar|트레이너|treynor|위험\s*조정|리스크\s*조정|성과\s*지표)/i.test(prompt) &&
    /(?:최대화|극대화|높(?:이|은)|개선|최적화|목표|기준|중심)/i.test(prompt) &&
    /(?:(?:전략|매매\s*규칙).*(?:만들|생성|구성|설계|연구|찾|최적화)|(?:만들|생성|구성|설계|연구|찾|최적화).*(?:전략|매매\s*규칙))/i.test(prompt);
  if (!pendingPrompt && !isNewRequest) return null;

  if (mentioned.length !== 1 || mentioned[0] === "treynor") {
    const treynorUnavailable = mentioned.length === 1 && mentioned[0] === "treynor";
    return {
      action: "ask_research_metric",
      speechAct: "ask",
      topic: "strategy",
      confidence: 1,
      reason: treynorUnavailable ? "treynor_metric_unavailable" : "research_metric_required",
      strategyPrompt,
      message: treynorUnavailable
        ? "트레이너 지수는 시장 벤치마크와 전략 베타 데이터가 필요해 현재 계산할 수 없습니다. 다른 지표를 선택해 주세요."
        : "어떤 성과 지표를 기준으로 과거 데이터를 탐색할까요?",
      suggestions: treynorUnavailable
        ? RESEARCH_METRIC_SUGGESTIONS
        : [...RESEARCH_METRIC_SUGGESTIONS, "트레이너 지수 (현재 계산 불가)"],
    };
  }

  const metric = mentioned[0] as ResearchMetric;
  return {
    action: "start_builder",
    speechAct: "create",
    topic: "strategy",
    confidence: 1,
    reason: "research_metric_selected",
    researchMetric: metric,
    seedPrompt: `${strategyPrompt}\n과거 데이터 연구 목표: ${getResearchMetricLabel(metric)}. 사용자가 선택하는 전략 조건의 파라미터 조합을 이 지표 기준으로 비교한다.`,
  };
}

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
  /(?:바꾸|바꿔|바꿀|변경|수정|고치|고쳐|교체|다른|새로|설정|옵션|종류|선택|원하|싶|보여|알려)/i;
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
// 영역 미지정 되묻기("조건을 변경할 수 있어?")의 통과 조건 — 구체 영역·필드·값이 하나라도
// 언급되면 기존 영역별 되묻기/수정 파싱 경로에 맡긴다.
const EXPLICIT_CONDITION_TARGET_PATTERN = new RegExp(
  [
    EXPLICIT_ENTRY_SIGNAL_PATTERN.source,
    EXPLICIT_EXIT_SIGNAL_PATTERN.source,
    EXPLICIT_UNIVERSE_PATTERN.source,
    EXPLICIT_PORTFOLIO_PATTERN.source,
    EXPLICIT_RISK_PATTERN.source,
    /(?:진입|매수|청산|매도|유니버스|시장|업종|섹터|테마|포트폴리오|종목|손절|익절|트레일링|낙폭|mdd|보유|리밸런싱|초기\s*자금|자본|수수료|슬리피지|백테스트|기간|배당|시총|매출|이익|부채)/
      .source,
  ].join("|"),
  "i",
);

export type ModificationClarification = {
  /** LLM이 고른 되묻기 대상(intent/clarify_targets.py의 닫힌 목록)과 같은 키. */
  target: string;
  area:
    | "entry_signal"
    | "universe"
    | "exit_signal"
    | "portfolio"
    | "risk"
    | "backtest"
    | "condition";
  topic: Topic;
  reason: string;
  message: string;
  suggestions: string[];
};

const MODIFICATION_CLARIFICATIONS: Array<ModificationClarification & {
  topicPattern: RegExp;
  explicitPattern: RegExp;
}> = [
  // ── 필드 언급+값 없음("손절 바꿔줘") ──────────────────────────────────────
  // 값이 없으면 백엔드 LLM diff가 전부 null이라 무변경 전략만 재렌더링되므로,
  // 값 칩(백엔드 결정론 fast-path가 처리하는 완결 지시문)으로 되묻는다. 익절은
  // buildTakeProfitPercentagePrompt가 이미 담당하므로 여기 없다. 영역·catch-all
  // 항목보다 앞이어야 한다(구체 필드 우선 매칭).
  {
    area: "risk",
    topic: "risk",
    topicPattern: /(?:손절|스탑\s*로스|스톱\s*로스|stop\s*loss)/i,
    explicitPattern: /\d/,
    target: "stop_loss",
    reason: "missing_stop_loss_value",
    message: "손절 기준을 몇 %로 변경할까요? 아래에서 선택하거나 원하는 값을 직접 입력해 주세요.",
    suggestions: ["손절을 -5%로 변경", "손절을 -10%로 변경", "손절을 -15%로 변경", "직접 입력"],
  },
  {
    area: "risk",
    topic: "risk",
    topicPattern: /(?:트레일링|trailing)/i,
    explicitPattern: /\d/,
    target: "trailing_stop",
    reason: "missing_trailing_stop_value",
    message: "트레일링 스탑 기준을 몇 %로 변경할까요? 아래에서 선택하거나 원하는 값을 직접 입력해 주세요.",
    suggestions: ["트레일링 스탑을 -5%로 변경", "트레일링 스탑을 -10%로 변경", "직접 입력"],
  },
  {
    area: "risk",
    topic: "risk",
    topicPattern: /(?:mdd|최대\s*낙폭|낙폭|드로우?\s*다운)/i,
    explicitPattern: /\d/,
    target: "mdd",
    reason: "missing_mdd_limit_value",
    message: "MDD 한도를 몇 %로 변경할까요? 아래에서 선택하거나 원하는 값을 직접 입력해 주세요.",
    suggestions: ["MDD 20% 한도로 변경", "MDD 30% 한도로 변경", "직접 입력"],
  },
  {
    area: "portfolio",
    topic: "strategy",
    topicPattern: /(?:종목\s*수(?!익)|보유\s*종목|동시\s*보유)/i,
    explicitPattern: /\d/,
    target: "max_positions",
    reason: "missing_max_positions_value",
    message: "최대 보유 종목 수를 몇 종목으로 변경할까요? 아래에서 선택하거나 원하는 수를 직접 입력해 주세요.",
    suggestions: ["최대 5종목으로 변경", "최대 10종목으로 변경", "최대 20종목으로 변경", "직접 입력"],
  },
  {
    area: "portfolio",
    topic: "strategy",
    topicPattern: /(?:보유\s*기간|홀딩\s*기간|보유\s*일수)/i,
    explicitPattern: /\d/,
    target: "hold_period",
    reason: "missing_hold_period_value",
    message: "보유 기간을 며칠로 변경할까요? 아래에서 선택하거나 원하는 기간을 직접 입력해 주세요.",
    suggestions: ["20일 보유로 변경", "60일 보유로 변경", "직접 입력"],
  },
  {
    area: "portfolio",
    topic: "strategy",
    topicPattern: /(?:리밸런싱|리밸런스|재조정)/i,
    explicitPattern: /(?:\d|매일|매주|주간|매월|월간|월별|분기|반기|매년|연간|없)/,
    target: "rebalancing",
    reason: "missing_rebalancing_value",
    message: "리밸런싱 주기를 어떻게 변경할까요? 아래에서 선택하거나 원하는 주기를 직접 입력해 주세요.",
    suggestions: ["매월 리밸런싱으로 변경", "분기 리밸런싱으로 변경", "매년 리밸런싱으로 변경", "직접 입력"],
  },
  {
    area: "portfolio",
    topic: "strategy",
    topicPattern: /(?:초기\s*자금|초기\s*자본|투자금|자본금|시드)/i,
    explicitPattern: /\d/,
    target: "initial_capital",
    reason: "missing_initial_capital_value",
    message: "초기자금을 얼마로 변경할까요? 아래에서 선택하거나 원하는 금액을 직접 입력해 주세요.",
    suggestions: ["초기자금 1000만원으로 변경", "초기자금 3000만원으로 변경", "초기자금 1억원으로 변경", "직접 입력"],
  },
  {
    area: "backtest",
    topic: "backtest",
    topicPattern: /(?:백테스트|테스트)\s*기간/i,
    explicitPattern: /(?:\d|전체)/,
    target: "backtest_period",
    reason: "missing_backtest_period_value",
    message: "백테스트 기간을 어떻게 변경할까요? 아래에서 선택하거나 원하는 기간을 직접 입력해 주세요.",
    suggestions: ["백테스트 기간을 3년으로 변경", "백테스트 기간을 5년으로 변경", "백테스트 전체 기간으로 변경", "직접 입력"],
  },
  // ── 영역 언급("진입 신호를 바꾸고 싶어") ─────────────────────────────────
  {
    area: "entry_signal",
    topic: "strategy",
    topicPattern: /(?:(?:진입|매수)\s*(?:신호|조건|기준)|엔트리)/i,
    explicitPattern: EXPLICIT_ENTRY_SIGNAL_PATTERN,
    target: "entry_signal",
    reason: "missing_entry_signal_definition",
    message: "어떤 진입 신호로 변경할까요? 아래 옵션을 선택하거나 원하는 조건을 직접 입력해 주세요.",
    suggestions: ["진입 신호를 5일·20일 이동평균 골든크로스로 변경", "진입 신호를 RSI 30 이하 반등으로 변경", "진입 신호를 20일 신고가 돌파로 변경", "진입 신호를 MACD 골든크로스로 변경", "직접 입력"],
  },
  // ── 대상 종목 변경 의향("종목을 변경 할 수 있나?", "종목 교체 할 수 있어?") ────
  // 구체 종목명 없이 교체 의향만 밝힌 발화 — 수정 파싱으로 흘리면 diff가 전부 null이라
  // 무변경 재렌더링+다음 조건 질문으로 흐름이 끊긴다(2026-07-26 사고). 칩 없이 채팅
  // 입력만 안내한다(사용자 결정 — 특정 종목 선택지를 내밀면 추천이 될 수 있고, 교체·
  // 제외·추가는 백엔드 수정 경로가 자유 발화로 처리한다). 구체 종목명이 함께 오면
  // ("종목을 삼성전자로 바꿔줘") 어미 인접성이 깨져 topicPattern에 걸리지 않아 자연히
  // 수정 파싱으로 간다.
  {
    area: "universe",
    topic: "strategy",
    topicPattern:
      /(?:(?:종목|주식)(?:들)?\s*(?:을|를|은|는|도|만)?\s*(?:변경|교체|바꾸|바꿀|바꿔|갈아)|다른\s*(?:종목|주식))/i,
    explicitPattern: EXPLICIT_UNIVERSE_PATTERN,
    target: "target_symbols",
    reason: "missing_target_symbols_change",
    message:
      "네, 대상 종목은 언제든 바꿀 수 있어요. 어떻게 바꿀지 채팅으로 말씀해 주세요. " +
      "예: '삼성전자만으로 백테스트해줘', '현대약품은 빼줘', '반도체 관련주로 바꿔줘'",
    suggestions: [],
  },
  {
    area: "universe",
    topic: "strategy",
    topicPattern: /(?:유니버스|투자\s*(?:대상|시장|범위))/i,
    explicitPattern: EXPLICIT_UNIVERSE_PATTERN,
    target: "universe",
    reason: "missing_universe_definition",
    message: "어떤 유니버스로 변경할까요? 시장 범위를 선택하거나 원하는 시장·업종을 직접 입력해 주세요.",
    suggestions: ["유니버스를 KOSPI200으로 변경", "유니버스를 KOSPI로 변경", "유니버스를 KOSDAQ으로 변경", "유니버스를 KOSPI와 KOSDAQ 전체 시장으로 변경", "직접 입력"],
  },
  {
    area: "exit_signal",
    topic: "strategy",
    topicPattern: /(?:(?:청산|매도)\s*(?:신호|조건|기준))/i,
    explicitPattern: EXPLICIT_EXIT_SIGNAL_PATTERN,
    target: "exit_signal",
    reason: "missing_exit_signal_definition",
    message: "어떤 청산 신호로 변경할까요? 아래 옵션을 선택하거나 원하는 조건을 직접 입력해 주세요.",
    suggestions: ["청산 신호를 5일·20일 이동평균 데드크로스로 변경", "청산 신호를 RSI 70 이상으로 변경", "청산 신호를 20일 저점 이탈 시 매도로 변경", "20일 보유로 변경", "직접 입력"],
  },
  {
    area: "portfolio",
    topic: "strategy",
    topicPattern: /(?:포트폴리오|포폴)/i,
    explicitPattern: EXPLICIT_PORTFOLIO_PATTERN,
    target: "portfolio",
    reason: "missing_portfolio_definition",
    message: "포트폴리오의 어떤 설정을 변경할까요? 아래 옵션을 선택하거나 원하는 설정을 직접 입력해 주세요.",
    suggestions: ["최대 5종목으로 변경", "20일 보유로 변경", "분기 리밸런싱으로 변경", "초기자금 1000만원으로 변경", "직접 입력"],
  },
  {
    area: "risk",
    topic: "risk",
    topicPattern: /(?:리스크|위험\s*(?:관리|조건)?|(?:^|\s)리스트(?:를|의|만|$))/i,
    explicitPattern: EXPLICIT_RISK_PATTERN,
    target: "risk",
    reason: "missing_risk_definition",
    message: "어떤 리스크 설정을 변경할까요? 아래 옵션을 선택하거나 원하는 기준을 직접 입력해 주세요.",
    suggestions: ["손절을 -10%로 변경", "익절을 20%로 변경", "트레일링 스탑을 -10%로 변경", "MDD 20% 한도로 변경", "직접 입력"],
  },
  // 영역 미지정 조건 변경("조건을 변경할 수 있어?") — 어느 영역 topicPattern에도 안 걸려
  // 수정 파싱으로 흘러가면 LLM diff가 전부 null이라 무변경 전략만 조용히 재렌더링된다.
  // 반드시 마지막 항목이어야 한다(영역이 언급되면 위의 구체 되묻기가 먼저 매칭).
  // 칩은 영역 문구라 클릭 시 위의 영역별 되묻기로 이어지는 2단계 플로우다.
  {
    area: "condition",
    topic: "strategy",
    topicPattern: /(?:조건|설정|옵션|항목|파라미터|세팅)/i,
    explicitPattern: EXPLICIT_CONDITION_TARGET_PATTERN,
    target: "condition",
    reason: "missing_condition_target",
    message: "네, 조건을 변경할 수 있어요. 어떤 조건을 바꿀까요? 아래에서 선택하거나 원하는 변경 내용을 직접 입력해 주세요.",
    suggestions: ["진입 신호 변경", "청산 신호 변경", "유니버스 변경", "포트폴리오 설정 변경", "리스크 설정 변경", "직접 입력"],
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
    target: match.target,
    area: match.area,
    topic: match.topic,
    reason: match.reason,
    message: match.message,
    suggestions: match.suggestions,
  };
}

/** 되묻기 대상 라벨 → 문구·선택지. LLM이 고른 라벨을 키로 정해진 문구를 고른다.
 *  목록에 없는 라벨이면 null — 없는 문구를 지어내지 않는다(백엔드 검증을 통과한 값만 온다). */
export function clarificationForTarget(target: string): ModificationClarification | null {
  const entry = MODIFICATION_CLARIFICATIONS.find((e) => e.target === target);
  if (entry) {
    return {
      target: entry.target,
      area: entry.area,
      topic: entry.topic,
      reason: entry.reason,
      message: entry.message,
      suggestions: entry.suggestions,
    };
  }
  if (target === "take_profit") {
    const prompt = takeProfitPrompt();
    return {
      target,
      area: "risk",
      topic: "risk",
      reason: "missing_take_profit_percentage",
      message: prompt.message,
      suggestions: [...prompt.suggestions, "직접 입력"],
    };
  }
  const factor = fundamentalFactorPromptFor(target);
  if (factor) {
    return {
      target,
      area: "condition",
      topic: "strategy",
      reason: "missing_fundamental_threshold",
      message: factor.message,
      suggestions: [...factor.suggestions, "직접 입력"],
    };
  }
  return null;
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

function isNamedStockStrategyRequest(
  prompt: string,
  symbol: string | null,
): boolean {
  return Boolean(
    symbol &&
    /(?:전략|백테스트|시뮬레이션|모의\s*투자)/i.test(prompt),
  );
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
  if (intent === "PERSONAL_ADVICE") {
    return "나이·자산·직업 같은 개인 상황에 맞춘 전략이나 종목 추천은 제공하지 않아요. 모든 투자 판단은 직접 내리셔야 하지만, 원하시는 조건을 하나씩 골라 전략을 만들고 과거 데이터로 검증해보실 수는 있어요. 제가 단계별로 여쭤볼 테니 골라 주시면 바로 백테스트까지 이어집니다.";
  }
  if (intent === "LIVE_TRADING") {
    return "실제 계좌로 매매를 실행하거나 자금을 대신 운용하는 기능은 제공하지 않아요. 이 서비스는 전략을 설계하고 과거 데이터로 검증하는 연구 도구예요. 대신 전략을 만들어 백테스트한 뒤, 가상계좌 모의투자로 실전처럼 시뮬레이션해볼 수 있어요.";
  }
  return "저는 투자 전략 및 분석 전용 모델입니다. 현재 질문에는 도움을 드릴 수 없습니다. 대신 투자 전략, 백테스트와 관련된 질문은 도와드릴 수 있습니다.";
}

function singleStockResearchMessage(): string {
  return "특정 종목에 대한 매수·매도 판단이나 종목 추천은 제공하지 않아요.\n\n대신 관심 있는 종목을 대상으로, 어떤 조건에서 진입하고 청산할지를 정해 과거 데이터에서 검증하는 전략을 만들 수 있어요.\n\n예를 들어 이렇게 시작해볼 수 있어요:\n• 5일 이동평균이 20일 이동평균을 상향 돌파하면 매수하고, 하향 돌파하면 매도하는 전략\n• RSI가 30 이하로 내려가면 매수하고 70 이상이면 매도하는 전략\n• 최근 60일 고점을 돌파하면 매수하고, 손절 -10%·익절 +20%를 적용하는 전략\n\n관심 가는 방식이 있으면 말씀해 주세요. 해당 종목을 대상으로 과거 데이터에서 전략을 검증할 수 있어요.";
}

/** 상태 기본 액션 — 아직 정하지 않은 조건을 진행 골격 순서대로 묻는다.
 *
 *  "지금 무엇을 할 수 있는가"는 발화가 아니라 **상태**가 답한다. 질문과 선택지가 같은
 *  슬롯 판정에서 나오므로 어긋날 수 없다(질문은 익절인데 칩은 리밸런싱이던 2026-07-31 사고).
 *  발화가 특정 항목을 지목한 경우에는 그 규칙이 먼저 이긴다(L2) — 사용자가 물은 것을
 *  진행 순서가 덮어쓰면 질문이 무시된다. 이것은 그런 규칙이 없을 때의 **기본값**이다.
 */
function nextConditionDecision(
  context: ConversationContext,
  reason: string,
): ConversationDecision | null {
  const next = context.slots?.next;
  if (!next) return null;
  return {
    action: "ask_next_condition",
    speechAct: "ask",
    topic: "strategy",
    confidence: 1,
    reason,
    field: next.field,
    message: next.question,
    suggestions: next.suggestions,
  };
}

/** 턴 중재 — 계층 순서로 액션을 고른다(위층이 이긴다).
 *
 *  L0 워크플로 제어(라벨)            — 멈춤·취소·되돌리기·정정
 *  L1 진행 중인 하위 대화(상태)      — 보유기간 질문·연구 지표·빌더 세션
 *  L2 발화가 지목한 규칙(원문)       — 기간 하한·실행 확인·수정 되묻기·익절·재무 팩터
 *  L3 라벨 분기(분류 LLM)            — 규제 게이트·종목·지식 질문
 *  L4 상태 기본 액션(상태)           — 다음에 정할 조건 되묻기
 *  L5 폴백                           — 전략 파싱(발화가 새 정보를 담았다고 보고 넘긴다)
 *
 *  L2가 원문 정규식인 것은 이관하지 못한 부채다(nl_interpretation_contract § 11 — 턴
 *  중재권이 프론트에 있는 것이 선행 문제). 계층으로 드러내 두어 이관 대상이 어디인지
 *  코드에서 바로 보이게 한다. 새 규칙을 L2에 추가하지 않는다.
 */
export function decideConversationTurn(
  prompt: string,
  context: ConversationContext,
  classification?: SemanticClassification,
): ConversationDecision {
  // ── L2 (원문 지목) ──────────────────────────────────────────────
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

  // ── L1 (진행 중인 하위 대화) ────────────────────────────────────
  // 사용자가 "이건 바꾸겠다"고 고른 항목들의 재질문 — 진행 골격 순서대로 하나씩 묻는다.
  // 큐는 물어보는 순간 소모된다: 답하면 슬롯이 채워지고, 답하지 않으면 그 슬롯은 비어
  // 있으므로 L4(상태 기본 액션)가 나중에 다시 데려간다 — 질문이 사라지지 않는다.
  if (context.reaskNext) {
    return {
      action: "ask_next_condition",
      speechAct: "ask",
      topic: "strategy",
      confidence: 1,
      reason: "reask_after_keep_selection",
      field: context.reaskNext.field,
      message: context.reaskNext.question,
      suggestions: context.reaskNext.suggestions,
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

  const metricResearch = researchMetricDecision(prompt, context.pendingResearchMetricPrompt);
  if (metricResearch) return metricResearch;

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

  // ── L3 (라벨 분기) ──────────────────────────────────────────────
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

  // 워크플로 제어(멈춤·재개·취소·초기화·되돌리기)는 라벨 분기보다 먼저 처리한다. 백엔드가
  // 이미 규제 게이트 라벨에서는 효과를 NONE으로 강등했으므로, 여기 도달하는 제어는 전략
  // 대화 맥락에서만 나온다 — 정형 안내를 제어가 삼킬 수 없다.
  const workflowEffect = classification.workflowEffect ?? "NONE";
  if (WORKFLOW_CONTROL_EFFECTS.includes(workflowEffect as WorkflowControlEffect)) {
    return {
      action: "control_workflow",
      effect: workflowEffect as WorkflowControlEffect,
      speechAct: "unknown",
      topic: "strategy",
      confidence: 1,
      reason: `workflow_${workflowEffect.toLowerCase()}`,
      message: suggestedReply,
    };
  }

  // STOCK_ANALYSIS 포함: 전략이 진행 중일 때 종목명이 섞인 발화("제주반도체도 추가해줘")는
  // 분류기가 종목 분석으로 오분류해도 수정 요청일 수 있다 — 결정론 canned 안내로 가로채지
  // 않고 백엔드 파싱(LLM 해석)에 맡긴다(2026-07-26 종목 추가 요청 삼킴 사고).
  if (
    context.hasCurrentStrategy &&
    (intent === "STOCK_PICK" ||
      intent === "STRATEGY_PICK" ||
      intent === "ONBOARDING" ||
      intent === "STOCK_ANALYSIS")
  ) {
    return buildStrategyInputDecision(prompt, context, "preserve_active_strategy");
  }

  if (
    (intent === "STOCK_PICK" || intent === "STRATEGY_PICK") &&
    isNamedStockStrategyRequest(prompt, symbol)
  ) {
    return buildStrategyInputDecision(prompt, context, "named_stock_strategy_request");
  }

  // [규제 안전] 맞춤 조언·실계좌 매매·미제공 기능 안내는 전략 진행 중에도 반드시 나간다.
  // OFF_TOPIC도 여기서 끝낸다 — 분류 LLM은 진행 중인 전략 여부(active_strategy)를 알고
  // 판정하므로, 그 위에 프론트가 정규식/조건으로 판정을 뒤집으면 "정규식이 LLM의 의미
  // 판정을 재심하는" 구조가 되살아난다(자연어 해석 계약 위반).
  if (
    intent === "GREETING" ||
    intent === "OFF_TOPIC" ||
    intent === "UNSUPPORTED_FEATURE" ||
    intent === "PERSONAL_ADVICE" ||
    intent === "LIVE_TRADING"
  ) {
    return {
      action: "respond",
      speechAct: "unknown",
      topic: "general",
      confidence: 1,
      reason: `classified_${intent.toLowerCase()}`,
      message: suggestedReply ?? fallbackMessage(intent),
      preservesOpenQuestion: true,
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
    return {
      action: "respond_stock",
      speechAct: "ask",
      topic: "stock",
      confidence: 1,
      reason: "classified_stock_analysis",
      symbol,
      // 단일 종목 맥락에서 서버의 범용 예시를 그대로 노출하면 다른 종목을 다시
      // 선별하는 전략이 섞일 수 있다. 이 경로는 해당 종목의 진입·청산 규칙만 안내한다.
      message: singleStockResearchMessage(),
    };
  }

  // ── L2' (값 없이 지목된 수정 대상 — LLM 레인) ──────────────────────
  // "바꿀 대상은 말했는데 값이 없다"는 의미 판정이므로 LLM이 하고(clarify_target),
  // 무엇을 물을지는 그 라벨을 키로 결정론이 고른다. 이관 전에는 프론트 정규식 3종이
  // 원문을 읽어 판정했다(대원칙 1 위반, nl_interpretation_contract § 11-20).
  // 백엔드가 이미 성립 검증을 마쳤다(규제 게이트 라벨·진행 중 전략 없음이면 null) —
  // 프론트는 그 판정을 재심하지 않고 문구만 고른다.
  // 진행 순서(L4)보다 먼저다: 사용자가 지목한 항목을 진행 순서가 덮어쓰면 질문이 무시된다.
  const clarifyTarget = classification.clarifyTarget;
  if (clarifyTarget && context.hasCurrentStrategy) {
    // 무엇을 바꿀지 말하지 않은 메타 요청("조건을 바꾸고 싶어")에는 영역 칩 5개 대신
    // **지금 설정된 항목을 값과 함께** 보여주고 그대로 둘 것을 고르게 한다(FR-SA-020).
    // 사용자는 화면의 값을 보며 고르고, 고르지 않은 항목만 다시 묻는다.
    if (clarifyTarget === "condition") {
      return {
        action: "ask_keep_items",
        speechAct: "modify",
        topic: "strategy",
        confidence: 1,
        reason: "keep_or_change_selection",
        message: "그대로 둘 항목을 선택해 주세요. 선택하지 않은 항목은 다시 여쭤볼게요.",
        // 설정된 항목이 하나도 없으면 고를 것이 없다 — 그때는 기존 영역 칩으로 되돌아간다.
        suggestions: clarificationForTarget("condition")?.suggestions ?? [],
      };
    }
    const clarification = clarificationForTarget(clarifyTarget);
    if (clarification) {
      return {
        action: "respond",
        speechAct: "modify",
        topic: clarification.topic,
        confidence: 1,
        reason: clarification.reason,
        message: clarification.message,
        suggestions: clarification.suggestions,
      };
    }
  }

  // ── L4 (상태 기본 액션) — 발화가 새 정보를 담지 않은 후속 질문일 때 ──────
  // L2'(지목된 대상)보다 뒤여야 한다 — '영업이익률을 추가해 볼까?'처럼 지목과 후속
  // 질문 표현이 겹치는 발화를 진행 순서가 가로채면 사용자가 물은 항목이 무시된다.
  // "어떻게 해야 할까?"류는 새 조건을 말한 게 아니라 **다음에 할 일**을 묻는 것이다.
  // 답은 상태에 있다: 아직 정하지 않은 조건이 남아 있으면 진행 골격 순서대로 그것을 묻고,
  // 다 정해졌으면 그때는 검증 도우미의 진단이 답이다(answer_follow_up).
  // 진입 판정(isAdvisorFollowUpPrompt)이 원문 정규식인 것은 L2와 같은 이관 대상 부채다.
  if (
    context.hasCurrentStrategy &&
    Object.keys(resolveStrategyAssumptions(prompt)).length === 0 &&
    isAdvisorFollowUpPrompt(prompt)
  ) {
    return nextConditionDecision(context, "active_strategy_next_condition") ?? {
      action: "answer_follow_up",
      speechAct: "ask",
      topic: "strategy",
      confidence: 1,
      reason: "active_strategy_follow_up",
    };
  }

  // GENERAL_INVESTMENT(용어 정의·일반 지식 질문, 예: "PBR이 뭐야?")는 전략이 있어도
  // 지식 답변 경로로 보낸다 — 수정 파싱으로 흘리면 바꿀 필드가 없어 무변경 전략 요약만
  // 다시 렌더링되고 질문은 답변되지 않는다. history는 answer_general 핸들러가 실어 보낸다.
  if (intent === "GENERAL_INVESTMENT" || (intent === "UNKNOWN" && !context.hasCurrentStrategy)) {
    return {
      action: "answer_general",
      speechAct: "ask",
      topic: "general",
      confidence: 1,
      reason: `classified_${intent.toLowerCase()}`,
      preservesOpenQuestion: true,
    };
  }

  // ── L5 (폴백) — 발화가 새 전략 정보를 담았다고 보고 파싱에 넘긴다 ──────
  // 여기서 상태 기본 액션으로 가로채면 안 된다: 무엇을 말했든 다음 조건만 되묻게 되어
  // 사용자가 방금 말한 조건이 반영되지 않는다. "새 정보인가"의 판정자는 파서(LLM)다.
  return buildStrategyInputDecision(prompt, context, "classified_strategy_input");
}
