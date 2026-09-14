import type { Region } from "@/lib/geo/region";
import {
  isChatLogEntry,
  isChatLogSnapshot,
  serializeChatLogSnapshot,
  sortChatLogEntries,
  type ChatLogEntry,
  type ChatLogSnapshot,
} from "@/lib/strategy/chatLogEntry";

// 전략연구소 대화 로그 — 지나간 대화를 계정별로 서버(DB)에 남겨 왼쪽 패널에서 다시 열 수
// 있게 한다. 세션 스냅샷(STRATEGY_CHAT_STATE_KEY)이 "지금 진행 중인 대화 하나"라면, 이
// 로그는 그 스냅샷을 대화(qaSessionId)별로 쌓은 목록이다. 항목의 snapshot은 세션 스냅샷과
// 같은 모양이라 복원 경로를 그대로 재사용한다. 계정당 최대 30건, 초과분은 가장 오래 쓰지
// 않은 것부터 서버가 지운다(LRU) — 2026-09-14 브라우저 localStorage에서 이관.
export {
  MAX_CHAT_LOG_ENTRIES,
  deriveChatLogTitle,
  type ChatLogEntry,
  type ChatLogSnapshot,
} from "@/lib/strategy/chatLogEntry";

const CHAT_LOG_API = "/api/strategy-chat-log";

function parseEntries(payload: unknown): ChatLogEntry[] {
  const entries = (payload as { entries?: unknown } | null)?.entries;
  if (!Array.isArray(entries)) return [];
  return sortChatLogEntries(entries.filter(isChatLogEntry));
}

async function requestEntries(input: string, init?: RequestInit): Promise<ChatLogEntry[]> {
  const response = await fetch(input, { credentials: "same-origin", ...init });
  if (!response.ok) throw new Error(`chat log request failed: ${response.status}`);
  return parseEntries(await response.json());
}

export function readChatLog(): Promise<ChatLogEntry[]> {
  return requestEntries(CHAT_LOG_API, { cache: "no-store" });
}

export async function readChatLogSnapshot(id: string): Promise<ChatLogSnapshot | null> {
  const response = await fetch(`${CHAT_LOG_API}/${encodeURIComponent(id)}`, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) return null;
  const snapshot = ((await response.json()) as { snapshot?: unknown } | null)?.snapshot;
  return isChatLogSnapshot(snapshot) ? snapshot : null;
}

// 저장 — 스냅샷이 상한을 넘으면 백테스트 결과부터 떨어뜨린다(복원은 best-effort). 그래도
// 넘치면 저장하지 않고 null을 돌려준다. keepalive는 화면을 떠나는 순간의 마지막 저장용.
export function upsertChatLogEntry(
  input: { id: string; region: Region; snapshot: ChatLogSnapshot },
  options: { keepalive?: boolean } = {},
): Promise<ChatLogEntry[] | null> {
  if (input.snapshot.messages.length === 0) return Promise.resolve(null);
  const snapshot = serializeChatLogSnapshot(input.snapshot);
  if (snapshot === null) return Promise.resolve(null);
  return requestEntries(`${CHAT_LOG_API}/${encodeURIComponent(input.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: `{"region":${JSON.stringify(input.region)},"snapshot":${snapshot}}`,
    keepalive: options.keepalive,
  });
}

export function removeChatLogEntry(id: string): Promise<ChatLogEntry[]> {
  return requestEntries(`${CHAT_LOG_API}/${encodeURIComponent(id)}`, { method: "DELETE" });
}
