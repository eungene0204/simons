import { beforeEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";
import {
  filterMonitorableSymbols,
  filterSymbolsForCurrency,
  resolveTrackedSymbolsForStrategy,
  savedUniverseId,
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

  it("DB 거래정지(TRADING_SUSPENDED) 종목을 모니터링 종목에서 제외한다", async () => {
    mockStockFindMany.mockResolvedValue([{ symbol: "000660" }] as any);

    await expect(
      filterMonitorableSymbols(["005930", "000660"])
    ).resolves.toEqual(["005930"]);

    expect(mockStockFindMany).toHaveBeenCalledWith(
      expect.objectContaining({
        where: expect.objectContaining({
          listingStatus: { in: ["DELISTED", "TRADING_SUSPENDED"] },
        }),
      })
    );
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

  // ── 사고(2026-09-13, prod USD 계좌 'us-test-account'): S&P 500 전략이 백테스트 요청형
  // (`universe_id: "sp500"` + `canonical_strategy_dsl.universe: ["SP500"]`)으로 저장돼 있는데
  // 해석기는 `settings.universe.id`만 읽어 기본값 kospi200 → KOSPI 상위 20종목이 모니터링 목록에.
  it("저장 형태 세 가지에서 유니버스 id를 읽는다", () => {
    expect(savedUniverseId({ universe: { id: "kosdaq", filters: {} } })).toBe("kosdaq");
    expect(savedUniverseId({ universe_id: "sp500" })).toBe("sp500");
    expect(savedUniverseId({ canonical_strategy_dsl: { universe: ["SP500"] } })).toBe("SP500");
    expect(savedUniverseId({})).toBeNull();
    expect(savedUniverseId(null)).toBeNull();
  });

  it("백테스트 요청형으로 저장된 미국 전략은 S&P 500 명부를 추적한다(한국 종목 금지)", async () => {
    const resolved = await resolveTrackedSymbolsForStrategy({
      strategyId: "strategy-us",
      strategyName: "Backtest strategy",
      strategySettings: JSON.stringify({
        universe_id: "sp500",
        canonical_strategy_dsl: { universe: ["SP500"] },
      }),
      currency: "USD",
    });
    expect(resolved.source).toBe("universe");
    expect(resolved.symbols.length).toBeGreaterThan(0);
    expect(resolved.symbols).toContain("MMM");
    expect(resolved.symbols.every((s) => /^[A-Z]/.test(s))).toBe(true);
    expect(resolved.symbols).not.toContain("005930");
  });

  it("USD 계좌는 유니버스를 알 수 없어도 kospi200으로 채우지 않는다", async () => {
    const resolved = await resolveTrackedSymbolsForStrategy({
      strategyId: "strategy-unknown",
      strategyName: "unknown",
      strategySettings: JSON.stringify({}),
      currency: "USD",
    });
    expect(resolved.symbols.length).toBeGreaterThan(0);
    expect(resolved.symbols.some((s) => /^\d{6}$/.test(s))).toBe(false);
  });

  it("통화 가드: USD 계좌에서 한국 코드, KRW 계좌에서 미국 티커를 걷어낸다", () => {
    expect(filterSymbolsForCurrency(["005930", "AAPL", "000660", "BRK.B"], "USD")).toEqual(["AAPL", "BRK.B"]);
    expect(filterSymbolsForCurrency(["005930", "AAPL", "000660"], "KRW")).toEqual(["005930", "000660"]);
    expect(filterSymbolsForCurrency(["005930", "AAPL"], null)).toEqual(["005930"]);
  });

  it("백테스트 상위 종목이 계좌 통화와 다르면 버리고 유니버스로 넘어간다", async () => {
    mockBacktestResultFindFirst.mockResolvedValue({
      summary: JSON.stringify({
        topSymbols: ["005930", "000660", "373220"],
        perAssetStats: {
          "005930": { totalReturn: 10, trades: 2 },
          "000660": { totalReturn: 8, trades: 2 },
          "373220": { totalReturn: 6, trades: 2 },
        },
      }),
    } as any);
    const resolved = await resolveTrackedSymbolsForStrategy({
      strategyId: "strategy-us",
      strategyName: "us",
      strategySettings: JSON.stringify({ universe_id: "sp500" }),
      currency: "USD",
    });
    expect(resolved.source).toBe("universe");
    expect(resolved.symbols).not.toContain("005930");
    expect(resolved.symbols).toContain("MMM");
  });
});
