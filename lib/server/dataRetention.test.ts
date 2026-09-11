import { beforeEach, describe, expect, it, vi } from "vitest";
import { RETENTION_DAYS, purgeExpiredRecords } from "./dataRetention";

const deleteMany = {
  chatQaLog: vi.fn(),
  emailVerification: vi.fn(),
  paymentWebhookEvent: vi.fn(),
  adminAuditLog: vi.fn(),
};

const prisma = {
  chatQaLog: { deleteMany: deleteMany.chatQaLog },
  emailVerification: { deleteMany: deleteMany.emailVerification },
  paymentWebhookEvent: { deleteMany: deleteMany.paymentWebhookEvent },
  adminAuditLog: { deleteMany: deleteMany.adminAuditLog },
} as any;

const NOW = new Date("2026-09-11T00:00:00Z");
const daysBefore = (days: number) => new Date(NOW.getTime() - days * 86_400_000);

describe("lib/server/dataRetention", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const fn of Object.values(deleteMany)) fn.mockResolvedValue({ count: 0 });
  });

  it("대상별 보존기간 경계로 삭제 조건을 만든다", async () => {
    await purgeExpiredRecords(prisma, NOW);

    expect(deleteMany.chatQaLog).toHaveBeenCalledWith({
      where: { createdAt: { lt: daysBefore(RETENTION_DAYS.chatQaLog) } },
    });
    expect(deleteMany.paymentWebhookEvent).toHaveBeenCalledWith({
      where: { receivedAt: { lt: daysBefore(RETENTION_DAYS.paymentWebhookEvent) } },
    });
    expect(deleteMany.adminAuditLog).toHaveBeenCalledWith({
      where: { createdAt: { lt: daysBefore(RETENTION_DAYS.adminAuditLog) } },
    });
  });

  // 재발송으로 만료가 밀리므로 발송 시각이 아니라 만료 시각을 기준으로 센다.
  it("이메일 인증번호는 만료 시각 기준으로 지운다", async () => {
    await purgeExpiredRecords(prisma, NOW);

    expect(deleteMany.emailVerification).toHaveBeenCalledWith({
      where: { expiresAt: { lt: daysBefore(RETENTION_DAYS.emailVerification) } },
    });
  });

  it("삭제 건수를 대상별로 돌려준다", async () => {
    deleteMany.chatQaLog.mockResolvedValue({ count: 12 });
    deleteMany.adminAuditLog.mockResolvedValue({ count: 3 });

    const summary = await purgeExpiredRecords(prisma, NOW);

    expect(summary.chatQaLog).toBe(12);
    expect(summary.adminAuditLog).toBe(3);
    expect(summary.paymentWebhookEvent).toBe(0);
  });

  // 한 대상이 실패했다고 나머지를 보존기간 초과 상태로 남겨 두지 않는다.
  it("한 대상이 실패해도 나머지는 계속 파기한다", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    deleteMany.chatQaLog.mockRejectedValue(new Error("db down"));
    deleteMany.adminAuditLog.mockResolvedValue({ count: 5 });

    const summary = await purgeExpiredRecords(prisma, NOW);

    expect(summary.chatQaLog).toBe(0);
    expect(summary.adminAuditLog).toBe(5);
  });

  // 지우면 안 되는 두 갈래: 법정 보존 의무(결제)와 처리방침이 약속한 보유(모의투자 기록).
  it("결제 주문과 모의투자 기록은 건드리지 않는다", async () => {
    const guarded = {
      ...prisma,
      paymentOrder: { deleteMany: vi.fn() },
      virtualMarketLog: { deleteMany: vi.fn() },
      virtualOrder: { deleteMany: vi.fn() },
    };

    await purgeExpiredRecords(guarded as any, NOW);

    expect(guarded.paymentOrder.deleteMany).not.toHaveBeenCalled();
    expect(guarded.virtualMarketLog.deleteMany).not.toHaveBeenCalled();
    expect(guarded.virtualOrder.deleteMany).not.toHaveBeenCalled();
  });
});
