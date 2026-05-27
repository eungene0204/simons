import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const virtualAccountFindMany = vi.fn();
const virtualAccountUpdateMany = vi.fn();
const virtualMarketStateDeleteMany = vi.fn();
const strategyDelete = vi.fn();
const backtestResultDeleteMany = vi.fn();
const transaction = vi.fn(async (callback: any) =>
  callback({
    virtualAccount: { updateMany: virtualAccountUpdateMany },
    virtualMarketState: { deleteMany: virtualMarketStateDeleteMany },
    strategy: { delete: strategyDelete },
    backtestResult: { deleteMany: backtestResultDeleteMany },
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
    strategyDelete.mockResolvedValue({});
    backtestResultDeleteMany.mockResolvedValue({ count: 0 });
  });

  it("deletes the strategy without deleting preserved backtest results", async () => {
    const response = await DELETE(new Request("http://localhost/api/strategy/strategy_a"), {
      params: { id: "strategy_a" },
    });

    expect(response.status).toBe(200);
    expect(transaction).toHaveBeenCalledTimes(1);
    expect(strategyDelete).toHaveBeenCalledWith({ where: { id: "strategy_a" } });
    expect(backtestResultDeleteMany).not.toHaveBeenCalled();
  });

  it("stops linked auto trading accounts before deleting the strategy", async () => {
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
