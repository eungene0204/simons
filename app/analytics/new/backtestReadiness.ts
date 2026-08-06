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

/** 슬롯 하나가 채워졌는가 — 프론트의 **유일한** 빈 슬롯 술어.
 *
 * 백엔드 정본(engine/strategy_slots.py)의 `_decided`/`_has_value`/`_explicit_ok` 3축을
 * 그대로 옮긴 것이며, 되묻기 게이트와 진행률 패널이 **둘 다 이 함수만** 부른다.
 * 프론트에 사본이 둘 이상 생기면 반드시 갈라진다 — 2026-07-29: 게이트만 고치고 패널이
 * 낡은 채 남아, 백테스트 창이 자동 확정됐는데 진행률 체크가 안 됐다. 같은 가드가
 * 그때 함께 드러낸 기존 드리프트가 3종 더 있었다(매도 조건·리스크 관리·리밸런싱 거부).
 *
 * 정본과의 일치는 계약 픽스처(`__fixtures__/slot-judgments.json`)가 대조한다.
 */
export function isSlotFilled(
  field: MissingBacktestCondition["field"],
  parsed: ParsedSummary | null | undefined,
  options: BacktestReadinessOptions = {},
): boolean {
  if (!parsed) return false;
  const explicitFields = options.explicitFields;
  const requireExplicit = options.requireExplicitConfiguration === true;
  const targetSymbolCount = parsed.target_symbols?.length ?? 0;
  const hasRebalancing = Boolean(
    parsed.rebalancing_period && parsed.rebalancing_period !== "none",
  );

  // ① 질문이 이미 끝난 필드 — 값 유무·provenance와 무관하다(백엔드 _decided).
  if (field === "rebalancing" && (targetSymbolCount === 1 || options.allowNoRebalancing === true)) {
    return true;
  }
  // 신규 상장 코호트(FR-STR-073)는 창 시작이 상장일 하한으로 확정돼 다른 답이 성립하지 않는다.
  if (field === "backtest_period" && parsed.listing_from) return true;

  // ② 값이 있는가(백엔드 _has_value). 각 슬롯의 입력 필드 집합은 provenance와 같아야 한다.
  let hasValue: boolean;
  switch (field) {
    case "universe":
      hasValue =
        nonEmpty(parsed.universe) ||
        nonEmpty(parsed.target_symbols) ||
        nonEmpty(parsed.sector) ||
        Boolean(parsed.new_listing_only);
      break;
    case "entry":
      // 지정 종목은 진입 조건이 아니다 — 종목이 정해져도 매수 시점 규칙이 없으면 0거래다.
      hasValue =
        nonEmpty(parsed.entry_signals) ||
        nonEmpty(parsed.fundamental_filters) ||
        Boolean(parsed.ranking_metric);
      break;
    case "exit":
      // 손절·익절은 '리스크 관리' 슬롯이지 매도 조건이 아니다 — 배지엔 함께 나오지만
      // 판정은 정본을 따른다(그러지 않으면 체크는 켜지고 시스템은 청산을 되묻는다).
      hasValue =
        nonEmpty(parsed.exit_signals) ||
        (parsed.hold_period_days ?? 0) > 0 ||
        hasRebalancing;
      break;
    case "max_positions":
      // 분위 그룹 전략(FR-BT-060b)의 이 자리는 '그룹당 보유 상한'이다 — cap은 물질화
      // 기본값이 없어 값의 존재가 곧 사용자 답변이다(백엔드 _has_value와 동형).
      hasValue = parsed.ranking_quantile_groups
        ? parsed.ranking_group_cap != null
        : (parsed.max_positions ?? 0) > 0;
      break;
    case "rebalancing":
      hasValue = hasRebalancing;
      break;
    case "stop_loss":
      hasValue = (parsed.stop_loss_pct ?? 0) > 0;
      break;
    case "take_profit":
      hasValue = (parsed.take_profit_pct ?? 0) > 0;
      break;
    case "backtest_period":
      hasValue =
        nonEmpty(parsed.backtest_period) ||
        nonEmpty(parsed.backtest_start_date) ||
        nonEmpty(parsed.backtest_end_date);
      break;
    case "initial_capital":
      hasValue = (parsed.initial_capital ?? 0) > 0;
      break;
  }
  if (!hasValue) return false;

  // ③ 사용자가 실제로 말했는가(백엔드 _explicit_ok). 기본값이 물질화되는 필드만 본다.
  if (!requireExplicit) return true;
  switch (field) {
    case "universe":
      return isExplicit("universe", explicitFields, parsed);
    case "max_positions":
      // 분위 그룹 모드의 cap은 물질화 기본값이 없어 provenance가 불필요(백엔드와 동형).
      if (parsed.ranking_quantile_groups) return true;
      return targetSymbolCount > 0 || isExplicit("max_positions", explicitFields);
    case "rebalancing":
      return isExplicit("rebalancing", explicitFields);
    case "backtest_period":
      return isExplicit("backtest_period", explicitFields);
    case "initial_capital":
      return isExplicit("initial_capital", explicitFields);
    default:
      return true;   // 진입·청산·손절·익절은 기본값이 없어 값의 존재가 곧 사용자 입력이다
  }
}

/** 진행 골격 8칸 중 채워진 슬롯 라벨(백엔드 filled_slots와 동형 — 리스크 관리는 손절·익절 둘 다). */
export const SLOT_LABELS: Record<MissingBacktestCondition["field"], string> = {
  universe: "유니버스",
  entry: "매수 조건",
  exit: "매도 조건",
  max_positions: "최대 보유",
  rebalancing: "리밸런싱",
  stop_loss: "리스크 관리",
  take_profit: "리스크 관리",
  backtest_period: "백테스트 기간",
  initial_capital: "초기 자본",
};

// 슬롯별 되묻기 문구·칩. 판정(isSlotFilled)과 같은 파일에 둔다 — 백엔드 정본이
// _QUESTIONS를 판정 옆에 두는 것과 같은 이유로, 슬롯이 늘 때 한쪽만 갱신되는 것을 막는다.
const SLOT_PROMPTS: Record<
  MissingBacktestCondition["field"],
  { question: string; suggestions: string[] }
> = {
  universe: {
    question: "대상 시장·종목이 빠져 있습니다. 어떤 시장·종목을 대상으로 할까요?",
    suggestions: ["코스피200", "코스피", "코스닥", "코스피+코스닥"],
  },
  entry: {
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
  },
  exit: {
    question: "청산 조건이 빠져 있습니다. 어떤 조건에서 청산할까요?",
    suggestions: ["데드크로스(5일/20일) 발생 시 매도", "20일 보유 후 청산", "RSI 70 이상에서 매도"],
  },
  max_positions: {
    question: "포트폴리오에 최대 몇 종목을 담을까요?",
    suggestions: ["최대 5종목", "최대 10종목", "최대 20종목"],
  },
  rebalancing: {
    question: "리밸런싱 주기가 빠져 있습니다. 포트폴리오를 얼마나 자주 다시 구성할까요?",
    suggestions: ["매주 리밸런싱", "매월 리밸런싱", "분기마다 리밸런싱", "안 함"],
  },
  stop_loss: {
    question: "손절 기준이 빠져 있습니다. 손절 기준을 몇 %로 설정할까요?",
    suggestions: ["손절 -5%", "손절 -10%", "손절 -15%"],
  },
  take_profit: {
    question: "익절 기준이 빠져 있습니다. 익절 기준을 몇 %로 설정할까요?",
    suggestions: ["익절 10%", "익절 20%", "익절 30%"],
  },
  backtest_period: {
    question: "어느 기간의 과거 데이터로 백테스트할까요?",
    suggestions: ["최근 1년 데이터", "최근 3년 데이터", "최근 5년 데이터", "사용 가능한 전체 데이터"],
  },
  initial_capital: {
    question: "초기 투자 자금을 얼마로 설정할까요?",
    suggestions: ["500만원", "1,000만원", "3,000만원", "5,000만원"],
  },
};

/** 제시한 선택지가 곧 답의 전부인 슬롯 — 자유 입력 칩("직접 입력")을 붙이지 않는다.
 *  유니버스는 우리가 지원하는 시장 범위가 위 네 개로 닫혀 있어, 자유 입력 칩이
 *  "다른 답도 된다"는 없는 여지를 만든다. 빌더 칩 경로는 이미 같은 판정을 한다
 *  (page.tsx `withBuilderNavigationSuggestions`의 유니버스 단계 분기). */
export function isClosedChoiceSlot(field: string | null | undefined): boolean {
  return field === "universe";
}

// 진행 순서 = 사용자에게 보이는 골격 순서(백엔드 FIELD_ORDER와 동일).
export const SLOT_FIELD_ORDER: MissingBacktestCondition["field"][] = [
  "universe", "entry", "exit", "max_positions", "rebalancing",
  "stop_loss", "take_profit", "backtest_period", "initial_capital",
];

// 분위 그룹 전략(FR-BT-060b) 전용 '최대 보유' 되묻기 — 그룹이 편입 구간을 정의하므로
// 일반 질문("포트폴리오에 최대 몇 종목")은 상황에 맞지 않는다. 답은 그룹당 보유 상한이며
// 칩은 그룹 수(최대 10) 이상에서 시작한다(2026-08-06 지시, 백엔드
// strategy_slots._QUANTILE_MAX_POSITIONS_QUESTION과 동형).
const QUANTILE_MAX_POSITIONS_PROMPT: { question: string; suggestions: string[] } = {
  question:
    "각 분위 그룹에 최대 몇 종목을 담을까요? (그룹 내 랭킹 상위순, 모든 그룹 동일 적용)",
  suggestions: ["그룹당 10종목", "그룹당 20종목", "그룹당 30종목"],
};

function promptFor(
  field: MissingBacktestCondition["field"],
  parsed: ParsedSummary | undefined | null,
): { question: string; suggestions: string[] } {
  if (field === "max_positions" && parsed?.ranking_quantile_groups) {
    return QUANTILE_MAX_POSITIONS_PROMPT;
  }
  return SLOT_PROMPTS[field];
}

/** 슬롯 하나의 되묻기 문구·선택지(정본 표에서 그대로). 재질문 큐가 이미 채워진 슬롯을
 *  다시 물을 때 쓴다 — getNextMissingBacktestCondition은 '비어 있는 첫 슬롯'만 내므로. */
export function promptForSlot(
  field: MissingBacktestCondition["field"],
  parsed?: ParsedSummary | null,
): MissingBacktestCondition {
  return { field, ...promptFor(field, parsed) };
}

export function getNextMissingBacktestCondition(
  parsed: ParsedSummary | undefined | null,
  options: BacktestReadinessOptions = {},
): MissingBacktestCondition | null {
  if (!parsed) {
    return { field: "universe", ...SLOT_PROMPTS.universe };
  }
  const field = SLOT_FIELD_ORDER.find((f) => !isSlotFilled(f, parsed, options));
  return field ? { field, ...promptFor(field, parsed) } : null;
}

/** 채워진 진행 골격 슬롯 라벨(순서 보존). 백엔드 filled_slots와 동형 — 리스크 관리는
 *  손절·익절이 **둘 다** 채워져야 완료다. */
export function getFilledSlotLabels(
  parsed: ParsedSummary | undefined | null,
  options: BacktestReadinessOptions = {},
): string[] {
  const byLabel = new Map<string, boolean>();
  for (const field of SLOT_FIELD_ORDER) {
    const label = SLOT_LABELS[field];
    const filled = isSlotFilled(field, parsed, options);
    byLabel.set(label, (byLabel.get(label) ?? true) && filled);
  }
  return [...byLabel.entries()].filter(([, filled]) => filled).map(([label]) => label);
}

export function isBacktestReady(
  parsed: ParsedSummary | undefined | null,
  options: BacktestReadinessOptions = {},
): boolean {
  return parsed != null && getNextMissingBacktestCondition(parsed, options) === null;
}
