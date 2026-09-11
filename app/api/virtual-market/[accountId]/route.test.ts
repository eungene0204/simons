import { beforeEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";
import { findOwnedAccountId } from "@/lib/server/accountOwnership";
import { DELETE, GET, PATCH, POST } from "./route";

vi.mock("@/lib/server/accountOwnership", () => ({
  findOwnedAccountId: vi.fn(),
}));

vi.mock("@/lib/get-user", () => ({
  isUnauthorizedAccessError: () => false,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    stock: {
      findMany: vi.fn(),
    },
    virtualMarketState: {
      upsert: vi.fn(),
      update: vi.fn(),
      findUnique: vi.fn(),
      deleteMany: vi.fn(),
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
  loadEtfMasterNameMap: vi.fn().mockResolvedValue({
    "488080": "TIGER 반도체TOP10레버리지",
  }),
}));

const mockStockFindMany = vi.mocked(prisma.stock.findMany);
const mockFindOwnedAccountId = vi.mocked(findOwnedAccountId);
const mockMarketStateFindUnique = vi.mocked(prisma.virtualMarketState.findUnique);
const mockMarketStateDeleteMany = vi.mocked(prisma.virtualMarketState.deleteMany);
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
    mockFindOwnedAccountId.mockResolvedValue("account-1");
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

  it("POST는 ETF 종목명을 ETF 마스터에서 채운다", async () => {
    mockMarketStateUpsert.mockResolvedValue({
      id: "state-1",
      accountId: "account-1",
      startDate: "2026-06-27",
      status: "running",
      symbols: JSON.stringify(["488080"]),
      updatedAt: new Date("2026-06-27"),
    } as any);

    const response = await POST(makeRequest({
      symbols: ["488080"],
    }), { params: { accountId: "account-1" } });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual(
      expect.objectContaining({
        symbols: ["488080"],
        symbolNames: { "488080": "TIGER 반도체TOP10레버리지" },
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

// 자동매매 추적 상태는 계좌에 딸린 사용자 데이터다 — 소유자가 아니면 어떤 메서드도
// 상태를 읽거나 바꾸지 못한다(2026-09-11 이전에는 네 메서드 모두 무방비였다).
describe("/api/virtual-market/[accountId] 계좌 소유권", () => {
  const params = { params: { accountId: "account-1" } };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    mockFindOwnedAccountId.mockResolvedValue(null);
  });

  it("남의 계좌 GET은 상태를 읽지 않고 404", async () => {
    const response = await GET(new Request("http://localhost/api/virtual-market/account-1"), params);

    expect(response.status).toBe(404);
    expect(mockMarketStateFindUnique).not.toHaveBeenCalled();
  });

  it("남의 계좌 POST는 추적을 시작하지 않고 404", async () => {
    const response = await POST(makeRequest({ symbols: ["005930"] }), params);

    expect(response.status).toBe(404);
    expect(mockMarketStateUpsert).not.toHaveBeenCalled();
  });

  it("남의 계좌 PATCH는 상태를 바꾸지 않고 404", async () => {
    const request = new Request("http://localhost/api/virtual-market/account-1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "paused" }),
    });

    const response = await PATCH(request, params);

    expect(response.status).toBe(404);
    expect(mockMarketStateUpdate).not.toHaveBeenCalled();
  });

  it("남의 계좌 DELETE는 추적 상태를 지우지 않고 404", async () => {
    const response = await DELETE(new Request("http://localhost/api/virtual-market/account-1"), params);

    expect(response.status).toBe(404);
    expect(mockMarketStateDeleteMany).not.toHaveBeenCalled();
  });
});
