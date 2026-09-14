// @ts-nocheck
/**
 * 대화 로그 서버 정본 — 계정당 30건 LRU, 진전된 대화만 순서가 올라간다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const findMany = vi.fn();
const deleteMany = vi.fn();
const findUnique = vi.fn();
const update = vi.fn();
const create = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategyChatLog: {
      findMany: (...a) => findMany(...a),
      deleteMany: (...a) => deleteMany(...a),
      findUnique: (...a) => findUnique(...a),
      update: (...a) => update(...a),
      create: (...a) => create(...a),
    },
  },
}));

import { MAX_CHAT_LOG_ENTRIES } from "@/lib/strategy/chatLogEntry";
import { listStrategyChatLog, upsertStrategyChatLog } from "./strategyChatLog";

const row = (i: number) => ({
  id: `row${i}`,
  sessionId: `s${i}`,
  region: "kr",
  title: `t${i}`,
  messageCount: 1,
  createdAt: new Date(1000 - i),
  updatedAt: new Date(1000 - i), // i가 작을수록 최근
});

beforeEach(() => {
  vi.clearAllMocks();
  deleteMany.mockResolvedValue({ count: 0 });
  update.mockResolvedValue({});
  create.mockResolvedValue({});
});

describe("listStrategyChatLog", () => {
  it("세션 사용자로 묶어 최근 사용 순으로 조회하고 상한 안이면 지우지 않는다", async () => {
    findMany.mockResolvedValue([row(0), row(1)]);
    const entries = await listStrategyChatLog(7);
    expect(findMany.mock.calls[0][0]).toMatchObject({ where: { userId: 7 }, orderBy: { updatedAt: "desc" } });
    expect(entries.map((e) => e.id)).toEqual(["s0", "s1"]);
    expect(entries[0]).toMatchObject({ region: "kr", title: "t0", messageCount: 1, updatedAt: 1000 });
    expect(deleteMany).not.toHaveBeenCalled();
  });

  it("상한을 넘는 가장 오래 쓰지 않은 항목을 지우고(LRU) 30건만 돌려준다", async () => {
    findMany.mockResolvedValue(Array.from({ length: MAX_CHAT_LOG_ENTRIES + 3 }, (_, i) => row(i)));
    const entries = await listStrategyChatLog(7);
    expect(entries).toHaveLength(MAX_CHAT_LOG_ENTRIES);
    expect(entries.at(-1)?.id).toBe(`s${MAX_CHAT_LOG_ENTRIES - 1}`);
    expect(deleteMany).toHaveBeenCalledWith({
      where: { userId: 7, id: { in: [`row${MAX_CHAT_LOG_ENTRIES}`, `row${MAX_CHAT_LOG_ENTRIES + 1}`, `row${MAX_CHAT_LOG_ENTRIES + 2}`] } },
    });
  });
});

describe("upsertStrategyChatLog", () => {
  const base = { userId: 7, sessionId: "s", region: "kr", title: "t", messageCount: 3, snapshot: "{}" };

  it("없던 대화는 새로 만들고 지금 시각을 사용 시각으로 적는다", async () => {
    findUnique.mockResolvedValue(null);
    const now = new Date(5000);
    await upsertStrategyChatLog({ ...base, now });
    expect(create).toHaveBeenCalledWith({
      data: { ...base, createdAt: now, updatedAt: now },
    });
    expect(update).not.toHaveBeenCalled();
  });

  it("메시지 수가 늘었으면 사용 시각을 올린다", async () => {
    findUnique.mockResolvedValue({ messageCount: 2 });
    const now = new Date(5000);
    await upsertStrategyChatLog({ ...base, now });
    expect(update.mock.calls[0][0].data).toMatchObject({ messageCount: 3, snapshot: "{}", updatedAt: now });
    expect(create).not.toHaveBeenCalled();
  });

  it("메시지 수가 그대로면(열어 보기·결과만 갱신) 내용은 저장하되 사용 시각은 두어 순서를 바꾸지 않는다", async () => {
    findUnique.mockResolvedValue({ messageCount: 3 });
    await upsertStrategyChatLog({ ...base, snapshot: '{"stage":"done"}' });
    const data = update.mock.calls[0][0].data;
    expect(data.snapshot).toBe('{"stage":"done"}');
    expect(data).not.toHaveProperty("updatedAt");
  });
});
