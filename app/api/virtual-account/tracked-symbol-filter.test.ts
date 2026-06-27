import { beforeEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";
import {
  filterMonitorableSymbols,
  resolveTrackedSymbolsForStrategy,
} from "@/lib/strategy-tracked-symbols";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    stock: {
      findMany: vi.fn(),
    },
    backtestResult: {
      findFirst: vi.fn(),
    },
    backtestHistory: {
      findFirst: vi.fn(),
    },
  },
}));

vi.mock("@/lib/krx-stocks", () => ({
  loadStockList: vi.fn().mockResolvedValue([
    { symbol: "005930", name: "삼성전자", market: "KOSPI" },
    { symbol: "000660", name: "SK하이닉스", market: "KOSPI" },
    { symbol: "001570", name: "금양", market: "KOSPI" },
  ]),
}));

const mockStockFindMany = vi.mocked(prisma.stock.findMany);
const mockBacktestResultFindFirst = vi.mocked(prisma.backtestResult.findFirst);
const mockBacktestHistoryFindFirst = vi.mocked(prisma.backtestHistory.findFirst);

describe("tracked symbol filtering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStockFindMany.mockResolvedValue([]);
    mockBacktestResultFindFirst.mockResolvedValue(null);
    mockBacktestHistoryFindFirst.mockResolvedValue(null);
  });

  it("로컬 상장폐지 목록과 DB DELISTED 종목을 모니터링 종목에서 제외한다", async () => {
    mockStockFindMany.mockResolvedValue([{ symbol: "123456" }] as any);

    await expect(
      filterMonitorableSymbols(["005930", "001570", "123456", "000660"])
    ).resolves.toEqual(["005930", "000660"]);
  });

  it("전략 백테스트 상위 종목에서도 상장폐지 종목을 제외한다", async () => {
    mockBacktestResultFindFirst.mockResolvedValue({
      summary: JSON.stringify({
        topSymbols: ["001570", "005930", "000660"],
        perAssetStats: {
          "001570": { totalReturn: 10, trades: 2 },
          "005930": { totalReturn: 8, trades: 2 },
          "000660": { totalReturn: 6, trades: 2 },
        },
      }),
    } as any);

    await expect(
      resolveTrackedSymbolsForStrategy({
        strategyId: "strategy-1",
        strategyName: "테스트 전략",
      })
    ).resolves.toEqual({
      symbols: ["005930", "000660"],
      source: "backtest",
    });
  });
});
