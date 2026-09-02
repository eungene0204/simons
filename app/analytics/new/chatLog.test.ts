import { afterEach, describe, expect, it } from "vitest";

import {
  MAX_CHAT_LOG_ENTRIES,
  STRATEGY_CHAT_LOG_KEY,
  deriveChatLogTitle,
  readChatLog,
  removeChatLogEntry,
  upsertChatLogEntry,
} from "./chatLog";

const snapshotWith = (texts: string[], extra: Record<string, unknown> = {}) => ({
  messages: texts.map((content, i) => ({ role: i % 2 === 0 ? "user" : "assistant", content })),
  ...extra,
});

// setItem이 특정 길이를 넘으면 QuotaExceededError처럼 던지는 가짜 저장소.
function makeQuotaStorage(limit: number): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    key: (i: number) => Array.from(map.keys())[i] ?? null,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      if (v.length > limit) throw new DOMException("quota", "QuotaExceededError");
      map.set(k, v);
    },
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
  };
}

describe("대화 로그 저장소", () => {
  afterEach(() => localStorage.clear());

  it("첫 사용자 발화의 첫 줄을 제목으로 삼고 길면 자른다", () => {
    expect(deriveChatLogTitle([{ role: "assistant", content: "안내" }, { role: "user", content: " 첫 줄\n둘째 줄 " }]))
      .toBe("첫 줄");
    expect(deriveChatLogTitle([{ role: "user", content: "가".repeat(100) }])).toBe(`${"가".repeat(80)}…`);
    expect(deriveChatLogTitle([{ role: "user", content: "  " }])).toBe("");
  });

  it("대화별로 한 항목을 두고 최근 갱신 순으로 정렬한다", () => {
    upsertChatLogEntry(localStorage, { id: "a", region: "kr", snapshot: snapshotWith(["A 전략"]), now: 1 });
    upsertChatLogEntry(localStorage, { id: "b", region: "kr", snapshot: snapshotWith(["B 전략"]), now: 2 });
    const entries = upsertChatLogEntry(localStorage, {
      id: "a",
      region: "kr",
      snapshot: snapshotWith(["A 전략", "답", "추가"]),
      now: 3,
    });
    expect(entries.map((e) => e.id)).toEqual(["a", "b"]);
    expect(entries[0]).toMatchObject({ title: "A 전략", messageCount: 3, createdAt: 1, updatedAt: 3 });
    expect(readChatLog(localStorage)).toEqual(entries);
  });

  it("메시지 수가 그대로인 재저장(열어 보기)은 순서를 바꾸지 않는다", () => {
    upsertChatLogEntry(localStorage, { id: "a", region: "kr", snapshot: snapshotWith(["A"]), now: 1 });
    upsertChatLogEntry(localStorage, { id: "b", region: "kr", snapshot: snapshotWith(["B"]), now: 2 });
    const entries = upsertChatLogEntry(localStorage, { id: "a", region: "kr", snapshot: snapshotWith(["A"]), now: 3 });
    expect(entries.map((e) => e.id)).toEqual(["b", "a"]);
    expect(entries[1].updatedAt).toBe(1);
  });

  it("메시지가 없는 스냅샷은 항목을 만들지 않는다", () => {
    expect(upsertChatLogEntry(localStorage, { id: "a", region: "kr", snapshot: { messages: [] } })).toEqual([]);
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBeNull();
  });

  it("항목 수를 상한으로 자른다", () => {
    for (let i = 0; i < MAX_CHAT_LOG_ENTRIES + 5; i++) {
      upsertChatLogEntry(localStorage, { id: `s${i}`, region: "kr", snapshot: snapshotWith([`전략 ${i}`]), now: i });
    }
    const entries = readChatLog(localStorage);
    expect(entries).toHaveLength(MAX_CHAT_LOG_ENTRIES);
    expect(entries[0].id).toBe(`s${MAX_CHAT_LOG_ENTRIES + 4}`);
  });

  it("삭제하면 목록에서 빠지고 마지막 항목이 빠지면 키도 지운다", () => {
    upsertChatLogEntry(localStorage, { id: "a", region: "kr", snapshot: snapshotWith(["A"]), now: 1 });
    upsertChatLogEntry(localStorage, { id: "b", region: "us", snapshot: snapshotWith(["B"]), now: 2 });
    expect(removeChatLogEntry(localStorage, "b").map((e) => e.id)).toEqual(["a"]);
    expect(removeChatLogEntry(localStorage, "a")).toEqual([]);
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBeNull();
  });

  it("손상된 저장값·모양이 다른 항목은 무시한다", () => {
    localStorage.setItem(STRATEGY_CHAT_LOG_KEY, "{not json");
    expect(readChatLog(localStorage)).toEqual([]);
    localStorage.setItem(
      STRATEGY_CHAT_LOG_KEY,
      JSON.stringify([{ id: "x" }, { id: "ok", region: "kr", title: "t", updatedAt: 1, snapshot: { messages: [] } }]),
    );
    expect(readChatLog(localStorage).map((e) => e.id)).toEqual(["ok"]);
  });

  it("용량이 넘치면 방금 갱신한 항목의 결과부터 떨어뜨리고, 그래도 넘치면 오래된 항목을 지운다", () => {
    const storage = makeQuotaStorage(600);
    upsertChatLogEntry(storage, { id: "old", region: "kr", snapshot: snapshotWith(["오래된 대화"]), now: 1 });
    const bigResult = { equity: "x".repeat(400) };
    const entries = upsertChatLogEntry(storage, {
      id: "new",
      region: "kr",
      snapshot: snapshotWith(["새 대화"], { stage: "done", result: bigResult }),
      now: 2,
    });
    expect(entries.map((e) => e.id)).toEqual(["new", "old"]);
    expect(entries[0].snapshot.result).toBeNull();
    expect(entries[0].snapshot.stage).toBe("ready");
    expect(readChatLog(storage).map((e) => e.id)).toEqual(["new", "old"]);

    const tiny = makeQuotaStorage(200);
    upsertChatLogEntry(tiny, { id: "old", region: "kr", snapshot: snapshotWith(["오래된 대화"]), now: 1 });
    const evicted = upsertChatLogEntry(tiny, { id: "new", region: "kr", snapshot: snapshotWith(["새 대화"]), now: 2 });
    expect(evicted.map((e) => e.id)).toEqual(["new"]);
    expect(readChatLog(tiny).map((e) => e.id)).toEqual(["new"]);
  });
});
