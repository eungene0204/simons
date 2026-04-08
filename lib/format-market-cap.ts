const formatNumber = (value: number) =>
  new Intl.NumberFormat("ko-KR").format(value);

export function formatMarketCap(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return "0원";
  }

  const roundedEok = Math.round(value / 100_000_000);

  if (roundedEok === 0) {
    return `${formatNumber(Math.round(value))}원`;
  }

  if (roundedEok < 10_000) {
    return `${formatNumber(roundedEok)}억`;
  }

  const jo = Math.floor(roundedEok / 10_000);
  const remainderEok = roundedEok % 10_000;

  if (remainderEok === 0) {
    return `${formatNumber(jo)}조`;
  }

  if (remainderEok % 1_000 === 0) {
    return `${formatNumber(jo)}조${formatNumber(remainderEok / 1_000)}천억`;
  }

  return `${formatNumber(jo)}조${formatNumber(remainderEok)}억`;
}
