import { describe, expect, it } from "vitest";

import { buildRealizedPerformanceSeries } from "@/app/virtual-account/performanceSeries";
import type { Transaction } from "@/types/portfolio";

const sell = (filledAt: string, realizedPnl: number, over: Partial<Transaction> = {}): Transaction => ({
  id: `${filledAt}-${realizedPnl}`,
  accountId: "acc-1",
  type: "sell",
  symbol: "005930",
  name: "삼성전자",
  quantity: 10,
  price: 70_000,
  realizedPnl,
  totalAmount: 700_000,
  orderType: "MARKET",
  status: "FILLED",
  timestamp: filledAt,
  filledAt,
  ...over,
});

describe("buildRealizedPerformanceSeries", () => {
  const createdAt = "2026-01-05T00:00:00.000Z";

  it("매도 체결이 없으면 개설일부터 오늘까지 100으로 평평하다", () => {
    const series = buildRealizedPerformanceSeries(createdAt, [], 10_000_000, "2026-03-01");
    expect(series).toEqual([
      { time: "2026-01-05", portfolio: 100 },
      { time: "2026-03-01", portfolio: 100 },
    ]);
  });

  it("실현손익을 날짜순으로 누적하고 초기 자본 대비 지수로 환산한다", () => {
    const series = buildRealizedPerformanceSeries(
      createdAt,
      [
        sell("2026-02-10T01:00:00.000Z", 300_000),
        sell("2026-01-20T01:00:00.000Z", 100_000),
        sell("2026-02-10T05:00:00.000Z", -50_000),
      ],
      10_000_000,
      "2026-03-01"
    );

    expect(series).toEqual([
      { time: "2026-01-05", portfolio: 100 },
      { time: "2026-01-20", portfolio: 101 },
      { time: "2026-02-10", portfolio: 103.5 },
      { time: "2026-03-01", portfolio: 103.5 },
    ]);
  });

  it("체결되지 않은 주문과 매수 주문은 누적에서 제외한다", () => {
    const series = buildRealizedPerformanceSeries(
      createdAt,
      [
        sell("2026-01-20T01:00:00.000Z", 500_000, { status: "PENDING" }),
        sell("2026-01-21T01:00:00.000Z", 500_000, { status: "CANCELLED" }),
        sell("2026-01-22T01:00:00.000Z", 500_000, { type: "buy", realizedPnl: undefined }),
      ],
      10_000_000,
      "2026-03-01"
    );

    expect(series.every((p) => p.portfolio === 100)).toBe(true);
  });

  it("마지막 체결일이 오늘이면 오늘 점을 중복 추가하지 않는다", () => {
    const series = buildRealizedPerformanceSeries(
      createdAt,
      [sell("2026-03-01T01:00:00.000Z", 200_000)],
      10_000_000,
      "2026-03-01"
    );

    expect(series).toEqual([
      { time: "2026-01-05", portfolio: 100 },
      { time: "2026-03-01", portfolio: 102 },
    ]);
  });

  it("초기 자본이 0 이하면 빈 배열을 반환한다", () => {
    expect(buildRealizedPerformanceSeries(createdAt, [sell("2026-02-01T00:00:00.000Z", 1)], 0)).toEqual([]);
  });

  it("개설일보다 앞선 체결은 개설일 시점으로 합산한다", () => {
    const series = buildRealizedPerformanceSeries(
      createdAt,
      [sell("2026-01-01T00:00:00.000Z", 200_000)],
      10_000_000,
      "2026-01-06"
    );

    expect(series).toEqual([
      { time: "2026-01-05", portfolio: 102 },
      { time: "2026-01-06", portfolio: 102 },
    ]);
  });
});
