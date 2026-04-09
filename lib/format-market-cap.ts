const formatNumber = (value: number) =>
  new Intl.NumberFormat("ko-KR").format(value);

function normalizeMarketCap(value: number): number {
  if (!Number.isFinite(value) || value <= 0) {
    return 0;
  }

  // KIS hts_avls/stck_avls 값은 억원 단위 정수로 들어온다.
  // 예: 12,475,253 -> 1,247조 5,253억원
  if (value < 100_000_000) {
    return value * 100_000_000;
  }

  return value;
}

export function formatMarketCap(value: number): string {
  const normalizedValue = normalizeMarketCap(value);

  if (!Number.isFinite(normalizedValue) || normalizedValue <= 0) {
    return "0원";
  }

  const roundedEok = Math.round(normalizedValue / 100_000_000);

  if (roundedEok === 0) {
    return `${formatNumber(Math.round(normalizedValue))}원`;
  }

  if (roundedEok < 10_000) {
    return `${formatNumber(roundedEok)}억원`;
  }

  const jo = Math.floor(roundedEok / 10_000);
  const remainderEok = roundedEok % 10_000;

  if (remainderEok === 0) {
    return `${formatNumber(jo)}조원`;
  }

  return `${formatNumber(jo)}조 ${formatNumber(remainderEok)}억원`;
}
