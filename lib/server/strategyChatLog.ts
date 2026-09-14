import { prisma } from "@/lib/prisma";
import {
  MAX_CHAT_LOG_ENTRIES,
  isRegion,
  type ChatLogEntry,
} from "@/lib/strategy/chatLogEntry";

// 전략연구소 대화 기록의 서버 정본 — 항상 세션 사용자로 쿼리를 묶는다(NFR-SEC-006).

type StoredRow = {
  sessionId: string;
  region: string;
  title: string;
  messageCount: number;
  createdAt: Date;
  updatedAt: Date;
};

function toEntry(row: StoredRow): ChatLogEntry {
  return {
    id: row.sessionId,
    region: isRegion(row.region) ? row.region : "kr",
    title: row.title,
    messageCount: row.messageCount,
    createdAt: row.createdAt.getTime(),
    updatedAt: row.updatedAt.getTime(),
  };
}

const ENTRY_SELECT = {
  sessionId: true,
  region: true,
  title: true,
  messageCount: true,
  createdAt: true,
  updatedAt: true,
} as const;

// 사용자의 대화 기록을 최근 사용 순으로 돌려주고, 상한을 넘는 오래된 항목은 지운다(LRU).
// 목록 조회와 정리를 한 번에 하므로 어떤 경로로 들어와도 30건을 넘긴 채 남지 않는다.
export async function listStrategyChatLog(userId: number): Promise<ChatLogEntry[]> {
  const rows = await prisma.strategyChatLog.findMany({
    where: { userId },
    orderBy: { updatedAt: "desc" },
    select: { id: true, ...ENTRY_SELECT },
  });
  const overflow = rows.slice(MAX_CHAT_LOG_ENTRIES);
  if (overflow.length > 0) {
    await prisma.strategyChatLog.deleteMany({
      where: { userId, id: { in: overflow.map((r) => r.id) } },
    });
  }
  return rows.slice(0, MAX_CHAT_LOG_ENTRIES).map(toEntry);
}

// 대화 하나를 저장한다. 메시지 수가 늘었을 때만 updatedAt(LRU 순서)을 올린다 — 열어 보기만 한
// 대화가 재저장돼도 맨 위로 올라오지 않는다.
export async function upsertStrategyChatLog(input: {
  userId: number;
  sessionId: string;
  region: string;
  title: string;
  messageCount: number;
  snapshot: string;
  now?: Date;
}): Promise<void> {
  const now = input.now ?? new Date();
  const existing = await prisma.strategyChatLog.findUnique({
    where: { userId_sessionId: { userId: input.userId, sessionId: input.sessionId } },
    select: { messageCount: true },
  });
  const advanced = !existing || existing.messageCount !== input.messageCount;
  const data = {
    region: input.region,
    title: input.title,
    messageCount: input.messageCount,
    snapshot: input.snapshot,
  };
  if (existing) {
    await prisma.strategyChatLog.update({
      where: { userId_sessionId: { userId: input.userId, sessionId: input.sessionId } },
      data: advanced ? { ...data, updatedAt: now } : data,
    });
    return;
  }
  await prisma.strategyChatLog.create({
    data: { ...data, userId: input.userId, sessionId: input.sessionId, createdAt: now, updatedAt: now },
  });
}

export async function readStrategyChatLogSnapshot(
  userId: number,
  sessionId: string,
): Promise<string | null> {
  const row = await prisma.strategyChatLog.findUnique({
    where: { userId_sessionId: { userId, sessionId } },
    select: { snapshot: true },
  });
  return row?.snapshot ?? null;
}

export async function deleteStrategyChatLog(userId: number, sessionId: string): Promise<void> {
  await prisma.strategyChatLog.deleteMany({ where: { userId, sessionId } });
}
