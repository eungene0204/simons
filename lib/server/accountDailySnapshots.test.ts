// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { calcBuyCost } from "@/lib/order-engine";

const accountFindMany = vi.fn();
const snapshotCreateMany = vi.fn();

const { syncAccountDailySnapshots, dateToTakenAt } = await import("./accountDailySnapshots");

const client = {
  virtualAccount: { findMany: accountFindMany },
  virtualAccountSnapshot: { createMany: snapshotCreateMany },
};

const NOW = new Date("2026-10-30T03:00:00.000Z"); // 12:00 KST
const cashAfterBuy = 1_000_000 - calcBuyCost(10_000, 10);

const account = (overrides = {}) => ({
  id: "acc-1",
  currency: "KRW",
  createdAt: new Date("2026-10-23T01:00:00.000Z"),
  initialCash: 1_000_000,
  currentCash: cashAfterBuy,
  VirtualPosition: [{ symbol: "005930", quantity: 10 }],
  VirtualOrder: [
    {
      side: "BUY", type: "MARKET", status: "FILLED", symbol: "005930", quantity: 10,
      price: 10_000, filledPrice: 10_000,
      createdAt: new Date("2026-10-26T01:00:00.000Z"), filledAt: new Date("2026-10-26T01:00:00.000Z"),
    },
  ],
  VirtualCashEvent: [],
  VirtualAccountSnapshot: [],
  ...overrides,
});

const closes = { "2026-10-26": 10_500, "2026-10-27": 9_000 };

describe("syncAccountDailySnapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    snapshotCreateMany.mockImplementation(async ({ data }) => ({ count: data.length }));
  });

  it("개설일부터 어제까지 복원한 일별 총 자산을 날짜 키로 저장한다", async () => {
    accountFindMany.mockResolvedValue([account()]);
    const fetchCloses = vi.fn(async () => closes);

    const result = await syncAccountDailySnapshots(client, { fetchCloses, now: NOW });

    expect(result).toEqual({ accounts: 1, written: 3, mismatched: [], fetchFailed: [] });
    expect(fetchCloses).toHaveBeenCalledWith("005930", "2026-10-23");
    expect(snapshotCreateMany).toHaveBeenCalledWith({
      data: [
        { accountId: "acc-1", takenAt: dateToTakenAt("2026-10-23"), totalValue: 1_000_000, totalContributed: 1_000_000 },
        { accountId: "acc-1", takenAt: dateToTakenAt("2026-10-26"), totalValue: cashAfterBuy + 105_000, totalContributed: 1_000_000 },
        { accountId: "acc-1", takenAt: dateToTakenAt("2026-10-27"), totalValue: cashAfterBuy + 90_000, totalContributed: 1_000_000 },
      ],
      skipDuplicates: true,
    });
  });

  it("이미 저장된 날짜는 다시 쓰지 않고 빠진 날짜만 채운다", async () => {
    accountFindMany.mockResolvedValue([
      account({ VirtualAccountSnapshot: [{ takenAt: dateToTakenAt("2026-10-23") }, { takenAt: dateToTakenAt("2026-10-26") }] }),
    ]);

    const result = await syncAccountDailySnapshots(client, { fetchCloses: async () => closes, now: NOW });

    expect(result.written).toBe(1);
    expect(snapshotCreateMany.mock.calls[0][0].data.map((r) => r.takenAt)).toEqual([dateToTakenAt("2026-10-27")]);
  });

  it("다 채워져 있으면 쓰지 않는다", async () => {
    accountFindMany.mockResolvedValue([
      account({ VirtualAccountSnapshot: ["2026-10-23", "2026-10-26", "2026-10-27"].map((d) => ({ takenAt: dateToTakenAt(d) })) }),
    ]);

    const result = await syncAccountDailySnapshots(client, { fetchCloses: async () => closes, now: NOW });

    expect(result.written).toBe(0);
    expect(snapshotCreateMany).not.toHaveBeenCalled();
  });

  it("복원한 현금이 실제 계좌와 다르면 저장하지 않는다 (관리자 초기화·기록 누락)", async () => {
    accountFindMany.mockResolvedValue([account({ currentCash: cashAfterBuy + 1 })]);

    const result = await syncAccountDailySnapshots(client, { fetchCloses: async () => closes, now: NOW });

    expect(result).toEqual({ accounts: 1, written: 0, mismatched: ["acc-1"], fetchFailed: [] });
    expect(snapshotCreateMany).not.toHaveBeenCalled();
  });

  it("복원한 보유 수량이 실제 계좌와 다르면 저장하지 않는다", async () => {
    accountFindMany.mockResolvedValue([account({ VirtualPosition: [{ symbol: "005930", quantity: 9 }] })]);

    const result = await syncAccountDailySnapshots(client, { fetchCloses: async () => closes, now: NOW });

    expect(result.mismatched).toEqual(["acc-1"]);
  });

  it("오늘 개설한 계좌는 건너뛰고, 같은 종목 종가는 계좌끼리 한 번만 받는다", async () => {
    accountFindMany.mockResolvedValue([
      account({ id: "acc-new", createdAt: new Date("2026-10-30T01:00:00.000Z") }),
      account({ id: "acc-a" }),
      account({ id: "acc-b" }),
    ]);
    const fetchCloses = vi.fn(async () => closes);

    const result = await syncAccountDailySnapshots(client, { fetchCloses, now: NOW });

    expect(fetchCloses).toHaveBeenCalledTimes(1);
    expect(snapshotCreateMany.mock.calls.map((c) => c[0].data[0].accountId)).toEqual(["acc-a", "acc-b"]);
    expect(result.written).toBe(6);
  });

  it("종가는 모든 계좌 중 가장 이른 개설일부터 받는다 — 뒤에 개설한 계좌가 먼저 와도 앞 계좌의 종가가 비지 않는다", async () => {
    // 2026-10-30 사고: 처음 요청한 계좌(10-26 개설)의 개설일부터만 받아 캐시해, 10-23 개설 계좌의
    // 10-23~10-25 종가가 비어 체결가로 평가된 값이 저장됐다.
    accountFindMany.mockResolvedValue([
      account({ id: "acc-late", createdAt: new Date("2026-10-26T00:30:00.000Z") }),
      account({ id: "acc-early", createdAt: new Date("2026-10-20T01:00:00.000Z") }),
    ]);
    const fetchCloses = vi.fn(async () => closes);

    await syncAccountDailySnapshots(client, { fetchCloses, now: NOW });

    expect(fetchCloses).toHaveBeenCalledTimes(1);
    expect(fetchCloses).toHaveBeenCalledWith("005930", "2026-10-20");
  });

  it("종가 조회에 실패한 종목이 있으면 그 계좌는 저장하지 않고 다음 실행에 다시 시도한다", async () => {
    accountFindMany.mockResolvedValue([account()]);

    const result = await syncAccountDailySnapshots(client, { fetchCloses: async () => null, now: NOW });

    expect(result).toEqual({ accounts: 1, written: 0, mismatched: [], fetchFailed: ["acc-1"] });
    expect(snapshotCreateMany).not.toHaveBeenCalled();
  });

  it("운용 중인 계좌만 대상으로 한다", async () => {
    accountFindMany.mockResolvedValue([]);

    await syncAccountDailySnapshots(client, { fetchCloses: async () => ({}), now: NOW });

    expect(accountFindMany.mock.calls[0][0].where).toEqual({ status: "ACTIVE" });
  });
});
