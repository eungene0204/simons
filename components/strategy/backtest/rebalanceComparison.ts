import { parseSseBlocks } from "@/app/analytics/new/sseEvents";
import { formatApiErrorDetail } from "@/app/analytics/new/walkForwardStream";
import { t } from "@/lib/i18n";

// 리밸런싱 기간별 결과 비교(FR-BT-064) — 백엔드 ai/rebalance_comparison.py 응답 계약.

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
  cagr: number | null;
  mdd: number | null;
  sharpe_ratio: number | null;
  /** null = 손실 거래 0건(∞). */
  profit_factor: number | null;
  trade_count: number;
  turnover: number | null;
  total_return?: number | null;
  win_rate?: number | null;
  calmar?: number | null;
  final_equity?: number | null;
  error?: string | null;
  elapsed_s?: number;
}

export interface RebalanceComparisonAnalysis {
  summary: {
    recommended_rebalance_period: string;
    confidence_score: number | null;
    strategy_character: string;
    stability_rating: "A" | "B" | "C" | "D" | null;
  };
  /** 주기 → 한 줄 평가(LLM). 비교표 숫자는 엔진 값이라 여기 없다. */
  evaluations: Record<string, string>;
  analysis: {
    performance_analysis: string;
    risk_analysis: string;
    transaction_cost_analysis: string;
    overfitting_analysis: string;
  };
  recommendation: {
    recommended_period: string;
    reason: string;
    warning: string;
  };
}

export interface RebalanceComparisonResult {
  status: "ok";
  message?: string;
  /** 결정론 안내(예: 보유 상한이 없어 6주기 결과가 같을 수 있음). */
  notices?: string[];
  current_period?: string;
  backtest_period?: { start: string; end: string } | null;
  rebalance_results?: RebalancePeriodRow[];
  evidence?: Record<string, unknown>;
  analysis?: RebalanceComparisonAnalysis | null;
  analysis_degraded?: boolean;
  analysis_error?: string | null;
}

export interface RebalanceComparisonProgress {
  stage: "backtest" | "analysis" | string;
  period?: string;
  index?: number;
  total?: number;
}

/** 메인 결과에서 '현재 설정' 참고 행을 만든다(재실행 없이 표·LLM 입력에 쓴다). */
export function buildCurrentSettingMetrics(input: {
  cagr?: number;
  maxDrawdown?: number;
  sharpe?: number;
  profitFactor?: number | null;
  trades?: number;
  turnoverRate?: number;
}): Record<string, number | null> {
  const num = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? Number(v.toFixed(4)) : null;
  return {
    cagr: num(input.cagr),
    mdd: num(input.maxDrawdown),
    sharpe_ratio: num(input.sharpe),
    profit_factor: input.profitFactor == null ? null : num(input.profitFactor),
    trade_count: num(input.trades),
    turnover: num(input.turnoverRate),
  };
}

const NETWORK_ERROR_MESSAGE =
  "서버와 연결이 끊겼습니다. 분석이 오래 걸리거나 백엔드 연결에 문제가 있을 수 있습니다. 잠시 후 다시 시도해 주세요.";

function isAbortError(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { name?: string }).name === "AbortError";
}

function isNetworkError(error: unknown): boolean {
  return (
    error instanceof TypeError ||
    (error instanceof Error && /network error|failed to fetch|load failed|terminated/i.test(error.message))
  );
}

/**
 * 리밸런싱 비교 SSE 스트림을 소비해 진행률을 전달하고 최종 결과를 돌려준다.
 * 이벤트 형식: {type: "progress"|"result"|"error", ...} + 종료 시 "[DONE]" (워크포워드와 동일).
 */
export async function runRebalanceComparisonStream(
  requestBody: unknown,
  options: { signal?: AbortSignal; onProgress?: (event: RebalanceComparisonProgress) => void } = {}
): Promise<RebalanceComparisonResult> {
  let res: Response;
  try {
    res = await fetch("/api/backtest/rebalance-comparison/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
      signal: options.signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    if (isNetworkError(error)) throw new Error(t(NETWORK_ERROR_MESSAGE));
    throw error;
  }

  if (!res.ok || !res.body) {
    const error = await res.json().catch(() => ({}));
    throw new Error(
      formatApiErrorDetail(error.detail) ?? formatApiErrorDetail(error.message) ?? t("리밸런싱 비교 분석 실패")
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: RebalanceComparisonResult | null = null;

  const handlePayload = (payload: string) => {
    if (payload === "[DONE]") return;
    let event: any;
    try {
      event = JSON.parse(payload);
    } catch {
      return;
    }
    if (event.type === "progress") {
      options.onProgress?.(event as RebalanceComparisonProgress);
    } else if (event.type === "result") {
      result = event.data as RebalanceComparisonResult;
    } else if (event.type === "error") {
      throw new Error(formatApiErrorDetail(event.message) ?? t("리밸런싱 비교 분석 실패"));
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        const parsed = parseSseBlocks(buffer + decoder.decode(), true);
        for (const event of parsed.events) handlePayload(event.payload);
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseBlocks(buffer);
      buffer = parsed.remaining;
      for (const event of parsed.events) handlePayload(event.payload);
    }
  } catch (error) {
    if (isAbortError(error)) throw error;
    if (isNetworkError(error)) throw new Error(t(NETWORK_ERROR_MESSAGE));
    throw error;
  }

  if (!result) {
    throw new Error(t("리밸런싱 비교 분석 결과를 받지 못했습니다."));
  }
  return result;
}
