import { getSessionUserId } from "@/lib/get-user";

/**
 * 백엔드에 보내는 소유자 헤더 — 세션의 사용자 id(비로그인이면 헤더 없음).
 * 백엔드는 이 값을 대화 기억의 소유자 칸에만 쓴다(권한 판정 아님). 요청 본문이 아니라
 * 프록시가 직접 싣는 헤더라 화면에서 바꿔 보낼 수 없다.
 */
export async function ownerHeader(): Promise<Record<string, string>> {
  const userId = await getSessionUserId();
  return userId == null ? {} : { "X-User-Id": String(userId) };
}
