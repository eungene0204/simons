import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const virtualAccountFindMany = vi.fn();
const virtualAccountUpdateMany = vi.fn();
const virtualMarketStateDeleteMany = vi.fn();
const strategyUpdate = vi.fn();
const strategyUpdateMany = vi.fn();
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
    virtualAccount: {
      findMany: virtualAccountFindMany,
    },
  },
}));

let DELETE: any;

beforeAll(async () => {
  const routeModule = await import("./route");
  DELETE = routeModule.DELETE;
});

describe("app/api/strategy/[id]/route DELETE", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
