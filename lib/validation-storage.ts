import { t } from "@/lib/i18n";
// 전략 최적화 검증 결과(워크포워드·몬테카를로) 저장/불러오기 클라이언트 헬퍼.
// 서버 라우트: app/api/validation

export type SavedValidationModelType = "walkForward" | "monteCarlo";

export interface SavedValidationSummary {
  id: string;
  modelType: SavedValidationModelType;
  strategyName: string;
  prompt?: string;
  cacheKey?: string;
  settings?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  createdAt: number;
}

export interface SavedValidationDetail extends SavedValidationSummary {
  result: unknown;
}

export interface SaveValidationInput {
  modelType: SavedValidationModelType;
  strategyName: string;
  prompt?: string;
  cacheKey?: string;
  settings: Record<string, unknown>;
  result: unknown;
  summary?: Record<string, unknown>;
}

// 목록 카드에 표시할 워크포워드 핵심 요약.
export function buildWalkForwardSummary(result: {
  walk_forward_efficiency?: number;
  wfe_valid?: boolean;
  n_splits?: number;
  aggregate?: Record<string, number>;
}): Record<string, unknown> {
  return {
    wfe: result.walk_forward_efficiency ?? null,
    wfeValid: result.wfe_valid !== false,
    nSplits: result.n_splits ?? null,
    avgOosCagr: result.aggregate?.avg_oos_cagr ?? null,
  };
}

// 목록 카드에 표시할 몬테카를로 핵심 요약.
export function buildMonteCarloSummary(result: {
  nIterations?: number;
  mode?: string;
  cagr?: { median?: number; p05?: number };
  mdd?: { p95?: number };
}): Record<string, unknown> {
  return {
    iterations: result.nIterations ?? null,
    mode: result.mode ?? null,
    medianCagr: result.cagr?.median ?? null,
    p05Cagr: result.cagr?.p05 ?? null,
    p95Mdd: result.mdd?.p95 ?? null,
  };
}

export async function saveValidation(input: SaveValidationInput): Promise<{ id: string }> {
  const res = await fetch("/api/validation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(t("검증 결과 저장 실패 ({0})", res.status));
  }
  return res.json();
}

export async function listSavedValidations(
  modelType?: SavedValidationModelType
): Promise<SavedValidationSummary[]> {
  const query = modelType ? `?modelType=${modelType}` : "";
  const res = await fetch(`/api/validation${query}`);
  if (!res.ok) {
    throw new Error(t("저장 목록을 불러오지 못했습니다 ({0})", res.status));
  }
  return res.json();
}

export async function getSavedValidation(id: string): Promise<SavedValidationDetail> {
  const res = await fetch(`/api/validation/${id}`);
  if (!res.ok) {
    throw new Error(t("저장된 결과를 불러오지 못했습니다 ({0})", res.status));
  }
  return res.json();
}

export async function deleteSavedValidation(id: string): Promise<void> {
  const res = await fetch(`/api/validation?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(t("삭제에 실패했습니다 ({0})", res.status));
  }
}
