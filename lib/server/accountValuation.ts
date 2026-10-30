// 가상계좌 평가금액의 공용 계산 — 모든 화면이 같은 현재가로 총 자산을 세게 한다.
//
// 2026-10-30 이전에는 가상계좌 목록·상세만 실시간 시세를 쓰고, 대시보드·전략 목록·관리자는
// 장부에 저장된 마지막 현재가를 써서 같은 계좌의 총 자산이 화면마다 달랐다.

import { moneyToNumber } from "@/lib/server/assetService";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import type { StockPriceSnapshot } from "@/lib/stock-prices";

type Numeric = Parameters<typeof moneyToNumber>[0];

export interface ValuedPosition {
  symbol: string;
  quantity: number;
  avgPrice: Numeric;
  currentPrice?: Numeric | null;
}

/** 종목별 실시간 현재가. 시세를 못 받은 종목은 빠진다(호출부가 저장값으로 폴백). */
export async function fetchLivePriceMap(symbols: string[]): Promise<Record<string, number>> {
  const unique = [...new Set(symbols)];
  if (unique.length === 0) return {};
  const snapshots: Record<string, StockPriceSnapshot> = await fetchStockPriceSnapshots(unique, {
    mode: "realtime",
    subscribe: false,
  }).catch(() => ({}));
  return Object.fromEntries(
    Object.entries(snapshots)
      .filter(([, snapshot]) => snapshot.price > 0)
      .map(([symbol, snapshot]) => [symbol, snapshot.price])
  );
}

/** 현재가: 실시간 시세 → 저장된 현재가 → 평균 매수가. */
export function positionPrice(position: ValuedPosition, priceMap: Record<string, number>): number {
  return priceMap[position.symbol] ?? moneyToNumber(position.currentPrice ?? position.avgPrice);
}

/** 보유 종목 평가금액 합계. */
export function positionsMarketValue(
  positions: ValuedPosition[] | null | undefined,
  priceMap: Record<string, number>
): number {
  return (positions ?? []).reduce((sum, p) => sum + p.quantity * positionPrice(p, priceMap), 0);
}
