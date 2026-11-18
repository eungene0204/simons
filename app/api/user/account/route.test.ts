// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 본인 계정 삭제(soft delete) 회귀 가드:
// - 활성 자동갱신 구독이 있으면 삭제를 거부한다 (남은 빌링키 청구 방지)
// - 삭제 시 status=DELETED와 함께 빌링 상태를 모두 비운다

const getCurrentUser = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const notifyWithdrawal = vi.fn();
vi.mock("./notification", () => ({ notifyWithdrawal: (...a) => notifyWithdrawal(...a) }));

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
  notifyWithdrawal.mockResolvedValue(undefined);
});

describe("/api/user/account DELETE", () => {
  it("미로그인 사용자는 401을 반환하고 아무것도 변경하지 않는다", async () => {
    getCurrentUser.mockResolvedValue(null);
    const res = await DELETE();
    expect(res.status).toBe(401);
    expect(userUpdate).not.toHaveBeenCalled();
    expect(notifyWithdrawal).not.toHaveBeenCalled();
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
    expect(notifyWithdrawal).not.toHaveBeenCalled();
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
        email: "deleted-7:u@example.com",
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

describe("/api/user/account DELETE 재가입 허용(이메일 해제)", () => {
  // 2026-11-18 사고: 본인 삭제 계정이 원래 이메일을 계속 점유해 같은 주소로 재가입이 막혔다
  it("본인 삭제 시 원래 이메일을 deleted-<id>: 접두 형식으로 바꿔 비운다", async () => {
    await DELETE();
    const data = userUpdate.mock.calls[0][0].data;
    expect(data.email).toBe("deleted-7:u@example.com");
    expect(data.email).not.toBe("u@example.com");
  });
});

describe("/api/user/account DELETE 게스트(특별 계정) 가드", () => {
  it("게스트는 본인 삭제가 막힌다 — 403, 어떤 행도 바꾸지 않는다", async () => {
    getCurrentUser.mockResolvedValue({
      id: 19,
      email: "guest_1234@guest.nullstock.im",
    });

    const res = await DELETE();
    const body = await res.json();

    expect(res.status).toBe(403);
    expect(body.error).toContain("특별 계정");
    expect(userUpdate).not.toHaveBeenCalled();
    expect(notifyWithdrawal).not.toHaveBeenCalled();
    // 구독 조회조차 하지 않는다 — 가드가 앞선다
    expect(userFindUnique).not.toHaveBeenCalled();
  });

  it("일반 회원은 종전대로 삭제된다(가드가 과잉 차단하지 않는다)", async () => {
    const res = await DELETE();
    expect(res.status).toBe(200);
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ where: { id: 7 } })
    );
  });
});

 it("sends original email only after successful withdrawal", async () => {
   await DELETE();
   expect(notifyWithdrawal).toHaveBeenCalledWith(7, "u@example.com");
   expect(userUpdate.mock.invocationCallOrder[0]).toBeLessThan(notifyWithdrawal.mock.invocationCallOrder[0]);
 });
 it("does not notify when saving withdrawal fails", async () => {
   userUpdate.mockRejectedValueOnce(new Error("database unavailable"));
   const res = await DELETE();
   expect(res.status).toBe(500);
   expect(notifyWithdrawal).not.toHaveBeenCalled();
 });
