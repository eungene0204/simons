// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 콘솔 대화 기록 — 사용자별·전략 카드 턴 필터, 저장된 카드, 칸 도입 전 턴의 대화 기록 복원(2026-09-30)
const { requireAdmin, qaCount, qaFindMany, chatFindMany } = vi.hoisted(() => ({
  requireAdmin: vi.fn(),
  qaCount: vi.fn(),
  qaFindMany: vi.fn(),
  chatFindMany: vi.fn(),
}));

vi.mock("@/lib/server/adminAuth", () => ({ requireAdmin }));
vi.mock("@/lib/prisma", () => ({
  prisma: {
    chatQaLog: { count: qaCount, findMany: qaFindMany },
    strategyChatLog: { findMany: chatFindMany },
  },
}));

const { GET } = await import("./route");

const req = (query) => ({ nextUrl: new URL(`http://localhost/api/admin/qa-logs${query}`) });

const row = (over) => ({
  id: "q1",
  userId: 31,
  userEmail: "g@guest.nullstock.im",
  sessionId: "s1",
  turnIndex: 0,
  question: "RSI 전략",
  answer: "[전략 요약 카드]",
  answerKind: "strategy",
  chipAnswer: false,
  latencyMs: 10,
  createdAt: new Date("2026-09-30T00:00:00Z"),
  strategySnapshot: null,
  ...over,
});

describe("GET /api/admin/qa-logs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    requireAdmin.mockResolvedValue({ id: 1 });
    qaCount.mockResolvedValue(1);
    chatFindMany.mockResolvedValue([]);
  });

  it("비관리자는 404", async () => {
    requireAdmin.mockResolvedValue(null);
    expect((await GET(req(""))).status).toBe(404);
  });

  it("사용자·전략 카드 턴으로 거른다", async () => {
    qaFindMany.mockResolvedValue([]);
    await GET(req("?userId=31&strategyOnly=1"));
    expect(qaFindMany.mock.calls[0][0].where).toEqual({
      userId: 31,
      answer: { contains: "[전략 요약 카드]" },
    });
  });

  it("저장된 카드를 객체로 준다", async () => {
    const strategy = { summaryItems: [{ label: "매수", value: "RSI 30 이하" }], parsed: { rsi: 30 } };
    qaFindMany.mockResolvedValue([row({ strategySnapshot: JSON.stringify(strategy) })]);

    const data = await (await GET(req("?userId=31"))).json();

    expect(data.logs[0]).toMatchObject({ strategy, strategySource: "log" });
    expect(data.logs[0].strategySnapshot).toBeUndefined();
    expect(chatFindMany).not.toHaveBeenCalled();
  });

  it("칸 도입 전 턴은 같은 세션의 대화 기록에서 같은 번호의 카드를 복원한다", async () => {
    qaFindMany.mockResolvedValue([row({ turnIndex: 1 })]);
    const items = [{ label: "종목군", value: "KOSPI200" }];
    chatFindMany.mockResolvedValue([
      {
        userId: 31,
        sessionId: "s1",
        snapshot: JSON.stringify({
          messages: [
            { role: "user", content: "안녕" },
            { role: "assistant", content: "안녕하세요" },
            { role: "user", content: "RSI 전략" },
            { role: "assistant", parsed: { u: 1 }, confirmedSummaryItems: items },
          ],
        }),
      },
    ]);

    const data = await (await GET(req("?userId=31"))).json();

    expect(data.logs[0]).toMatchObject({
      strategy: { summaryItems: items, parsed: { u: 1 } },
      strategySource: "chat_snapshot",
    });
  });

  it("복원할 대화 기록이 없으면 카드 없이 준다", async () => {
    qaFindMany.mockResolvedValue([row()]);
    const data = await (await GET(req("?userId=31"))).json();
    expect(data.logs[0]).toMatchObject({ strategy: null, strategySource: null });
  });
});
