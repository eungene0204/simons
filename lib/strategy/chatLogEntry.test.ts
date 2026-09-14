import { describe, expect, it } from "vitest";

import {
  deriveChatLogTitle,
  isChatLogEntry,
  isChatLogSnapshot,
  serializeChatLogSnapshot,
  sortChatLogEntries,
} from "./chatLogEntry";

const snapshotWith = (texts: string[], extra: Record<string, unknown> = {}) => ({
  messages: texts.map((content, i) => ({ role: i % 2 === 0 ? "user" : "assistant", content })),
  ...extra,
});

describe("대화 로그 공통 규칙", () => {
  it("첫 사용자 발화의 첫 줄을 제목으로 삼고 길면 자른다", () => {
    expect(deriveChatLogTitle([{ role: "assistant", content: "안내" }, { role: "user", content: " 첫 줄\n둘째 줄 " }]))
      .toBe("첫 줄");
    expect(deriveChatLogTitle([{ role: "user", content: "가".repeat(100) }])).toBe(`${"가".repeat(80)}…`);
    expect(deriveChatLogTitle([{ role: "user", content: "  " }])).toBe("");
  });

  it("스냅샷은 role이 있는 메시지 배열이어야 한다", () => {
    expect(isChatLogSnapshot(snapshotWith(["A"]))).toBe(true);
    expect(isChatLogSnapshot({ messages: [] })).toBe(true);
    expect(isChatLogSnapshot({ messages: [{ content: "role 없음" }] })).toBe(false);
    expect(isChatLogSnapshot({ messages: "x" })).toBe(false);
    expect(isChatLogSnapshot(null)).toBe(false);
  });

  it("목록 항목은 모양이 맞는 것만 인정하고 최근 사용 순으로 정렬한다", () => {
    const ok = { id: "a", region: "kr" as const, title: "t", messageCount: 1, createdAt: 1, updatedAt: 1 };
    expect(isChatLogEntry(ok)).toBe(true);
    expect(isChatLogEntry({ ...ok, region: "jp" })).toBe(false);
    expect(isChatLogEntry({ ...ok, updatedAt: "1" })).toBe(false);
    expect(
      sortChatLogEntries([ok, { ...ok, id: "b", updatedAt: 3 }, { ...ok, id: "c", updatedAt: 2 }]).map((e) => e.id),
    ).toEqual(["b", "c", "a"]);
  });

  it("상한을 넘는 스냅샷은 백테스트 결과를 떨어뜨리고 done을 ready로 강등하며, 그래도 넘치면 null", () => {
    const small = snapshotWith(["새 대화"], { stage: "done", result: { equity: "x".repeat(400) } });
    expect(serializeChatLogSnapshot(small, 10_000)).toBe(JSON.stringify(small));

    const slim = JSON.parse(serializeChatLogSnapshot(small, 300)!);
    expect(slim.result).toBeNull();
    expect(slim.stage).toBe("ready");
    expect(slim.messages).toEqual(small.messages);

    expect(serializeChatLogSnapshot(snapshotWith(["결과 없이 긴 대화".repeat(50)]), 100)).toBeNull();
  });
});
