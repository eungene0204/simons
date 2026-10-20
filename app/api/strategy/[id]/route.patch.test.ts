import { beforeEach, describe, expect, it, vi } from "vitest";

const strategyUpdateMany = vi.hoisted(() => vi.fn());

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: async () => ({ userId: 7 }),
  withOwnership: (where: Record<string, unknown>, userId: number | null) =>
    userId == null ? where : { ...where, userId },
  isUnauthorizedAccessError: () => false,
}));
vi.mock("@/lib/prisma", () => ({
  prisma: { strategy: { updateMany: strategyUpdateMany } },
}));
vi.mock("@/lib/server/strategyHistorySummary", () => ({ findBacktestHistorySummary: vi.fn() }));

import { PATCH } from "./route";

function patch(body: unknown) {
  return PATCH(
    new Request("http://localhost/api/strategy/s1", { method: "PATCH", body: JSON.stringify(body) }),
    { params: { id: "s1" } }
  );
}

describe("PATCH /api/strategy/[id] — 공개 전환", () => {
  beforeEach(() => vi.clearAllMocks());

  it("소유자의 저장 전략만 공개 여부를 바꾼다", async () => {
    strategyUpdateMany.mockResolvedValue({ count: 1 });
    const res = await patch({ isPublic: true });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ id: "s1", isPublic: true });
    expect(strategyUpdateMany).toHaveBeenCalledWith({
      where: { id: "s1", isSaved: true, userId: 7 },
      data: { isPublic: true },
    });
  });

  it("남의 전략·없는 전략은 404", async () => {
    strategyUpdateMany.mockResolvedValue({ count: 0 });
    expect((await patch({ isPublic: true })).status).toBe(404);
  });

  it("isPublic이 불리언이 아니면 400이고 DB를 건드리지 않는다", async () => {
    expect((await patch({ isPublic: "yes" })).status).toBe(400);
    expect((await patch({ name: "x" })).status).toBe(400);
    expect(strategyUpdateMany).not.toHaveBeenCalled();
  });
});
