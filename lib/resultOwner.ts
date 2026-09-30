// 백테스트 결과의 주인 — 결과를 실행(또는 열람)한 로그인 계정.
//
// 로그인 쿠키는 브라우저 전체가 같이 쓴다. A 계정으로 받은 결과 화면을 한 탭에 띄워 둔 채
// 다른 탭에서 B 계정으로 로그인하면(또는 뒤로 가기로 옛 화면이 복원되면) 그 화면의 저장·
// 가상계좌 만들기가 B 계정으로 들어가, B는 백테스트를 한 번도 돌리지 않았는데 전략·계좌가
// 생긴다(2026-09-22 guest_1656 사고, 09-30 규명). 서버가 결과를 내줄 때 주인을 붙이고,
// 결과 화면의 쓰기 요청은 그 주인을 함께 보내 지금 로그인 계정과 대조한다.

/** 스트림 응답(엔진 SSE를 그대로 흘려보내 본문에 끼울 수 없음)에서 결과 주인을 알리는 헤더 */
export const RESULT_OWNER_HEADER = "X-Result-Owner";

export const RESULT_OWNER_MISMATCH = "RESULT_OWNER_MISMATCH";

export const RESULT_OWNER_MISMATCH_MESSAGE =
  "로그인 계정이 바뀌었습니다. 이 결과는 이전 계정으로 실행한 것이라 지금 계정에 저장할 수 없어요. 페이지를 새로 고친 뒤 다시 실행해 주세요.";

/** 헤더 값 → 주인 id (없거나 잘못되면 undefined) */
export function parseResultOwner(value: string | null | undefined): number | undefined {
  if (value == null || value.trim() === "") return undefined;
  const id = Number(value);
  return Number.isInteger(id) ? id : undefined;
}

/**
 * 결과 주인과 지금 로그인 계정이 다른가.
 * 주인을 모르는 결과(이 기능 이전에 받은 결과)는 판단할 수 없으므로 막지 않는다.
 */
export function isResultOwnerMismatch(claimedOwner: unknown, userId: number | null): boolean {
  return typeof claimedOwner === "number" && userId != null && claimedOwner !== userId;
}

/** 대조 실패 응답 본문(409) — 결과 화면은 message를 안내로 띄운다 */
export const RESULT_OWNER_MISMATCH_BODY = {
  error: RESULT_OWNER_MISMATCH_MESSAGE,
  code: RESULT_OWNER_MISMATCH,
  message: RESULT_OWNER_MISMATCH_MESSAGE,
} as const;

/** 저장 전에 주인 표시를 뗀다 — 공유 결과 행(cacheKey 기준)에 남의 계정 id를 남기지 않는다 */
export function stripResultOwner<T>(result: T): T {
  if (!result || typeof result !== "object" || !("ownerUserId" in result)) return result;
  const { ownerUserId: _owner, ...rest } = result as Record<string, unknown>;
  return rest as T;
}
