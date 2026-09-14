// @ts-nocheck
/**
 * 대화 로그 API — 세션 사용자 없이는 아무것도 하지 않고, 제목·메시지 수는 서버가 스냅샷에서 뽑는다.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const getCurrentUser = vi.fn();
const upsert = vi.fn();
const list = vi.fn();
const readSnapshot = vi.fn();
const remove = vi.fn();

vi.mock("@/lib/get-user", () => ({ getCurrentUser: (...a) => getCurrentUser(...a) }));
vi.mock("@/lib/server/strategyChatLog", () => ({
  upsertStrategyChatLog: (...a) => upsert(...a),
  listStrategyChatLog: (...a) => list(...a),
  readStrategyChatLogSnapshot: (...a) => readSnapshot(...a),
  deleteStrategyChatLog: (...a) => remove(...a),
}));

import { DELETE, GET, PUT } from "./route";
import { GET as LIST } from "../route";

const params = { params: { sessionId: "sess-1" } };
const put = (body: unknown) =>
  PUT(new Request("http://x/api/strategy-chat-log/sess-1", { method: "PUT", body: JSON.stringify(body) }), params);
const snapshot = { messages: [{ role: "user", content: "PBR 1 이하\n둘째 줄" }, { role: "assistant" }], stage: "ready" };

beforeEach(() => {
  vi.clearAllMocks();
  getCurrentUser.mockResolvedValue({ id: 7, email: "u@example.com" });
  upsert.mockResolvedValue(undefined);
  remove.mockResolvedValue(undefined);
  list.mockResolvedValue([{ id: "sess-1", region: "kr", title: "PBR 1 이하", messageCount: 2, createdAt: 1, updatedAt: 1 }]);
  readSnapshot.mockResolvedValue(JSON.stringify(snapshot));
});

describe("/api/strategy-chat-log", () => {
  it("비로그인은 401이고 아무것도 읽거나 쓰지 않는다", async () => {
    getCurrentUser.mockResolvedValue(null);
    expect((await LIST()).status).toBe(401);
    expect((await GET(new Request("http://x"), params)).status).toBe(401);
    expect((await put({ region: "kr", snapshot })).status).toBe(401);
    expect((await DELETE(new Request("http://x"), params)).status).toBe(401);
    expect(list).not.toHaveBeenCalled();
    expect(upsert).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });

  it("목록은 세션 사용자의 것만 조회한다", async () => {
    const res = await LIST();
    expect(res.status).toBe(200);
    expect((await res.json()).entries).toHaveLength(1);
    expect(list).toHaveBeenCalledWith(7);
  });

  it("저장은 서버가 제목·메시지 수를 스냅샷에서 뽑아 세션 사용자로 쓰고 갱신된 목록을 돌려준다", async () => {
    const res = await put({ region: "kr", snapshot });
    expect(res.status).toBe(200);
    expect(upsert).toHaveBeenCalledWith({
      userId: 7,
      sessionId: "sess-1",
      region: "kr",
      title: "PBR 1 이하",
      messageCount: 2,
      snapshot: JSON.stringify(snapshot),
    });
    expect((await res.json()).entries[0].id).toBe("sess-1");
  });

  it("지역·스냅샷 모양이 틀리거나 메시지가 없으면 400", async () => {
    expect((await put({ region: "jp", snapshot })).status).toBe(400);
    expect((await put({ region: "kr", snapshot: { messages: "x" } })).status).toBe(400);
    expect((await put({ region: "kr", snapshot: { messages: [] } })).status).toBe(400);
    expect(upsert).not.toHaveBeenCalled();
  });

  it("세션 id가 상한을 넘으면 400", async () => {
    const long = { params: { sessionId: "x".repeat(101) } };
    expect((await GET(new Request("http://x"), long)).status).toBe(400);
    expect((await DELETE(new Request("http://x"), long)).status).toBe(400);
  });

  it("스냅샷 읽기는 저장된 JSON을 그대로 돌려주고 없으면 404", async () => {
    const res = await GET(new Request("http://x"), params);
    expect(res.status).toBe(200);
    expect((await res.json()).snapshot).toEqual(snapshot);
    expect(readSnapshot).toHaveBeenCalledWith(7, "sess-1");

    readSnapshot.mockResolvedValue(null);
    expect((await GET(new Request("http://x"), params)).status).toBe(404);
  });

  it("삭제는 세션 사용자로 묶어 지우고 갱신된 목록을 돌려준다", async () => {
    list.mockResolvedValue([]);
    const res = await DELETE(new Request("http://x"), params);
    expect(res.status).toBe(200);
    expect(remove).toHaveBeenCalledWith(7, "sess-1");
    expect((await res.json()).entries).toEqual([]);
  });
});
