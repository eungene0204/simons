// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 청구서 목록 회귀 가드: 본인 주문만, PENDING(승인 전 이탈) 제외, 승인 시각 우선 표기

const getSessionUserId = vi.fn();
const assertActiveUser = vi.fn();
const orderFindMany = vi.fn();

class FakeUnauthorizedError extends Error {}

vi.mock("@/lib/get-user", () => ({
  getSessionUserId: (...a) => getSessionUserId(...a),
  assertActiveUser: (...a) => assertActiveUser(...a),
  isUnauthorizedAccessError: (e) => e instanceof FakeUnauthorizedError,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    paymentOrder: { findMany: (...a) => orderFindMany(...a) },
  },
}));

let GET;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ GET } = await import("./route"));
  getSessionUserId.mockResolvedValue(7);
  assertActiveUser.mockResolvedValue(undefined);
  orderFindMany.mockResolvedValue([]);
});

describe("/api/payment/orders GET", () => {
  it("세션이 없으면 401을 반환한다", async () => {
    getSessionUserId.mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(401);
    expect(orderFindMany).not.toHaveBeenCalled();
  });

  it("정지/삭제 계정은 401을 반환한다", async () => {
    assertActiveUser.mockRejectedValue(new FakeUnauthorizedError());
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it("본인 주문만, PENDING 제외로 조회한다", async () => {
    await GET();
    expect(orderFindMany).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { userId: 7, status: { in: ["DONE", "FAILED"] } },
      })
    );
  });

  it("승인 시각(approvedAt)을 우선 사용하고 없으면 생성 시각으로 표기한다", async () => {
    orderFindMany.mockResolvedValue([
      {
        id: "o1",
        planId: "PRO",
        amount: 25_000,
        status: "DONE",
        approvedAt: new Date("2026-07-01T02:00:00Z"),
        createdAt: new Date("2026-07-01T01:59:00Z"),
      },
      {
        id: "o2",
        planId: "PRO",
        amount: 25_000,
        status: "FAILED",
        approvedAt: null,
        createdAt: new Date("2026-06-01T00:00:00Z"),
      },
    ]);
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.orders).toEqual([
      {
        id: "o1",
        planId: "PRO",
        amount: 25_000,
        status: "DONE",
        date: "2026-07-01T02:00:00.000Z",
      },
      {
        id: "o2",
        planId: "PRO",
        amount: 25_000,
        status: "FAILED",
        date: "2026-06-01T00:00:00.000Z",
      },
    ]);
  });
});
