/**
 * POST /api/virtual-market/[accountId]/refresh
 *
 * 실제 KRX 시세 기반 가상 계좌 새로고침:
 * 1. 추적 종목 실제 가격 조회 (Python /market/prices)
 * 2. 전략 시그널 평가 (Python /market/signals)
 * 3. auto 모드 시 신호에 따라 자동 매매 실행
 * 4. 보유 포지션 현재가 갱신
 * 5. lastRefreshed 업데이트
 */

import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  calcMarketFilledPrice,
  calcFee,
  calcTransactionTax,
  calcBuyCost,
  calcSellProceeds,
  calcRealizedPnl,
} from "@/lib/order-engine";
import koreaStocks from "@/data/korea-stocks.json";

const stockNameMap: Record<string, string> = Object.fromEntries(
  (koreaStocks as Array<{ symbol: string; name: string }>).map((s) => [s.symbol, s.name])
);

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    // 1. 마켓 상태 + 계좌 로드
    const state = await prisma.virtualMarketState.findUnique({
      where: { accountId: params.accountId },
    });
    if (!state || state.status !== "running") {
      return NextResponse.json({ refreshed: false, reason: "not running" });
    }

    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.accountId },
      include: { positions: true },
    });
    if (!account) {
      return NextResponse.json({ refreshed: false, reason: "account not found" });
    }

    const symbols: string[] = JSON.parse(state.symbols);

    // 2. 실제 가격 조회
    let priceMap: Record<string, { close: number; open: number; high: number; low: number; volume: number; name: string; date: string }> = {};
    try {
      const priceRes = await fetch(`${BACKEND_URL}/market/prices`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols }),
      });
      if (priceRes.ok) {
        priceMap = await priceRes.json();
      }
    } catch (e) {
      console.error("Price fetch failed:", e);
    }

    // 3. 전략 시그널 평가
    let entryConditions: Array<Record<string, unknown>> = [];
    let exitConditions: Array<Record<string, unknown>> = [];
    let positionSizePct = 10;
    let maxPositions = 5;

    if (account.strategyId) {
      const strategy = await prisma.strategy.findUnique({
        where: { id: account.strategyId },
      });
      if (strategy) {
        const dsl = JSON.parse(strategy.settings);
        entryConditions = dsl.entry?.conditions || [];
        exitConditions = dsl.exit?.conditions || [];
        const risk = dsl.risk || {};
        positionSizePct = risk.position_size_pct || 10;
        maxPositions = risk.max_positions || 5;
      }
    }

    type SignalResult = {
      symbol: string;
      date?: string;
      close?: number;
      open?: number;
      high?: number;
      low?: number;
      volume?: number;
      entry_signal?: boolean;
      exit_signal?: boolean;
      entry_reason?: string | null;
      exit_reason?: string | null;
      error?: string;
    };

    let signals: SignalResult[] = symbols.map((sym) => ({
      symbol: sym,
      ...(priceMap[sym] || {}),
      entry_signal: false,
      exit_signal: false,
    }));

    if (entryConditions.length > 0 || exitConditions.length > 0) {
      try {
        const sigRes = await fetch(`${BACKEND_URL}/market/signals`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbols,
            entry_conditions: entryConditions,
            exit_conditions: exitConditions,
          }),
        });
        if (sigRes.ok) {
          const sigData = await sigRes.json();
          // 시그널 결과에 실제 가격 덮어쓰기 (parquet보다 KRX 가격이 더 최신)
          signals = sigData.signals.map((sig: SignalResult) => ({
            ...sig,
            ...(priceMap[sig.symbol]
              ? {
                  close: priceMap[sig.symbol].close,
                  open: priceMap[sig.symbol].open,
                  high: priceMap[sig.symbol].high,
                  low: priceMap[sig.symbol].low,
                  volume: priceMap[sig.symbol].volume,
                }
              : {}),
          }));
        }
      } catch (e) {
        console.error("Signal evaluation failed:", e);
      }
    }

    // 4. 시그널에 따른 매매 실행
    const today = new Date().toISOString().split("T")[0];
    const logs: Array<Record<string, unknown>> = [];

    for (const sig of signals) {
      if (sig.error || !sig.close) continue;

      const freshAccount = await prisma.virtualAccount.findUnique({
        where: { id: params.accountId },
        include: { positions: true },
      });
      if (!freshAccount) break;

      if (sig.entry_signal) {
        const existingPos = freshAccount.positions.find((p) => p.symbol === sig.symbol);
        const positionCount = freshAccount.positions.length;

        if (existingPos) {
          await logSignal(params.accountId, today, sig, "entry", "skipped");
          logs.push({ symbol: sig.symbol, type: "entry", action: "skipped", reason: "이미 보유 중" });
        } else if (positionCount >= maxPositions) {
          await logSignal(params.accountId, today, sig, "entry", "skipped");
          logs.push({ symbol: sig.symbol, type: "entry", action: "skipped", reason: "최대 보유 종목 초과" });
        } else if (freshAccount.tradingMode === "auto") {
          const result = await executeBuy(params.accountId, sig.symbol, sig.close, freshAccount.currentCash, positionSizePct);
          if (result) {
            await logSignal(params.accountId, today, sig, "entry", "auto_executed", result.orderId);
            logs.push({ symbol: sig.symbol, type: "entry", action: "auto_executed", price: sig.close, quantity: result.quantity });
          } else {
            await logSignal(params.accountId, today, sig, "entry", "skipped");
            logs.push({ symbol: sig.symbol, type: "entry", action: "skipped", reason: "잔액 부족" });
          }
        } else {
          await logSignal(params.accountId, today, sig, "entry", "notified");
          logs.push({ symbol: sig.symbol, type: "entry", action: "notified", price: sig.close, reason: sig.entry_reason });
        }
      }

      if (sig.exit_signal) {
        const existingPos = freshAccount.positions.find((p) => p.symbol === sig.symbol);
        if (!existingPos) continue;

        if (freshAccount.tradingMode === "auto") {
          const result = await executeSell(params.accountId, sig.symbol, sig.close, existingPos.quantity);
          if (result) {
            await logSignal(params.accountId, today, sig, "exit", "auto_executed", result.orderId);
            logs.push({ symbol: sig.symbol, type: "exit", action: "auto_executed", price: sig.close, quantity: existingPos.quantity });
          }
        } else {
          await logSignal(params.accountId, today, sig, "exit", "notified");
          logs.push({ symbol: sig.symbol, type: "exit", action: "notified", price: sig.close, reason: sig.exit_reason });
        }
      }
    }

    // 5. 포지션 현재가 갱신
    const currentPositions = await prisma.virtualPosition.findMany({
      where: { accountId: params.accountId },
    });
    for (const pos of currentPositions) {
      const price = priceMap[pos.symbol]?.close;
      if (price) {
        await prisma.virtualPosition.update({
          where: { accountId_symbol: { accountId: params.accountId, symbol: pos.symbol } },
          data: { currentPrice: price, updatedAt: new Date() },
        });
      }
    }

    // 6. lastRefreshed 갱신
    await prisma.virtualMarketState.update({
      where: { accountId: params.accountId },
      data: { lastRefreshed: today, updatedAt: new Date() },
    });

    return NextResponse.json({ refreshed: true, date: today, signals, logs, prices: priceMap });
  } catch (error) {
    console.error("Virtual market refresh error:", error);
    return NextResponse.json({ error: "Refresh failed" }, { status: 500 });
  }
}

// ─── 헬퍼 ─────────────────────────────────────────────────────────────

async function logSignal(
  accountId: string,
  date: string,
  sig: { symbol: string; close?: number; entry_reason?: string | null; exit_reason?: string | null },
  signalType: string,
  action: string,
  orderId?: string
) {
  return prisma.virtualMarketLog.create({
    data: {
      id: crypto.randomUUID(),
      accountId,
      date,
      symbol: sig.symbol,
      signalType,
      reason: signalType === "entry" ? sig.entry_reason ?? null : sig.exit_reason ?? null,
      price: sig.close ?? 0,
      action,
      orderId: orderId ?? null,
    },
  });
}

async function executeBuy(
  accountId: string,
  symbol: string,
  price: number,
  currentCash: number,
  positionSizePct: number
): Promise<{ orderId: string; quantity: number } | null> {
  const investAmount = currentCash * (positionSizePct / 100);
  const filledPrice = calcMarketFilledPrice(price, "BUY");
  const quantity = Math.floor(investAmount / filledPrice);
  if (quantity <= 0) return null;

  const cost = calcBuyCost(filledPrice, quantity);
  if (cost > currentCash) return null;

  const name = stockNameMap[symbol] || symbol;
  const fee = calcFee(filledPrice, quantity);

  const order = await prisma.virtualOrder.create({
    data: {
      id: crypto.randomUUID(),
      accountId, symbol, name,
      side: "BUY", type: "MARKET",
      quantity, price, filledPrice, fee,
      status: "FILLED", filledAt: new Date(),
    },
  });

  await prisma.virtualAccount.update({
    where: { id: accountId },
    data: { currentCash: { decrement: cost }, updatedAt: new Date() },
  });

  const existing = await prisma.virtualPosition.findUnique({
    where: { accountId_symbol: { accountId, symbol } },
  });
  if (existing) {
    const newQty = existing.quantity + quantity;
    const newAvg = (existing.avgPrice * existing.quantity + filledPrice * quantity) / newQty;
    await prisma.virtualPosition.update({
      where: { accountId_symbol: { accountId, symbol } },
      data: { quantity: newQty, avgPrice: newAvg, updatedAt: new Date() },
    });
  } else {
    await prisma.virtualPosition.create({
      data: {
        id: crypto.randomUUID(),
        accountId, symbol, name, quantity,
        avgPrice: filledPrice,
        updatedAt: new Date(),
      },
    });
  }

  return { orderId: order.id, quantity };
}

async function executeSell(
  accountId: string,
  symbol: string,
  price: number,
  quantity: number
): Promise<{ orderId: string; quantity: number } | null> {
  const pos = await prisma.virtualPosition.findUnique({
    where: { accountId_symbol: { accountId, symbol } },
  });
  if (!pos || pos.quantity < quantity) return null;

  const filledPrice = calcMarketFilledPrice(price, "SELL");
  const fee = calcFee(filledPrice, quantity);
  const tax = calcTransactionTax(filledPrice, quantity);
  const proceeds = calcSellProceeds(filledPrice, quantity);
  const realizedPnl = calcRealizedPnl(filledPrice, pos.avgPrice, quantity, fee, tax);

  const order = await prisma.virtualOrder.create({
    data: {
      id: crypto.randomUUID(),
      accountId, symbol,
      name: stockNameMap[symbol] || symbol,
      side: "SELL", type: "MARKET",
      quantity, price, filledPrice,
      fee, tax, avgBuyPrice: pos.avgPrice, realizedPnl,
      status: "FILLED", filledAt: new Date(),
    },
  });

  await prisma.virtualAccount.update({
    where: { id: accountId },
    data: { currentCash: { increment: proceeds }, updatedAt: new Date() },
  });

  const newQty = pos.quantity - quantity;
  if (newQty === 0) {
    await prisma.virtualPosition.delete({
      where: { accountId_symbol: { accountId, symbol } },
    });
  } else {
    await prisma.virtualPosition.update({
      where: { accountId_symbol: { accountId, symbol } },
      data: { quantity: newQty, updatedAt: new Date() },
    });
  }

  return { orderId: order.id, quantity };
}
