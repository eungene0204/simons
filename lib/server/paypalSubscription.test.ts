// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// PayPal 구독의 서버 반영 — 승인 복귀와 웹훅이 같은 사실을 두 번 알려오므로 전부 멱등이어야 한다:
// - 이미 같은 구독으로 활성이면 다시 쓰지 않는다(구독 시작일이 매 통지마다 갱신되면 안 된다)
// - 같은 결제(saleId)가 두 번 통지돼도 이력이 겹치지 않는다
// - USD 결제 이력은 센트 단위로 남는다

const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const orderFindUnique = vi.fn();
const orderCreate = vi.fn();

const prisma = {
  user: { findUnique: (...a) => userFindUnique(...a), update: (...a) => userUpdate(...a) },
  paymentOrder: {
    findUnique: (...a) => orderFindUnique(...a),
    create: (...a) => orderCreate(...a),
  },
  $transaction: async (ops) => Promise.all(ops),
};

let activatePaypalSubscription;
let recordPaypalSubscriptionPayment;
let downgradePaypalSubscriber;

beforeEach(async () => {
  vi.clearAllMocks();
  ({
    activatePaypalSubscription,
    recordPaypalSubscriptionPayment,
    downgradePaypalSubscriber,
  } = await import("./paypalSubscription"));
  userUpdate.mockResolvedValue({});
  orderCreate.mockImplementation(async ({ data }) => data);
});

describe("activatePaypalSubscription", () => {
  it("구독을 활성화하고 다음 결제일을 PayPal이 알려준 시각으로 둔다", async () => {
    userFindUnique.mockResolvedValue({ planTier: "FREE", paypalSubscriptionId: "I-SUB-1" });

    const changed = await activatePaypalSubscription(prisma, {
      userId: 42,
      planId: "PRO",
      subscriptionId: "I-SUB-1",
      payerId: "PAYER-1",
      nextBillingTime: "2026-09-30T10:00:00Z",
    });

    expect(changed).toBe(true);
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 42 },
        data: expect.objectContaining({
          planTier: "PRO",
          paymentProvider: "paypal",
          paypalSubscriptionId: "I-SUB-1",
          subscriptionPlanId: "PRO",
          nextBillingAt: new Date("2026-09-30T10:00:00Z"),
          subscriptionCanceledAt: null,
        }),
      })
    );
  });

  it("이미 같은 구독으로 활성이면 다시 쓰지 않는다", async () => {
    userFindUnique.mockResolvedValue({
      planTier: "PRO",
      paypalSubscriptionId: "I-SUB-1",
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: null,
      nextBillingAt: new Date("2026-09-30T10:00:00Z"),
    });

    const changed = await activatePaypalSubscription(prisma, {
      userId: 42,
      planId: "PRO",
      subscriptionId: "I-SUB-1",
      nextBillingTime: "2026-09-30T10:00:00Z",
    });

    expect(changed).toBe(false);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  // 예약된 플랜 변경(PREMIUM→PRO revise 승인) 중에는 조회 경로(sync)가 등급을 앞당기면 안 된다
  it("플랜 변경 예약 중에는 등급(planTier)을 건드리지 않는다", async () => {
    userFindUnique.mockResolvedValue({
      planTier: "PREMIUM", // 남은 기간의 등급
      paypalSubscriptionId: "I-SUB-1",
      subscriptionPlanId: "PRO", // 다음 결제일부터의 청구 플랜
      subscriptionCanceledAt: null,
      nextBillingAt: new Date("2026-09-30T10:00:00Z"),
    });

    const changed = await activatePaypalSubscription(prisma, {
      userId: 42,
      planId: "PRO",
      subscriptionId: "I-SUB-1",
      nextBillingTime: "2026-09-30T10:00:00Z",
    });

    expect(changed).toBe(false);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("업그레이드 완료 — 즉시 등급 전환 + 옛 플랜의 백테스트 잔여를 새 주기에 병합한다", async () => {
    const planStart = new Date("2026-08-20T10:00:00Z");
    userFindUnique.mockResolvedValue({
      planTier: "PRO",
      planStartDate: planStart,
      paypalSubscriptionId: "I-SUB-NEW",
      paypalPriorSubscriptionId: "I-SUB-OLD", // 업그레이드 전환 중 표식
      subscriptionPlanId: "PREMIUM",
      subscriptionCanceledAt: null,
      nextBillingAt: new Date("2026-09-30T10:00:00Z"),
      // PRO 500회 중 100회 사용 — 잔여 400회가 이월돼야 한다
      backtestUsageMonth: planStart.toISOString(),
      backtestCountThisMonth: 100,
    });

    const changed = await activatePaypalSubscription(prisma, {
      userId: 42,
      planId: "PREMIUM",
      subscriptionId: "I-SUB-NEW",
      nextBillingTime: "2026-09-30T10:00:00Z",
    });

    expect(changed).toBe(true);
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          planTier: "PREMIUM",
          // 음수 카운터 = 병합된 이월분(500 - 100 = 400)
          backtestCountThisMonth: -400,
        }),
      })
    );
  });

  it("업그레이드 병합은 사용량 주기가 지난 옛 기록을 이월하지 않는다 — 잔여는 전액", async () => {
    userFindUnique.mockResolvedValue({
      planTier: "PRO",
      planStartDate: new Date("2026-08-20T10:00:00Z"),
      paypalSubscriptionId: "I-SUB-NEW",
      paypalPriorSubscriptionId: "I-SUB-OLD",
      subscriptionPlanId: "PREMIUM",
      subscriptionCanceledAt: null,
      nextBillingAt: null,
      backtestUsageMonth: "stale-old-key", // 지난 주기 기록 — 이번 주기 사용량은 0
      backtestCountThisMonth: 480,
    });

    await activatePaypalSubscription(prisma, {
      userId: 42,
      planId: "PREMIUM",
      subscriptionId: "I-SUB-NEW",
    });

    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ backtestCountThisMonth: -500 }),
      })
    );
  });

  it("활성 상태여도 다음 청구일이 PayPal 값과 다르면 맞춘다(드리프트 복구)", async () => {
    userFindUnique.mockResolvedValue({
      planTier: "PRO",
      paypalSubscriptionId: "I-SUB-1",
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: null,
      nextBillingAt: new Date("2026-10-30T10:00:00Z"),
    });

    const changed = await activatePaypalSubscription(prisma, {
      userId: 42,
      planId: "PRO",
      subscriptionId: "I-SUB-1",
      nextBillingTime: "2026-09-30T10:00:00Z",
    });

    expect(changed).toBe(true);
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ nextBillingAt: new Date("2026-09-30T10:00:00Z") }),
      })
    );
  });
});

describe("recordPaypalSubscriptionPayment", () => {
  it("결제 이력을 센트 단위로 남기고 다음 결제일은 PayPal이 알려준 값으로 맞춘다", async () => {
    orderFindUnique.mockResolvedValue(null);

    const recorded = await recordPaypalSubscriptionPayment(prisma, {
      userId: 42,
      planId: "PRO",
      saleId: "SALE-1",
      approvedAt: "2026-09-30T10:00:00Z",
      nextBillingTime: "2026-10-30T10:00:00Z",
    });

    expect(recorded).toBe(true);
    expect(orderCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          userId: 42,
          planId: "PRO",
          provider: "paypal",
          currency: "USD",
          amount: 1900, // $19.00 — 원 단위 이력과 자릿수가 섞이지 않게 센트로 남긴다
          status: "DONE",
          paymentKey: "SALE-1",
        }),
      })
    );
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        // 청구가 확정된 플랜이 곧 등급이다 — 예약된 플랜 변경은 이 순간 전환된다
        data: expect.objectContaining({
          planTier: "PRO",
          nextBillingAt: new Date("2026-10-30T10:00:00Z"),
        }),
      })
    );
  });

  // 회귀(2026-08-31 prod E2E): 활성화가 PayPal 정본 날짜를 넣은 뒤 첫 결제가 거기에 +1개월을
  // 더해 한 달이 밀렸다(PayPal 9/30 vs 우리 10/30). 이제 날짜는 PayPal 값만 쓴다.
  it("다음 청구 시각을 모르면 기존 값을 그대로 둔다(우리가 계산하지 않는다)", async () => {
    orderFindUnique.mockResolvedValue(null);

    await recordPaypalSubscriptionPayment(prisma, {
      userId: 42,
      planId: "PRO",
      saleId: "SALE-2",
    });

    const data = userUpdate.mock.calls[0][0].data;
    expect(data.nextBillingAt).toBeUndefined();
    expect(data.billingFailCount).toBe(0);
  });

  it("같은 결제가 다시 통지되면 이력을 겹쳐 남기지 않는다", async () => {
    orderFindUnique.mockResolvedValue({ id: "existing" });

    const recorded = await recordPaypalSubscriptionPayment(prisma, {
      userId: 42,
      planId: "PRO",
      saleId: "SALE-1",
    });

    expect(recorded).toBe(false);
    expect(orderCreate).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });
});

describe("downgradePaypalSubscriber", () => {
  it("FREE 전환 시 구독 ID까지 비운다(잔존 ID로 재반영되지 않게)", async () => {
    await downgradePaypalSubscriber(prisma, 42);

    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          planTier: "FREE",
          paypalSubscriptionId: null,
          subscriptionPlanId: null,
        }),
      })
    );
  });
});
