// 백테스트 최소 조건 게이트(프론트) — 유니버스·진입·청산·손절·익절이 모두 갖춰졌는지 판정한다.
// [정책 2026-07-22] 조건이 비면 "현재 상태로도 실행 가능"으로 넘기지 않고 채우도록 가이드하며,
// 다 채우기 전엔 '백테스트 실행' 버튼을 숨긴다. 백엔드 detect_incomplete_backtest_conditions와
// 동일한 규칙(진입은 랭킹·재무필터·지정 종목도 인정, 청산은 매도신호·보유기간·정기 리밸런싱)을
// 프론트에도 두어, 백엔드 clarification 라우팅과 무관하게 버튼 노출을 확실히 막는다.

import type { ParsedSummary } from "@/lib/strategy-summary";

export type MissingBacktestCondition = {
  field:
    | "universe"
    | "entry"
    | "exit"
    | "max_positions"
    | "rebalancing"
    | "stop_loss"
    | "take_profit"
    | "backtest_period"
    | "initial_capital";
  question: string;
  suggestions: string[];
};

export type BacktestReadinessOptions = {
  allowNoRebalancing?: boolean;
  prompt?: string;
  requireExplicitConfiguration?: boolean;
};

function nonEmpty(value: unknown): boolean {
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

export function hasExplicitUniverse(
  prompt: string,
  parsed?: ParsedSummary | null,
): boolean {
  return Boolean(
    parsed?.target_symbols?.length ||
    /코스피\s*200|코스피|코스닥|KOSPI\s*200|KOSPI|KOSDAQ|ETF|유니버스|투자\s*대상|대상\s*(?:시장|종목)/i.test(
      prompt,
    ),
  );
}

export function hasExplicitMaxPositions(prompt: string): boolean {
  return /(?:최대|상위)\s*\d+\s*(?:개|종목)|\d+\s*(?:개\s*)?종목|보유\s*(?:종목\s*)?\d+/i.test(
    prompt,
  );
}

export function hasExplicitRebalancing(prompt: string): boolean {
  return /리밸런싱|리밸런스|종목\s*교체|매일|매주|매월|월마다|분기(?:마다)?|매년|연간|안\s*함|하지\s*않/i.test(
    prompt,
  );
}

export function hasExplicitBacktestPeriod(prompt: string): boolean {
  return /백테스트\s*(?:기간\s*)?(?:\d+\s*(?:년|개월|일)|전체)|최근\s*\d+\s*(?:년|개월|일)|전체\s*(?:기간|데이터)|전\s*기간|\d{4}\s*년?\s*(?:부터|~|-)/i.test(
    prompt,
  );
}

export function hasExplicitInitialCapital(prompt: string): boolean {
  return /(?:초기\s*(?:자금|자본)|투자\s*(?:금액|자금|자본)|시드\s*머니)\s*(?:은|을|:)?\s*\d[\d,]*(?:\.\d+)?\s*(?:조|억|천만|백만|만|천)?\s*원?|\d[\d,]*(?:\.\d+)?\s*(?:조|억|천만|백만|만|천)?\s*원/i.test(
    prompt,
  );
}

export function getNextMissingBacktestCondition(
  parsed: ParsedSummary | undefined | null,
  options: BacktestReadinessOptions = {},
): MissingBacktestCondition | null {
  if (!parsed) {
    return {
      field: "universe",
      question: "대상 시장·종목이 빠져 있습니다. 어떤 시장·종목을 대상으로 할까요?",
      suggestions: ["코스피200", "코스피", "코스닥", "코스피+코스닥"],
    };
  }
  const hasUniverse =
    nonEmpty(parsed.universe) || nonEmpty(parsed.target_symbols) || nonEmpty(parsed.sector);
  const hasEntry =
    nonEmpty(parsed.entry_signals) ||
    nonEmpty(parsed.fundamental_filters) ||
    Boolean(parsed.ranking_metric) ||
    nonEmpty(parsed.target_symbols);
  const rebal = parsed.rebalancing_period;
  const hasRebalancing = Boolean(rebal && rebal !== "none");
  const hasExit =
    nonEmpty(parsed.exit_signals) || Boolean(parsed.hold_period_days) || hasRebalancing;
  const hasStop = parsed.stop_loss_pct != null && parsed.stop_loss_pct > 0;
  const hasTake = parsed.take_profit_pct != null && parsed.take_profit_pct > 0;
  const hasMaxPositions = parsed.max_positions != null && parsed.max_positions > 0;
  const hasBacktestPeriod = nonEmpty(parsed.backtest_period);
  const hasInitialCapital = parsed.initial_capital != null && parsed.initial_capital > 0;
  // 단독 종목이 아니면(유니버스/다종목) 리밸런싱 주기도 필수다(단독 종목은 교체가 없어 제외).
  const isSingleAsset = nonEmpty(parsed.target_symbols);
  const rebalancingOk =
    isSingleAsset || hasRebalancing || options.allowNoRebalancing === true;
  const prompt = options.prompt ?? "";
  const requireExplicit = options.requireExplicitConfiguration === true;

  if (!hasUniverse || (requireExplicit && !hasExplicitUniverse(prompt, parsed))) {
    return {
      field: "universe",
      question: "대상 시장·종목이 빠져 있습니다. 어떤 시장·종목을 대상으로 할까요?",
      suggestions: ["코스피200", "코스피", "코스닥", "코스피+코스닥"],
    };
  }
  if (!hasEntry) {
    return {
      field: "entry",
      question: "매수 조건이 빠져 있습니다. 어떤 조건에서 매수할까요?",
      suggestions: [
        "골든크로스 발생 시 매수",
        "RSI 30 이하에서 매수",
        "MACD 골든크로스 매수",
        "볼린저밴드 하단 터치 시 매수",
        "20일 고점 돌파 시 매수",
        "거래량 급증 시 매수",
        "PER 10 이하",
        "ROE 15% 이상",
      ],
    };
  }
  if (!hasExit) {
    return {
      field: "exit",
      question: "청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?",
      suggestions: ["데드크로스 발생 시 매도", "20일 보유 후 청산", "RSI 70 이상에서 매도"],
    };
  }
  if (
    !hasMaxPositions ||
    (requireExplicit && !isSingleAsset && !hasExplicitMaxPositions(prompt))
  ) {
    return {
      field: "max_positions",
      question: "포트폴리오에 최대 몇 종목을 담을까요?",
      suggestions: ["최대 5종목", "최대 10종목", "최대 20종목"],
    };
  }
  if (
    !rebalancingOk ||
    (requireExplicit && !isSingleAsset && !hasExplicitRebalancing(prompt))
  ) {
    return {
      field: "rebalancing",
      question:
        "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
      suggestions: ["매주 리밸런싱", "매월 리밸런싱", "분기마다 리밸런싱", "안 함"],
    };
  }
  if (!hasStop) {
    return {
      field: "stop_loss",
      question: "손절 기준이 빠져 있습니다. 손절 기준을 몇 %로 설정할까요?",
      suggestions: ["손절 5%", "손절 10%", "손절 15%"],
    };
  }
  if (!hasTake) {
    return {
      field: "take_profit",
      question: "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
      suggestions: ["익절 10%", "익절 20%", "익절 30%"],
    };
  }
  if (
    !hasBacktestPeriod ||
    (requireExplicit && !hasExplicitBacktestPeriod(prompt))
  ) {
    return {
      field: "backtest_period",
      question: "어느 기간의 과거 데이터로 백테스트할까요?",
      suggestions: [
        "최근 1년 데이터",
        "최근 3년 데이터",
        "최근 5년 데이터",
        "사용 가능한 전체 데이터",
      ],
    };
  }
  if (
    !hasInitialCapital ||
    (requireExplicit && !hasExplicitInitialCapital(prompt))
  ) {
    return {
      field: "initial_capital",
      question: "초기 투자 자금을 얼마로 설정할까요?",
      suggestions: ["500만원", "1,000만원", "3,000만원", "5,000만원"],
    };
  }
  return null;
}

export function isBacktestReady(
  parsed: ParsedSummary | undefined | null,
  options: BacktestReadinessOptions = {},
): boolean {
  return parsed != null && getNextMissingBacktestCondition(parsed, options) === null;
}
