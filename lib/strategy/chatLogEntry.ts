import type { Region } from "@/lib/geo/region";

// 전략연구소 대화 기록(왼쪽 대화 로그) — 화면과 API 라우트가 같이 쓰는 순수 규칙.
// 계정당 최대 30건, 초과분은 가장 오래 쓰지 않은(updatedAt 오래된) 것부터 지운다(LRU).
// "쓴다"는 대화가 진전된 것(메시지 수 증가)이고, 열어 보기만 한 대화는 순서를 바꾸지 않는다.
export const MAX_CHAT_LOG_ENTRIES = 30;
// 스냅샷 JSON 상한 — 넘치면 백테스트 결과(result)부터 떨어뜨린다(복원은 best-effort).
export const MAX_CHAT_LOG_SNAPSHOT_CHARS = 2_000_000;
export const MAX_CHAT_LOG_SESSION_ID_CHARS = 100;
const TITLE_MAX_LENGTH = 80;

export type ChatLogMessage = {
  role: string;
  content?: string;
};

export type ChatLogSnapshot = {
  messages: ChatLogMessage[];
  stage?: string;
  result?: unknown;
  [key: string]: unknown;
};

// 목록 항목 — 스냅샷은 싣지 않는다(30건 × 결과 포함 스냅샷은 무겁다). 열 때 따로 받는다.
export type ChatLogEntry = {
  id: string; // 대화 세션 id(qaSessionId)
  region: Region;
  title: string;
  messageCount: number;
  createdAt: number;
  updatedAt: number;
};

export function isRegion(value: unknown): value is Region {
  return value === "kr" || value === "us";
}

// 제목은 첫 사용자 발화의 첫 줄이다. 의미를 해석하지 않고 표시 길이만 자른다.
export function deriveChatLogTitle(messages: ChatLogMessage[]): string {
  const first = messages.find((m) => m.role === "user" && m.content?.trim());
  const line = (first?.content ?? "").trim().split("\n")[0].trim();
  return line.length > TITLE_MAX_LENGTH ? `${line.slice(0, TITLE_MAX_LENGTH)}…` : line;
}

export function isChatLogSnapshot(value: unknown): value is ChatLogSnapshot {
  if (!value || typeof value !== "object") return false;
  const messages = (value as { messages?: unknown }).messages;
  return (
    Array.isArray(messages) &&
    messages.every((m) => !!m && typeof m === "object" && typeof (m as { role?: unknown }).role === "string")
  );
}

export function isChatLogEntry(value: unknown): value is ChatLogEntry {
  if (!value || typeof value !== "object") return false;
  const e = value as Partial<ChatLogEntry>;
  return (
    typeof e.id === "string" &&
    isRegion(e.region) &&
    typeof e.title === "string" &&
    typeof e.messageCount === "number" &&
    typeof e.createdAt === "number" &&
    typeof e.updatedAt === "number"
  );
}

// 스냅샷을 저장 상한 안의 JSON 문자열로 만든다. 넘치면 백테스트 결과를 떨어뜨리고
// 완료(done) 단계는 ready로 강등한다(결과 없는 done은 복원할 수 없다). 그래도 넘치면 null.
export function serializeChatLogSnapshot(
  snapshot: ChatLogSnapshot,
  maxChars: number = MAX_CHAT_LOG_SNAPSHOT_CHARS,
): string | null {
  const full = JSON.stringify(snapshot);
  if (full.length <= maxChars) return full;
  if (snapshot.result == null) return null;
  const slim = JSON.stringify({
    ...snapshot,
    result: null,
    stage: snapshot.stage === "done" ? "ready" : snapshot.stage,
  });
  return slim.length <= maxChars ? slim : null;
}

export function sortChatLogEntries(entries: ChatLogEntry[]): ChatLogEntry[] {
  return [...entries].sort((a, b) => b.updatedAt - a.updatedAt);
}
