// @ts-nocheck
/**
 * POST /api/strategy/save-with-backtest 회귀 테스트 — 플랜의 저장 전략 수 한도.
 *
 * 결과 화면의 "저장" 버튼이 이 라우트를 쓴다. 2026-09-03 감사에서 이 라우트만
 * assertCanSaveStrategy를 건너뛰어 무료 플랜의 3개 제한이 주 경로에서 작동하지 않았다.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { strategyFindUnique, strategyUpsert, getOwnershipContext, assertCanSaveStrategy } = vi.hoisted(
  () => ({
    strategyFindUnique: vi.fn(),
    strategyUpsert: vi.fn(),
    getOwnershipContext: vi.fn(),
    assertCanSaveStrategy: vi.fn(),
  })
);

vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategy: { findUnique: strategyFindUnique },
    $transaction: async (fn) =>
      fn({
        strategy: { upsert: strategyUpsert },
        backtestResult: { create: vi.fn(async () => null) },
      }),
  },
}));

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext,
  isUnauthorizedAccessError: () => false,
}));

vi.mock("@/lib/server/backtestCache", () => ({
  computeStrategyIdFromDsl: () => "dslhash",
  triggerVectorMemoryBacktestUpsert: vi.fn(),
}));

vi.mock("@/lib/server/planLimits", () => ({
  assertCanSaveStrategy,
  PLAN_LIMIT_STRATEGIES: "PLAN_LIMIT_STRATEGIES",
  PLAN_LIMIT_MESSAGES: { PLAN_LIMIT_STRATEGIES: "전략 저장 한도에 도달했습니다." },
}));

const { POST } = await import("./route");

const DSL = { universe: { id: "KOSPI" }, entry: { conditions: [] }, exit: { conditions: [] } };

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/strategy/save-with-backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/strategy/save-with-backtest 플랜 한도", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOwnershipContext.mockResolvedValue({ userId: 7 });
    strategyFindUnique.mockResolvedValue(null);
    strategyUpsert.mockImplementation(async ({ create }) => ({ id: create.id, name: create.name }));
  });

  it("신규 저장은 저장 전략 수 한도를 검사한다", async () => {
    const res = await POST(makeRequest({ name: "저PBR 전략", dsl: DSL }));

    expect(res.status).toBe(200);
    expect(assertCanSaveStrategy).toHaveBeenCalledWith(expect.anything(), 7);
    expect(strategyUpsert).toHaveBeenCalledTimes(1);
  });

  it("한도를 넘으면 403과 안내 문구를 주고 아무것도 저장하지 않는다", async () => {
    assertCanSaveStrategy.mockRejectedValue(new Error("PLAN_LIMIT_STRATEGIES"));

    const res = await POST(makeRequest({ name: "저PBR 전략", dsl: DSL }));
    const data = await res.json();

    expect(res.status).toBe(403);
    expect(data.code).toBe("PLAN_LIMIT_STRATEGIES");
    expect(data.message).toBe("전략 저장 한도에 도달했습니다.");
    expect(strategyUpsert).not.toHaveBeenCalled();
  });

  it("이미 저장된 같은 전략의 갱신(같은 이름)은 한도를 검사하지 않는다", async () => {
    strategyFindUnique.mockResolvedValue({
      id: "7:dslhash",
      name: "저PBR 전략",
      isSaved: true,
      deletedAt: null,
    });
    strategyUpsert.mockImplementation(async ({ update }) => ({ id: "7:dslhash", name: update.name }));

    const res = await POST(makeRequest({ name: "저PBR 전략", dsl: DSL }));

    expect(res.status).toBe(200);
    expect(assertCanSaveStrategy).not.toHaveBeenCalled();
  });

  it("소프트 삭제된 전략을 다시 저장하면 신규로 보고 한도를 검사한다", async () => {
    strategyFindUnique.mockResolvedValue({
      id: "7:dslhash",
      name: "저PBR 전략",
      isSaved: false,
      deletedAt: new Date("2026-08-01"),
    });
    strategyUpsert.mockImplementation(async ({ update }) => ({ id: "7:dslhash", name: update.name }));

    await POST(makeRequest({ name: "저PBR 전략", dsl: DSL }));

    expect(assertCanSaveStrategy).toHaveBeenCalledTimes(1);
  });
});
