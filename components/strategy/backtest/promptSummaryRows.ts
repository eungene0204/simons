import { resolveUniverseDisplayName } from "@/lib/strategy-summary";
import { t } from "@/lib/i18n";
import type { BacktestInflation, BacktestRiskFreeRate, BacktestTradingCosts } from "@/types/strategy";

export interface PromptSummarySource {
  universeName: string;
  entryBlocks?: string[];
  exitBlocks?: string[];
  positionText?: string;
  riskText?: string;
  rebalancingText?: string;
  backtestPeriodText?: string;
  initialCapitalText?: string;
  /** 체결 가정(익일 시가 / 당일 종가 / 신호 후 N번째 거래일 시가) — 실행 요청에서 파생. */
  executionText?: string;
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
  // 체결 가정은 전략이 아니라 실행 설정이라 맨 뒤 — 지연 체결(execution_delay_days)을 설정한
  // 결과가 어떤 체결 가정으로 계산됐는지 여기서만 보인다(2026-09-14).
  if (summary.executionText) rows.push({ label: t("체결"), values: [summary.executionText] });
  return rows;
}

// 수수료·슬리피지처럼 작은 비율은 소수 2자리로는 0이 된다(0.015% → 0.01%) — 4자리까지 남기고 뒤 0을 뗀다.
function formatRate(fraction: number): string {
  return `${Number((fraction * 100).toFixed(4))}%`;
}

/**
 * 결과 화면 "프롬프트" 팝오버의 '거래 비용' 행 — 설정 화면 값이 아니라 **이 결과가 실제로 적용한**
 * 비용(result.tradingCosts, 엔진 동봉)만 보인다. 구버전 저장 결과처럼 동봉이 없으면 행을 만들지
 * 않는다(현재 설정값을 적용값처럼 보이면 거짓 안내가 된다).
 */
export function buildTradingCostRow(costs: BacktestTradingCosts | null | undefined): PromptSummaryRow | null {
  if (!costs) return null;
  const values: string[] = [];
  if (costs.buyFeeRate === costs.sellFeeRate) {
    values.push(`${t("수수료")} ${formatRate(costs.buyFeeRate)}`);
  } else {
    values.push(
      `${t("수수료")} ${t("매수")} ${formatRate(costs.buyFeeRate)} · ${t("매도")} ${formatRate(costs.sellFeeRate)}`
    );
  }
  values.push(`${t("슬리피지")} ${formatRate(costs.slippageRate)}`);
  if (costs.sellTaxRate != null) {
    values.push(`${t("거래세")} ${formatRate(costs.sellTaxRate)}`);
  } else if (costs.sellTaxRateRange) {
    const [lo, hi] = costs.sellTaxRateRange;
    values.push(
      lo === hi
        ? `${t("거래세")} ${formatRate(hi)}`
        : `${t("거래세")} ${formatRate(hi)} → ${formatRate(lo)} (${t("시행일 기준")})`
    );
  }
  // 배당소득세(엔진 v16.33) — 배당 재투자를 세후로 굴렸는지. 배당 미반영이면 null이라 행에 없다.
  if (costs.dividendTaxRate != null) {
    values.push(`${t("배당소득세")} ${formatRate(costs.dividendTaxRate)}`);
  }
  return { label: t("거래 비용"), values };
}

/**
 * '기준값' 행 — 샤프·소르티노가 어떤 무위험수익률로 계산됐는지와, 물가를 뺀 실질 수익률(엔진 v16.33).
 * 둘 다 없으면 행을 만들지 않는다(구버전 저장 결과).
 */
export function buildReferenceRateRow(
  riskFree: BacktestRiskFreeRate | null | undefined,
  inflation: BacktestInflation | null | undefined,
): PromptSummaryRow | null {
  const values: string[] = [];
  if (riskFree && riskFree.source !== "unavailable") {
    values.push(
      riskFree.source === "explicit"
        ? `${t("무위험수익률")} ${riskFree.annualPct.toFixed(2)}%`
        : `${t("무위험수익률")} ${riskFree.annualPct.toFixed(2)}% (${t("기간 평균")})`,
    );
  }
  if (inflation?.annualPct != null) {
    values.push(`${t("물가상승률")} ${t("연")} ${inflation.annualPct.toFixed(2)}%`);
    if (inflation.realCagrPct != null) {
      values.push(`${t("실질 CAGR")} ${inflation.realCagrPct.toFixed(2)}%`);
    }
    if (!inflation.covered) {
      values.push(t("물가 자료 {0}까지", inflation.to));
    }
  }
  if (values.length === 0) return null;
  return { label: t("기준값"), values };
}
