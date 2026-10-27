// 엔진 요청(BacktestRequest) 계약의 키 — 저장 전략을 다시 실행(재백테스트·워크포워드·전략 시뮬레이션)할 수 있는
// 최소 형태의 단일 정의. 클라이언트(저장 버튼)와 서버(저장 경로·기록·공개 시뮬레이션)가 같은 기준을 쓴다.
export const ENGINE_REQUEST_KEYS = [
  "symbols", "universe_id", "backtest_mode", "target_stocks", "sector", "etf_theme",
  "listing_from", "listing_to", "entry", "exit", "risk", "period", "startDate", "endDate", "options",
] as const;

/** 엔진 요청형 키만 고른다. entry·exit·risk가 없으면 실행할 수 없는 설정이라 null. */
export function pickExecutedRequest(body: any): Record<string, unknown> | null {
  if (!body || typeof body !== "object" || !body.entry || !body.exit || !body.risk) return null;
  const picked: Record<string, unknown> = {};
  for (const key of ENGINE_REQUEST_KEYS) {
    if (body[key] !== undefined) picked[key] = body[key];
  }
  return picked;
}

export const isExecutableStrategy = (dsl: unknown): boolean => pickExecutedRequest(dsl) !== null;

/**
 * 전략 저장 시 보낼 설정 — 화면이 가진 전략 DSL이 실행 가능하면 그것을, 아니면 결과에 동봉된 실행 요청
 * (그 결과를 만든 엔진 요청)을 쓴다. 둘 다 없으면 null이고, 저장하지 않는다(빈 설정으로 대신 저장 금지).
 */
export function resolveStrategyToSave(dsl: unknown, result: unknown): Record<string, unknown> | null {
  if (isExecutableStrategy(dsl)) return dsl as Record<string, unknown>;
  const executed = (result as { executedRequest?: unknown } | null | undefined)?.executedRequest;
  return isExecutableStrategy(executed) ? (executed as Record<string, unknown>) : null;
}

export const NOT_EXECUTABLE_CODE = "STRATEGY_NOT_EXECUTABLE";
export const NOT_EXECUTABLE_MESSAGE = "실행 조건이 없어 저장할 수 없습니다. 백테스트를 다시 실행한 뒤 저장해 주세요.";
