import { beforeEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";
import { PATCH, POST } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    stock: {
      findMany: vi.fn(),
    },
    virtualAccount: {
      findUnique: vi.fn(),
    },
    virtualMarketState: {
      upsert: vi.fn(),
      update: vi.fn(),
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
  getStockNameMap: vi.fn().mockResolvedValue({
    "005930": "삼성전자",
    "000660": "SK하이닉스",
  }),
}));

const mockStockFindMany = vi.mocked(prisma.stock.findMany);
const mockAccountFindUnique = vi.mocked(prisma.virtualAccount.findUnique);
const mockMarketStateUpsert = vi.mocked(prisma.virtualMarketState.upsert);
const mockMarketStateUpdate = vi.mocked(prisma.virtualMarketState.update);

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/virtual-market/account-1", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("/api/virtual-market/[accountId]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    mockStockFindMany.mockResolvedValue([]);
    mockAccountFindUnique.mockResolvedValue({ id: "account-1" } as any);
    mockMarketStateUpsert.mockResolvedValue({
      id: "state-1",
      accountId: "account-1",
      startDate: "2026-06-27",
      status: "running",
      symbols: JSON.stringify(["005930"]),
      updatedAt: new Date("2026-06-27"),
    } as any);
    mockMarketStateUpdate.mockResolvedValue({
      id: "state-1",
      accountId: "account-1",
      startDate: "2026-06-27",
      status: "running",
      symbols: JSON.stringify(["005930"]),
      updatedAt: new Date("2026-06-27"),
    } as any);
  });

  it("POST는 상장폐지 종목을 제외한 symbols만 저장한다", async () => {
    mockStockFindMany.mockResolvedValue([{ symbol: "123456" }] as any);

    const response = await POST(makeRequest({
      symbols: ["005930", "001570", "123456"],
    }), { params: { accountId: "account-1" } });

    expect(response.status).toBe(200);
    expect(mockMarketStateUpsert).toHaveBeenCalledWith(
      expect.objectContaining({
        create: expect.objectContaining({
          symbols: JSON.stringify(["005930"]),
        }),
        update: expect.objectContaining({
          symbols: JSON.stringify(["005930"]),
        }),
      })
    );
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        symbols: ["005930"],
        symbolNames: { "005930": "삼성전자" },
      })
    );
  });

  it("POST는 모니터링 가능한 종목이 하나도 없으면 저장하지 않는다", async () => {
    const response = await POST(makeRequest({
      symbols: ["001570"],
    }), { params: { accountId: "account-1" } });

    expect(response.status).toBe(400);
    expect(mockMarketStateUpsert).not.toHaveBeenCalled();
  });

  it("PATCH는 symbols 업데이트 전에 상장폐지 종목을 제외한다", async () => {
    const response = await PATCH(makeRequest({
      symbols: ["005930", "001570"],
    }), { params: { accountId: "account-1" } });

    expect(response.status).toBe(200);
    expect(mockMarketStateUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          symbols: JSON.stringify(["005930"]),
        }),
      })
    );
  });
});
