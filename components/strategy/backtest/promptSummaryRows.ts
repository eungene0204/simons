import { resolveUniverseDisplayName } from "@/lib/strategy-summary";
import { t } from "@/lib/i18n";

export interface PromptSummarySource {
  universeName: string;
  entryBlocks?: string[];
  exitBlocks?: string[];
  positionText?: string;
  riskText?: string;
  rebalancingText?: string;
  backtestPeriodText?: string;
  initialCapitalText?: string;
}

export interface PromptSummaryRow {
  label: string;
  values: string[];
}

/**
 * 결과 화면 "프롬프트" 팝오버의 전략 요약 행 — 대화 카드(ParsedSummaryBubble)와 같은 항목을
 * 같은 순서로 보인다: 유니버스 → 진입 신호 → 청산 신호 → 백테스트 기간 → 초기 자본 → 리스크.
 * 백테스트 기간은 상대 라벨("3년") 뒤에 실제 실행 구간(result.dates 양끝)을 한 줄 더 붙인다 —
 * 직접 지정 창은 라벨에 이미 날짜가 들어 있으므로 다시 붙이지 않는다.
 * (2026-08-18: 카드에는 기간·자본 행이 있는데 결과 화면 DTO에는 칸이 없어 빠져 있던 결함 수정.)
 */
export function buildPromptSummaryRows(
  summary: PromptSummarySource | null | undefined,
  promptText: string | undefined,
  resultDates: string[] | undefined
): PromptSummaryRow[] {
  const rows: PromptSummaryRow[] = [];
  if (!summary) return rows;

  const universeLabel = resolveUniverseDisplayName(summary.universeName, promptText);
  if (universeLabel) rows.push({ label: t("유니버스"), values: [universeLabel] });
  if (summary.entryBlocks?.length) rows.push({ label: t("진입 신호"), values: summary.entryBlocks });
  if (summary.exitBlocks?.length) rows.push({ label: t("청산 신호"), values: summary.exitBlocks });

  const first = resultDates?.[0];
  const last = resultDates?.[resultDates.length - 1];
  const executedSpan =
    first && last && !(summary.backtestPeriodText ?? "").includes("~") ? `${first} ~ ${last}` : null;
  const periodValues = [summary.backtestPeriodText, executedSpan].filter(
    (value): value is string => Boolean(value)
  );
  if (periodValues.length > 0) rows.push({ label: t("백테스트 기간"), values: periodValues });
  if (summary.initialCapitalText) rows.push({ label: t("초기 자본"), values: [summary.initialCapitalText] });

  const riskValues = [summary.positionText, summary.rebalancingText, summary.riskText].filter(
    (value): value is string => Boolean(value)
  );
  if (riskValues.length > 0) rows.push({ label: t("리스크"), values: riskValues });
  return rows;
}
