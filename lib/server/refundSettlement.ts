// 정기결제 중도 해지 정산(부분 환불) — 약관 제12조 제9항.
//
// 환불액 = 결제 금액 × (잔여 일수 / 결제 기간 전체 일수), 원 단위 미만 버림.
// 이용 일수는 이용을 개시한 날을 1일로 보아 환불 신청일까지로 센다. 월간·연간이 같은
// 기준을 쓴다 — 기준이 갈리면 두 상품의 환불액을 설명할 수 없다.
//
// 적용 범위는 한국(토스) 레인이다. PayPal 구독(/us)은 연간 상품이 없고 환불 API도
// 배선돼 있지 않아 이 경로에 태우지 않는다(호출부에서 거부한다).
import type { PrismaClient } from "@prisma/client";
import { addMonthsClamped, currentUsagePeriodKey } from "@/lib/server/planLimits";
import { freeDowngradeData } from "@/lib/server/billingRenewal";
import { cancelPayment } from "@/lib/server/tossPayments";
import { isValidBillingCycle, type BillingCycle } from "@/lib/plans";

const DAY_MS = 24 * 60 * 60 * 1000;

export interface RefundSettlement {
  /** 정산 대상 결제 금액(원) */
  paidAmount: number;
  /** 이용 개시일 = 결제 승인 시각 */
  paidAt: Date;
  /** 결제로 확보한 이용 기간의 종료 시각 */
  periodEnd: Date;
  /** 결제 기간 전체 일수 */
  totalDays: number;
  /** 이용 일수(개시일을 1일로 센다) */
  usedDays: number;
  /** 잔여 일수 */
  remainingDays: number;
  /** 환불액(원 단위 미만 버림) */
  refundAmount: number;
}

/**
 * 일할 정산액을 계산한다. 결제 시각 이전(시계 역전)이면 이용 1일로 본다.
 * 기간을 모두 쓴 뒤라면 잔여 0일 → 환불액 0원.
 */
export function computeProratedRefund(params: {
  amount: number;
  paidAt: Date;
  cycle: BillingCycle;
  now?: Date;
}): RefundSettlement {
  const { amount, paidAt, cycle } = params;
  const now = params.now ?? new Date();
  const periodEnd = addMonthsClamped(paidAt, cycle === "yearly" ? 12 : 1);
  // 달마다 길이가 다르므로 일수는 실제 경과로 센다(월 30일 고정 금지).
  const totalDays = Math.max(1, Math.round((periodEnd.getTime() - paidAt.getTime()) / DAY_MS));
  const elapsedDays = Math.floor((now.getTime() - paidAt.getTime()) / DAY_MS);
  const usedDays = Math.min(totalDays, Math.max(1, elapsedDays + 1));
  const remainingDays = totalDays - usedDays;
  return {
    paidAmount: amount,
    paidAt,
    periodEnd,
    totalDays,
    usedDays,
    remainingDays,
    refundAmount: Math.floor((amount * remainingDays) / totalDays),
  };
}

export interface RefundableOrder {
  orderId: string;
  paymentKey: string;
  planId: string;
  cycle: BillingCycle;
}

/**
 * 결제 이후 유료 기능 사용 흔적 — 약관 제12조 2항(미사용 전액 환불) 해당 여부는 관리자가
 * 판단한다. 코드는 근거만 세어 보여주고 결정을 대신하지 않는다.
 */
export interface PaidUsageEvidence {
  /** 현재 사용량 주기(결제일 기준 롤링 1개월)에 실행한 백테스트 수 */
  backtestsThisPeriod: number;
  /** 결제 이후 새로 만든 전략 수 */
  strategiesSincePaid: number;
  /** 결제 이후 새로 만든 가상계좌 수 */
  accountsSincePaid: number;
  /** 결제 이후 저장한 검증(워크포워드·몬테카를로) 수 */
  validationsSincePaid: number;
}

export type RefundPreview =
  | { status: "unavailable"; reason: string }
  | {
      status: "ready";
      order: RefundableOrder;
      settlement: RefundSettlement;
      usage: PaidUsageEvidence;
    };

/** 정산 대상 = 사용자의 가장 최근 토스 승인 결제 중 아직 환불되지 않은 건. */
export async function loadRefundPreview(
  prisma: PrismaClient,
  userId: number,
  now: Date = new Date()
): Promise<RefundPreview> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { subscriptionPlanId: true, paymentProvider: true },
  });
  if (!user) return { status: "unavailable", reason: "사용자를 찾을 수 없습니다." };
  if (!user.subscriptionPlanId) {
    return { status: "unavailable", reason: "이용 중인 유료 구독이 없습니다." };
  }
  if (user.paymentProvider !== "toss") {
    return {
      status: "unavailable",
      reason: "해외(PayPal) 구독은 이 경로로 정산할 수 없습니다. PayPal에서 처리해야 합니다.",
    };
  }

  const order = await prisma.paymentOrder.findFirst({
    where: { userId, provider: "toss", status: "DONE", refundedAt: null },
    orderBy: { approvedAt: "desc" },
    select: {
      orderId: true,
      paymentKey: true,
      planId: true,
      billingCycle: true,
      amount: true,
      approvedAt: true,
    },
  });
  if (!order || !order.paymentKey || !order.approvedAt) {
    return { status: "unavailable", reason: "환불할 수 있는 승인 결제 내역이 없습니다." };
  }

  const cycle: BillingCycle = isValidBillingCycle(order.billingCycle)
    ? order.billingCycle
    : "monthly";
  const paidAt = order.approvedAt;

  const [counter, strategiesSincePaid, accountsSincePaid, validationsSincePaid] =
    await Promise.all([
      prisma.user.findUnique({
        where: { id: userId },
        select: { planStartDate: true, backtestUsageMonth: true, backtestCountThisMonth: true },
      }),
      prisma.strategy.count({ where: { userId, createdAt: { gte: paidAt }, deletedAt: null } }),
      prisma.virtualAccount.count({ where: { userId, createdAt: { gte: paidAt } } }),
      prisma.savedValidation.count({ where: { userId, createdAt: { gte: paidAt } } }),
    ]);
  // 카운터는 주기 키가 현재 주기와 같을 때만 이번 주기 값이다(planLimits와 같은 판정).
  const periodKey = currentUsagePeriodKey(counter?.planStartDate ?? paidAt, now);
  const backtestsThisPeriod =
    counter?.backtestUsageMonth === periodKey
      ? Math.max(0, counter.backtestCountThisMonth ?? 0)
      : 0;

  return {
    status: "ready",
    order: {
      orderId: order.orderId,
      paymentKey: order.paymentKey,
      planId: order.planId,
      cycle,
    },
    settlement: computeProratedRefund({ amount: order.amount, paidAt, cycle, now }),
    usage: { backtestsThisPeriod, strategiesSincePaid, accountsSincePaid, validationsSincePaid },
  };
}

export class RefundSettlementError extends Error {
  readonly httpStatus: number;

  constructor(message: string, httpStatus: number) {
    super(message);
    this.name = "RefundSettlementError";
    this.httpStatus = httpStatus;
  }
}

export type RefundMode = "prorated" | "full";

export interface RefundResult {
  mode: RefundMode;
  order: RefundableOrder;
  settlement: RefundSettlement;
  /** 실제로 결제사에 취소를 요청한 금액 */
  refundedAmount: number;
}

/**
 * 결제사 취소가 성공한 뒤에만 우리 기록을 바꾼다. 환불이 처리되면 유료 플랜은 즉시
 * 종료되고 한도는 무료 플랜 기준이 된다(약관 제12조 2항·9항 공통).
 */
async function executeRefund(
  prisma: PrismaClient,
  userId: number,
  preview: Extract<RefundPreview, { status: "ready" }>,
  mode: RefundMode,
  amount: number,
  reason: string,
  now: Date
): Promise<RefundResult> {
  const { order, settlement } = preview;
  await cancelPayment({
    paymentKey: order.paymentKey,
    cancelReason: reason,
    // 전액은 cancelAmount 없이 보낸다 — 부분 취소 금액이 총액과 같아도 토스는 전액 취소로
    // 처리하지만, 의도를 요청에 그대로 드러낸다.
    ...(mode === "full" ? {} : { cancelAmount: amount }),
    // 같은 주문을 두 번 눌러도 토스가 첫 응답을 돌려준다(중복 환불 방지).
    idempotencyKey: `refund:${order.orderId}`,
  });

  const carrySource = await prisma.user.findUnique({
    where: { id: userId },
    select: {
      planStartDate: true,
      createdAt: true,
      backtestUsageMonth: true,
      backtestCountThisMonth: true,
    },
  });

  await prisma.$transaction([
    prisma.paymentOrder.update({
      where: { orderId: order.orderId },
      data: { refundedAmount: amount, refundedAt: now },
    }),
    prisma.user.update({
      where: { id: userId },
      data: freeDowngradeData(carrySource ?? {}, now),
    }),
  ]);

  return { mode, order, settlement, refundedAmount: amount };
}

async function requireReadyPreview(prisma: PrismaClient, userId: number, now: Date) {
  const preview = await loadRefundPreview(prisma, userId, now);
  if (preview.status !== "ready") {
    throw new RefundSettlementError(preview.reason, 400);
  }
  return preview;
}

/**
 * 일할 정산 환불(약관 제12조 9항) — 토스 부분 취소.
 *
 * expectedRefundAmount는 관리자가 화면에서 확인한 금액이다. 미리보기 이후 날짜가 넘어가
 * 금액이 달라졌으면 집행하지 않고 거절한다 — 돈이 나가는 작업은 본 금액과 같아야 한다.
 */
export async function settleRefund(
  prisma: PrismaClient,
  userId: number,
  params: { expectedRefundAmount: number; reason?: string; now?: Date }
): Promise<RefundResult> {
  const now = params.now ?? new Date();
  const preview = await requireReadyPreview(prisma, userId, now);
  const { settlement } = preview;
  if (settlement.refundAmount <= 0) {
    throw new RefundSettlementError("잔여 기간이 없어 환불할 금액이 없습니다.", 400);
  }
  if (settlement.refundAmount !== params.expectedRefundAmount) {
    throw new RefundSettlementError(
      `정산액이 ${settlement.refundAmount}원으로 바뀌었습니다. 다시 확인한 뒤 진행해주세요.`,
      409
    );
  }
  return executeRefund(
    prisma,
    userId,
    preview,
    "prorated",
    settlement.refundAmount,
    params.reason?.trim() || "중도 해지 정산 환불",
    now
  );
}

/**
 * 미사용 전액 환불(약관 제12조 2항) — 토스 전액 취소.
 *
 * 2항 해당 여부(유료 기능을 한 번도 쓰지 않았는가)는 관리자가 미리보기의 사용 흔적을 보고
 * 판단한다. 코드는 사용 흔적이 있어도 막지 않는다 — 이력이 남는 방식(예: 실패한 백테스트)까지
 * 코드가 단정할 수 없고, 최종 판단은 약관상 회사 몫이다. 대신 결제 금액을 되돌려 보내게 해
 * 관리자가 어느 결제를 전액 환불하는지 확인했음을 강제한다.
 */
export async function settleFullRefund(
  prisma: PrismaClient,
  userId: number,
  params: { expectedRefundAmount: number; reason?: string; now?: Date }
): Promise<RefundResult> {
  const now = params.now ?? new Date();
  const preview = await requireReadyPreview(prisma, userId, now);
  const { settlement } = preview;
  if (settlement.paidAmount !== params.expectedRefundAmount) {
    throw new RefundSettlementError(
      `전액 환불 금액은 결제 금액 ${settlement.paidAmount}원과 같아야 합니다.`,
      409
    );
  }
  return executeRefund(
    prisma,
    userId,
    preview,
    "full",
    settlement.paidAmount,
    params.reason?.trim() || "미사용 전액 환불",
    now
  );
}
