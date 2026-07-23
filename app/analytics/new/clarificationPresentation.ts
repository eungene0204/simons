import type { ParsedSummary } from "@/lib/strategy-summary";

import {
  getNextMissingBacktestCondition,
  type MissingBacktestCondition,
} from "./backtestReadiness";

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
      : `세부 조건이 빠져 있습니다. ${backendQuestion}`,
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
