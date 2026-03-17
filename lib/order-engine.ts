// Order Engine — 슬리피지, 수수료, 틱 단위, 체결 판단 로직

export const FEE_RATE = 0.00015;       // 수수료 0.015% (한국 MTS 수준)
export const TAX_RATE = 0.002;         // 증권거래세 0.20% (매도 시 적용, 2024년 기준)
export const MARKET_SLIPPAGE = 0.0005; // 시장가 슬리피지 0.05%

/**
 * 한국거래소 호가 단위(tick size) 적용
 * https://www.krx.co.kr/contents/COM/GenerateOTP.jspx (호가단위)
 */
export function roundToTick(price: number): number {
  if (price < 1_000)   return Math.round(price);
  if (price < 5_000)   return Math.round(price / 5) * 5;
  if (price < 10_000)  return Math.round(price / 10) * 10;
  if (price < 50_000)  return Math.round(price / 50) * 50;
  if (price < 100_000) return Math.round(price / 100) * 100;
  if (price < 500_000) return Math.round(price / 500) * 500;
  return Math.round(price / 1_000) * 1_000;
}

/** 시장가 체결가 (슬리피지 + 틱 반올림) */
export function calcMarketFilledPrice(
  basePrice: number,
  side: "BUY" | "SELL"
): number {
  const slippage = basePrice * MARKET_SLIPPAGE;
  const raw = side === "BUY" ? basePrice + slippage : basePrice - slippage;
  return roundToTick(Math.max(1, raw));
}

/** 수수료 (원 단위 절사) */
export function calcFee(filledPrice: number, quantity: number): number {
  return Math.floor(filledPrice * quantity * FEE_RATE);
}

/** 증권거래세 — 매도 시 적용 (원 단위 절사) */
export function calcTransactionTax(filledPrice: number, quantity: number): number {
  return Math.floor(filledPrice * quantity * TAX_RATE);
}

/** 매수 총비용 (체결가 × 수량 + 수수료) */
export function calcBuyCost(filledPrice: number, quantity: number): number {
  return filledPrice * quantity + calcFee(filledPrice, quantity);
}

/** 매도 순수익 (체결가 × 수량 − 수수료 − 증권거래세) */
export function calcSellProceeds(filledPrice: number, quantity: number): number {
  return filledPrice * quantity - calcFee(filledPrice, quantity) - calcTransactionTax(filledPrice, quantity);
}

/**
 * 실현 손익 (매도 체결 시)
 * = (매도가 − 평균매수가) × 수량 − 매도수수료 − 증권거래세
 * (매수수수료는 평균매수가에 반영되지 않으므로 별도 차감하지 않음)
 */
export function calcRealizedPnl(
  sellPrice: number,
  avgBuyPrice: number,
  quantity: number,
  fee: number,
  tax: number
): number {
  return (sellPrice - avgBuyPrice) * quantity - fee - tax;
}

/**
 * 지정가 즉시 체결 조건:
 *   매수: 지정가 >= 현재가 (더 비싸게 살 의사 → 즉시 체결)
 *   매도: 지정가 <= 현재가 (더 싸게 팔 의사 → 즉시 체결)
 */
export function isImmediateFill(
  side: "BUY" | "SELL",
  limitPrice: number,
  currentPrice: number
): boolean {
  return side === "BUY"
    ? limitPrice >= currentPrice
    : limitPrice <= currentPrice;
}

/**
 * PENDING 주문 체결 조건 (가격 갱신 시 폴링):
 *   매수 지정가: 현재가 <= 지정가
 *   매도 지정가: 현재가 >= 지정가
 */
export function isPendingFillable(
  side: "BUY" | "SELL",
  limitPrice: number,
  currentPrice: number
): boolean {
  return side === "BUY"
    ? currentPrice <= limitPrice
    : currentPrice >= limitPrice;
}
