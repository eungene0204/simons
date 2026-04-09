import { describe, expect, it } from "vitest";
import { buildDisplayRows, ORDERBOOK_DEPTH } from "@/lib/orderbook-display";

describe("buildDisplayRows", () => {
  it("매도 호가가 부족하면 위쪽을 빈 줄로 채워 best ask를 하단(현재가 인접)에 고정한다", () => {
    const rows = buildDisplayRows(
      [
        { price: 1000, quantity: 10 },
        { price: 995, quantity: 20 },
        { price: 990, quantity: 30 },
      ],
      "sell"
    );

    expect(rows).toHaveLength(ORDERBOOK_DEPTH);
    // 위쪽 7행은 빈 줄
    expect(rows.slice(0, 7).every((row) => row.price === undefined && row.type === "sell")).toBe(true);
    // 아래쪽 3행에 호가가 가격 desc로 채워지고 best ask(990)가 가장 아래
    expect(rows.slice(7)).toEqual([
      { price: 1000, sellQuantity: 10, buyQuantity: undefined, type: "sell" },
      { price: 995, sellQuantity: 20, buyQuantity: undefined, type: "sell" },
      { price: 990, sellQuantity: 30, buyQuantity: undefined, type: "sell" },
    ]);
  });

  it("매수 호가가 부족하면 아래쪽을 빈 줄로 채워 best bid를 상단(현재가 인접)에 고정한다", () => {
    const rows = buildDisplayRows(
      [
        { price: 990, quantity: 10 },
        { price: 985, quantity: 20 },
        { price: 980, quantity: 30 },
      ],
      "buy"
    );

    expect(rows).toHaveLength(ORDERBOOK_DEPTH);
    expect(rows.slice(0, 3)).toEqual([
      { price: 990, sellQuantity: undefined, buyQuantity: 10, type: "buy" },
      { price: 985, sellQuantity: undefined, buyQuantity: 20, type: "buy" },
      { price: 980, sellQuantity: undefined, buyQuantity: 30, type: "buy" },
    ]);
    expect(rows.slice(3).every((row) => row.price === undefined && row.type === "buy")).toBe(true);
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
