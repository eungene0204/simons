// @ts-nocheck
/** DELETE /api/strategy?id= — 계좌→전략 복합 FK(NO ACTION, 2026-11-17)가 막지 않게 연결부터 끊고 지운다. */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { accountUpdateMany, strategyDeleteMany, transaction } = vi.hoisted(() => ({
  accountUpdateMany: vi.fn((args) => ({ op: "unlink", args })),
  strategyDeleteMany: vi.fn((args) => ({ op: "delete", args })),
  transaction: vi.fn(async (ops) => ops),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { updateMany: accountUpdateMany },
    strategy: { deleteMany: strategyDeleteMany },
    $transaction: transaction,
  },
}));
vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: async () => ({ userId: 7 }),
  isUnauthorizedAccessError: () => false,
  withOwnership: (where, userId) => ({ ...where, userId }),
}));
vi.mock("@/lib/server/planLimits", () => ({
  assertCanSaveStrategy: vi.fn(),
  PLAN_LIMIT_STRATEGIES: "PLAN_LIMIT_STRATEGIES",
  PLAN_LIMIT_MESSAGES: {},
}));

const { DELETE } = await import("./route");

describe("DELETE /api/strategy?id=", () => {
  beforeEach(() => vi.clearAllMocks());

  it("내 계좌의 연결을 먼저 끊고, 같은 트랜잭션에서 전략을 지운다", async () => {
    const res = await DELETE(new Request("http://localhost/api/strategy?id=7:abc", { method: "DELETE" }));

    expect(res.status).toBe(200);
    const ops = transaction.mock.calls[0][0];
    expect(ops.map((o) => o.op)).toEqual(["unlink", "delete"]);
    expect(ops[0].args).toEqual({ where: { strategyId: "7:abc", userId: 7 }, data: { strategyId: null } });
    expect(ops[1].args).toEqual({ where: { id: "7:abc", userId: 7 } });
  });
});
