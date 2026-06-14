import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const virtualAccountFindMany = vi.fn();
const virtualAccountUpdateMany = vi.fn();
const virtualMarketStateDeleteMany = vi.fn();
const strategyUpdate = vi.fn();
const strategyUpdateMany = vi.fn();
const strategyFindUnique = vi.fn();
const strategyFindFirst = vi.fn();
const backtestHistoryFindFirst = vi.fn();
const userBacktestHistoryFindFirst = vi.fn();
const strategyDelete = vi.fn();
const backtestResultDeleteMany = vi.fn();
const strategyEmbeddingDeleteMany = vi.fn();
const adviceExperienceDeleteMany = vi.fn();
const backtestRunDeleteMany = vi.fn();
const transaction = vi.fn(async (callback: any) =>
  callback({
    virtualAccount: { updateMany: virtualAccountUpdateMany },
    virtualMarketState: { deleteMany: virtualMarketStateDeleteMany },
    strategy: { update: strategyUpdate, updateMany: strategyUpdateMany, delete: strategyDelete },
    backtestResult: { deleteMany: backtestResultDeleteMany },
    strategyEmbedding: { deleteMany: strategyEmbeddingDeleteMany },
    adviceExperience: { deleteMany: adviceExperienceDeleteMany },
    backtestRun: { deleteMany: backtestRunDeleteMany },
  })
);

vi.mock("@/lib/prisma", () => ({
  prisma: {
    $transaction: transaction,
    strategy: {
      findUnique: strategyFindUnique,
      findFirst: strategyFindFirst,
    },
    backtestHistory: {
      findFirst: backtestHistoryFindFirst,
    },
    userBacktestHistory: {
      findFirst: userBacktestHistoryFindFirst,
    },
    virtualAccount: {
      findMany: virtualAccountFindMany,
    },
  },
}));

let DELETE: any;
let GET: any;

beforeAll(async () => {
  const routeModule = await import("./route");
  DELETE = routeModule.DELETE;
  GET = routeModule.GET;
});

describe("app/api/strategy/[id]/route GET", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    strategyFindUnique.mockResolvedValue({
      id: "strategy_a",
      name: "첫번째 전략",
      description: "프롬프트 원문",
      settings: JSON.stringify({ description: "프롬프트 원문" }),
      BacktestResult: [],
    });
    backtestHistoryFindFirst
      .mockResolvedValueOnce({
        id: "hist-direct",
        strategyId: "strategy_a",
        strategyName: "첫번째 전략",
        universe: "000020,000040,000050",
        conditions: JSON.stringify({ entry: null, exit: null }),
        createdAt: new Date("2026-06-14T15:00:00Z"),
      })
      .mockResolvedValueOnce({
        id: "hist-visible",
        strategyId: null,
        strategyName: "첫번째 전략",
        universe: "KOSPI",
        conditions: JSON.stringify({
          entry: { logic: "AND", names: ["PBR <= 1"] },
          exit: { logic: "AND", names: ["손절 -12% 하락시 매도"] },
          position: "최대 8종목 · 126일 보유",
          risk: "손절 12%",
        }),
        createdAt: new Date("2026-06-14T15:00:01Z"),
      });
    userBacktestHistoryFindFirst.mockResolvedValue(null);
  });

  it("strategyId 히스토리 조건이 비어 있으면 저장 목록의 조건 SOT를 fallback으로 반환한다", async () => {
    const response = await GET(new Request("http://localhost/api/strategy/strategy_a"), {
      params: { id: "strategy_a" },
    });
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(backtestHistoryFindFirst).toHaveBeenNthCalledWith(1, {
      where: { OR: [{ strategyId: "strategy_a" }, { cacheKey: "strategy_a" }] },
      orderBy: { createdAt: "desc" },
    });
    expect(backtestHistoryFindFirst).toHaveBeenNthCalledWith(2, {
      where: {
        strategyName: "첫번째 전략",
        isVisible: true,
      },
      orderBy: { createdAt: "desc" },
    });
    expect(payload.historySummary).toMatchObject({
      id: "hist-visible",
      universeName: "KOSPI",
      entryBlocks: ["PBR <= 1"],
      exitBlocks: ["손절 -12% 하락시 매도"],
      positionText: "최대 8종목 · 126일 보유",
      riskText: "손절 12%",
    });
  });
});

describe("app/api/strategy/[id]/route DELETE", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    strategyFindFirst.mockResolvedValue({ id: "strategy_a" });
    virtualAccountFindMany.mockResolvedValue([]);
    virtualAccountUpdateMany.mockResolvedValue({ count: 0 });
    virtualMarketStateDeleteMany.mockResolvedValue({ count: 0 });
    strategyUpdate.mockResolvedValue({});
    strategyUpdateMany.mockResolvedValue({ count: 1 });
    strategyDelete.mockResolvedValue({});
    backtestResultDeleteMany.mockResolvedValue({ count: 0 });
    strategyEmbeddingDeleteMany.mockResolvedValue({ count: 0 });
    adviceExperienceDeleteMany.mockResolvedValue({ count: 0 });
    backtestRunDeleteMany.mockResolvedValue({ count: 0 });
  });

  it("소프트 삭제: 전략을 DB에서 지우지 않고 isSaved=false + deletedAt만 기록한다", async () => {
    const response = await DELETE(new Request("http://localhost/api/strategy/strategy_a"), {
      params: { id: "strategy_a" },
    });

    expect(response.status).toBe(200);
    expect(transaction).toHaveBeenCalledTimes(1);
    expect(strategyDelete).not.toHaveBeenCalled();
    expect(strategyUpdate).toHaveBeenCalledTimes(1);
    const updateArg = strategyUpdate.mock.calls[0][0];
    expect(updateArg.where).toEqual({ id: "strategy_a" });
    expect(updateArg.data.isSaved).toBe(false);
    expect(updateArg.data.deletedAt).toBeInstanceOf(Date);
  });

  it("공유 캐시·코칭 데이터(BacktestResult/Run, Embedding, AdviceExperience)는 보존한다", async () => {
    const response = await DELETE(new Request("http://localhost/api/strategy/strategy_a"), {
      params: { id: "strategy_a" },
    });

    expect(response.status).toBe(200);
    expect(backtestResultDeleteMany).not.toHaveBeenCalled();
    expect(backtestRunDeleteMany).not.toHaveBeenCalled();
    expect(strategyEmbeddingDeleteMany).not.toHaveBeenCalled();
    expect(adviceExperienceDeleteMany).not.toHaveBeenCalled();
  });

  it("stops linked auto trading accounts before soft-deleting the strategy", async () => {
    virtualAccountFindMany.mockResolvedValue([{ id: "account_a", name: "Auto A" }]);

    const response = await DELETE(new Request("http://localhost/api/strategy/strategy_a"), {
      params: { id: "strategy_a" },
    });
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(virtualMarketStateDeleteMany).toHaveBeenCalledWith({ where: { accountId: { in: ["account_a"] } } });
    expect(virtualAccountUpdateMany).toHaveBeenCalledWith({
      where: { id: { in: ["account_a"] } },
      data: { tradingMode: "manual" },
    });
    expect(payload.stoppedAccounts).toEqual([{ id: "account_a", name: "Auto A" }]);
  });
});
