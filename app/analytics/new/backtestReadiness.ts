// 백테스트 최소 조건 게이트(프론트) — 유니버스·진입·청산·손절·익절이 모두 갖춰졌는지 판정한다.
// [정책 2026-07-22] 조건이 비면 "현재 상태로도 실행 가능"으로 넘기지 않고 채우도록 가이드하며,
// 다 채우기 전엔 '백테스트 실행' 버튼을 숨긴다. 백엔드 detect_incomplete_backtest_conditions와
// 동일한 규칙(진입은 신호·랭킹·재무필터만 인정, 청산은 매도신호·보유기간·정기 리밸런싱)을
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

// 사용자가 실제로 말한 설정 필드(백엔드 응답 `explicit_fields`). 판정 근거는 인터프리터
// LLM의 구조화 출력뿐이며, 프론트는 그 결과를 읽기만 한다.
//
// [2026-07-29 계약 전환] 이전에는 이 파일이 사용자 원문을 정규식으로 재분석해
// "말했나"를 스스로 판정했다(hasExplicit* 5종). 그것은 자연어 해석이므로 LLM 소관인데
// (nl_interpretation_contract § 판정 기준), 실제로 양방향 사고를 냈다:
//   · 오탐 — '거래대금 20억 원'을 초기 자본 명시로 오인해 되묻기를 삼킴('원자력 관련주')
//   · 미탐 — '보유 종목은 10개'를 못 잡아 진행률 미체크('부채비율·ROE 보유 조건')
// 두 사고 모두 원문 정규식이라는 같은 원인이라 채널 자체를 백엔드 provenance로 교체했다.
export type ExplicitField =
  | "universe"
  | "max_positions"
  | "rebalancing"
  | "backtest_period"
  | "initial_capital";

export type BacktestReadinessOptions = {
  allowNoRebalancing?: boolean;
  explicitFields?: readonly string[];
  requireExplicitConfiguration?: boolean;
};

function nonEmpty(value: unknown): boolean {
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

/** 지정 종목은 그 자체가 사용자의 유니버스 명시다(백엔드 spec의 universe.symbols와 동형). */
export function isExplicit(
  field: ExplicitField,
  explicitFields: readonly string[] | undefined,
  parsed?: ParsedSummary | null,
): boolean {
  if (field === "universe" && parsed?.target_symbols?.length) return true;
  return (explicitFields ?? []).includes(field);
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
  // 지정 종목(target_symbols)은 진입 조건으로 인정하지 않는다 — 종목이 정해져도 매수
  // 시점 규칙이 없으면 엔진은 매수를 전혀 만들지 않는다(signals.py: 빈 조건 그룹=all-False,
  // 0거래). 테마 유니버스 자동 적용(FR-STR-071 ④)이 target_symbols를 채우면서 매수 조건
  // 질문이 통째로 생략되던 버그(2026-07-25)의 원인.
  const hasEntry =
    nonEmpty(parsed.entry_signals) ||
    nonEmpty(parsed.fundamental_filters) ||
    Boolean(parsed.ranking_metric);
  const rebal = parsed.rebalancing_period;
  const hasRebalancing = Boolean(rebal && rebal !== "none");
  const hasExit =
    nonEmpty(parsed.exit_signals) || Boolean(parsed.hold_period_days) || hasRebalancing;
  const hasStop = parsed.stop_loss_pct != null && parsed.stop_loss_pct > 0;
  const hasTake = parsed.take_profit_pct != null && parsed.take_profit_pct > 0;
  const hasMaxPositions = parsed.max_positions != null && parsed.max_positions > 0;
  const hasBacktestPeriod = nonEmpty(parsed.backtest_period);
  const hasInitialCapital = parsed.initial_capital != null && parsed.initial_capital > 0;
  const isSingleAsset = nonEmpty(parsed.target_symbols);
  // 단독 종목(지정 1개)이 아니면(유니버스/다종목) 리밸런싱 주기도 필수다(단독 종목은 교체가
  // 없어 제외). 지정 종목이라도 여러 개(테마 유니버스 자동 적용 등)면 포트폴리오이므로
  // 묻는다 — '지정 종목 존재=단독'으로 판정해 질문 없이 기본값 '설정 안 함'으로 확정되던
  // 사고(2026-07-28 '모바일솔루션 관련주'). 백엔드 _missing_backtest_conditions와 동일 규칙.
  const isSingleSymbol = (parsed.target_symbols?.length ?? 0) === 1;
  const rebalancingOk =
    isSingleSymbol || hasRebalancing || options.allowNoRebalancing === true;
  const explicitFields = options.explicitFields;
  const requireExplicit = options.requireExplicitConfiguration === true;

  if (!hasUniverse || (requireExplicit && !isExplicit("universe", explicitFields, parsed))) {
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
        "골든크로스(5일/20일) 발생 시 매수",
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
      suggestions: ["데드크로스(5일/20일) 발생 시 매도", "20일 보유 후 청산", "RSI 70 이상에서 매도"],
    };
  }
  if (
    !hasMaxPositions ||
    (requireExplicit && !isSingleAsset && !isExplicit("max_positions", explicitFields))
  ) {
    return {
      field: "max_positions",
      question: "포트폴리오에 최대 몇 종목을 담을까요?",
      suggestions: ["최대 5종목", "최대 10종목", "최대 20종목"],
    };
  }
  if (
    !rebalancingOk ||
    // '안 함' 선택은 사용자의 명시적 결정이지만 LLM 스펙에서는 rebalance_frequency=null이라
    // 미언급과 구분되지 않는다 — 프론트가 그 선택을 들고 있으므로(allowNoRebalancing)
    // provenance와 동등하게 취급한다.
    (requireExplicit && !isSingleSymbol &&
      !isExplicit("rebalancing", explicitFields) && options.allowNoRebalancing !== true)
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
    (requireExplicit && !isExplicit("backtest_period", explicitFields))
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
    (requireExplicit && !isExplicit("initial_capital", explicitFields))
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
