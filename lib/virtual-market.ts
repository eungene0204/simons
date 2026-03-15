// Virtual Market Service — 가상주식시장 API 래퍼

export interface VirtualMarketState {
  id: string;
  accountId: string;
  virtualDate: string;
  startDate: string;
  scenario: string;
  speed: number;
  status: "running" | "paused" | "stopped";
  symbols: string[];
  symbolNames?: Record<string, string>;
  createdAt: string;
  updatedAt: string;
}

export interface VirtualMarketLog {
  id: string;
  accountId: string;
  virtualDate: string;
  symbol: string;
  stockName: string | null;
  signalType: "entry" | "exit";
  reason: string | null;
  price: number;
  action: "auto_executed" | "notified" | "skipped";
  orderId: string | null;
  createdAt: string;
}

export interface StartMarketConfig {
  symbols: string[];
  scenario?: string;
  speed?: number;
  startDate?: string;
}

export interface TickResult {
  stepped: boolean;
  reason?: string;
  nextStepIn?: number;
  currentDate?: string;
  date?: string;
  nextDate?: string;
  signals?: Array<{
    symbol: string;
    close: number;
    entry_signal: boolean;
    exit_signal: boolean;
    entry_reason: string | null;
    exit_reason: string | null;
  }>;
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
  config: StartMarketConfig
): Promise<VirtualMarketState> {
  const res = await fetch(`/api/virtual-market/${accountId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "가상시장 시작에 실패했습니다");
  }
  return data;
}

export async function updateMarketState(
  accountId: string,
  updates: Partial<{
    status: string;
    speed: number;
    scenario: string;
    symbols: string[];
  }>
): Promise<VirtualMarketState> {
  const res = await fetch(`/api/virtual-market/${accountId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function stopVirtualMarket(
  accountId: string
): Promise<void> {
  await fetch(`/api/virtual-market/${accountId}`, {
    method: "DELETE",
  });
}

export async function tickVirtualMarket(
  accountId: string
): Promise<TickResult> {
  const res = await fetch(`/api/virtual-market/${accountId}/tick`, {
    method: "POST",
  });
  return res.json();
}

export async function getMarketLogs(
  accountId: string,
  limit: number = 50
): Promise<VirtualMarketLog[]> {
  const res = await fetch(
    `/api/virtual-market/${accountId}/logs?limit=${limit}`
  );
  if (!res.ok) return [];
  return res.json();
}
