import { prisma } from '@/lib/prisma';
import { getStockNameMap, loadEtfMasterNameMap } from '@/lib/krx-stocks';
import { moneyToNumber } from '@/lib/server/assetService';
import { totalContributed } from '@/lib/virtual-account/contributions';
import { calcFee } from '@/lib/order-engine';

// 계좌 상세 화면(소유자 API·공개 열람 API 공용)의 응답 매퍼.

function resolvePositionName(
  symbol: string,
  storedName: string | null | undefined,
  stockNameMap: Record<string, string>
) {
  if (stockNameMap[symbol]) return stockNameMap[symbol];
  if (storedName && storedName.trim().length > 0 && storedName !== symbol) return storedName;
  return symbol;
}

async function loadEtfNameMapSafely(): Promise<Record<string, string>> {
  try {
    return await loadEtfMasterNameMap();
  } catch {
    return {};
  }
}

export function mapAccount(
  a: any,
  priceMap: Record<string, number>,
  stockNameMap: Record<string, string>,
  settlementValue?: number
) {
  const positions = a.VirtualPosition ?? [];
  const currentCash = moneyToNumber(a.currentCash);
  const liveValue =
    currentCash +
    positions.reduce((sum: number, p: any) => {
      const currentPrice = priceMap[p.symbol] ?? moneyToNumber(p.currentPrice ?? p.avgPrice);
      return sum + p.quantity * currentPrice;
    }, 0);
  // CLOSED 계좌는 강제 정산 후 currentCash/포지션이 0/삭제되므로, 정산 시점 금액을 그대로 보여준다.
  const totalValue = a.status === "CLOSED" && settlementValue != null ? settlementValue : liveValue;
  const holdings = positions.map((p: any) => {
    const avgPrice = moneyToNumber(p.avgPrice);
    const currentPrice = priceMap[p.symbol] ?? moneyToNumber(p.currentPrice ?? p.avgPrice);
    const cost = p.quantity * avgPrice;
    const totalVal = p.quantity * currentPrice;
    const profit = totalVal - cost;
    return {
      symbol: p.symbol,
      name: resolvePositionName(p.symbol, p.name, stockNameMap),
      quantity: p.quantity,
      averagePrice: avgPrice,
      currentPrice,
      totalValue: totalVal,
      profit,
      profitPercent: cost > 0 ? (profit / cost) * 100 : 0,
    };
  });
  return {
    id: a.id,
    name: a.name,
    initialAmount: moneyToNumber(a.initialCash),
    totalContributed: totalContributed(a.initialCash, a.contributedCash),
    currency: (a.currency ?? "KRW") as "KRW" | "USD",
    currentBalance: currentCash,
    totalValue,
    status: a.status ?? "ACTIVE",
    strategyId: a.strategyId ?? undefined,
    strategyName: a.strategyName ?? undefined,
    tradingMode: (a.tradingMode ?? "manual") as "auto" | "manual",
    isPublic: a.isPublic === true,
    createdAt: a.createdAt.toISOString(),
    updatedAt: a.updatedAt.toISOString(),
    closedAt: a.closedAt ? a.closedAt.toISOString() : undefined,
    holdings,
  };
}

export async function buildNameMap(symbols: string[]): Promise<Record<string, string>> {
  const [stockNameMap, etfNameMap, dbStocks] = await Promise.all([
    getStockNameMap(),
    loadEtfNameMapSafely(),
    symbols.length > 0
      ? prisma.stock.findMany({ where: { symbol: { in: symbols }, name: { not: null } }, select: { symbol: true, name: true } })
      : Promise.resolve([]),
  ]);
  const merged: Record<string, string> = {};
  for (const s of dbStocks) if (s.name) merged[s.symbol] = s.name;
  return { ...merged, ...etfNameMap, ...stockNameMap };
}

export function mapOrder(o: any, nameMap: Record<string, string>) {
  const filledPrice = o.filledPrice == null ? undefined : moneyToNumber(o.filledPrice);
  const price = moneyToNumber(o.price);
  const fee = o.fee ?? (filledPrice ? calcFee(filledPrice, o.quantity) : undefined);
  // name이 없거나 symbol과 동일한 경우 korea-stocks.json에서 조회
  const storedName = o.name as string | null | undefined;
  const resolvedName = storedName && storedName !== o.symbol ? storedName : (nameMap[o.symbol] ?? o.symbol);
  return {
    id: o.id,
    accountId: o.accountId,
    type: o.side.toLowerCase() as 'buy' | 'sell',
    symbol: o.symbol,
    name: resolvedName,
    quantity: o.quantity,
    price,
    filledPrice,
    fee: fee == null ? undefined : moneyToNumber(fee),
    tax: o.tax == null ? undefined : moneyToNumber(o.tax),
    avgBuyPrice: o.avgBuyPrice == null ? undefined : moneyToNumber(o.avgBuyPrice),
    realizedPnl: o.realizedPnl == null ? undefined : moneyToNumber(o.realizedPnl),
    totalAmount: (filledPrice ?? price) * o.quantity,
    orderType: o.type as 'MARKET' | 'LIMIT',
    status: o.status as 'PENDING' | 'FILLED' | 'CANCELLED',
    timestamp: o.createdAt.toISOString(),
    filledAt: o.filledAt?.toISOString(),
  };
}
