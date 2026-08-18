import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  getNextMissingBacktestCondition,
  type MissingBacktestCondition,
} from "./backtestReadiness";
import { t } from "@/lib/i18n";

export type PresentedClarification = {
  question: string;
  suggestions: string[];
  missingCondition: MissingBacktestCondition | null;
};

type ClarificationInput = {
  prompt: string;
  parsed: ParsedSummary;
  backendQuestion?: string | null;
  backendSuggestions?: string[] | null;
};

const DIRECT_INPUT = "직접 입력";
const STOCK_TYPO_QUESTION = "입력하신 종목명을 인식하지 못했어요";

function hasExplicitPortfolioSize(prompt: string): boolean {
  return (
    /(?:최대\s*)?\d+\s*종목/i.test(prompt) ||
    /포트폴리오|동시\s*보유/i.test(prompt)
  );
}

function shouldSuppressContradictedQuestion(
  prompt: string,
  parsed: ParsedSummary,
  question: string,
): boolean {
  if (
    question.includes(STOCK_TYPO_QUESTION) &&
    !parsed.target_symbols?.length &&
    hasExplicitPortfolioSize(prompt)
  ) {
    return true;
  }
  if (question.includes("배당") && !prompt.includes("배당")) {
    return true;
  }
  if (
    question.includes("상위 몇 종목") &&
    parsed.max_positions != null &&
    hasExplicitPortfolioSize(prompt)
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
  prompt,
  parsed,
  backendQuestion,
  backendSuggestions,
}: ClarificationInput): PresentedClarification | null {
  const missingCondition = getNextMissingBacktestCondition(parsed);
  if (missingCondition) {
    return {
      question: missingCondition.question,
      suggestions: missingCondition.suggestions,
      missingCondition,
    };
  }

  if (
    !backendQuestion ||
    shouldSuppressContradictedQuestion(prompt, parsed, backendQuestion)
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
