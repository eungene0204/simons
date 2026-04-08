export type VIMarket = "KOSPI" | "KOSDAQ";

export function getTickSize(price: number): number {
  if (price < 1000) return 1;
  if (price < 5000) return 5;
  if (price < 10000) return 10;
  if (price < 50000) return 50;
  if (price < 100000) return 100;
  if (price < 500000) return 500;
  return 1000;
}

export function roundDownToTick(price: number): number {
  const tick = getTickSize(price);
  return Math.floor(price / tick) * tick;
}

export function roundUpToTick(price: number): number {
  const tick = getTickSize(price);
  return Math.ceil(price / tick) * tick;
}

export function getStaticVIPrices(referencePrice: number) {
  const rate = 0.1;
  return {
    upVI: roundUpToTick(referencePrice * (1 + rate)),
    downVI: roundDownToTick(referencePrice * (1 - rate)),
    rate,
  };
}
