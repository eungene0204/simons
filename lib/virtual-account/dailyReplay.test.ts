import { describe, expect, it } from "vitest";
import { calcBuyCost, calcSellProceeds } from "@/lib/order-engine";
import { replayDailyValues, type ReplayOrder } from "./dailyReplay";

const KST = "Asia/Seoul";
// KST 날짜 d의 장중 시각(10:00 KST = 01:00Z)
const at = (d: string) => `${d}T01:00:00.000Z`;

const order = (o: Partial<ReplayOrder>): ReplayOrder => ({
  side: "BUY",
  type: "MARKET",
  status: "FILLED",
  symbol: "005930",
  quantity: 10,
  price: 10_000,
  filledPrice: 10_000,
  createdAt: at("2026-10-26"),
  filledAt: at("2026-10-26"),
  ...o,
});

const base = {
  createdAt: at("2026-10-23"), // 금요일 개설
  initialCash: 1_000_000,
  currency: "KRW",
  cashEvents: [],
  today: "2026-10-30",
  timeZone: KST,
};

describe("replayDailyValues", () => {
  it("개설일 점과 그 뒤 거래일(어제까지)마다 현금 + 보유 수량 × 그날 종가를 낸다", () => {
    const r = replayDailyValues({
      ...base,
      orders: [order({})],
      closes: { "005930": { "2026-10-26": 10_500, "2026-10-27": 9_000, "2026-10-30": 12_000 } },
    });

    const cash = 1_000_000 - calcBuyCost(10_000, 10);
    expect(r.points).toEqual([
      { date: "2026-10-23", totalValue: 1_000_000, totalContributed: 1_000_000 },
      { date: "2026-10-26", totalValue: cash + 10 * 10_500, totalContributed: 1_000_000 },
      { date: "2026-10-27", totalValue: cash + 10 * 9_000, totalContributed: 1_000_000 },
    ]); // 오늘(10-30)은 장중이라 점을 남기지 않는다
    expect(r.finalCash).toBe(cash);
    expect(r.finalPositions).toEqual({ "005930": 10 });
  });

  it("매도는 체결가 기준 순입금, 다 판 종목은 보유에서 빠진다", () => {
    const r = replayDailyValues({
      ...base,
      orders: [order({}), order({ side: "SELL", filledPrice: 11_000, createdAt: at("2026-10-27"), filledAt: at("2026-10-27") })],
      closes: { "005930": { "2026-10-26": 10_500, "2026-10-27": 11_000 } },
    });

    expect(r.finalCash).toBe(1_000_000 - calcBuyCost(10_000, 10) + calcSellProceeds(11_000, 10));
    expect(r.finalPositions).toEqual({});
    expect(r.points.at(-1)!.totalValue).toBe(r.finalCash);
  });

  it("지정가 매수는 주문 시점에 지정가로 예약 차감하고, 더 싸게 체결돼도 현금은 다시 바뀌지 않는다", () => {
    const r = replayDailyValues({
      ...base,
      orders: [order({ type: "LIMIT", price: 10_000, filledPrice: 9_800, createdAt: at("2026-10-26"), filledAt: at("2026-10-27") })],
      closes: { "005930": { "2026-10-26": 10_100, "2026-10-27": 9_900 } },
    });

    const cash = 1_000_000 - calcBuyCost(10_000, 10);
    expect(r.finalCash).toBe(cash);
    // 10-26: 예약금은 빠졌지만 주식은 아직 없다(실제 계좌 총 자산 정의와 같다)
    expect(r.points.find((p) => p.date === "2026-10-26")!.totalValue).toBe(cash);
    expect(r.points.find((p) => p.date === "2026-10-27")!.totalValue).toBe(cash + 10 * 9_900);
  });

  it("미체결 지정가 매수는 예약금만 빠지고, 취소된 지정가 매수는 현금에 영향이 없다", () => {
    const r = replayDailyValues({
      ...base,
      orders: [
        order({ type: "LIMIT", status: "PENDING", filledPrice: null, filledAt: null }),
        order({ type: "LIMIT", status: "CANCELLED", filledPrice: null, filledAt: null, quantity: 50 }),
      ],
      closes: {},
    });

    expect(r.finalCash).toBe(1_000_000 - calcBuyCost(10_000, 10));
    expect(r.finalPositions).toEqual({});
  });

  it("정기 납입은 그날 현금과 총 납입액을 함께 늘린다", () => {
    const r = replayDailyValues({
      ...base,
      orders: [],
      cashEvents: [
        { date: "2026-10-27", type: "CONTRIBUTION", amount: 500_000 },
        { date: "2026-10-27", type: "CONTRIBUTION_START", amount: 0 },
      ],
      closes: { "069500": { "2026-10-26": 1, "2026-10-27": 1 } },
    });

    expect(r.points.map((p) => [p.date, p.totalValue, p.totalContributed])).toEqual([
      ["2026-10-23", 1_000_000, 1_000_000],
      ["2026-10-26", 1_000_000, 1_000_000],
      ["2026-10-27", 1_500_000, 1_500_000],
    ]);
  });

  it("그날 종가가 없으면 직전 종가, 종가가 아예 없으면 마지막 체결가로 평가한다", () => {
    const r = replayDailyValues({
      ...base,
      orders: [order({}), order({ symbol: "000660", filledPrice: 20_000, quantity: 1 })],
      closes: { "005930": { "2026-10-26": 10_500, "2026-10-28": 11_000 }, "000660": {} },
    });
    const cash = 1_000_000 - calcBuyCost(10_000, 10) - calcBuyCost(20_000, 1);

    // 10-27 은 다른 종목도 종가가 없어 거래일로 잡히지 않는다 — 10-26, 10-28 만
    expect(r.points.slice(1)).toEqual([
      { date: "2026-10-26", totalValue: cash + 10 * 10_500 + 20_000, totalContributed: 1_000_000 },
      { date: "2026-10-28", totalValue: cash + 10 * 11_000 + 20_000, totalContributed: 1_000_000 },
    ]);
  });

  it("달러 계좌는 센트 절사 수수료 규칙으로 계산하고 날짜는 뉴욕 기준이다", () => {
    const r = replayDailyValues({
      ...base,
      currency: "USD",
      timeZone: "America/New_York",
      initialCash: 10_000,
      createdAt: "2026-10-23T14:00:00.000Z",
      // 10-27 01:00Z 는 뉴욕 10-26 21:00 — 체결일은 10-26 이다
      orders: [order({ symbol: "AAPL", price: 250.37, filledPrice: 250.37, quantity: 3, createdAt: "2026-10-27T01:00:00.000Z", filledAt: "2026-10-27T01:00:00.000Z" })],
      closes: { AAPL: { "2026-10-26": 251, "2026-10-27": 252 } },
    });

    expect(r.finalCash).toBeCloseTo(10_000 - calcBuyCost(250.37, 3, true), 10);
    expect(r.points.find((p) => p.date === "2026-10-26")!.totalValue).toBeCloseTo(r.finalCash + 3 * 251, 10);
  });

  it("오늘 개설한 계좌는 점이 없다", () => {
    const r = replayDailyValues({ ...base, createdAt: at("2026-10-30"), orders: [], closes: {} });

    expect(r.points).toEqual([]);
    expect(r.finalCash).toBe(1_000_000);
  });
});
