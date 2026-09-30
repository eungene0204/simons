// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 2026-09-22 게스트 사고 회귀: 다른 계정으로 받은 결과 화면의 자동 저장이 지금 계정의
// "내 목록"에 남의 백테스트를 담지 않는다. 공유 기록 행에 계정 id를 남기지 않는다.
const { getOwnershipContext, bhFindUnique, bhUpdate, bhCreate, ubhUpsert } = vi.hoisted(() => ({
  getOwnershipContext: vi.fn(),
  bhFindUnique: vi.fn(),
  bhUpdate: vi.fn(),
  bhCreate: vi.fn(),
  ubhUpsert: vi.fn(),
}));

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext,
  getSessionUserId: vi.fn(),
  isUnauthorizedAccessError: () => false,
}));
vi.mock("@/lib/prisma", () => ({
  prisma: {
    backtestHistory: { findUnique: bhFindUnique, update: bhUpdate, create: bhCreate },
    userBacktestHistory: { upsert: ubhUpsert },
  },
}));
vi.mock("@/lib/server/backtestCache", () => ({ isPlaceholderStrategyName: () => false }));
vi.mock("@/lib/server/backtest-history-list", () => ({
  BACKTEST_LIST_SELECT: {},
  fetchUserBacktestHistory: vi.fn(),
  formatBacktestListItem: vi.fn(),
}));

const { POST } = await import("./route");

const body = (owner) => ({
  strategyName: "전략",
  universe: "KOSPI200",
  conditions: [],
  metrics: {},
  isAutoSave: true,
  result: { totalReturn: 1, ownerUserId: owner },
});

describe("POST /api/backtest/history 결과 주인 대조", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOwnershipContext.mockResolvedValue({ userId: 31 });
    bhCreate.mockImplementation(async ({ data }) => ({ id: "bh1", createdAt: new Date(), ...data }));
  });

  it("다른 계정으로 받은 결과는 409이고 목록에 담지 않는다", async () => {
    const res = await POST({ json: async () => body(2) });

    expect(res.status).toBe(409);
    expect(bhCreate).not.toHaveBeenCalled();
    expect(ubhUpsert).not.toHaveBeenCalled();
  });

  it("자기 결과는 저장하되 공유 행에는 계정 id를 남기지 않는다", async () => {
    const res = await POST({ json: async () => body(31) });

    expect(res.status).toBe(200);
    expect(JSON.parse(bhCreate.mock.calls[0][0].data.result)).toEqual({ totalReturn: 1 });
    expect(ubhUpsert).toHaveBeenCalled();
  });
});
