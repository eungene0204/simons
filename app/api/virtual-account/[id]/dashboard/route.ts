import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export interface DashboardStats {
  // 종합 성과
  totalRealizedPnl: number;
  totalReturn: number; // %
  totalTrades: number;
  winCount: number;
  lossCount: number;
  winRate: number; // %
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  totalFees: number;
  totalTax: number;

  // 일별 PnL (최근 90일)
  dailyPnl: { date: string; pnl: number; cumPnl: number }[];

  // 월별 PnL (최근 12개월)
  monthlyPnl: { month: string; pnl: number; trades: number }[];

  // 종목별 성과 Top5 / Worst5
  bySymbol: {
    symbol: string;
    name: string;
    trades: number;
    pnl: number;
    winRate: number;
  }[];
}

export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.id },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    // 체결된 주문 전체 조회
    const orders = await prisma.virtualOrder.findMany({
      where: { accountId: params.id, status: 'FILLED' },
      orderBy: { filledAt: 'asc' },
    });

    const sellOrders = orders.filter((o) => o.side === 'SELL');

    // ── 종합 성과 ────────────────────────────────────────────────────────────
    const wins = sellOrders.filter((o) => (o.realizedPnl ?? 0) > 0);
    const losses = sellOrders.filter((o) => (o.realizedPnl ?? 0) <= 0);

    const totalRealizedPnl = sellOrders.reduce((s, o) => s + (o.realizedPnl ?? 0), 0);
    const totalReturn = account.initialCash > 0 ? (totalRealizedPnl / account.initialCash) * 100 : 0;

    const totalWinPnl = wins.reduce((s, o) => s + (o.realizedPnl ?? 0), 0);
    const totalLossPnl = Math.abs(losses.reduce((s, o) => s + (o.realizedPnl ?? 0), 0));
    const profitFactor = totalLossPnl > 0 ? totalWinPnl / totalLossPnl : totalWinPnl > 0 ? 999 : 0;

    const totalFees = orders.reduce((s, o) => s + (o.fee ?? 0), 0);
    const totalTax = orders.reduce((s, o) => s + (o.tax ?? 0), 0);

    // ── 일별 PnL ─────────────────────────────────────────────────────────────
    const dailyMap: Record<string, number> = {};
    for (const o of sellOrders) {
      const dt = (o.filledAt ?? o.createdAt).toISOString().slice(0, 10);
      dailyMap[dt] = (dailyMap[dt] ?? 0) + (o.realizedPnl ?? 0);
    }

    // 최근 90일 날짜 목록 생성
    const today = new Date();
    const dailyPnl: { date: string; pnl: number; cumPnl: number }[] = [];
    let cumPnl = 0;
    for (let i = 89; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().slice(0, 10);
      const pnl = dailyMap[dateStr] ?? 0;
      cumPnl += pnl;
      dailyPnl.push({ date: dateStr, pnl, cumPnl });
    }

    // ── 월별 PnL ─────────────────────────────────────────────────────────────
    const monthlyMap: Record<string, { pnl: number; trades: number }> = {};
    for (const o of sellOrders) {
      const month = (o.filledAt ?? o.createdAt).toISOString().slice(0, 7);
      if (!monthlyMap[month]) monthlyMap[month] = { pnl: 0, trades: 0 };
      monthlyMap[month].pnl += o.realizedPnl ?? 0;
      monthlyMap[month].trades += 1;
    }

    // 최근 12개월
    const monthlyPnl: { month: string; pnl: number; trades: number }[] = [];
    for (let i = 11; i >= 0; i--) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      const monthStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      const data = monthlyMap[monthStr] ?? { pnl: 0, trades: 0 };
      monthlyPnl.push({ month: monthStr, ...data });
    }

    // ── 종목별 성과 ───────────────────────────────────────────────────────────
    const symbolMap: Record<string, { name: string; wins: number; losses: number; pnl: number }> = {};
    for (const o of sellOrders) {
      if (!symbolMap[o.symbol]) {
        symbolMap[o.symbol] = { name: o.name ?? o.symbol, wins: 0, losses: 0, pnl: 0 };
      }
      symbolMap[o.symbol].pnl += o.realizedPnl ?? 0;
      if ((o.realizedPnl ?? 0) > 0) symbolMap[o.symbol].wins += 1;
      else symbolMap[o.symbol].losses += 1;
    }

    const bySymbol = Object.entries(symbolMap)
      .map(([symbol, data]) => ({
        symbol,
        name: data.name,
        trades: data.wins + data.losses,
        pnl: data.pnl,
        winRate: data.wins + data.losses > 0 ? (data.wins / (data.wins + data.losses)) * 100 : 0,
      }))
      .sort((a, b) => b.pnl - a.pnl);

    const stats: DashboardStats = {
      totalRealizedPnl,
      totalReturn,
      totalTrades: sellOrders.length,
      winCount: wins.length,
      lossCount: losses.length,
      winRate: sellOrders.length > 0 ? (wins.length / sellOrders.length) * 100 : 0,
      avgWin: wins.length > 0 ? totalWinPnl / wins.length : 0,
      avgLoss: losses.length > 0 ? -(totalLossPnl / losses.length) : 0,
      profitFactor,
      totalFees,
      totalTax,
      dailyPnl,
      monthlyPnl,
      bySymbol,
    };

    return NextResponse.json(stats);
  } catch (error) {
    console.error('Failed to fetch dashboard stats:', error);
    return NextResponse.json({ error: 'Failed to fetch dashboard stats' }, { status: 500 });
  }
}
