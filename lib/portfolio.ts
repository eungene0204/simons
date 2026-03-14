// Portfolio Utility Functions — API 기반 (DB 저장)

import { VirtualAccount, PortfolioHolding, Transaction } from "@/types/portfolio";
import { generateStockPriceData } from "@/lib/mock-stock-data";

// ─── 가상계좌 관리 ────────────────────────────────────────────────────────────

export async function getAllAccounts(): Promise<VirtualAccount[]> {
  const res = await fetch("/api/virtual-account");
  if (!res.ok) return [];
  return res.json();
}

export async function getAccount(id: string): Promise<VirtualAccount | null> {
  const res = await fetch(`/api/virtual-account/${id}`);
  if (!res.ok) return null;
  return res.json();
}

export async function createAccount(
  name: string,
  initialAmount: number,
  strategyId?: string,
  strategyName?: string
): Promise<VirtualAccount> {
  const res = await fetch("/api/virtual-account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, initialAmount, strategyId, strategyName }),
  });
  return res.json();
}

export async function updateAccount(account: VirtualAccount): Promise<void> {
  await fetch(`/api/virtual-account/${account.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ currentBalance: account.currentBalance }),
  });
}

export async function deleteAccount(id: string): Promise<void> {
  await fetch(`/api/virtual-account/${id}`, { method: "DELETE" });
}

// ─── 보유 종목 관리 ───────────────────────────────────────────────────────────

export async function getHoldingsByAccount(
  accountId: string
): Promise<PortfolioHolding[]> {
  const res = await fetch(`/api/virtual-account/${accountId}/positions`);
  if (!res.ok) return [];
  const positions: PortfolioHolding[] = await res.json();

  // 실시간 현재가 반영 (mock)
  return positions.map((p) => {
    const priceData = generateStockPriceData(p.symbol);
    const currentPrice = priceData.currentPrice;
    const totalValue = p.quantity * currentPrice;
    const profit = totalValue - p.quantity * p.averagePrice;
    const profitPercent = (profit / (p.quantity * p.averagePrice)) * 100;
    return { ...p, currentPrice, totalValue, profit, profitPercent };
  });
}

// ─── 주문 실행 (매수/매도) ────────────────────────────────────────────────────

export async function executeTrade(
  accountId: string,
  type: "buy" | "sell",
  symbol: string,
  name: string,
  quantity: number,
  price: number
): Promise<{ success: boolean; error?: string }> {
  const res = await fetch(`/api/virtual-account/${accountId}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, symbol, name, quantity, price }),
  });
  const data = await res.json();
  if (!res.ok) return { success: false, error: data.error };
  return { success: true };
}

// ─── 거래 내역 조회 ───────────────────────────────────────────────────────────

export async function getTransactionsByAccount(
  accountId: string
): Promise<Transaction[]> {
  const res = await fetch(`/api/virtual-account/${accountId}/orders`);
  if (!res.ok) return [];
  return res.json();
}

// ─── 계좌 총 자산 계산 (읽기 전용, DB 기록 없음) ─────────────────────────────

export async function refreshAccountValue(
  accountId: string
): Promise<{ account: VirtualAccount; holdings: PortfolioHolding[] } | null> {
  const [account, holdings] = await Promise.all([
    getAccount(accountId),
    getHoldingsByAccount(accountId),
  ]);
  if (!account) return null;

  const stocksValue = holdings.reduce((sum, h) => sum + h.totalValue, 0);
  const totalValue = account.currentBalance + stocksValue;

  return { account: { ...account, totalValue }, holdings };
}
