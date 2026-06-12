// @ts-nocheck
/**
 * app/api/virtual-account/route.ts 및 [id]/route.ts 회귀 테스트
 *
 * 수정 내용:
 * - VirtualAccount.id에 @default 없음 → create 시 id를 명시적으로 제공해야 함
 * - VirtualAccount.updatedAt에 @default/@updatedAt 없음 → create/update 시 명시적 제공 필요
 * - 위 두 문제로 계좌 개설 시 Prisma 오류 → 계좌가 DB에 저장되지 않는 버그 발생
 *
 * 검증 항목:
 * 1. POST: id(UUID)와 updatedAt(Date)을 명시적으로 create에 전달
 * 2. POST: name/initialAmount 없을 때 400 반환
 * 3. POST: strategyId 없이 수동 계좌 생성 가능
 * 4. POST: 성공 시 매핑된 계좌 반환
 * 5. PATCH: updatedAt을 명시적으로 update에 전달
 * 6. PATCH: strategyId/strategyName으로 전략 교체 가능
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// ── Prisma mock ──────────────────────────────────────────────────────────────
const mockAccountCreate = vi.fn();
const mockAccountUpdate = vi.fn();
const mockAccountDelete = vi.fn();
const mockAccountFindUnique = vi.fn();
const mockAccountFindMany = vi.fn();
const mockBacktestResultFindFirst = vi.fn();
const mockBacktestHistoryFindFirst = vi.fn();
const mockMarketStateFindUnique = vi.fn();
const mockMarketStateUpsert = vi.fn();
const mockStrategyFindUnique = vi.fn();
const mockLoadStockList = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: {
      create: mockAccountCreate,
      update: mockAccountUpdate,
      delete: mockAccountDelete,
      findUnique: mockAccountFindUnique,
      findMany: mockAccountFindMany,
    },
    backtestResult: {
      findFirst: mockBacktestResultFindFirst,
    },
    backtestHistory: {
      findFirst: mockBacktestHistoryFindFirst,
    },
    strategy: {
      findUnique: mockStrategyFindUnique,
    },
    virtualMarketState: {
      findUnique: mockMarketStateFindUnique,
      upsert: mockMarketStateUpsert,
    },
    stock: {
      findMany: vi.fn().mockResolvedValue([]),
    },
  },
}));

vi.mock("@/lib/krx-stocks", () => ({
  loadStockList: mockLoadStockList,
  getStockNameMap: async () => {
    const list = await mockLoadStockList();
    return Object.fromEntries(list.map((s: { symbol: string; name: string }) => [s.symbol, s.name]));
  },
}));

// ── route 핸들러 import (mock 이후) ─────────────────────────────────────────
const { POST, GET } = await import("@/app/api/virtual-account/route");
const { GET: GET_BY_ID, PATCH } = await import("@/app/api/virtual-account/[id]/route");

// ── 헬퍼: Request 생성 ────────────────────────────────────────────────────
function makePostRequest(body: object): Request {
  return new Request("http://localhost/api/virtual-account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function makePatchRequest(id: string, body: object): Request {
  return new Request(`http://localhost/api/virtual-account/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── 픽스처 ──────────────────────────────────────────────────────────────────
const MOCK_DB_ACCOUNT = {
  id: "test-uuid-1234",
  name: "테스트 계좌",
  initialCash: 1000000,
  currentCash: 1000000,
  strategyId: "strategy-123",
  strategyName: "모멘텀 전략",
  tradingMode: "manual",
  createdAt: new Date("2026-01-01"),
  updatedAt: new Date("2026-01-01"),
  VirtualPosition: [],
};

const MOCK_DB_ACCOUNT_WITH_POSITION = {
  ...MOCK_DB_ACCOUNT,
  currentCash: 400000,
  VirtualPosition: [
    {
      symbol: "005930",
      name: "삼성전자",
      quantity: 10,
      avgPrice: 50000,
      currentPrice: 61000,
    },
  ],
};

const VALID_POST_BODY = {
  name: "테스트 계좌",
  initialAmount: 1000000,
  strategyId: "strategy-123",
  strategyName: "모멘텀 전략",
  tradingMode: "manual",
};

// ── POST /api/virtual-account ────────────────────────────────────────────────

describe("POST /api/virtual-account", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoadStockList.mockResolvedValue([
      { symbol: "005930", name: "삼성전자" },
      { symbol: "000660", name: "SK하이닉스" },
    ]);
    mockAccountCreate.mockResolvedValue(MOCK_DB_ACCOUNT);
    mockBacktestResultFindFirst.mockResolvedValue(null);
    mockBacktestHistoryFindFirst.mockResolvedValue(null);
    mockStrategyFindUnique.mockResolvedValue({
      id: "strategy-123",
      name: "모멘텀 전략",
      settings: JSON.stringify({ universe: { id: "kospi200", filters: {} } }),
    });
    mockMarketStateUpsert.mockResolvedValue({
      id: "market-state-1",
      accountId: "test-uuid-1234",
      startDate: "2026-01-01",
      status: "paused",
      symbols: JSON.stringify(["005930", "000660", "373220"]),
      updatedAt: new Date(),
    });
  });

  // ── 핵심 회귀: id/updatedAt 명시적 전달 ──────────────────────────────────

  it("create 호출 시 id를 UUID 문자열로 명시적으로 전달해야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));

    expect(mockAccountCreate).toHaveBeenCalledOnce();
    const createArg = mockAccountCreate.mock.calls[0][0];

    // id가 존재하고 비어있지 않아야 함
    expect(createArg.data).toHaveProperty("id");
    expect(typeof createArg.data.id).toBe("string");
    expect(createArg.data.id.length).toBeGreaterThan(0);
  });

  it("create 호출 시 UUID 형식의 id를 전달해야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));

    const createArg = mockAccountCreate.mock.calls[0][0];
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    expect(createArg.data.id).toMatch(uuidRegex);
  });

  it("create 호출 시 updatedAt을 Date 객체로 명시적으로 전달해야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));

    const createArg = mockAccountCreate.mock.calls[0][0];

    // updatedAt이 존재하고 Date 객체여야 함
    expect(createArg.data).toHaveProperty("updatedAt");
    expect(createArg.data.updatedAt).toBeInstanceOf(Date);
  });

  it("create 호출마다 고유한 id가 생성되어야 함", async () => {
    await POST(makePostRequest(VALID_POST_BODY));
    await POST(makePostRequest(VALID_POST_BODY));

    const id1 = mockAccountCreate.mock.calls[0][0].data.id;
    const id2 = mockAccountCreate.mock.calls[1][0].data.id;
    expect(id1).not.toBe(id2);
  });

  // ── 유효성 검사 ────────────────────────────────────────────────────────────

  it("name이 없으면 400 반환", async () => {
    const res = await POST(
      makePostRequest({ initialAmount: 1000000, strategyId: "s-1" })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBeTruthy();
    expect(mockAccountCreate).not.toHaveBeenCalled();
  });

  it("initialAmount가 없으면 400 반환", async () => {
    const res = await POST(
      makePostRequest({ name: "테스트", strategyId: "s-1" })
    );
    expect(res.status).toBe(400);
    expect(mockAccountCreate).not.toHaveBeenCalled();
  });

  it("strategyId가 없어도 수동 계좌를 생성할 수 있음", async () => {
    const res = await POST(
      makePostRequest({ name: "테스트", initialAmount: 1000000 })
    );
    expect(res.status).toBe(200);
    expect(mockStrategyFindUnique).not.toHaveBeenCalled();
    expect(mockMarketStateUpsert).not.toHaveBeenCalled();

    const createArg = mockAccountCreate.mock.calls[0][0];
    expect(createArg.data.strategyId).toBeNull();
    expect(createArg.data.strategyName).toBeNull();
    expect(createArg.data.tradingMode).toBe("manual");
  });

  // ── 성공 케이스 ────────────────────────────────────────────────────────────

  it("성공 시 200과 매핑된 계좌 반환", async () => {
    const res = await POST(makePostRequest(VALID_POST_BODY));
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.id).toBe(MOCK_DB_ACCOUNT.id);
    expect(body.name).toBe(MOCK_DB_ACCOUNT.name);
    expect(body.initialAmount).toBe(MOCK_DB_ACCOUNT.initialCash);
    expect(body.currentBalance).toBe(MOCK_DB_ACCOUNT.currentCash);
  });

  it("성공 시 totalValue(현금 + 포지션)를 포함한 응답 반환", async () => {
    const res = await POST(makePostRequest(VALID_POST_BODY));
    const body = await res.json();

    // 포지션이 없으므로 totalValue = currentCash
    expect(body.totalValue).toBe(MOCK_DB_ACCOUNT.currentCash);
  });

  it("tradingMode 기본값은 manual", async () => {
    const { tradingMode: _tm, ...bodyWithoutMode } = VALID_POST_BODY;
    await POST(makePostRequest(bodyWithoutMode));

    const createArg = mockAccountCreate.mock.calls[0][0];
    expect(createArg.data.tradingMode).toBe("manual");
  });

  it("계좌 생성 시 전략 기준 추적 종목 상태를 함께 초기화해야 함", async () => {
    mockBacktestResultFindFirst.mockResolvedValue({
      id: "backtest-1",
      strategyId: "strategy-123",
      summary: JSON.stringify({
        topSymbols: ["005930", "000660", "035420"],
        perAssetStats: {
          "005930": { symbol: "005930", totalReturn: 20, trades: 3 },
          "000660": { symbol: "000660", totalReturn: 15, trades: 2 },
          "035420": { symbol: "035420", totalReturn: 12, trades: 2 },
        },
      }),
    });

    await POST(makePostRequest(VALID_POST_BODY));

    expect(mockStrategyFindUnique).toHaveBeenCalledWith({
      where: { id: "strategy-123" },
    });
    expect(mockMarketStateUpsert).toHaveBeenCalledOnce();
    const upsertArg = mockMarketStateUpsert.mock.calls[0][0];
    expect(JSON.parse(upsertArg.create.symbols)).toEqual(["005930", "000660", "035420"]);
    expect(upsertArg.create.status).toBe("paused");
  });

  // ── Prisma 오류 처리 ────────────────────────────────────────────────────────

  it("Prisma 오류 발생 시 500 반환", async () => {
    mockAccountCreate.mockRejectedValue(new Error("DB connection failed"));

    const res = await POST(makePostRequest(VALID_POST_BODY));
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBeTruthy();
  });
});

// ── PATCH /api/virtual-account/[id] ─────────────────────────────────────────

describe("GET /api/virtual-account", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoadStockList.mockResolvedValue([
      { symbol: "005930", name: "삼성전자" },
      { symbol: "000660", name: "SK하이닉스" },
    ]);
  });

  it("저장된 currentPrice 기준으로 목록을 즉시 반환한다", async () => {
    mockAccountFindMany.mockResolvedValue([MOCK_DB_ACCOUNT_WITH_POSITION]);

    const res = await GET();

    expect(res.status).toBe(200);
    expect(mockAccountFindMany).toHaveBeenCalledOnce();

    const body = await res.json();
    expect(body).toHaveLength(1);
    expect(body[0].totalValue).toBe(1010000);
  });
});

describe("GET /api/virtual-account/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("실시간 시세를 기다리지 않고 저장된 보유 가격으로 상세를 반환한다", async () => {
    mockAccountFindUnique.mockResolvedValue(MOCK_DB_ACCOUNT_WITH_POSITION);

    const res = await GET_BY_ID(
      new Request("http://localhost/api/virtual-account/test-uuid-1234"),
      { params: { id: "test-uuid-1234" } }
    );

    expect(res.status).toBe(200);
    expect(mockAccountFindUnique).toHaveBeenCalledOnce();

    const body = await res.json();
    expect(body.totalValue).toBe(1010000);
    expect(body.holdings).toEqual([
      expect.objectContaining({
        symbol: "005930",
        name: "삼성전자",
        currentPrice: 61000,
        totalValue: 610000,
        profit: 110000,
      }),
    ]);
  });

  it("기존 포지션 name에 종목코드가 저장돼 있어도 종목명을 복원해서 반환한다", async () => {
    mockAccountFindUnique.mockResolvedValue({
      ...MOCK_DB_ACCOUNT_WITH_POSITION,
      VirtualPosition: [
        {
          symbol: "000660",
          name: "000660",
          quantity: 3,
          avgPrice: 200000,
          currentPrice: 210000,
        },
      ],
    });

    const res = await GET_BY_ID(
      new Request("http://localhost/api/virtual-account/test-uuid-1234"),
      { params: { id: "test-uuid-1234" } }
    );

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.holdings).toEqual([
      expect.objectContaining({
        symbol: "000660",
        name: "SK하이닉스",
      }),
    ]);
  });
});

describe("PATCH /api/virtual-account/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // fetch mock: 실제 네트워크 호출 방지 (AbortSignal 타이머로 인한 지연 방지)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    mockLoadStockList.mockResolvedValue([
      { symbol: "005930", name: "삼성전자" },
      { symbol: "000660", name: "SK하이닉스" },
    ]);
    mockAccountUpdate.mockResolvedValue(MOCK_DB_ACCOUNT);
    mockBacktestResultFindFirst.mockResolvedValue(null);
    mockBacktestHistoryFindFirst.mockResolvedValue(null);
    mockMarketStateFindUnique.mockResolvedValue(null);
    mockStrategyFindUnique.mockResolvedValue({
      id: "strategy-999",
      name: "새 전략",
      settings: JSON.stringify({ universe: { id: "kospi200", filters: {} } }),
    });
    mockMarketStateUpsert.mockResolvedValue({
      id: "market-state-1",
      accountId: "test-uuid-1234",
      startDate: "2026-01-01",
      status: "running",
      symbols: JSON.stringify([]),
      updatedAt: new Date(),
    });
  });

  // ── 핵심 회귀: updatedAt 명시적 전달 ──────────────────────────────────────

  it("update 호출 시 updatedAt을 Date 객체로 명시적으로 전달해야 함", async () => {
    await PATCH(makePatchRequest("test-uuid-1234", { tradingMode: "auto" }), {
      params: { id: "test-uuid-1234" },
    });

    expect(mockAccountUpdate).toHaveBeenCalledOnce();
    const updateArg = mockAccountUpdate.mock.calls[0][0];

    expect(updateArg.data).toHaveProperty("updatedAt");
    expect(updateArg.data.updatedAt).toBeInstanceOf(Date);
  });

  it("전략 교체 시 strategyId와 strategyName을 함께 update에 전달해야 함", async () => {
    mockBacktestResultFindFirst.mockResolvedValue({
      id: "backtest-1",
      strategyId: "strategy-999",
      summary: JSON.stringify({
        topSymbols: ["005930", "000660", "035420"],
      }),
    });

    mockAccountUpdate.mockResolvedValue({
      ...MOCK_DB_ACCOUNT,
      strategyId: "strategy-999",
      strategyName: "새 전략",
    });

    const res = await PATCH(
      makePatchRequest("test-uuid-1234", {
        strategyId: "strategy-999",
        strategyName: "새 전략",
      }),
      { params: { id: "test-uuid-1234" } }
    );

    expect(mockAccountUpdate).toHaveBeenCalledOnce();
    const updateArg = mockAccountUpdate.mock.calls[0][0];
    expect(updateArg.data.strategyId).toBe("strategy-999");
    expect(updateArg.data.strategyName).toBe("새 전략");
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.strategyId).toBe("strategy-999");
    expect(body.strategyName).toBe("새 전략");
    expect(mockBacktestResultFindFirst).toHaveBeenCalledOnce();
    expect(mockMarketStateUpsert).toHaveBeenCalledOnce();
    const upsertArg = mockMarketStateUpsert.mock.calls[0][0];
    expect(JSON.parse(upsertArg.create.symbols)).toEqual(["005930", "000660", "035420"]);
    expect(JSON.parse(upsertArg.update.symbols)).toEqual(["005930", "000660", "035420"]);
  });

  it("tradingMode 업데이트 시 해당 값이 전달됨", async () => {
    await PATCH(makePatchRequest("test-uuid-1234", { tradingMode: "auto" }), {
      params: { id: "test-uuid-1234" },
    });

    const updateArg = mockAccountUpdate.mock.calls[0][0];
    expect(updateArg.data.tradingMode).toBe("auto");
    expect(updateArg.where.id).toBe("test-uuid-1234");
  });

  it("currentBalance 업데이트 시 currentCash로 변환되어 전달됨", async () => {
    await PATCH(
      makePatchRequest("test-uuid-1234", { currentBalance: 500000 }),
      { params: { id: "test-uuid-1234" } }
    );

    const updateArg = mockAccountUpdate.mock.calls[0][0];
    expect(updateArg.data.currentCash).toBe(500000);
  });

  it("성공 시 200과 매핑된 계좌 반환", async () => {
    const res = await PATCH(
      makePatchRequest("test-uuid-1234", { tradingMode: "manual" }),
      { params: { id: "test-uuid-1234" } }
    );
    expect(res.status).toBe(200);

    const body = await res.json();
    expect(body.id).toBe(MOCK_DB_ACCOUNT.id);
  });
});
