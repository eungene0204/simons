// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 정책 스위치(lib/plans.ts)는 기본 OFF다 — 켜진 경로를 검증하고, 꺼진 케이스는 flags를 내려 확인한다.
const flags = { PRORATED_REFUND_ENABLED: true };
vi.mock("@/lib/plans", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/plans")>();
  return {
    ...actual,
    get PRORATED_REFUND_ENABLED() { return flags.PRORATED_REFUND_ENABLED; },
  };
});

// 중도 해지 정산 라우트 회귀:
// - 비관리자는 404 (관리자 API 존재 자체를 숨긴다)
// - 미리보기(GET)는 돈을 건드리지 않는다
// - 집행(POST)은 화면에서 확인한 금액을 함께 받아야 하고, 감사 로그를 남긴다

const requireAdmin = vi.fn();
const writeAuditLog = vi.fn();
const loadRefundPreview = vi.fn();
const settleRefund = vi.fn();
const settleFullRefund = vi.fn();
const userFindUnique = vi.fn();

vi.mock("@/lib/server/adminAuth", () => ({
  requireAdmin: (...a) => requireAdmin(...a),
  writeAuditLog: (...a) => writeAuditLog(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: { user: { findUnique: (...a) => userFindUnique(...a) } },
}));

vi.mock("@/lib/server/refundSettlement", async () => {
  const actual = await vi.importActual("@/lib/server/refundSettlement");
  return {
    RefundSettlementError: actual.RefundSettlementError,
    loadRefundPreview: (...a) => loadRefundPreview(...a),
    settleRefund: (...a) => settleRefund(...a),
    settleFullRefund: (...a) => settleFullRefund(...a),
  };
});

let GET;
let POST;
let RefundSettlementError;

const admin = { id: 1, email: "admin@example.com", name: "Admin" };

beforeEach(async () => {
  vi.clearAllMocks();
  ({ GET, POST } = await import("./route"));
  ({ RefundSettlementError } = await vi.importActual("@/lib/server/refundSettlement"));
  userFindUnique.mockResolvedValue({ planTier: "PRO", subscriptionPlanId: "PRO" });
});

function getReq(query = "?userId=2") {
  return { nextUrl: new URL(`http://localhost/api/admin/users/refund${query}`) };
}

function postReq(body) {
  return { json: async () => body };
}

const readyPreview = {
  status: "ready",
  order: { orderId: "order-1", paymentKey: "tviva-1", planId: "PRO", cycle: "yearly" },
  settlement: {
    paidAmount: 240_000,
    paidAt: new Date("2026-09-13T00:00:00Z"),
    periodEnd: new Date("2027-09-13T00:00:00Z"),
    totalDays: 365,
    usedDays: 31,
    remainingDays: 334,
    refundAmount: 219_616,
  },
  usage: { backtestsThisPeriod: 0, strategiesSincePaid: 0, accountsSincePaid: 0, validationsSincePaid: 0 },
};

describe("/api/admin/users/refund 권한 게이트", () => {
  it("비관리자는 GET에서 404", async () => {
    requireAdmin.mockResolvedValue(null);
    const res = await GET(getReq());
    expect(res.status).toBe(404);
    expect(loadRefundPreview).not.toHaveBeenCalled();
  });

  it("비관리자는 POST에서 404 — 환불을 시도하지 않는다", async () => {
    requireAdmin.mockResolvedValue(null);
    const res = await POST(postReq({ userId: 2, expectedRefundAmount: 219_616 }));
    expect(res.status).toBe(404);
    expect(settleRefund).not.toHaveBeenCalled();
  });
});

describe("정산 미리보기", () => {
  it("정산액과 일수 내역을 돌려주고 환불은 시도하지 않는다", async () => {
    requireAdmin.mockResolvedValue(admin);
    loadRefundPreview.mockResolvedValue(readyPreview);

    const res = await GET(getReq());
    const body = await res.json();

    expect(body.available).toBe(true);
    expect(body.refundAmount).toBe(219_616);
    expect(body.usedDays).toBe(31);
    expect(body.totalDays).toBe(365);
    expect(body.usage).toEqual(readyPreview.usage);
    expect(settleRefund).not.toHaveBeenCalled();
    expect(settleFullRefund).not.toHaveBeenCalled();
    expect(writeAuditLog).not.toHaveBeenCalled();
  });

  it("대상이 아니면 사유를 그대로 전달한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    loadRefundPreview.mockResolvedValue({
      status: "unavailable",
      reason: "이용 중인 유료 구독이 없습니다.",
    });

    const body = await (await GET(getReq())).json();
    expect(body.available).toBe(false);
    expect(body.reason).toMatch(/유료 구독이 없습니다/);
  });
});

describe("정산 집행", () => {
  it("확인한 금액 없이는 집행하지 않는다", async () => {
    requireAdmin.mockResolvedValue(admin);
    const res = await POST(postReq({ userId: 2 }));
    expect(res.status).toBe(400);
    expect(settleRefund).not.toHaveBeenCalled();
  });

  it("집행 후 감사 로그에 환불액과 이용 일수를 남긴다", async () => {
    requireAdmin.mockResolvedValue(admin);
    settleRefund.mockResolvedValue({
      mode: "prorated",
      order: readyPreview.order,
      settlement: readyPreview.settlement,
      refundedAmount: 219_616,
    });

    const res = await POST(postReq({ userId: 2, expectedRefundAmount: 219_616 }));
    const body = await res.json();

    expect(body.ok).toBe(true);
    expect(settleRefund).toHaveBeenCalledWith(
      expect.anything(),
      2,
      expect.objectContaining({ expectedRefundAmount: 219_616 })
    );
    expect(writeAuditLog).toHaveBeenCalledWith(
      admin,
      expect.objectContaining({
        action: "USER_REFUND_SETTLEMENT",
        targetId: "order-1",
        targetUserId: 2,
        after: expect.objectContaining({ refundAmount: 219_616, planTier: "FREE" }),
      })
    );
    expect(settleFullRefund).not.toHaveBeenCalled();
  });

  it("mode=full은 전액 환불 경로로 가고 별도 감사 액션을 남긴다", async () => {
    requireAdmin.mockResolvedValue(admin);
    settleFullRefund.mockResolvedValue({
      mode: "full",
      order: readyPreview.order,
      settlement: readyPreview.settlement,
      refundedAmount: 240_000,
    });

    const res = await POST(postReq({ userId: 2, mode: "full", expectedRefundAmount: 240_000 }));
    const body = await res.json();

    expect(body).toMatchObject({ ok: true, mode: "full", refundAmount: 240_000 });
    expect(settleFullRefund).toHaveBeenCalledWith(
      expect.anything(),
      2,
      expect.objectContaining({ expectedRefundAmount: 240_000 })
    );
    expect(settleRefund).not.toHaveBeenCalled();
    expect(writeAuditLog).toHaveBeenCalledWith(
      admin,
      expect.objectContaining({
        action: "USER_REFUND_FULL",
        after: expect.objectContaining({ mode: "full", refundAmount: 240_000 }),
      })
    );
  });

  it("알 수 없는 mode는 400", async () => {
    requireAdmin.mockResolvedValue(admin);
    const res = await POST(postReq({ userId: 2, mode: "half", expectedRefundAmount: 1 }));
    expect(res.status).toBe(400);
    expect(settleRefund).not.toHaveBeenCalled();
    expect(settleFullRefund).not.toHaveBeenCalled();
  });

  it("일할 스위치가 꺼져 있으면 prorated는 거부하고 full은 그대로 집행한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    settleFullRefund.mockResolvedValue({
      mode: "full",
      order: readyPreview.order,
      settlement: readyPreview.settlement,
      refundedAmount: 240_000,
    });
    flags.PRORATED_REFUND_ENABLED = false;
    try {
      const denied = await POST(postReq({ userId: 2, expectedRefundAmount: 219_616 }));
      expect(denied.status).toBe(400);
      expect(settleRefund).not.toHaveBeenCalled();

      const full = await POST(postReq({ userId: 2, mode: "full", expectedRefundAmount: 240_000 }));
      expect(full.status).toBe(200);
      expect(settleFullRefund).toHaveBeenCalled();
    } finally {
      flags.PRORATED_REFUND_ENABLED = true;
    }
  });

  it("금액이 달라졌으면 409로 거절하고 로그를 남기지 않는다", async () => {
    requireAdmin.mockResolvedValue(admin);
    settleRefund.mockRejectedValue(
      new RefundSettlementError("정산액이 219000원으로 바뀌었습니다.", 409)
    );

    const res = await POST(postReq({ userId: 2, expectedRefundAmount: 219_616 }));
    expect(res.status).toBe(409);
    expect(writeAuditLog).not.toHaveBeenCalled();
  });
});
