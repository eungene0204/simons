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
  const trimmed = [...orders]
    .sort((a, b) => b.price - a.price)
    .slice(0, depth)
    .map((order) => ({
      price: order.price,
      sellQuantity: side === "sell" ? order.quantity : undefined,
      buyQuantity: side === "buy" ? order.quantity : undefined,
      type: side,
    }));

  const placeholders = Array.from({ length: Math.max(0, depth - trimmed.length) }, () => ({
    type: side,
  }));

  return [...trimmed, ...placeholders];
}
