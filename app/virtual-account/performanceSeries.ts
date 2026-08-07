import type { PerformancePoint } from "@/components/portfolio/PortfolioPerformanceChart";
import type { Transaction } from "@/types/portfolio";

const toDateKey = (iso: string) => iso.slice(0, 10);

/**
 * 계좌 개설일부터 오늘까지의 누적 실현손익 곡선(초기 자본 = 100 기준).
 *
 * 일별 자산 스냅샷이 없으므로 체결된 매도의 실현손익만 누적한다 —
 * 보유 중인 종목의 평가손익은 포함되지 않는다.
 */
export function buildRealizedPerformanceSeries(
  createdAt: string,
  transactions: Transaction[],
  initialAmount: number,
  today: string = new Date().toISOString().slice(0, 10)
): PerformancePoint[] {
  if (!createdAt || initialAmount <= 0) return [];

  const start = toDateKey(createdAt);
  const dailyPnl = new Map<string, number>();
  for (const t of transactions) {
    if (t.type !== "sell" || t.status !== "FILLED") continue;
    const filledAt = t.filledAt ?? t.timestamp;
    if (!filledAt) continue;
    const day = toDateKey(filledAt);
    const key = day < start ? start : day;
    dailyPnl.set(key, (dailyPnl.get(key) ?? 0) + (t.realizedPnl ?? 0));
  }

  const points: PerformancePoint[] = [{ time: start, portfolio: 100 }];
  let cumulative = 0;
  for (const day of [...dailyPnl.keys()].sort()) {
    cumulative += dailyPnl.get(day) ?? 0;
    const value = +(100 + (cumulative / initialAmount) * 100).toFixed(2);
    if (day === start) points[0] = { time: day, portfolio: value };
    else points.push({ time: day, portfolio: value });
  }

  const last = points[points.length - 1];
  if (last.time < today) points.push({ time: today, portfolio: last.portfolio });

  return points;
}
