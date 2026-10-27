// @ts-nocheck
/** POST /api/strategy — 다시 실행할 수 없는 설정(빈 DSL)은 저장하지 않는다(2026-10-27 빈 설정 저장 사고). */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { strategyUpsert, strategyFindFirst } = vi.hoisted(() => ({ strategyUpsert: vi.fn(), strategyFindFirst: vi.fn() }));

vi.mock("@/lib/prisma", () => ({ prisma: { strategy: { upsert: strategyUpsert, findFirst: strategyFindFirst } } }));
vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: async () => ({ userId: 7 }),
  isUnauthorizedAccessError: () => false,
  withOwnership: (where) => where,
}));
vi.mock("@/lib/server/planLimits", () => ({
  assertCanSaveStrategy: vi.fn(),
  PLAN_LIMIT_STRATEGIES: "PLAN_LIMIT_STRATEGIES",
  PLAN_LIMIT_MESSAGES: {},
}));

const { POST } = await import("./route");
const post = (body: object) =>
  POST(new Request("http://localhost/api/strategy", { method: "POST", body: JSON.stringify(body) }));

describe("POST /api/strategy 실행 가능 설정 검사", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    strategyFindFirst.mockResolvedValue(null);
    strategyUpsert.mockImplementation(async ({ create }) => create);
  });

  it("이름·설명뿐인 설정은 400이고 저장하지 않는다", async () => {
    const res = await post({ name: "전략", description: "설명" });
    expect(res.status).toBe(400);
    expect((await res.json()).code).toBe("STRATEGY_NOT_EXECUTABLE");
    expect(strategyUpsert).not.toHaveBeenCalled();
  });

  it("엔진 요청형 설정은 그대로 저장한다", async () => {
    const res = await post({ name: "전략", universe_id: "kospi", entry: { conditions: [] }, exit: { conditions: [] }, risk: {} });
    expect(res.status).toBe(200);
    expect(JSON.parse(strategyUpsert.mock.calls[0][0].create.settings)).toMatchObject({ entry: { conditions: [] }, risk: {} });
  });
});
