// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 본인 계정 삭제(soft delete) 회귀 가드:
// - 활성 자동갱신 구독이 있으면 삭제를 거부한다 (남은 빌링키 청구 방지)
// - 삭제 시 status=DELETED와 함께 빌링 상태를 모두 비운다

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

let DELETE;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ DELETE } = await import("./route"));
  getCurrentUser.mockResolvedValue({ id: 7, email: "u@example.com" });
  userFindUnique.mockResolvedValue({
    subscriptionPlanId: null,
    subscriptionCanceledAt: null,
  });
  userUpdate.mockResolvedValue({});
});

describe("/api/user/account DELETE", () => {
  it("미로그인 사용자는 401을 반환하고 아무것도 변경하지 않는다", async () => {
    getCurrentUser.mockResolvedValue(null);
    const res = await DELETE();
    expect(res.status).toBe(401);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("활성 자동갱신 구독이 있으면 400으로 거부한다", async () => {
    userFindUnique.mockResolvedValue({
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: null,
    });
    const res = await DELETE();
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toContain("구독을 취소");
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("해지 예약된 구독은 삭제를 허용한다", async () => {
    userFindUnique.mockResolvedValue({
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: new Date("2026-07-01T00:00:00Z"),
    });
    const res = await DELETE();
    expect(res.status).toBe(200);
    expect(userUpdate).toHaveBeenCalled();
  });

  it("soft delete 시 status=DELETED와 빌링 상태 초기화를 함께 수행한다", async () => {
    const res = await DELETE();
    expect(res.status).toBe(200);
    expect(userUpdate).toHaveBeenCalledWith({
      where: { id: 7 },
      data: {
        status: "DELETED",
        planTier: "FREE",
        planStartDate: null,
        tossBillingKey: null,
        subscriptionPlanId: null,
        nextBillingAt: null,
        subscriptionCanceledAt: null,
        billingFailCount: 0,
      },
    });
  });
});
