import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  getNextMissingBacktestCondition,
  isExplicit,
  type BacktestReadinessOptions,
  type MissingBacktestCondition,
} from "./backtestReadiness";
import { t } from "@/lib/i18n";

export type PresentedClarification = {
  question: string;
  suggestions: string[];
  missingCondition: MissingBacktestCondition | null;
};

type ClarificationInput = {
  parsed: ParsedSummary;
  backendQuestion?: string | null;
  backendSuggestions?: string[] | null;
  /** 되묻기 게이트와 같은 판정 입력 — 빠지면 '안 함'으로 거부한 슬롯을 다시 묻는다
   *  (2026-11-12: 기간만 바꿨는데 '익절 안 함'으로 정한 익절을 반복해서 물었다). */
  gateOptions?: BacktestReadinessOptions;
};

const DIRECT_INPUT = "직접 입력";
const STOCK_TYPO_QUESTION = "입력하신 종목명을 인식하지 못했어요";

// 사용자가 종목 수를 직접 말했는가는 인터프리터 LLM이 판정한 provenance(explicit_fields)로만 본다 —
// 원문을 정규식으로 다시 읽지 않는다(2026-11-12 원문 판정 제거, CLAUDE.md 대원칙 1).
function shouldSuppressContradictedQuestion(
  parsed: ParsedSummary,
  question: string,
  gateOptions: BacktestReadinessOptions | undefined,
): boolean {
  const portfolioSizeStated = isExplicit("max_positions", gateOptions?.explicitFields);
  if (
    question.includes(STOCK_TYPO_QUESTION) &&
    !parsed.target_symbols?.length &&
    portfolioSizeStated
  ) {
    return true;
  }
  if (
    question.includes("상위 몇 종목") &&
    parsed.max_positions != null &&
    portfolioSizeStated
  ) {
    return true;
  }
  // 진입(종목 선정) 조건이 이미 있는데 "어떤 조건으로 종목을 선택할까요?"를 되묻는 것은
  // parsed에 모순된다 — 완성된 전략을 확정한 뒤 다시 진입을 묻는 사고를 막는다. 진입이
  // 정말 비어 있으면 이 함수 호출 전에 getNextMissingBacktestCondition이 먼저 가로챈다.
  if (
    question.includes("종목을 선택") &&
    (parsed.entry_signals?.length ||
      parsed.fundamental_filters?.length ||
      Boolean(parsed.ranking_metric) ||
      parsed.target_symbols?.length)
  ) {
    return true;
  }
  return false;
}

export function presentStrategyClarification({
  parsed,
  backendQuestion,
  backendSuggestions,
  gateOptions,
}: ClarificationInput): PresentedClarification | null {
  const missingCondition = getNextMissingBacktestCondition(parsed, gateOptions);
  if (missingCondition) {
    return {
      question: missingCondition.question,
      suggestions: missingCondition.suggestions,
      missingCondition,
    };
  }

  if (
    !backendQuestion ||
    shouldSuppressContradictedQuestion(parsed, backendQuestion, gateOptions)
  ) {
    return null;
  }

  return {
    question: backendQuestion.includes("빠져 있습니다")
      ? backendQuestion
      : t("세부 조건이 빠져 있습니다. {0}", backendQuestion),
    suggestions: backendSuggestions?.length
      ? backendSuggestions
      : [DIRECT_INPUT],
    missingCondition: null,
  };
}

export function shouldContinueWithSingleAssetBuilder(
  parsed: ParsedSummary,
): boolean {
  return Boolean(
    parsed.target_symbols?.length === 1 &&
      !parsed.entry_signals?.length &&
      !parsed.fundamental_filters?.length &&
      !parsed.ranking_metric,
  );
}
