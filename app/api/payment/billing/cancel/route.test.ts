// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 자동갱신 해지 라우트 회귀 테스트:
// - 해지는 즉시 FREE 전환이 아니라 해지 예약(subscriptionCanceledAt)만 기록한다
// - 구독이 없으면 400, 이미 해지 예약이면 멱등 처리

const getCurrentUser = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getCurrentUser: (...a) => getCurrentUser(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
    },
  },
}));

let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ POST } = await import("./route"));
  getCurrentUser.mockResolvedValue({ id: 7, email: "u@example.com", name: "유저" });
  userUpdate.mockResolvedValue({});
});

describe("/api/payment/billing/cancel", () => {
  it("미로그인 요청은 401", async () => {
    getCurrentUser.mockResolvedValue(null);
    const res = await POST();
    expect(res.status).toBe(401);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("구독이 없으면 400", async () => {
    userFindUnique.mockResolvedValue({
      subscriptionPlanId: null,
      nextBillingAt: null,
      subscriptionCanceledAt: null,
    });
    const res = await POST();
    expect(res.status).toBe(400);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("해지 예약만 기록하고 planTier는 바꾸지 않는다 (만료일 반환)", async () => {
    const nextBillingAt = new Date("2026-08-10T00:00:00Z");
    userFindUnique.mockResolvedValue({
      subscriptionPlanId: "PRO",
      nextBillingAt,
      subscriptionCanceledAt: null,
    });

    const res = await POST();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ ok: true, expiresAt: nextBillingAt.toISOString() });

    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: { subscriptionCanceledAt: expect.any(Date) },
      })
    );
  });

  it("이미 해지 예약된 구독은 멱등 처리(200, 추가 업데이트 없음)", async () => {
    userFindUnique.mockResolvedValue({
      subscriptionPlanId: "PRO",
      nextBillingAt: new Date("2026-08-10T00:00:00Z"),
      subscriptionCanceledAt: new Date("2026-07-15T00:00:00Z"),
    });

    const res = await POST();
    expect(res.status).toBe(200);
    expect(userUpdate).not.toHaveBeenCalled();
  });
});
