// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 2026-09-29 사고 회귀: 한도 소비(consumeBacktestQuota)는 카운터를 롤링 주기 키로 적는데
// 콘솔은 달력 월 키("YYYY-MM")로 읽고 적었다 — 사용량이 전부 0으로 보였고, 콘솔의
// 사용량 조정은 실제 한도에 반영되지 않았다.

const requireAdmin = vi.fn();
const writeAuditLog = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const userFindMany = vi.fn();

vi.mock("@/lib/server/adminAuth", () => ({
  requireAdmin: (...a) => requireAdmin(...a),
  writeAuditLog: (...a) => writeAuditLog(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
      findMany: (...a) => userFindMany(...a),
    },
    planConfig: { findUnique: vi.fn().mockResolvedValue(null) },
  },
}));

let GET;
let PATCH;

beforeEach(async () => {
  vi.clearAllMocks();
  requireAdmin.mockResolvedValue({ id: 1, email: "admin@example.com", name: "Admin" });
  writeAuditLog.mockResolvedValue(undefined);
  userUpdate.mockResolvedValue({});
  ({ GET, PATCH } = await import("./route"));
});

const DAY = 24 * 60 * 60 * 1000;
const planStartDate = new Date(Date.now() - 3 * DAY);
const periodKey = planStartDate.toISOString();

function getReq(query = "") {
  return { nextUrl: new URL(`http://localhost/api/admin/backtests${query}`) };
}

describe("/api/admin/backtests GET", () => {
  it("현재 주기 사용량으로 보이고, 지난 주기 카운터는 0으로 읽어 뒤로 정렬한다", async () => {
    userFindMany.mockResolvedValue([
      // 지난 주기 값이 큰 사용자 — 현재 주기 사용량은 0
      {
        id: 3,
        email: "stale@example.com",
        planTier: "FREE",
        planStartDate: null,
        createdAt: new Date(Date.now() - 400 * DAY),
        backtestUsageMonth: "2026-07",
        backtestCountThisMonth: 40,
      },
      {
        id: 2,
        email: "me@example.com",
        planTier: "PREMIUM",
        planStartDate,
        createdAt: new Date("2026-07-11T00:00:00Z"),
        backtestUsageMonth: periodKey,
        backtestCountThisMonth: 26,
        backtestRunTotal: 120,
      },
    ]);

    const data = await (await GET(getReq())).json();

    expect(data.users.map((u) => [u.id, u.used])).toEqual([
      [2, 26],
      [3, 0],
    ]);
    expect(data.total).toBe(2);
    expect(data.users[0].runTotal).toBe(120);
  });
});

describe("/api/admin/backtests PATCH", () => {
  it("조정은 한도 소비가 읽는 주기 키로 적는다", async () => {
    userFindUnique.mockResolvedValue({
      planStartDate,
      createdAt: new Date("2026-07-11T00:00:00Z"),
      backtestUsageMonth: periodKey,
      backtestCountThisMonth: 26,
    });

    const res = await PATCH({ json: async () => ({ userId: 2, action: "decrease", amount: 6 }) });
    const data = await res.json();

    expect(data.used).toBe(20);
    expect(userUpdate).toHaveBeenCalledWith({
      where: expect.objectContaining({ id: 2 }),
      data: { backtestUsageMonth: periodKey, backtestCountThisMonth: 20 },
    });
    expect(writeAuditLog).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ before: { used: 26 }, after: { used: 20 } })
    );
  });

  it("초기화는 업그레이드 이월분(음수 카운터)을 지우지 않는다", async () => {
    userFindUnique.mockResolvedValue({
      planStartDate,
      createdAt: new Date("2026-07-11T00:00:00Z"),
      backtestUsageMonth: periodKey,
      backtestCountThisMonth: -5,
    });

    await PATCH({ json: async () => ({ userId: 2, action: "reset" }) });

    expect(userUpdate).toHaveBeenCalledWith({
      where: expect.objectContaining({ id: 2 }),
      data: { backtestUsageMonth: periodKey, backtestCountThisMonth: -5 },
    });
  });
});


it("rejects stale admin adjustments instead of overwriting a concurrent run", async () => {
  userFindUnique.mockResolvedValue({ backtestUsageMonth: periodKey, backtestCountThisMonth: 26, planStartDate });
  userUpdate.mockRejectedValueOnce(Object.assign(new Error("conflict"), { code: "P2025" }));
  const res = await PATCH({ json: async () => ({ userId: 2, action: "decrease" }) });
  expect(res.status).toBe(409);
  expect(userUpdate.mock.calls[0][0].where).toMatchObject({
    backtestUsageMonth: periodKey, backtestCountThisMonth: 26,
  });
  expect(writeAuditLog).not.toHaveBeenCalled();
});

it("rejects fractional usage adjustments", async () => {
  expect((await PATCH({ json: async () => ({ userId: 2, action: "increase", amount: 0.5 }) })).status).toBe(400);
  expect(userUpdate).not.toHaveBeenCalled();
});
