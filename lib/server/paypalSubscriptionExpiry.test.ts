// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 해지 예약된 PayPal 구독의 기간 만료 스윕:
// - 대상은 paypal + 해지 예약 + 결제일 도래인 구독뿐이다
// - 해지하지 않은 활성 구독은 건드리지 않는다(웹훅이 늦어도 유료 사용자를 내리면 안 된다)

const userFindMany = vi.fn();
const userUpdate = vi.fn();

const prisma = {
  user: {
    findMany: (...a) => userFindMany(...a),
    update: (...a) => userUpdate(...a),
  },
};

const NOW = new Date("2026-09-30T01:00:00Z");
let processDuePaypalExpirations;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ processDuePaypalExpirations } = await import("./paypalSubscriptionExpiry"));
  userUpdate.mockResolvedValue({});
});

describe("processDuePaypalExpirations", () => {
  it("해지 예약된 구독만 조회한다", async () => {
    userFindMany.mockResolvedValue([]);

    await processDuePaypalExpirations(prisma, NOW);

    expect(userFindMany).toHaveBeenCalledWith(
      expect.objectContaining({
        where: expect.objectContaining({
          paymentProvider: "paypal",
          subscriptionCanceledAt: { not: null },
          nextBillingAt: { lte: NOW },
        }),
      })
    );
  });

  it("기간이 끝난 해지 예약 구독을 FREE로 내리고 구독 상태를 비운다", async () => {
    userFindMany.mockResolvedValue([{ id: 42 }]);

    const summary = await processDuePaypalExpirations(prisma, NOW);

    expect(summary).toEqual({ downgraded: 1 });
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 42 },
        data: expect.objectContaining({
          planTier: "FREE",
          paypalSubscriptionId: null,
          subscriptionPlanId: null,
          nextBillingAt: null,
        }),
      })
    );
  });

  it("한 명의 실패가 나머지 전환을 막지 않는다", async () => {
    userFindMany.mockResolvedValue([{ id: 1 }, { id: 2 }]);
    userUpdate.mockRejectedValueOnce(new Error("db down")).mockResolvedValue({});

    const summary = await processDuePaypalExpirations(prisma, NOW);

    expect(summary).toEqual({ downgraded: 1 });
    expect(userUpdate).toHaveBeenCalledTimes(2);
  });
});
