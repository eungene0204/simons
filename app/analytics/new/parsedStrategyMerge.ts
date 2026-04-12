import type { ParsedSummary } from "./strategySummary";

export interface StrategyBacktestRequest {
  symbols?: string[];
  entry?: { conditions?: Array<Record<string, unknown>> };
  exit?: { conditions?: Array<Record<string, unknown>> };
  risk?: Record<string, unknown>;
  period?: string;
  options?: Record<string, unknown>;
}

export type RequestedDomain =
  | "universe"
  | "entry"
  | "exit"
  | "risk"
  | "portfolio"
  | "backtest";

const DOMAIN_PATTERNS: Record<RequestedDomain, RegExp[]> = {
  universe: [/코스피200|코스피 200|코스피|코스닥|kospi200|kospi|kosdaq|유니버스|전체 시장|시장/iu],
  entry: [/진입|매수|골든크로스|rsi|macd|볼린저|브레이크아웃|돌파|pbr|per|roe|부채비율|시총|거래대금|필터|저평가|ai/iu],
  exit: [/청산|매도|보유|데드크로스|하락/iu],
  risk: [/손절|익절|트레일링|리스크|mdd/iu],
  portfolio: [/최대\s*\d+\s*종목|\d+\s*개\s*종목|\d+\s*종목|포트폴리오|리밸런싱|리밸런스|분산|집중/iu],
  backtest: [/백테스트|테스트 기간|전체 데이터|초기자금|자본금|원금|만원|억원?|\d[\d,]*원/iu],
};

function hasMatch(text: string, patterns: RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(text));
}

export function detectRequestedDomains(prompt: string): Set<RequestedDomain> {
  const normalizedPrompt = prompt.trim();
  const domains = new Set<RequestedDomain>();

  if (!normalizedPrompt) return domains;

  (Object.keys(DOMAIN_PATTERNS) as RequestedDomain[]).forEach((domain) => {
    if (hasMatch(normalizedPrompt, DOMAIN_PATTERNS[domain])) {
      domains.add(domain);
    }
  });

  return domains;
}

function mergeParsedSummary(
  previous: ParsedSummary,
  next: ParsedSummary,
  requestedDomains: Set<RequestedDomain>
): ParsedSummary {
  return {
    ...next,
    universe: requestedDomains.has("universe") ? next.universe : previous.universe,
    fundamental_filters: requestedDomains.has("entry") ? next.fundamental_filters : previous.fundamental_filters,
    entry_signals: requestedDomains.has("entry") ? next.entry_signals : previous.entry_signals,
    exit_signals: requestedDomains.has("exit") ? next.exit_signals : previous.exit_signals,
    max_positions: requestedDomains.has("portfolio") ? next.max_positions : previous.max_positions,
    hold_period_days: requestedDomains.has("exit") ? next.hold_period_days : previous.hold_period_days,
    rebalancing_period: requestedDomains.has("portfolio") ? next.rebalancing_period : previous.rebalancing_period,
    stop_loss_pct: requestedDomains.has("risk") ? next.stop_loss_pct : previous.stop_loss_pct,
    take_profit_pct: requestedDomains.has("risk") ? next.take_profit_pct : previous.take_profit_pct,
    backtest_period: requestedDomains.has("backtest") ? next.backtest_period : previous.backtest_period,
    initial_capital: requestedDomains.has("backtest") ? next.initial_capital : previous.initial_capital,
  };
}

function mergeBacktestRequest(
  previous: StrategyBacktestRequest | null | undefined,
  next: StrategyBacktestRequest | null | undefined,
  requestedDomains: Set<RequestedDomain>
): StrategyBacktestRequest | null {
  if (!next) return previous ?? null;
  if (!previous) return next;

  const mergedRisk = {
    ...(previous.risk ?? {}),
    ...(next.risk ?? {}),
  };

  if (!requestedDomains.has("portfolio")) {
    mergedRisk.position_size_pct = previous.risk?.position_size_pct;
    mergedRisk.max_positions = previous.risk?.max_positions;
    mergedRisk.rebalancing_period = previous.risk?.rebalancing_period;
  }

  if (!requestedDomains.has("exit")) {
    mergedRisk.max_holding_days = previous.risk?.max_holding_days;
  }

  if (!requestedDomains.has("risk")) {
    mergedRisk.stop_loss_pct = previous.risk?.stop_loss_pct;
    mergedRisk.take_profit_pct = previous.risk?.take_profit_pct;
    mergedRisk.trailing_stop_pct = previous.risk?.trailing_stop_pct;
    mergedRisk.max_mdd_limit_pct = previous.risk?.max_mdd_limit_pct;
  }

  if (!requestedDomains.has("backtest")) {
    mergedRisk.init_cash = previous.risk?.init_cash;
  }

  return {
    ...previous,
    ...next,
    symbols: requestedDomains.has("universe") ? (next.symbols ?? previous.symbols) : previous.symbols,
    entry: requestedDomains.has("entry") ? (next.entry ?? previous.entry) : previous.entry,
    exit: requestedDomains.has("exit") ? (next.exit ?? previous.exit) : previous.exit,
    risk: mergedRisk,
    period: requestedDomains.has("backtest") ? (next.period ?? previous.period) : previous.period,
    options: requestedDomains.has("backtest")
      ? { ...(previous.options ?? {}), ...(next.options ?? {}) }
      : previous.options,
  };
}

function clarificationLooksLikeEntryRegression(
  clarificationQuestion: string | null | undefined,
  previousParsed: ParsedSummary,
  requestedDomains: Set<RequestedDomain>
): boolean {
  if (!clarificationQuestion || requestedDomains.has("entry")) {
    return false;
  }

  const previousHadEntry =
    previousParsed.fundamental_filters.length > 0 || previousParsed.entry_signals.length > 0;

  if (!previousHadEntry) {
    return false;
  }

  return /진입 조건|매수 조건|종목을 선택|어떤 조건으로 종목/u.test(clarificationQuestion);
}

export function mergeStrategyModification(params: {
  previousParsed: ParsedSummary | null;
  nextParsed: ParsedSummary;
  previousBacktestRequest?: StrategyBacktestRequest | null;
  nextBacktestRequest?: StrategyBacktestRequest | null;
  userPrompt: string;
  clarificationQuestion?: string | null;
}) {
  const requestedDomains = detectRequestedDomains(params.userPrompt);

  if (!params.previousParsed || requestedDomains.size === 0) {
    return {
      parsed: params.nextParsed,
      backtestRequest: params.nextBacktestRequest ?? params.previousBacktestRequest ?? null,
      requestedDomains,
      shouldReusePreviousClarification: false,
    };
  }

  const parsed = mergeParsedSummary(params.previousParsed, params.nextParsed, requestedDomains);
  const backtestRequest = mergeBacktestRequest(
    params.previousBacktestRequest,
    params.nextBacktestRequest,
    requestedDomains
  );

  return {
    parsed,
    backtestRequest,
    requestedDomains,
    shouldReusePreviousClarification: clarificationLooksLikeEntryRegression(
      params.clarificationQuestion,
      params.previousParsed,
      requestedDomains
    ),
  };
}
