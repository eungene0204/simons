import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getStockNameMap } from '@/lib/krx-stocks';
import { getAccountSettlementValues, moneyToNumber } from '@/lib/server/assetService';
import { findBacktestHistorySummary } from '@/lib/server/strategyHistorySummary';
import { mapAccount, mapOrder, buildNameMap } from '@/lib/server/virtualAccountDetail';
import { buildDashboardStats } from '@/lib/server/virtualAccountDashboard';

// 공개(isPublic) 계좌의 읽기 전용 열람 — 로그인 불필요, 소유자 정보·운용 전략의 상세 규칙은 싣지 않는다.
// 비공개·없는 계좌는 모두 404(존재 여부를 알리지 않는다).
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const account = await prisma.virtualAccount.findFirst({
      where: { id: params.id, isPublic: true },
      include: { VirtualPosition: true, VirtualCashEvent: { orderBy: { date: 'asc' } } },
    });
    if (!account) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 });
    }

    const [orders, marketState, logs, settlementValues] = await Promise.all([
      prisma.virtualOrder.findMany({
        where: { accountId: account.id, status: 'FILLED' },
        orderBy: { createdAt: 'desc' },
      }),
      prisma.virtualMarketState.findUnique({ where: { accountId: account.id } }),
      prisma.virtualMarketLog.findMany({
        where: { accountId: account.id },
        orderBy: { createdAt: 'desc' },
        take: 30,
      }),
      getAccountSettlementValues(prisma, [account.id]),
    ]);

    let trackedSymbols: string[] = [];
    try {
      trackedSymbols = marketState ? JSON.parse(marketState.symbols) : [];
    } catch {
      trackedSymbols = [];
    }
    const symbols = [
      ...account.VirtualPosition.map((p) => p.symbol),
      ...trackedSymbols,
      ...logs.map((l) => l.symbol),
    ];
    const [nameMap, stockNameMap] = await Promise.all([buildNameMap(symbols), getStockNameMap()]);

    // 운용 전략 — 계좌 소유자의 전략만 조회한다(전략 ID 자체는 응답에 싣지 않는다).
    let strategy: { description: string | null; settings: unknown; historySummary: unknown } | null = null;
    if (account.strategyId && account.userId != null) {
      const row = await prisma.strategy.findFirst({ where: { id: account.strategyId, userId: account.userId } });
      if (row) {
        let settings: any = null;
        try {
          settings = JSON.parse(row.settings);
        } catch {}
        strategy = {
          description: row.description ?? null,
          settings,
          historySummary: await findBacktestHistorySummary(row, row.id, account.userId, settings),
        };
      }
    }

    const mapped = mapAccount(account, {}, nameMap, settlementValues[account.id]);
    return NextResponse.json({
      account: {
        ...mapped,
        // 소유자 전용 식별자(전략 ID)는 내보내지 않는다 — 전략명만 보여준다.
        strategyId: undefined,
        cashEvents: account.VirtualCashEvent.map((e) => ({
          date: e.date,
          type: e.type,
          amount: moneyToNumber(e.amount),
        })),
      },
      strategy,
      // 성과 리포트(소유자 대시보드와 같은 계산). 체결 주문 전체로 만든다.
      dashboard: buildDashboardStats(account, orders),
      holdings: mapped.holdings,
      transactions: orders.map((o) => mapOrder(o, stockNameMap)),
      trackedSymbols: trackedSymbols.map((symbol) => ({ symbol, name: nameMap[symbol] ?? symbol })),
      // 허용 필드만 싣는다 — 컬럼이 늘어도 비로그인 응답으로 새지 않게.
      signalLogs: logs.map((l) => ({
        id: l.id,
        accountId: l.accountId,
        date: l.date,
        symbol: l.symbol,
        stockName: l.stockName ?? nameMap[l.symbol] ?? null,
        signalType: l.signalType,
        reason: l.reason,
        price: l.price,
        action: l.action,
        orderId: l.orderId,
        createdAt: l.createdAt,
      })),
    });
  } catch (error) {
    console.error('Failed to fetch shared virtual account:', error);
    return NextResponse.json({ error: 'Failed to fetch account' }, { status: 500 });
  }
}
