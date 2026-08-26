// 주문 정산의 통화 규칙(2026-08-26) — USD 계좌는 달러 규칙, 원화 계좌는 종전 그대로.
//
// 계좌 금액 숫자는 통화 단위 그대로다(VirtualAccount.currency). 원화 규칙(정수 절사·
// KRX 틱 반올림·증권거래세 0.15%)을 달러 체결에 쓰면 $214.53이 $215로 뭉개지고
// 미국엔 없는 매도세가 붙는다(백테스트 US 레인은 매도세 0 계약).
import { describe, expect, it } from "vitest";
import {
  calcBuyCost,
  calcFee,
  calcMarketFilledPrice,
  calcSellProceeds,
  calcTransactionTax,
  roundToTick,
} from "@/lib/order-engine";

describe("USD 정산 규칙", () => {
  it("호가는 센트 단위 — 정수·KRX 틱으로 뭉개지 않는다", () => {
    expect(roundToTick(214.534, true)).toBe(214.53);
    expect(calcMarketFilledPrice(214.53, "BUY", true)).toBe(214.64);
    expect(calcMarketFilledPrice(214.53, "SELL", true)).toBe(214.42);
    // 저가주가 $1로 올라가지 않는다(원화 규칙의 max(1, ...))
    expect(calcMarketFilledPrice(0.5, "BUY", true)).toBe(0.5);
  });

  it("증권거래세는 0이고 수수료는 센트 절사다", () => {
    expect(calcTransactionTax(214.64, 10, true)).toBe(0);
    expect(calcFee(214.64, 10, true)).toBe(0.32);
    expect(calcSellProceeds(214.64, 10, true)).toBeCloseTo(214.64 * 10 - 0.32, 6);
    expect(calcBuyCost(214.64, 10, true)).toBeCloseTo(214.64 * 10 + 0.32, 6);
  });
});

describe("KRW 정산 규칙(불변)", () => {
  it("틱 반올림·정수 수수료·증권거래세가 종전 그대로다", () => {
    expect(roundToTick(70_035)).toBe(70_000);
    expect(calcMarketFilledPrice(70_000, "BUY")).toBe(70_000);
    expect(calcFee(70_050, 10)).toBe(105);
    expect(calcTransactionTax(70_050, 10)).toBe(1050);
    expect(calcSellProceeds(70_050, 10)).toBe(70_050 * 10 - 105 - 1050);
  });
});
