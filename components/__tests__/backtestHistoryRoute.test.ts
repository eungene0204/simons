// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFindUnique = vi.fn();
const mockUpdate = vi.fn();
const mockCreate = vi.fn();
const mockDelete = vi.fn();
const mockDeleteMany = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    backtestHistory: {
      findUnique: mockFindUnique,
      update: mockUpdate,
      create: mockCreate,
      delete: mockDelete,
      deleteMany: mockDeleteMany,
    },
  },
}));

const { POST, DELETE } = await import("@/app/api/backtest/history/route");

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/backtest/history", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/backtest/history", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});

describe("DELETE /api/backtest/history", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("id 없이 호출되면 visible 여부와 무관하게 DB의 백테스트 기록 전체를 삭제해야 함", async () => {
    mockDeleteMany.mockResolvedValue({ count: 7 });

    const response = await DELETE(
      new Request("http://localhost/api/backtest/history", {
        method: "DELETE",
      })
    );

    expect(response.status).toBe(200);
    expect(mockDeleteMany).toHaveBeenCalledOnce();
    expect(mockDeleteMany).toHaveBeenCalledWith();
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it("id가 있으면 해당 백테스트 기록만 삭제해야 함", async () => {
    mockDelete.mockResolvedValue({ id: "hist-1" });

    const response = await DELETE(
      new Request("http://localhost/api/backtest/history?id=hist-1", {
        method: "DELETE",
      })
    );

    expect(response.status).toBe(200);
    expect(mockDelete).toHaveBeenCalledOnce();
    expect(mockDelete).toHaveBeenCalledWith({ where: { id: "hist-1" } });
    expect(mockDeleteMany).not.toHaveBeenCalled();
  });
});
