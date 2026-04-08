// Portfolio Utility Functions — API 기반 (DB 저장)

import { VirtualAccount, PortfolioHolding, Transaction, PendingOrder } from "@/types/portfolio";

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
  strategyName?: string,
  tradingMode?: "auto" | "manual"
): Promise<VirtualAccount> {
  const res = await fetch("/api/virtual-account", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, initialAmount, strategyId, strategyName, tradingMode }),
  });
  return res.json();
}

export async function updateTradingMode(
  accountId: string,
  tradingMode: "auto" | "manual"
): Promise<VirtualAccount> {
  const res = await fetch(`/api/virtual-account/${accountId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tradingMode }),
  });
  return res.json();
}

export async function updateAccountStrategy(
  accountId: string,
  strategyId: string,
  strategyName: string
): Promise<VirtualAccount> {
  const res = await fetch(`/api/virtual-account/${accountId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategyId, strategyName }),
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
  return res.json();
}

// ─── 주문 실행 (매수/매도, 시장가/지정가) ────────────────────────────────────

export async function executeTrade(
  accountId: string,
  type: "buy" | "sell",
  symbol: string,
  name: string,
  quantity: number,
  price: number,
  orderType: "MARKET" | "LIMIT" = "MARKET"
): Promise<{ success: boolean; order?: Transaction; error?: string }> {
  const res = await fetch(`/api/virtual-account/${accountId}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, symbol, name, quantity, price, orderType }),
  });
  const data = await res.json();
  if (!res.ok) return { success: false, error: data.error };
  return { success: true, order: data };
}

// ─── 미체결 주문 조회 ─────────────────────────────────────────────────────────

export async function getPendingOrders(
  accountId: string
): Promise<PendingOrder[]> {
  const res = await fetch(
    `/api/virtual-account/${accountId}/orders?status=PENDING`
  );
  if (!res.ok) return [];
  return res.json();
}

// ─── 주문 취소 ────────────────────────────────────────────────────────────────

export async function cancelOrder(
  accountId: string,
  orderId: string
): Promise<{ success: boolean; error?: string }> {
  const res = await fetch(
    `/api/virtual-account/${accountId}/orders/${orderId}`,
    { method: "DELETE" }
  );
  const data = await res.json();
  if (!res.ok) return { success: false, error: data.error };
  return { success: true };
}

// ─── PENDING 주문 체결 트리거 (가격 갱신 시 호출) ─────────────────────────────

export async function fillPendingOrders(
  accountId: string,
  symbol: string,
  currentPrice: number
): Promise<{ filled: string[]; count: number }> {
  const res = await fetch(
    `/api/virtual-account/${accountId}/orders/fill`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, currentPrice }),
    }
  );
  if (!res.ok) return { filled: [], count: 0 };
  return res.json();
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
  // account API가 holdings도 포함해서 반환하므로 1회 요청으로 충분
  const account = await getAccount(accountId);
  if (!account) return null;
  const holdings: PortfolioHolding[] = (account as any).holdings ?? [];
  return { account, holdings };
}
