export interface RollingReturnPoint {
  time: string; // YYYY-MM-DD, 창 종료 거래일(차트 x축)
  value: number; // percent
  start: string; // YYYY-MM-DD, 창 시작 거래일 — 툴팁에 "시작 ~ 종료"로 표시
}

// 하나의 롤링 투자 구간(창) — 창 시작 거래일부터 종료 거래일까지의 수익률과 창 안 MDD.
export interface RollingWindowPoint {
  start: string; // YYYY-MM-DD, 기준 시점(창 시작) 거래일
  end: string; // YYYY-MM-DD, 창 종료 거래일
  value: number; // 구간 수익률(%)
  mdd: number; // 창 안 최대 낙폭(%, 0 이하) — 고점은 창 시작에서 다시 센다
}

// 투자 기간(개월) 하나에 대한 롤링 창 통계 — 표의 한 행.
export interface RollingWindowStats {
  windowMonths: number;
  count: number; // 창(구간) 수
  meanReturn: number;
  medianReturn: number;
  minReturn: number;
  maxReturn: number;
  minReturnWindow: { start: string; end: string };
  maxReturnWindow: { start: string; end: string };
  lossRatio: number; // 수익률 < 0 인 창 비율(%)
  meanMdd: number; // 창 안 MDD 평균(%, 0 이하)
  worstMdd: number; // 창 안 MDD 최악(%, 0 이하)
  worstMddWindow: { start: string; end: string };
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

// 자산곡선(dates 오름차순)에서 매 거래일 기준 "최근 windowMonths개월" 창을 만든다.
// 기준 시점은 (해당일 - windowMonths) 이하의 마지막 거래일 equity이며,
// 창 전체가 백테스트 구간 안에 들어오는 날짜만 포함한다(불완전 창 제외).
// 창 안 MDD는 창 시작 equity를 첫 고점으로 삼아 창 안에서만 잰다.
export function buildRollingWindowPoints(
  dates: string[],
  equity: number[],
  windowMonths: number
): RollingWindowPoint[] {
  const n = Math.min(dates.length, equity.length);
  if (n === 0 || windowMonths <= 0) return [];

  const points: RollingWindowPoint[] = [];
  let base = 0;
  for (let i = 0; i < n; i++) {
    const target = subtractMonths(dates[i], windowMonths);
    if (dates[0] > target) continue;
    while (base + 1 < n && dates[base + 1] <= target) base++;
    const baseEquity = equity[base];
    const current = equity[i];
    if (!(baseEquity > 0) || !isFinite(current)) continue;

    let peak = baseEquity;
    let mdd = 0;
    for (let j = base + 1; j <= i; j++) {
      const v = equity[j];
      if (!isFinite(v)) continue;
      if (v > peak) peak = v;
      const dd = (v / peak - 1) * 100;
      if (dd < mdd) mdd = dd;
    }

    points.push({
      start: dates[base],
      end: dates[i],
      value: (current / baseEquity - 1) * 100,
      mdd,
    });
  }
  return points;
}

// 롤링 수익률 라인 시계열(창 종료일 기준, 창 시작일 동반). buildRollingWindowPoints의 투영이다.
export function buildRollingReturnSeries(
  dates: string[],
  equity: number[],
  windowMonths: number
): RollingReturnPoint[] {
  return buildRollingWindowPoints(dates, equity, windowMonths).map((p) => ({
    time: p.end,
    value: p.value,
    start: p.start,
  }));
}

function median(sorted: number[]): number {
  const n = sorted.length;
  const mid = Math.floor(n / 2);
  return n % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

// 롤링 창들을 투자 기간 하나의 통계 행으로 요약한다. 창이 없으면 null.
export function summarizeRollingWindows(
  windowMonths: number,
  points: RollingWindowPoint[]
): RollingWindowStats | null {
  if (points.length === 0) return null;
  let sum = 0;
  let losses = 0;
  let mddSum = 0;
  let minP = points[0];
  let maxP = points[0];
  let worstP = points[0];
  for (const p of points) {
    sum += p.value;
    if (p.value < 0) losses++;
    mddSum += p.mdd;
    if (p.value < minP.value) minP = p;
    if (p.value > maxP.value) maxP = p;
    if (p.mdd < worstP.mdd) worstP = p;
  }
  const sortedReturns = points.map((p) => p.value).sort((a, b) => a - b);
  return {
    windowMonths,
    count: points.length,
    meanReturn: sum / points.length,
    medianReturn: median(sortedReturns),
    minReturn: minP.value,
    maxReturn: maxP.value,
    minReturnWindow: { start: minP.start, end: minP.end },
    maxReturnWindow: { start: maxP.start, end: maxP.end },
    lossRatio: (losses / points.length) * 100,
    meanMdd: mddSum / points.length,
    worstMdd: worstP.mdd,
    worstMddWindow: { start: worstP.start, end: worstP.end },
  };
}

// 여러 투자 기간에 대해 통계 행을 만든다. 창을 하나도 담지 못하는 기간은 건너뛴다.
export function buildRollingWindowStatsTable(
  dates: string[],
  equity: number[],
  windowMonthsList: readonly number[]
): RollingWindowStats[] {
  const rows: RollingWindowStats[] = [];
  for (const w of windowMonthsList) {
    if (!hasRollingWindowSpan(dates, w)) continue;
    const stats = summarizeRollingWindows(w, buildRollingWindowPoints(dates, equity, w));
    if (stats) rows.push(stats);
  }
  return rows;
}

// 백테스트 구간이 windowMonths개월 창을 최소 1개 담을 수 있는지 여부.
export function hasRollingWindowSpan(
  dates: string[],
  windowMonths: number
): boolean {
  if (dates.length < 2) return false;
  return subtractMonths(dates[dates.length - 1], windowMonths) >= dates[0];
}
