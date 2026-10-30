// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

const accountFindFirst = vi.fn();
const snapshotFindMany = vi.fn();
const fetchStockPriceSnapshots = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    virtualAccount: { findFirst: accountFindFirst },
    virtualAccountSnapshot: { findMany: snapshotFindMany },
  },
}));
vi.mock("@/lib/server/stock-prices", () => ({ fetchStockPriceSnapshots }));
vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: vi.fn().mockResolvedValue({ userId: 7 }),
  isUnauthorizedAccessError: vi.fn().mockReturnValue(false),
  withOwnership: vi.fn((where) => ({ ...where, userId: 7 })),
}));

const { GET } = await import("./route");

const account = (overrides = {}) => ({
  id: "acc-1",
  status: "ACTIVE",
  initialCash: 1_000_000,
  contributedCash: 0,
  currentCash: 500_000,
  VirtualPosition: [{ symbol: "005930", quantity: 10, avgPrice: 50_000, currentPrice: 50_000 }],
  ...overrides,
});

vi.useFakeTimers({ toFake: ["Date"] });
vi.setSystemTime(new Date("2026-10-30T03:00:00.000Z")); // 12:00 KST

const call = (query = "") =>
  GET(new Request(`http://localhost/api/virtual-account/acc-1/snapshots${query}`), { params: { id: "acc-1" } });

describe("GET /api/virtual-account/[id]/snapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchStockPriceSnapshots.mockResolvedValue({ "005930": { price: 40_000 } });
    snapshotFindMany.mockResolvedValue([
      { takenAt: new Date("2026-10-28T00:00:00Z"), totalValue: 1_000_000, totalContributed: 1_000_000 },
      { takenAt: new Date("2026-10-29T00:00:00Z"), totalValue: 990_000, totalContributed: 1_000_000 },
    ]);
  });

  it("저장된 일별 값을 수익률 점으로 돌려주고 오늘 날짜로 현재 값을 붙인다", async () => {
    accountFindFirst.mockResolvedValue(account());

    const response = await call();
    const { range, points } = await response.json();

    expect(range).toBe("all");
    // 오늘: 현금 50만 + 10주 × 4만 = 90만
    expect(points).toEqual([
      { time: "2026-10-28", returnPct: 0 },
      { time: "2026-10-29", returnPct: -1 },
      { time: "2026-10-30", returnPct: -10 },
    ]);
  });

  it("기간 파라미터를 시작 날짜 조건으로 바꾼다", async () => {
    accountFindFirst.mockResolvedValue(account());

    await call("?range=1m");

    const where = snapshotFindMany.mock.calls[0][0].where;
    expect(where.accountId).toBe("acc-1");
    expect(where.takenAt.gte).toEqual(new Date("2026-09-30T00:00:00.000Z"));
  });

  it("all 은 시작 날짜 조건 없이 전체를 조회하고, 잘못된 기간은 전체로 본다", async () => {
    accountFindFirst.mockResolvedValue(account());

    await call("?range=all");
    expect(snapshotFindMany.mock.calls[0][0].where.takenAt).toBeUndefined();

    const response = await call("?range=bogus");
    expect((await response.json()).range).toBe("all");
  });

  it("닫은 계좌는 현재 값을 붙이지 않는다 (현금 0·포지션 없음이라 -100%로 보이기 때문)", async () => {
    accountFindFirst.mockResolvedValue(account({ status: "CLOSED", currentCash: 0, VirtualPosition: [] }));

    const { points } = await (await call()).json();

    expect(points.map((p) => p.returnPct)).toEqual([0, -1]);
    expect(fetchStockPriceSnapshots).not.toHaveBeenCalled();
  });

  it("내 계좌가 아니면 404 이고 스냅샷을 조회하지 않는다", async () => {
    accountFindFirst.mockResolvedValue(null);

    const response = await call();

    expect(response.status).toBe(404);
    expect(snapshotFindMany).not.toHaveBeenCalled();
    expect(accountFindFirst.mock.calls[0][0].where).toEqual({ id: "acc-1", userId: 7 });
  });
});
