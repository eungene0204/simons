import { t } from "@/lib/i18n";
// Virtual Market Service — 가상 계좌 실제 시세 연동 API 래퍼

export interface VirtualMarketState {
  id: string;
  accountId: string;
  startDate: string;
  status: "running" | "paused" | "stopped";
  symbols: string[];
  symbolNames?: Record<string, string>;
  lastRefreshed: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface VirtualMarketLog {
  id: string;
  accountId: string;
  date: string;
  symbol: string;
  stockName: string | null;
  signalType: "entry" | "exit";
  reason: string | null;
  price: number;
  action: "auto_executed" | "notified" | "skipped";
  orderId: string | null;
  createdAt: string;
}

export interface RefreshResult {
  refreshed: boolean;
  reason?: string;
  date?: string;
  warnings?: string[];
  signals?: Array<{
    symbol: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
    entry_signal: boolean;
    exit_signal: boolean;
    entry_reason: string | null;
    exit_reason: string | null;
    error?: string;
  }>;
  prices?: Record<string, { close: number; open: number; high: number; low: number; volume: number; name: string; date: string }>;
  logs?: Array<{
    symbol: string;
    type: string;
    action: string;
    price?: number;
    quantity?: number;
    reason?: string;
  }>;
}

// ─── API 함수들 ──────────────────────────────────────────────────────────

export async function getMarketState(
  accountId: string
): Promise<VirtualMarketState | null> {
  const res = await fetch(`/api/virtual-market/${accountId}`);
  if (!res.ok) return null;
  return res.json();
}

export async function startVirtualMarket(
  accountId: string,
  symbols: string[]
): Promise<VirtualMarketState> {
  const res = await fetch(`/api/virtual-market/${accountId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || t("시장 추적 시작 실패"));
  return data;
}

export async function updateMarketState(
  accountId: string,
  updates: Partial<{ status: string; symbols: string[] }>
): Promise<VirtualMarketState> {
  const res = await fetch(`/api/virtual-market/${accountId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function stopVirtualMarket(accountId: string): Promise<void> {
  await fetch(`/api/virtual-market/${accountId}`, { method: "DELETE" });
}

export async function refreshMarket(accountId: string): Promise<RefreshResult> {
  const res = await fetch(`/api/virtual-market/${accountId}/refresh`, {
    method: "POST",
  });
  return res.json();
}

export async function getMarketLogs(
  accountId: string,
  limit: number = 50
): Promise<VirtualMarketLog[]> {
  const res = await fetch(`/api/virtual-market/${accountId}/logs?limit=${limit}`);
  if (!res.ok) return [];
  return res.json();
}

export async function startStrategyExecution(
  accountId: string
): Promise<VirtualMarketState> {
  const res = await fetch(`/api/virtual-account/${accountId}/strategy/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || t("전략 자동 실행 시작 실패"));
  return data;
}

export async function stopStrategyExecution(accountId: string): Promise<void> {
  await fetch(`/api/virtual-account/${accountId}/strategy/stop`, { method: "POST" });
}
