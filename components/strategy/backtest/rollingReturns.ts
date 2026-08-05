export interface RollingReturnPoint {
  time: string; // YYYY-MM-DD
  value: number; // percent
}

const daysInMonth = (year: number, month: number): number =>
  new Date(Date.UTC(year, month, 0)).getUTCDate();

// "YYYY-MM-DD"에서 N개월 전 날짜를 반환한다. 말일은 대상 월의 말일로 클램프한다.
// (예: 03-31 - 1개월 → 02-28)
export function subtractMonths(dateStr: string, months: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const total = y * 12 + (m - 1) - months;
  const targetYear = Math.floor(total / 12);
  const targetMonth = ((total % 12) + 12) % 12; // 0-based
  const targetDay = Math.min(d, daysInMonth(targetYear, targetMonth + 1));
  return `${targetYear}-${String(targetMonth + 1).padStart(2, "0")}-${String(
    targetDay
  ).padStart(2, "0")}`;
}

// 자산곡선(dates 오름차순)에서 매 거래일 기준 "최근 windowMonths개월" 구간 수익률을 계산한다.
// 기준 시점은 (해당일 - windowMonths) 이하의 마지막 거래일 equity이며,
// 창 전체가 백테스트 구간 안에 들어오는 날짜만 포함한다(불완전 창 제외).
export function buildRollingReturnSeries(
  dates: string[],
  equity: number[],
  windowMonths: number
): RollingReturnPoint[] {
  const n = Math.min(dates.length, equity.length);
  if (n === 0 || windowMonths <= 0) return [];

  const points: RollingReturnPoint[] = [];
  let base = 0;
  for (let i = 0; i < n; i++) {
    const target = subtractMonths(dates[i], windowMonths);
    if (dates[0] > target) continue;
    while (base + 1 < n && dates[base + 1] <= target) base++;
    const baseEquity = equity[base];
    const current = equity[i];
    if (!(baseEquity > 0) || !isFinite(current)) continue;
    points.push({ time: dates[i], value: (current / baseEquity - 1) * 100 });
  }
  return points;
}

// 백테스트 구간이 windowMonths개월 창을 최소 1개 담을 수 있는지 여부.
export function hasRollingWindowSpan(
  dates: string[],
  windowMonths: number
): boolean {
  if (dates.length < 2) return false;
  return subtractMonths(dates[dates.length - 1], windowMonths) >= dates[0];
}
