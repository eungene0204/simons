// @ts-nocheck
import { describe, expect, it, vi } from "vitest";

const virtualAccountFindFirst = vi.fn();
const stockFindUnique = vi.fn();
const transaction = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    $transaction: transaction,
    stock: {
      findUnique: stockFindUnique,
    },
    delistingAuditLog: {
      create: vi.fn(),
    },
    virtualAccount: {
      findFirst: virtualAccountFindFirst,
    },
  },
}));

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: async () => ({ userId: 1 }),
  isUnauthorizedAccessError: () => false,
  withOwnership: (where: Record<string, unknown>, userId: number) => ({
    ...where,
    userId,
  }),
}));

vi.mock("@/lib/krx-stocks", () => ({
  getStockNameMap: async () => ({}),
}));

const { POST } = await import("@/app/api/virtual-account/[id]/orders/route");

describe("POST /api/virtual-account/[id]/orders CLOSED account guard", () => {
  it("CLOSED 계좌는 다시 매매할 수 없다", async () => {
    stockFindUnique.mockResolvedValue({ listingStatus: "NORMAL" });
    transaction.mockImplementation(async (callback) =>
      callback({
        virtualAccount: {
          findFirst: vi.fn().mockResolvedValue({
            id: "account-1",
            userId: 1,
            currentCash: 1_000_000,
            status: "CLOSED",
          }),
        },
      })
    );

    const response = await POST(
      new Request("http://localhost/api/virtual-account/account-1/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "buy",
          symbol: "005930",
          name: "삼성전자",
          quantity: 1,
          price: 60_000,
          orderType: "MARKET",
        }),
      }),
      { params: { id: "account-1" } }
    );

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({
      error: "닫힌 계좌에서는 매매할 수 없습니다.",
    });
  });
});
