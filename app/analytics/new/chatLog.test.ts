/**
 * 대화 로그 클라이언트 — 계정별 서버 저장(`/api/strategy-chat-log`)을 부르는 얇은 층.
 * 목록 응답 정리, 저장 본문 모양, 상한 초과 시 결과 떨어뜨리기, 떠날 때 keepalive.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readChatLog, readChatLogSnapshot, removeChatLogEntry, upsertChatLogEntry } from "./chatLog";

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const entry = (id: string, updatedAt: number) => ({
  id,
  region: "kr",
  title: id,
  messageCount: 1,
  createdAt: updatedAt,
  updatedAt,
});

describe("대화 로그 클라이언트", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("목록은 서버 응답에서 모양이 맞는 항목만 최근 사용 순으로 돌려준다", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ entries: [entry("a", 1), { id: "bad" }, entry("b", 2)] }));
    expect((await readChatLog()).map((e) => e.id)).toEqual(["b", "a"]);
    expect(fetchMock).toHaveBeenCalledWith("/api/strategy-chat-log", expect.objectContaining({ cache: "no-store" }));
  });

  it("목록 요청이 실패하면 거부한다(호출부가 무시)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "Unauthorized" }, 401));
    await expect(readChatLog()).rejects.toThrow();
  });

  it("저장은 PUT /api/strategy-chat-log/{id}에 지역과 스냅샷을 보내고 갱신된 목록을 받는다", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ entries: [entry("s 1", 1)] }));
    const snapshot = { messages: [{ role: "user", content: "PBR 1 이하" }], stage: "ready" };
    const entries = await upsertChatLogEntry({ id: "s 1", region: "us", snapshot });
    expect(entries?.map((e) => e.id)).toEqual(["s 1"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/strategy-chat-log/s%201");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ region: "us", snapshot });
    expect(init.keepalive).toBeUndefined();
  });

  it("메시지 없는 스냅샷은 보내지 않는다", async () => {
    expect(await upsertChatLogEntry({ id: "s", region: "kr", snapshot: { messages: [] } })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("화면을 떠날 때의 저장은 keepalive로 보낸다", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ entries: [] }));
    await upsertChatLogEntry(
      { id: "s", region: "kr", snapshot: { messages: [{ role: "user", content: "x" }] } },
      { keepalive: true },
    );
    expect(fetchMock.mock.calls[0][1].keepalive).toBe(true);
  });

  it("삭제는 DELETE를 보내고 갱신된 목록을 받는다", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ entries: [entry("a", 1)] }));
    expect((await removeChatLogEntry("b")).map((e) => e.id)).toEqual(["a"]);
    expect(fetchMock).toHaveBeenCalledWith("/api/strategy-chat-log/b", expect.objectContaining({ method: "DELETE" }));
  });

  it("스냅샷 읽기는 모양이 맞을 때만 돌려주고 실패·손상은 null", async () => {
    const snapshot = { messages: [{ role: "user", content: "x" }] };
    fetchMock.mockResolvedValueOnce(jsonResponse({ snapshot }));
    expect(await readChatLogSnapshot("a")).toEqual(snapshot);
    fetchMock.mockResolvedValueOnce(jsonResponse({ snapshot: { messages: "x" } }));
    expect(await readChatLogSnapshot("a")).toBeNull();
    fetchMock.mockResolvedValueOnce(jsonResponse({ error: "Not found" }, 404));
    expect(await readChatLogSnapshot("a")).toBeNull();
  });
});
