import { beforeEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";
import { GET } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualMarketLog: {
      findMany: vi.fn(),
    },
    stock: {
      findMany: vi.fn(),
    },
  },
}));

vi.mock("@/lib/krx-stocks", () => ({
  getStockNameMap: vi.fn().mockResolvedValue({
    "005440": "현대지에프홀딩스",
    "138930": "BNK금융지주",
  }),
}));

const mockLogFindMany = vi.mocked(prisma.virtualMarketLog.findMany);
const mockStockFindMany = vi.mocked(prisma.stock.findMany);

function makeRequest(): Request {
  return new Request("http://localhost/api/virtual-market/account-1/logs?limit=30");
}

function makeLog(overrides: Partial<Record<string, unknown>>) {
  return {
    id: "log-1",
    accountId: "account-1",
    date: "2026-07-08",
    symbol: "005440",
    stockName: null,
    signalType: "entry",
    reason: "PBR 1 이하",
    price: 14390,
    action: "auto_executed",
    orderId: null,
    createdAt: new Date("2026-07-08"),
    ...overrides,
  };
}

describe("/api/virtual-market/[accountId]/logs GET", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStockFindMany.mockResolvedValue([]);
  });

  it("stockName이 없으면 종목명 맵에서 이름을 채운다", async () => {
    mockLogFindMany.mockResolvedValue([makeLog({ symbol: "005440", stockName: null })] as any);

    const res = await GET(makeRequest(), { params: { accountId: "account-1" } });
    const body = await res.json();

    expect(body[0].stockName).toBe("현대지에프홀딩스");
  });

  it("stockName에 종목코드가 그대로 저장된 경우에도 실제 종목명으로 교정한다", async () => {
    // 백엔드 자동매매가 Stock 테이블에서 이름을 못 찾아 symbol을 stockName에 저장한 케이스
    mockLogFindMany.mockResolvedValue([
      makeLog({ symbol: "005440", stockName: "005440" }),
      makeLog({ id: "log-2", symbol: "138930", stockName: "138930" }),
    ] as any);

    const res = await GET(makeRequest(), { params: { accountId: "account-1" } });
    const body = await res.json();

    expect(body[0].stockName).toBe("현대지에프홀딩스");
    expect(body[1].stockName).toBe("BNK금융지주");
  });

  it("정상적으로 저장된 종목명은 그대로 유지한다", async () => {
    mockLogFindMany.mockResolvedValue([
      makeLog({ symbol: "005440", stockName: "현대지에프홀딩스" }),
    ] as any);

    const res = await GET(makeRequest(), { params: { accountId: "account-1" } });
    const body = await res.json();

    expect(body[0].stockName).toBe("현대지에프홀딩스");
  });

  it("어디에서도 이름을 못 찾으면 null로 둔다 (UI가 코드로 폴백)", async () => {
    mockLogFindMany.mockResolvedValue([
      makeLog({ symbol: "999999", stockName: "999999" }),
    ] as any);

    const res = await GET(makeRequest(), { params: { accountId: "account-1" } });
    const body = await res.json();

    expect(body[0].stockName).toBeNull();
  });
});
