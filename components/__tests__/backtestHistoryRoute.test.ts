// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFindUnique = vi.fn();
const mockUpdate = vi.fn();
const mockUpdateMany = vi.fn();
const mockCreate = vi.fn();
const mockDelete = vi.fn();
const mockDeleteMany = vi.fn();
const mockFindMany = vi.fn();

const userLinkFindMany = vi.fn();
const userLinkUpsert = vi.fn();
const userLinkDeleteMany = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    backtestHistory: {
      findUnique: mockFindUnique,
      update: mockUpdate,
      updateMany: mockUpdateMany,
      create: mockCreate,
      delete: mockDelete,
      deleteMany: mockDeleteMany,
      findMany: mockFindMany,
    },
    userBacktestHistory: {
      findMany: userLinkFindMany,
      upsert: userLinkUpsert,
      deleteMany: userLinkDeleteMany,
    },
  },
}));

let currentUserId: number | null = null;
vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: () => Promise.resolve({ userId: currentUserId }),
  isUnauthorizedAccessError: () => false,
}));

const { GET, POST, DELETE } = await import("@/app/api/backtest/history/route");

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/backtest/history", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/backtest/history (legacy, 비인증)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentUserId = null;
  });

  it("자동 저장이 기존 cache 레코드를 visible로 승격할 때 result가 비어 있으면 전달된 result로 보완해야 함", async () => {
    const result = { executionId: "exec-1", equity: [1, 2], dates: ["2025-01-01"] };

    mockFindUnique.mockResolvedValue({
      id: "hist-1",
      cacheKey: "cache-1",
      strategyName: "",
      universe: "KOSPI",
      conditions: "{}",
      metrics: "{}",
      result: null,
      createdAt: new Date("2026-04-06T00:00:00Z"),
    });

    mockUpdate.mockResolvedValue({
      id: "hist-1",
      strategyName: "전략",
      universe: "KOSPI",
      conditions: "{}",
      metrics: "{}",
      result: JSON.stringify(result),
      createdAt: new Date("2026-04-06T00:00:00Z"),
    });

    const response = await POST(
      makeRequest({
        strategyName: "전략",
        universe: "KOSPI",
        conditions: {},
        metrics: {},
        cacheKey: "cache-1",
        isAutoSave: true,
        result,
      })
    );

    expect(response.status).toBe(200);
    expect(mockUpdate).toHaveBeenCalledOnce();
    expect(mockUpdate.mock.calls[0][0].data.result).toBe(JSON.stringify(result));
    // 비인증이면 사용자 목록 연결을 만들지 않는다.
    expect(userLinkUpsert).not.toHaveBeenCalled();
  });

  it("cacheKey가 없는 자동 저장은 새 레코드에 상세 result를 그대로 저장해야 함", async () => {
    const result = { executionId: "exec-2", equity: [1, 2], dates: ["2025-01-01"] };

    mockCreate.mockResolvedValue({
      id: "hist-2",
      strategyName: "전략",
      universe: "KOSPI",
      conditions: "{}",
      metrics: "{}",
      result: JSON.stringify(result),
      createdAt: new Date("2026-04-06T00:00:00Z"),
    });

    const response = await POST(
      makeRequest({
        strategyName: "전략",
        universe: "KOSPI",
        conditions: {},
        metrics: {},
        isAutoSave: true,
        result,
      })
    );

    expect(response.status).toBe(200);
    expect(mockCreate).toHaveBeenCalledOnce();
    expect(mockCreate.mock.calls[0][0].data.result).toBe(JSON.stringify(result));
  });

  it("새 레코드 생성 시 프롬프트 원문을 스냅샷으로 함께 저장한다", async () => {
    mockCreate.mockResolvedValue({
      id: "hist-3",
      strategyName: "전략",
      prompt: "KOSPI 골든크로스 매수 전략",
      universe: "KOSPI",
      conditions: "{}",
      metrics: "{}",
      result: null,
      createdAt: new Date("2026-04-06T00:00:00Z"),
    });

    const response = await POST(
      makeRequest({
        strategyName: "전략",
        prompt: "KOSPI 골든크로스 매수 전략",
        universe: "KOSPI",
        conditions: {},
        metrics: {},
        isAutoSave: true,
      })
    );

    expect(response.status).toBe(200);
    expect(mockCreate.mock.calls[0][0].data.prompt).toBe("KOSPI 골든크로스 매수 전략");
  });
});

describe("POST /api/backtest/history (로그인 사용자)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentUserId = 7;
  });

  it("저장 시 공유 BacktestHistory를 사용자 '내 목록'(UserBacktestHistory)에 연결한다", async () => {
    mockFindUnique.mockResolvedValue({
      id: "hist-1",
      cacheKey: "cache-1",
      strategyName: "전략",
      universe: "KOSPI",
      conditions: "{}",
      metrics: "{}",
      result: "{}",
      createdAt: new Date("2026-04-06T00:00:00Z"),
    });
    mockUpdate.mockResolvedValue({
      id: "hist-1",
      strategyName: "전략",
      universe: "KOSPI",
      conditions: "{}",
      metrics: "{}",
      result: "{}",
      createdAt: new Date("2026-04-06T00:00:00Z"),
    });

    const response = await POST(
      makeRequest({
        strategyName: "전략",
        universe: "KOSPI",
        conditions: {},
        metrics: {},
        cacheKey: "cache-1",
      })
    );

    expect(response.status).toBe(200);
    expect(userLinkUpsert).toHaveBeenCalledOnce();
    expect(userLinkUpsert.mock.calls[0][0].where).toEqual({
      userId_backtestHistoryId: { userId: 7, backtestHistoryId: "hist-1" },
    });
    expect(userLinkUpsert.mock.calls[0][0].create).toEqual({ userId: 7, backtestHistoryId: "hist-1" });
  });
});

describe("GET /api/backtest/history", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("로그인 사용자는 자신이 담은 기록만 조인으로 조회한다", async () => {
    currentUserId = 7;
    userLinkFindMany.mockResolvedValue([
      {
        BacktestHistory: {
          id: "hist-1",
          strategyName: "내 전략",
          universe: "KOSPI",
          conditions: "{}",
          metrics: "{}",
          result: null,
          createdAt: new Date("2026-04-06T00:00:00Z"),
        },
      },
    ]);

    const response = await GET();
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(userLinkFindMany).toHaveBeenCalledOnce();
    expect(userLinkFindMany.mock.calls[0][0].where).toEqual({ userId: 7 });
    expect(payload).toHaveLength(1);
    expect(payload[0].strategyName).toBe("내 전략");
    expect(mockFindMany).not.toHaveBeenCalled();
  });

  it("비인증이면 레거시 전역(isVisible) 조회로 폴백한다", async () => {
    currentUserId = null;
    mockFindMany.mockResolvedValue([]);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(mockFindMany).toHaveBeenCalledWith({
      where: { isVisible: true },
      orderBy: { createdAt: "desc" },
      take: 50,
    });
    expect(userLinkFindMany).not.toHaveBeenCalled();
  });
});

describe("DELETE /api/backtest/history (로그인 사용자)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentUserId = 7;
  });

  it("id가 있으면 공유 결과는 보존하고 사용자 연결만 끊는다", async () => {
    userLinkDeleteMany.mockResolvedValue({ count: 1 });

    const response = await DELETE(
      new Request("http://localhost/api/backtest/history?id=hist-1", { method: "DELETE" })
    );

    expect(response.status).toBe(200);
    expect(userLinkDeleteMany).toHaveBeenCalledWith({ where: { userId: 7, backtestHistoryId: "hist-1" } });
    expect(mockDelete).not.toHaveBeenCalled();
    expect(mockDeleteMany).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it("id 없이 호출되면 사용자 연결 전체만 끊는다(공유 결과 보존)", async () => {
    userLinkDeleteMany.mockResolvedValue({ count: 5 });

    const response = await DELETE(
      new Request("http://localhost/api/backtest/history", { method: "DELETE" })
    );

    expect(response.status).toBe(200);
    expect(userLinkDeleteMany).toHaveBeenCalledWith({ where: { userId: 7 } });
    expect(mockDelete).not.toHaveBeenCalled();
    expect(mockDeleteMany).not.toHaveBeenCalled();
  });
});

describe("DELETE /api/backtest/history (legacy, 비인증)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentUserId = null;
  });

  it("id 없이 호출되면 DB 레코드를 지우지 않고 전체를 isVisible=false 로만 숨긴다", async () => {
    mockUpdateMany.mockResolvedValue({ count: 7 });

    const response = await DELETE(
      new Request("http://localhost/api/backtest/history", { method: "DELETE" })
    );

    expect(response.status).toBe(200);
    expect(mockUpdateMany).toHaveBeenCalledWith({ data: { isVisible: false } });
    expect(mockDelete).not.toHaveBeenCalled();
    expect(mockDeleteMany).not.toHaveBeenCalled();
  });

  it("id가 있으면 DB 레코드를 지우지 않고 해당 기록만 isVisible=false 로 숨긴다", async () => {
    mockUpdate.mockResolvedValue({ id: "hist-1" });

    const response = await DELETE(
      new Request("http://localhost/api/backtest/history?id=hist-1", { method: "DELETE" })
    );

    expect(response.status).toBe(200);
    expect(mockUpdate).toHaveBeenCalledWith({ where: { id: "hist-1" }, data: { isVisible: false } });
    expect(mockDelete).not.toHaveBeenCalled();
    expect(mockDeleteMany).not.toHaveBeenCalled();
  });
});
