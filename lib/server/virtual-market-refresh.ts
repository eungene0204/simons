/**
 * 가상 계좌 시장 새로고침 — 표시 전용(display-only)
 *
 * 자동매매 체결의 정본은 FastAPI 백엔드의 VirtualTrader 단일 엔진이다
 * (backend/engine/virtual_trader.py, 30초 간격). 과거에는 이 함수도 시그널을
 * 평가하고 진입/청산/지정가를 체결해 VirtualTrader 와 같은 계좌를 이중으로
 * 매매하는 두 번째 체결 경로였다(브라우저 패널 새로고침 + 인-프로세스 스케줄러).
 * 이제 체결은 VirtualTrader 로 일원화하고, 이 함수는 화면 표시용 데이터만 갱신한다:
 *   1. 추적 종목 실제 가격 조회
 *   2. KIS WebSocket 구독 보장
 *   3. 보유 포지션 현재가/최고가 갱신 (표시용)
 *   4. lastRefreshed 갱신
 * 매매(시그널 평가·진입/청산·지정가 체결)는 하지 않는다.
 *
 * 호출처: 브라우저 새로고침 라우트(app/api/virtual-market/[accountId]/refresh).
 */

import { prisma } from "@/lib/prisma";
import koreaStocks from "@/data/korea-stocks.json";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";
import { moneyToNumber, toMoney } from "@/lib/server/assetService";

const stockNameMap: Record<string, string> = Object.fromEntries(
  (koreaStocks as Array<{ symbol: string; name: string }>).map((s) => [s.symbol, s.name])
);

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export type VirtualMarketRefreshResult =
  | { refreshed: false; reason: string }
  | {
      refreshed: true;
      date: string;
      signals: Array<Record<string, unknown>>;
      logs: Array<Record<string, unknown>>;
      prices: Record<string, unknown>;
      warnings: string[];
    };

export async function refreshVirtualMarket(
  accountId: string
): Promise<VirtualMarketRefreshResult> {
  const warnings: string[] = [];

  // 1. 마켓 상태 + 계좌 로드
  const state = await prisma.virtualMarketState.findUnique({
    where: { accountId },
  });
  if (!state || state.status !== "running") {
    return { refreshed: false, reason: "not running" };
  }

  const account = await prisma.virtualAccount.findUnique({
    where: { id: accountId },
    include: { VirtualPosition: true },
  });
  if (!account) {
    return { refreshed: false, reason: "account not found" };
  }

  const symbols: string[] = JSON.parse(state.symbols);

  // 2. KIS WebSocket 구독 보장 (서버 재시작 후 구독 초기화 대비)
  fetch(`${BACKEND_URL}/market/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols }),
  }).catch(() => {}); // fire-and-forget, 실패해도 무시

  // 3. 실제 가격 조회 (표시용)
  let priceMap: Record<string, { close: number; open: number; high: number; low: number; volume: number; name: string; date: string }> = {};
  try {
    const snapshots = await fetchStockPriceSnapshots(symbols, {
      subscribe: true,
      mode: 'realtime',
    });
    priceMap = Object.fromEntries(
      Object.entries(snapshots)
        .filter(([, value]) => value.price > 0)
        .map(([symbol, value]) => [
          symbol,
          {
            close: value.price,
            open: value.open ?? value.price,
            high: value.high ?? value.price,
            low: value.low ?? value.price,
            volume: value.volume ?? 0,
            name: stockNameMap[symbol] || symbol,
            date: value.date || new Date().toISOString().slice(0, 10),
          },
        ])
    );
  } catch (e) {
    console.error("Price fetch failed:", e);
    warnings.push("가격 조회 실패");
  }

  const today = new Date().toISOString().split("T")[0];

  // 4. 보유 포지션 현재가 + peakPrice 갱신 (표시용 — 체결은 VirtualTrader 담당)
  for (const pos of account.VirtualPosition) {
    const price = priceMap[pos.symbol]?.close;
    if (!price) continue;
    const highPrice = priceMap[pos.symbol]?.high ?? price;
    const newPeak = Math.max(moneyToNumber(pos.peakPrice ?? pos.avgPrice), highPrice);
    await prisma.virtualPosition.update({
      where: { accountId_symbol: { accountId, symbol: pos.symbol } },
      data: { currentPrice: toMoney(price), peakPrice: toMoney(newPeak), updatedAt: new Date() },
    });
  }

  // 5. lastRefreshed 갱신
  await prisma.virtualMarketState.update({
    where: { accountId },
    data: { lastRefreshed: today, updatedAt: new Date() },
  });

  return { refreshed: true, date: today, signals: [], logs: [], prices: priceMap, warnings };
}
