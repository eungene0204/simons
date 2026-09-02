import type { Region } from "@/lib/geo/region";

// 전략연구소 대화 로그 — 지나간 대화를 브라우저(localStorage)에 남겨 우측 패널에서
// 다시 열 수 있게 한다. 세션 스냅샷(STRATEGY_CHAT_STATE_KEY)이 "지금 진행 중인 대화
// 하나"라면, 이 로그는 그 스냅샷을 대화(qaSessionId)별로 쌓은 목록이다.
// 항목의 snapshot은 세션 스냅샷과 같은 모양이라 복원 경로를 그대로 재사용한다.
export const STRATEGY_CHAT_LOG_KEY = "simons.strategyChatLog";
export const MAX_CHAT_LOG_ENTRIES = 30;
const TITLE_MAX_LENGTH = 80;

type LogSourceMessage = {
  role: string;
  content?: string;
};

export type ChatLogSnapshot = {
  messages: LogSourceMessage[];
  stage?: string;
  result?: unknown;
  [key: string]: unknown;
};

export type ChatLogEntry = {
  id: string;
  region: Region;
  title: string;
  messageCount: number;
  createdAt: number;
  updatedAt: number;
  snapshot: ChatLogSnapshot;
};

// 제목은 첫 사용자 발화의 첫 줄이다. 의미를 해석하지 않고 표시 길이만 자른다.
export function deriveChatLogTitle(messages: LogSourceMessage[]): string {
  const first = messages.find((m) => m.role === "user" && m.content?.trim());
  const line = (first?.content ?? "").trim().split("\n")[0].trim();
  return line.length > TITLE_MAX_LENGTH ? `${line.slice(0, TITLE_MAX_LENGTH)}…` : line;
}

function isEntry(value: unknown): value is ChatLogEntry {
  if (!value || typeof value !== "object") return false;
  const e = value as Partial<ChatLogEntry>;
  return (
    typeof e.id === "string" &&
    (e.region === "kr" || e.region === "us") &&
    typeof e.title === "string" &&
    typeof e.updatedAt === "number" &&
    !!e.snapshot &&
    Array.isArray(e.snapshot.messages)
  );
}

export function readChatLog(storage: Storage): ChatLogEntry[] {
  try {
    const raw = storage.getItem(STRATEGY_CHAT_LOG_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isEntry).sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

// 용량 초과 시 순서대로 양보한다: ① 방금 갱신한 항목의 백테스트 결과(result)를 떨어뜨리고
// ② 그래도 안 들어가면 오래된 항목부터 지운다. 로그는 best-effort다 — 끝내 실패하면
// 저장을 포기하되 메모리 목록은 돌려준다.
function writeChatLog(storage: Storage, entries: ChatLogEntry[], freshId: string): ChatLogEntry[] {
  let next = entries.slice(0, MAX_CHAT_LOG_ENTRIES);
  let resultDropped = false;
  for (;;) {
    try {
      storage.setItem(STRATEGY_CHAT_LOG_KEY, JSON.stringify(next));
      return next;
    } catch {
      if (!resultDropped) {
        resultDropped = true;
        next = next.map((e) =>
          e.id === freshId && e.snapshot.result != null
            ? {
                ...e,
                snapshot: {
                  ...e.snapshot,
                  result: null,
                  stage: e.snapshot.stage === "done" ? "ready" : e.snapshot.stage,
                },
              }
            : e,
        );
        continue;
      }
      if (next.length <= 1) return next;
      next = next.slice(0, -1);
    }
  }
}

export function upsertChatLogEntry(
  storage: Storage,
  input: { id: string; region: Region; snapshot: ChatLogSnapshot; now?: number },
): ChatLogEntry[] {
  const now = input.now ?? Date.now();
  const messageCount = input.snapshot.messages.length;
  if (messageCount === 0) return readChatLog(storage);
  const existing = readChatLog(storage);
  const prev = existing.find((e) => e.id === input.id);
  // 열어 보기만 한 대화(메시지 수 그대로)는 순서를 바꾸지 않는다 — 복원·재저장 때마다
  // 맨 위로 올라오면 최근에 '말한' 대화가 아니라 최근에 '연' 대화 순서가 돼 버린다.
  const advanced = !prev || prev.messageCount !== messageCount;
  const entry: ChatLogEntry = {
    id: input.id,
    region: input.region,
    title: deriveChatLogTitle(input.snapshot.messages) || prev?.title || "",
    messageCount,
    createdAt: prev?.createdAt ?? now,
    updatedAt: advanced ? now : prev.updatedAt,
    snapshot: input.snapshot,
  };
  const merged = [entry, ...existing.filter((e) => e.id !== input.id)].sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );
  return writeChatLog(storage, merged, input.id);
}

export function removeChatLogEntry(storage: Storage, id: string): ChatLogEntry[] {
  const next = readChatLog(storage).filter((e) => e.id !== id);
  try {
    if (next.length === 0) storage.removeItem(STRATEGY_CHAT_LOG_KEY);
    else storage.setItem(STRATEGY_CHAT_LOG_KEY, JSON.stringify(next));
  } catch {
    // 삭제 실패는 목록 표시를 막지 않는다.
  }
  return next;
}
