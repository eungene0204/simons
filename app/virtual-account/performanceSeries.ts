import type { PerformancePoint } from "@/components/portfolio/PortfolioPerformanceChart";
import type { Transaction } from "@/types/portfolio";

export function marketDateKey(iso: string, timeZone: string = "UTC"): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(iso));
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export type CashEvent = { date: string; type: string; amount: number };

/**
 * 계좌 개설일부터 오늘까지의 누적 실현손익 곡선(해당일 총 납입액 = 100 기준).
 *
 * 일별 자산 스냅샷이 없으므로 체결된 매도의 실현손익만 누적한다 —
 * 보유 중인 종목의 평가손익은 포함되지 않는다.
 */
export function buildRealizedPerformanceSeries(
  createdAt: string,
  transactions: Transaction[],
  initialAmount: number,
  today: string = new Date().toISOString().slice(0, 10),
  cashEvents: CashEvent[] = [],
  timeZone: string = "UTC"
): PerformancePoint[] {
  if (!createdAt || initialAmount <= 0) return [];

  const start = marketDateKey(createdAt, timeZone);
  const dailyPnl = new Map<string, number>();
  for (const t of transactions) {
    if (t.type !== "sell" || t.status !== "FILLED") continue;
    const filledAt = t.filledAt ?? t.timestamp;
    if (!filledAt) continue;
    const day = marketDateKey(filledAt, timeZone);
    if (day > today) continue;
    const key = day < start ? start : day;
    dailyPnl.set(key, (dailyPnl.get(key) ?? 0) + (t.realizedPnl ?? 0));
  }

  const dailyContributions = new Map<string, number>();
  for (const event of cashEvents) {
    if (event.type !== "CONTRIBUTION" || !Number.isFinite(event.amount) || event.amount <= 0) continue;
    if (event.date > today) continue;
    const day = event.date < start ? start : event.date;
    dailyContributions.set(day, (dailyContributions.get(day) ?? 0) + event.amount);
  }

  const points: PerformancePoint[] = [{ time: start, portfolio: 100 }];
  let cumulative = 0;
  let contributed = initialAmount;
  const days = [...new Set([...dailyPnl.keys(), ...dailyContributions.keys()])].sort();
  for (const day of days) {
    cumulative += dailyPnl.get(day) ?? 0;
    contributed += dailyContributions.get(day) ?? 0;
    const value = +(100 + (cumulative / contributed) * 100).toFixed(2);
    if (day === start) points[0] = { time: day, portfolio: value };
    else points.push({ time: day, portfolio: value });
  }

  const last = points[points.length - 1];
  if (last.time < today) points.push({ time: today, portfolio: last.portfolio });

  return points;
}
