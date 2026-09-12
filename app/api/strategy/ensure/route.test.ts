// @ts-nocheck
/**
 * POST /api/strategy/ensure 회귀 테스트.
 *
 * 이 라우트는 백테스트 결과에서 바로 가상계좌를 만들 때, 계좌가 참조할 Strategy 행을
 * "있으면 그대로, 없으면 저장"으로 확정한다. 핵심 계약은 **이미 저장된 같은 DSL 의 전략을
 * 개명하지 않는 것** — POST /api/strategy 를 그대로 썼다면 사용자가 붙여둔 이름이
 * 백테스트 요약 이름으로 덮어써졌다.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const strategyFindUnique = vi.fn();
const strategyUpsert = vi.fn();
const backtestResultFindFirst = vi.fn();
const backtestResultCreate = vi.fn();
const getOwnershipContext = vi.fn();
const assertCanSaveStrategy = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategy: {
      findUnique: (...a) => strategyFindUnique(...a),
      upsert: (...a) => strategyUpsert(...a),
    },
    backtestResult: {
      findFirst: (...a) => backtestResultFindFirst(...a),
      create: (...a) => backtestResultCreate(...a),
    },
  },
}));

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: (...a) => getOwnershipContext(...a),
  isUnauthorizedAccessError: () => false,
}));

vi.mock("@/lib/server/planLimits", () => ({
  assertCanSaveStrategy: (...a) => assertCanSaveStrategy(...a),
  PLAN_LIMIT_STRATEGIES: "PLAN_LIMIT_STRATEGIES",
  PLAN_LIMIT_MESSAGES: { PLAN_LIMIT_STRATEGIES: "전략 저장 한도에 도달했습니다." },
}));

const { POST } = await import("@/app/api/strategy/ensure/route");

const DSL = { universe: ["KOSPI"], entry: { conditions: [] }, exit: { conditions: [] } };

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/strategy/ensure", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/strategy/ensure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOwnershipContext.mockResolvedValue({ userId: 7 });
    strategyFindUnique.mockResolvedValue(null);
    strategyUpsert.mockImplementation(async ({ create }) => ({ id: create.id, name: create.name }));
    backtestResultFindFirst.mockResolvedValue(null);
    backtestResultCreate.mockImplementation(async ({ data }) => ({ id: "bt1", ...data }));
  });

  it("이름이나 DSL이 없으면 400", async () => {
    expect((await POST(makeRequest({ dsl: DSL }))).status).toBe(400);
    expect((await POST(makeRequest({ name: "전략" }))).status).toBe(400);
  });

  it("저장된 전략이 없으면 사용자 소유로 새로 저장한다", async () => {
    const res = await POST(makeRequest({ name: "저PBR 전략", description: "프롬프트", dsl: DSL }));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.created).toBe(true);
    expect(data.id).toMatch(/^7:/);
    expect(strategyUpsert).toHaveBeenCalledTimes(1);
    const create = strategyUpsert.mock.calls[0][0].create;
    expect(create.userId).toBe(7);
    expect(create.name).toBe("저PBR 전략");
    expect(create.isSaved).toBe(true);
    expect(JSON.parse(create.settings).universe).toEqual(["KOSPI"]);
  });

  it("이미 저장된 같은 전략이 있으면 이름을 덮어쓰지 않고 그대로 돌려준다", async () => {
    strategyFindUnique.mockResolvedValue({
      id: "7:abc",
      name: "내가 붙인 이름",
      isSaved: true,
      deletedAt: null,
    });

    const res = await POST(makeRequest({ name: "백테스트 요약 이름", dsl: DSL }));
    const data = await res.json();

    expect(data).toEqual({ id: "7:abc", name: "내가 붙인 이름", created: false });
    expect(strategyUpsert).not.toHaveBeenCalled();
    expect(assertCanSaveStrategy).not.toHaveBeenCalled();
  });

  it("백테스트 실행이 남긴 미저장 행은 저장 상태로 승격한다", async () => {
    strategyFindUnique.mockResolvedValue({
      id: "7:abc",
      name: "전략 abcdef12",
      isSaved: false,
      deletedAt: null,
    });
    strategyUpsert.mockImplementation(async ({ update }) => ({ id: "7:abc", name: update.name }));

    const res = await POST(makeRequest({ name: "저PBR 전략", dsl: DSL }));
    const data = await res.json();

    expect(data.created).toBe(true);
    expect(strategyUpsert.mock.calls[0][0].update.isSaved).toBe(true);
    expect(data.name).toBe("저PBR 전략");
  });

  /**
   * 이 경로로 저장된 전략도 "내 전략" 목록에 그대로 뜬다. 결과 행이 없으면 목록에서
   * 눌렀을 때 /analytics/[id] 가 "저장된 백테스트 결과가 없습니다"로만 끝나므로,
   * 전략을 저장할 때 실행한 백테스트 결과도 함께 남긴다.
   */
  it("백테스트 결과를 함께 받으면 전략과 같이 저장한다", async () => {
    const backtestResult = {
      totalReturn: 12.5,
      cagr: 8.1,
      maxDrawdown: -18,
      trades: 53,
      equity: [1000, 1100],
      dates: ["2024-01-02", "2024-01-03"],
      tradesList: [{ date: "2024-01-02", symbol: "005930", type: "buy" }],
      perAssetStats: {},
    };

    await POST(makeRequest({ name: "저PBR 전략", dsl: DSL, backtestResult }));

    expect(backtestResultCreate).toHaveBeenCalledTimes(1);
    const data = backtestResultCreate.mock.calls[0][0].data;
    expect(data.strategyId).toMatch(/^7:/);
    expect(JSON.parse(data.summary).cagr).toBe(8.1);
    expect(JSON.parse(data.trades)).toHaveLength(1);
  });

  it("이미 저장된 전략이라도 결과 행이 없으면 채워 넣는다", async () => {
    strategyFindUnique.mockResolvedValue({
      id: "7:abc",
      name: "내가 붙인 이름",
      isSaved: true,
      deletedAt: null,
    });

    await POST(makeRequest({ name: "백테스트 요약 이름", dsl: DSL, backtestResult: { cagr: 8.1 } }));

    expect(backtestResultCreate).toHaveBeenCalledTimes(1);
    expect(backtestResultCreate.mock.calls[0][0].data.strategyId).toBe("7:abc");
  });

  it("이미 결과 행이 있으면 덮어쓰지 않는다", async () => {
    backtestResultFindFirst.mockResolvedValue({ id: "bt-old" });

    await POST(makeRequest({ name: "저PBR 전략", dsl: DSL, backtestResult: { cagr: 8.1 } }));

    expect(backtestResultCreate).not.toHaveBeenCalled();
  });

  it("백테스트 결과가 없으면 결과 행을 만들지 않는다", async () => {
    await POST(makeRequest({ name: "저PBR 전략", dsl: DSL }));

    expect(backtestResultFindFirst).not.toHaveBeenCalled();
    expect(backtestResultCreate).not.toHaveBeenCalled();
  });

  it("전략 저장 한도를 넘으면 403과 안내 문구를 준다", async () => {
    assertCanSaveStrategy.mockRejectedValue(new Error("PLAN_LIMIT_STRATEGIES"));

    const res = await POST(makeRequest({ name: "저PBR 전략", dsl: DSL }));
    const data = await res.json();

    expect(res.status).toBe(403);
    expect(data.message).toBe("전략 저장 한도에 도달했습니다.");
    expect(strategyUpsert).not.toHaveBeenCalled();
  });
});
