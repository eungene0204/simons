import { t } from "@/lib/i18n";

// 리밸런싱 기간별 결과 비교(FR-BT-064) — 백테스트 결과(BacktestResult.rebalanceComparison)에
// 엔진이 동봉하는 6주기 재시뮬레이션 계약(backend/engine/rebalance_comparison.py).

export const REBALANCE_COMPARISON_PERIODS = [
  "daily",
  "weekly",
  "monthly",
  "quarterly",
  "semiannual",
  "yearly",
] as const;

export type RebalanceComparisonPeriod = (typeof REBALANCE_COMPARISON_PERIODS)[number];

/** 주기 키 → 한국어 라벨(표시 지점에서 t()로 감싼다). */
export const REBALANCE_PERIOD_LABELS: Record<string, string> = {
  daily: "매일",
  weekly: "매주",
  monthly: "매월",
  bimonthly: "격월",
  quarterly: "분기",
  semiannual: "반기",
  yearly: "연간",
  none: "리밸런싱 없음",
};

export function rebalancePeriodLabel(period: string | null | undefined): string {
  if (!period) return t("리밸런싱 없음");
  return t(REBALANCE_PERIOD_LABELS[period] ?? period);
}

export interface RebalancePeriodRow {
  period: string;
  cagr?: number | null;
  mdd?: number | null;
  sharpe?: number | null;
  /** null = 손실 거래 0건(∞). */
  profitFactor?: number | null;
  trades?: number;
  turnover?: number | null;
  totalReturn?: number | null;
  winRate?: number | null;
  finalEquity?: number | null;
  error?: string | null;
}

export interface RebalanceComparisonResult {
  periods: RebalancePeriodRow[];
  /** 전략의 현재 리밸런싱 주기('none' 포함). */
  currentPeriod?: string;
  /** 보유 상한이 없어 주기가 결과에 영향을 주지 않는 전략 — 6행이 같을 수 있다. */
  positionCapAbsent?: boolean;
}

export type ComparisonRow = RebalancePeriodRow & { isCurrent: boolean; isReference: boolean };

/** 메인 결과의 지표 — 현재 주기가 6주기 밖(없음·격월)일 때 '현재 설정' 참고 행으로 쓴다. */
export interface CurrentSettingMetrics {
  cagr?: number;
  maxDrawdown?: number;
  sharpe?: number;
  profitFactor?: number | null;
  trades?: number;
  turnoverRate?: number;
}

/** 비교표 행 순서 — 6주기(짧은 → 긴) 뒤에 '현재 설정' 참고 행(6주기 밖일 때만). */
export function orderComparisonRows(
  data: RebalanceComparisonResult,
  current: CurrentSettingMetrics
): ComparisonRow[] {
  const currentPeriod = data.currentPeriod || "none";
  const byPeriod = new Map((data.periods ?? []).map((row) => [row.period, row]));
  const ordered: ComparisonRow[] = REBALANCE_COMPARISON_PERIODS
    .map((period) => byPeriod.get(period))
    .filter((row): row is RebalancePeriodRow => Boolean(row))
    .map((row) => ({ ...row, isCurrent: row.period === currentPeriod, isReference: false }));
  if (!byPeriod.has(currentPeriod)) {
    ordered.push({
      period: currentPeriod,
      cagr: current.cagr ?? null,
      mdd: current.maxDrawdown ?? null,
      sharpe: current.sharpe ?? null,
      profitFactor: current.profitFactor ?? null,
      trades: current.trades ?? 0,
      turnover: current.turnoverRate ?? null,
      isCurrent: true,
      isReference: true,
    });
  }
  return ordered;
}
