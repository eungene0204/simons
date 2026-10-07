// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 대화 기록 라우트 가드: 비로그인도 기록, 상한 절단, 알 수 없는 종류 거부

const getCurrentUser = vi.fn();
const chatQaLogCreate = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getCurrentUser: (...a) => getCurrentUser(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    chatQaLog: { create: (...a) => chatQaLogCreate(...a) },
  },
}));

let POST;

const validBody = {
  sessionId: "session-1",
  turnIndex: 0,
  question: "RSI 30 이하 매수 전략",
  answer: "전략을 이렇게 이해했어요",
  answerKind: "coach",
  chipAnswer: false,
  latencyMs: 1234,
};

const post = (body) => POST({ json: async () => body });

beforeEach(async () => {
  vi.resetAllMocks();
  ({ POST } = await import("./route"));
  getCurrentUser.mockResolvedValue({ id: 7, email: "a@b.com" });
  chatQaLogCreate.mockResolvedValue({});
});

describe("/api/chat-log POST", () => {
  it("질문과 답변을 사용자와 함께 기록한다", async () => {
    const res = await post(validBody);

    expect(res.status).toBe(204);
    expect(chatQaLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({
        userId: 7,
        userEmail: "a@b.com",
        sessionId: "session-1",
        turnIndex: 0,
        question: "RSI 30 이하 매수 전략",
        answer: "전략을 이렇게 이해했어요",
        answerKind: "coach",
        latencyMs: 1234,
      }),
    });
  });

  it("비로그인 대화도 기록한다", async () => {
    getCurrentUser.mockResolvedValue(null);

    const res = await post(validBody);

    expect(res.status).toBe(204);
    expect(chatQaLogCreate).toHaveBeenCalledWith({
      data: expect.objectContaining({ userId: null, userEmail: null }),
    });
  });

  it("질문·답변이 비면 기록하지 않는다", async () => {
    const res = await post({ ...validBody, answer: "   " });

    expect(res.status).toBe(400);
    expect(chatQaLogCreate).not.toHaveBeenCalled();
  });

  it("알 수 없는 답변 종류는 거부한다", async () => {
    const res = await post({ ...validBody, answerKind: "made-up" });

    expect(res.status).toBe(400);
    expect(chatQaLogCreate).not.toHaveBeenCalled();
  });

  it("긴 답변은 상한까지만 저장한다", async () => {
    await post({ ...validBody, answer: "가".repeat(30_000) });

    expect(chatQaLogCreate.mock.calls[0][0].data.answer).toHaveLength(20_000);
  });

  it("기록 실패는 500으로 알리되 예외를 던지지 않는다", async () => {
    chatQaLogCreate.mockRejectedValue(new Error("db down"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const res = await post(validBody);

    expect(res.status).toBe(500);
  });

  // 2026-09-30: 콘솔에서 사용자가 입력한 전략을 우리가 어떻게 해석했는지 보기 위해 카드를 저장한다.
  it("그 턴의 전략 카드를 JSON으로 함께 기록한다", async () => {
    const strategy = { summaryItems: [{ label: "매수", value: "RSI 30 이하" }], parsed: { rsi: 30 } };
    await post({ ...validBody, answerKind: "strategy", strategy });

    const saved = chatQaLogCreate.mock.calls[0][0].data.strategySnapshot;
    expect(JSON.parse(saved)).toEqual(strategy);
  });

  it("카드가 없는 턴은 비워 둔다", async () => {
    await post(validBody);
    expect(chatQaLogCreate.mock.calls[0][0].data.strategySnapshot).toBeNull();
  });
});


describe("acknowledged QA delivery", () => {
  const delivery = { ...validBody, deliveryId: "delivery-1", ownerId: 7 };

  it("retries use one row ID and a duplicate acknowledgement succeeds", async () => {
    await post(delivery);
    const id = chatQaLogCreate.mock.calls[0][0].data.id;
    chatQaLogCreate.mockRejectedValue(Object.assign(new Error("duplicate"), { code: "P2002" }));
    expect((await post(delivery)).status).toBe(204);
    expect(chatQaLogCreate.mock.calls[1][0].data.id).toBe(id);
  });

  it("keeps guest identity and separates users even with the same delivery ID", async () => {
    await post(delivery);
    const memberId = chatQaLogCreate.mock.calls[0][0].data.id;
    getCurrentUser.mockResolvedValue({ id: 8, email: "guest_1234@guest.nullstock.im" });
    await post({ ...delivery, ownerId: 8 });
    const saved = chatQaLogCreate.mock.calls[1][0].data;
    expect(saved.id).not.toBe(memberId);
    expect(saved).toMatchObject({ userId: 8, userEmail: "guest_1234@guest.nullstock.im" });
  });

  it.each([null, { id: 8 }])("rejects delivery after the session owner changes", async (user) => {
    getCurrentUser.mockResolvedValue(user);
    expect((await post(delivery)).status).toBe(409);
    expect(chatQaLogCreate).not.toHaveBeenCalled();
  });

  it("preserves an unknown latency instead of reporting zero", async () => {
    await post({ ...delivery, latencyMs: null });
    expect(chatQaLogCreate.mock.calls[0][0].data.latencyMs).toBeNull();
  });

  it("rejects null JSON", async () => {
    expect((await post(null)).status).toBe(400);
  });
});
