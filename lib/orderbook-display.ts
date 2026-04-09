import type { OrderBookItem } from "@/lib/mock-stock-data";

export const ORDERBOOK_DEPTH = 10;

export interface DisplayPriceRow {
  price?: number;
  sellQuantity?: number;
  buyQuantity?: number;
  type: "sell" | "buy";
}

export function buildDisplayRows(
  orders: OrderBookItem[],
  side: "sell" | "buy",
  depth: number = ORDERBOOK_DEPTH
): DisplayPriceRow[] {
  // 한국 표준 호가창:
  //  - 매도(sell): 위쪽이 높은 가격, 아래쪽으로 갈수록 best ask(현재가에 근접). 가격 desc 정렬.
  //  - 매수(buy): 위쪽이 best bid(현재가에 근접), 아래쪽으로 갈수록 낮은 가격. 가격 desc 정렬.
  // 데이터가 부족하면 매도는 "위"를, 매수는 "아래"를 빈 줄로 채운다.
  // 이렇게 해야 best ask와 best bid가 항상 매도/매수 블록의 경계(중앙)에 붙는다.
  const sorted = [...orders]
    .sort((a, b) => b.price - a.price)
    .slice(0, depth);

  // best level이 현재가와 가장 가까운 쪽이므로
  //  - 매도: best ask = price asc 기준 첫 번째 = sorted의 마지막 → 출력의 마지막
  //  - 매수: best bid = price desc 기준 첫 번째 = sorted의 첫 번째 → 출력의 첫 번째
  const visible: DisplayPriceRow[] = sorted.map((order) => ({
    price: order.price,
    sellQuantity: side === "sell" ? order.quantity : undefined,
    buyQuantity: side === "buy" ? order.quantity : undefined,
    type: side,
  }));

  const padCount = Math.max(0, depth - visible.length);
  const placeholders: DisplayPriceRow[] = Array.from({ length: padCount }, () => ({
    type: side,
  }));

  return side === "sell"
    ? [...placeholders, ...visible]
    : [...visible, ...placeholders];
}
