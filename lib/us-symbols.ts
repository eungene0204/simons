// 미국 티커 판별 (클라이언트에서 사용 가능한 순수 함수)
// 한국 심볼은 6자리·숫자 시작(005930, 0151S0), 미국 티커는 영문 시작(AAPL, BRK-B)
// — backend/engine/providers/toss_us.py의 is_us_symbol과 동일 규칙

export function isUsTicker(symbol: string | null | undefined): boolean {
  return !!symbol && /^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol);
}
