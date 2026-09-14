import { STRATEGY_CHAT_STATE_KEY } from "./strategyTemplateSession";

// 전략연구소 대화는 브라우저 저장소에 남는다 — 대화 로그(localStorage)와 진행 중 대화
// 스냅샷(sessionStorage). 브라우저 저장소는 로그인 계정을 모르므로, 같은 브라우저에서
// 다른 계정으로 들어오면 먼저 쓰던 계정의 대화가 그대로 보인다(2026-09-14 게스트 계정
// 사고). 그래서 저장소마다 "주인"(로그인 사용자 id) 표식을 두고, 읽기 전에 지금 계정과
// 대조해 다르면 대화 데이터를 지운다. 비로그인은 대화를 시작할 수 없으므로 비로그인
// 상태에서 남아 있는 대화는 항상 남의 것이다 — 무조건 지운다.
// 2026-09-14 대화 로그는 계정별 DB로 이관됐다(`/api/strategy-chat-log`). 이 키는 이관 전
// 브라우저에 남은 옛 로그를 지우기 위해서만 남긴다 — 새로 쓰지 않는다.
export const STRATEGY_CHAT_LOG_KEY = "simons.strategyChatLog";
export const STRATEGY_CHAT_OWNER_KEY = "simons.strategyChatOwner";

// 저장소 주인 표식 — 로그인 사용자 id의 문자열, 비로그인은 "".
export function chatStorageOwnerOf(user: { id?: number | null } | null | undefined): string {
  return typeof user?.id === "number" ? String(user.id) : "";
}

function reconcileOwner(storage: Storage, owner: string, dataKeys: readonly string[]): void {
  try {
    const stored = storage.getItem(STRATEGY_CHAT_OWNER_KEY) ?? "";
    if (!owner || stored !== owner) {
      for (const key of dataKeys) storage.removeItem(key);
    }
    if (owner) storage.setItem(STRATEGY_CHAT_OWNER_KEY, owner);
    else storage.removeItem(STRATEGY_CHAT_OWNER_KEY);
  } catch {
    // 저장소 접근이 막힌 환경에서는 읽을 대화도 없다.
  }
}

// 지금 로그인 계정(owner)과 저장소 주인이 다르면 대화 로그·스냅샷을 지우고 주인을 바꿔 적는다.
// 대화를 읽기 전에 반드시 한 번 부른다. 대기 프롬프트(PENDING_STRATEGY_PROMPT_KEY)는
// 비로그인으로 입력한 뒤 로그인해서 이어 가는 값이라 여기서 지우지 않는다.
export function reconcileStrategyChatStorage(
  owner: string,
  local: Storage = window.localStorage,
  session: Storage = window.sessionStorage,
): void {
  reconcileOwner(local, owner, [STRATEGY_CHAT_LOG_KEY]);
  reconcileOwner(session, owner, [STRATEGY_CHAT_STATE_KEY]);
}

// 로그아웃 — 이 브라우저에 남은 대화 데이터를 주인 표식까지 모두 지운다.
export function clearStrategyChatStorage(
  local: Storage = window.localStorage,
  session: Storage = window.sessionStorage,
): void {
  for (const [storage, key] of [
    [local, STRATEGY_CHAT_LOG_KEY],
    [local, STRATEGY_CHAT_OWNER_KEY],
    [session, STRATEGY_CHAT_STATE_KEY],
    [session, STRATEGY_CHAT_OWNER_KEY],
  ] as const) {
    try {
      storage.removeItem(key);
    } catch {
      // 정리는 best-effort.
    }
  }
}
