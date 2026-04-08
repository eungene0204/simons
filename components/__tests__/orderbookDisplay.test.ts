import { describe, expect, it } from "vitest";
import { buildDisplayRows, ORDERBOOK_DEPTH } from "@/lib/orderbook-display";

describe("buildDisplayRows", () => {
  it("호가가 부족해도 표시 행 수를 항상 고정한다", () => {
    const rows = buildDisplayRows(
      [
        { price: 1000, quantity: 10 },
        { price: 995, quantity: 20 },
        { price: 990, quantity: 30 },
      ],
      "sell"
    );

    expect(rows).toHaveLength(ORDERBOOK_DEPTH);
    expect(rows.slice(0, 3)).toEqual([
      { price: 1000, sellQuantity: 10, buyQuantity: undefined, type: "sell" },
      { price: 995, sellQuantity: 20, buyQuantity: undefined, type: "sell" },
      { price: 990, sellQuantity: 30, buyQuantity: undefined, type: "sell" },
    ]);
    expect(rows.slice(3).every((row) => row.price === undefined && row.type === "sell")).toBe(true);
  });

  it("표시용 호가는 항상 가격 기준으로 정렬된 상위 10단계를 사용한다", () => {
    const rows = buildDisplayRows(
      [
        { price: 1010, quantity: 1 },
        { price: 980, quantity: 2 },
        { price: 1005, quantity: 3 },
        { price: 995, quantity: 4 },
        { price: 990, quantity: 5 },
        { price: 1000, quantity: 6 },
        { price: 985, quantity: 7 },
        { price: 975, quantity: 8 },
        { price: 970, quantity: 9 },
        { price: 965, quantity: 10 },
        { price: 960, quantity: 11 },
        { price: 955, quantity: 12 },
      ],
      "buy"
    );

    expect(rows).toHaveLength(ORDERBOOK_DEPTH);
    expect(rows.map((row) => row.price)).toEqual([
      1010,
      1005,
      1000,
      995,
      990,
      985,
      980,
      975,
      970,
      965,
    ]);
  });
});
