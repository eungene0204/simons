// 가상계좌 일별 총 자산 복원 — 체결·입금 내역을 계좌 개설일부터 다시 따라가 장 마감 기준 총 자산을 구한다.
//
// 현금 규칙은 실제 체결 경로와 같아야 한다(어긋나면 마지막 현금이 실제 계좌와 달라져 저장하지 않는다).
//   - 시장가 매수: 체결 시점에 calcBuyCost(체결가) 차감 (TS 주문 라우트·VirtualTrader 공통)
//   - 지정가 매수: 주문 시점에 calcBuyCost(지정가) 예약 차감, 체결 때 현금 변화 없음(차액 무시),
//     취소 때 같은 금액 환불 — 취소 시각이 남지 않아 예약·환불을 같은 날로 본다(그날 순변화 0)
//   - 매도: 체결 시점에 calcSellProceeds(체결가) 입금
//   - 정기 납입(VirtualCashEvent CONTRIBUTION): 그날 입금
// 평가는 그날 종가(없으면 직전 종가, 그것도 없으면 마지막 체결가)로 한다.

import { calcBuyCost, calcSellProceeds } from "@/lib/order-engine";
import { marketDateKey } from "@/app/virtual-account/performanceSeries";

export interface ReplayOrder {
  side: string;
  type: string;
  status: string;
  symbol: string;
  quantity: number;
  price: number;
  filledPrice: number | null;
  createdAt: string;
  filledAt: string | null;
}

export interface ReplayCashEvent {
  date: string;
  type: string;
  amount: number;
}

/** 종목 → (날짜 YYYY-MM-DD → 종가) */
export type ClosesBySymbol = Record<string, Record<string, number>>;

export interface DailyValue {
  date: string;
  totalValue: number;
  totalContributed: number;
}

export interface ReplayResult {
  /** 개설일(오늘 이전일 때) + 개설일 다음 날부터 어제까지의 거래일 */
  points: DailyValue[];
  /** 오늘 체결까지 모두 반영한 현금 — 실제 계좌 현금과 대조한다 */
  finalCash: number;
  /** 오늘 체결까지 모두 반영한 보유 수량(0주 종목 제외) — 실제 보유 종목과 대조한다 */
  finalPositions: Record<string, number>;
}

type LedgerEvent = { date: string; cash: number; contributed: number; symbol?: string; quantity?: number; price?: number };

export function replayDailyValues(input: {
  createdAt: string;
  initialCash: number;
  currency: string;
  orders: ReplayOrder[];
  cashEvents: ReplayCashEvent[];
  closes: ClosesBySymbol;
  /** 계좌 시장 기준 오늘(YYYY-MM-DD) — 오늘은 장중이라 점으로 남기지 않는다 */
  today: string;
  timeZone: string;
}): ReplayResult {
  const usd = input.currency === "USD";
  const start = marketDateKey(input.createdAt, input.timeZone);
  const day = (iso: string) => {
    const d = marketDateKey(iso, input.timeZone);
    return d < start ? start : d;
  };

  const events: LedgerEvent[] = [];
  for (const o of input.orders) {
    const isBuy = o.side === "BUY";
    if (isBuy && o.type === "LIMIT" && o.status !== "CANCELLED") {
      events.push({ date: day(o.createdAt), cash: -calcBuyCost(o.price, o.quantity, usd), contributed: 0 });
    }
    if (o.status !== "FILLED" || !o.filledAt || o.filledPrice == null) continue;
    const date = day(o.filledAt);
    if (isBuy) {
      const cash = o.type === "LIMIT" ? 0 : -calcBuyCost(o.filledPrice, o.quantity, usd);
      events.push({ date, cash, contributed: 0, symbol: o.symbol, quantity: o.quantity, price: o.filledPrice });
    } else {
      events.push({
        date,
        cash: calcSellProceeds(o.filledPrice, o.quantity, usd),
        contributed: 0,
        symbol: o.symbol,
        quantity: -o.quantity,
        price: o.filledPrice,
      });
    }
  }
  for (const e of input.cashEvents) {
    if (e.type !== "CONTRIBUTION" || !(e.amount > 0)) continue;
    events.push({ date: e.date < start ? start : e.date, cash: e.amount, contributed: e.amount });
  }
  events.sort((a, b) => a.date.localeCompare(b.date));

  const tradingDays = new Set<string>();
  for (const series of Object.values(input.closes)) {
    for (const d of Object.keys(series)) if (d > start && d < input.today) tradingDays.add(d);
  }
  const dates = [...(start < input.today ? [start] : []), ...[...tradingDays].sort()];

  let cash = input.initialCash;
  let contributed = input.initialCash;
  const quantities = new Map<string, number>();
  const lastFillPrice = new Map<string, number>();
  const lastClose = new Map<string, number>();
  const apply = (e: LedgerEvent) => {
    cash += e.cash;
    contributed += e.contributed;
    if (e.symbol && e.quantity) {
      quantities.set(e.symbol, (quantities.get(e.symbol) ?? 0) + e.quantity);
      if (e.price) lastFillPrice.set(e.symbol, e.price);
    }
  };

  const points: DailyValue[] = [];
  let next = 0;
  for (const date of dates) {
    while (next < events.length && events[next].date <= date) apply(events[next++]);
    let holdings = 0;
    for (const [symbol, qty] of quantities) {
      if (qty === 0) continue;
      const close = input.closes[symbol]?.[date];
      if (close != null && close > 0) lastClose.set(symbol, close);
      holdings += qty * (lastClose.get(symbol) ?? lastFillPrice.get(symbol) ?? 0);
    }
    points.push({ date, totalValue: cash + holdings, totalContributed: contributed });
  }
  while (next < events.length) apply(events[next++]);

  const finalPositions: Record<string, number> = {};
  for (const [symbol, qty] of quantities) if (qty !== 0) finalPositions[symbol] = qty;
  return { points, finalCash: cash, finalPositions };
}
