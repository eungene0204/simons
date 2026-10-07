import { beforeEach, describe, expect, it, vi } from "vitest";
import { createQaLogOutbox, qaTurnKey } from "./qaLogDelivery";
import { sendQaLog, type QaLogPayload } from "./qaLog";

const payload: QaLogPayload = {
  sessionId: "session", turnIndex: 0, question: "질문", answer: "답변",
  answerKind: "text", chipAnswer: false, latencyMs: null, strategy: null,
};

beforeEach(() => { sessionStorage.clear(); vi.unstubAllGlobals(); });

describe("QA delivery outbox", () => {
  it("keeps failed writes across a reload and removes them only after acknowledgement", async () => {
    const send = vi.fn().mockResolvedValue(false);
    const first = createQaLogOutbox(7, sessionStorage, send);
    first.enqueue(payload);
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    first.stop();
    expect(sessionStorage.length).toBe(1);
    const retry = vi.fn().mockResolvedValue(true);
    const restored = createQaLogOutbox(7, sessionStorage, retry);
    await restored.flush();
    expect(retry).toHaveBeenCalledWith(send.mock.calls[0][0]);
    expect(sessionStorage.length).toBe(0);
  });

  it("does not send a guest's pending logs under another user's session", async () => {
    const fail = vi.fn().mockResolvedValue(false);
    createQaLogOutbox(7, sessionStorage, fail).enqueue(payload);
    await vi.waitFor(() => expect(fail).toHaveBeenCalled());
    const send = vi.fn();
    await createQaLogOutbox(8, sessionStorage, send).flush();
    expect(send).not.toHaveBeenCalled();
    expect(sessionStorage.length).toBe(1);
  });

  it("coalesces duplicate enqueues while a write is pending", async () => {
    let resolve!: (ok: boolean) => void;
    const send = vi.fn(() => new Promise<boolean>((r) => { resolve = r; }));
    const box = createQaLogOutbox(7, sessionStorage, send);
    box.enqueue(payload);
    box.enqueue({ ...payload, latencyMs: 500 });
    expect(send).toHaveBeenCalledTimes(1);
    expect(sessionStorage.length).toBe(1);
    resolve(true);
    await vi.waitFor(() => expect(sessionStorage.length).toBe(0));
  });

  it("records edits at the same turn index as different revisions", () => {
    expect(qaTurnKey(payload)).not.toBe(qaTurnKey({ ...payload, question: "수정 질문" }));
    expect(qaTurnKey(payload)).toBe(qaTurnKey({ ...payload }));
  });

  it("retries HTTP failures and handles strategy snapshots above the keepalive limit", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false });
    vi.stubGlobal("fetch", fetchMock);
    expect(await sendQaLog(payload)).toBe(false);
    fetchMock.mockResolvedValue({ ok: true });
    expect(await sendQaLog({ ...payload, strategy: { summaryItems: null, parsed: "가".repeat(30_000) } })).toBe(true);
    expect(fetchMock.mock.calls[0][1].keepalive).toBe(true);
    expect(fetchMock.mock.calls[1][1].keepalive).toBe(false);
  });
});
