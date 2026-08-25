// 미국 티커 판별 (클라이언트에서 사용 가능한 순수 함수)
// 한국 심볼은 6자리·숫자 시작(005930, 0151S0), 미국 티커는 영문 시작(AAPL, BRK-B)
// — backend/engine/providers/toss_us.py의 is_us_symbol과 동일 규칙

export function isUsTicker(symbol: string | null | undefined): boolean {
  return !!symbol && /^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol);
}

// 미국 유니버스 id — backend engine/universe_pit.US_UNIVERSE_IDS와 동일 목록
const US_UNIVERSE_IDS = new Set(["us", "sp500", "nasdaq100", "nasdaq", "dow30", "us_etf"]);

export function isUsUniverseId(universeId: string | null | undefined): boolean {
  return !!universeId && US_UNIVERSE_IDS.has(universeId.toLowerCase());
}

/** 백테스트 결과가 미국 시장 전략인지 — 유니버스 id 우선, 지정 종목 모드는 거래 심볼 과반. */
export function isUsBacktestResult(result: {
  universeId?: string | null;
  tradesList?: Array<{ symbol?: string | null }> | null;
}): boolean {
  if (isUsUniverseId(result.universeId)) return true;
  const symbols = [
    ...new Set((result.tradesList ?? []).map((t) => t.symbol).filter((s): s is string => !!s)),
  ];
  if (symbols.length === 0) return false;
  return symbols.filter(isUsTicker).length * 2 > symbols.length;
}

/** 달러 표기 — 금액은 정수($12,345), price 옵션은 소수 2자리($214.00). 음수는 -$ 접두. */
export function formatUsd(value: number, opts?: { price?: boolean }): string {
  const num = Number(value);
  if (isNaN(num)) return "$0";
  const abs = Math.abs(num);
  const body = opts?.price
    ? abs.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : Math.round(abs).toLocaleString("en-US");
  return `${num < 0 ? "-" : ""}$${body}`;
}
