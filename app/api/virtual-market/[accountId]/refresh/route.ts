/**
 * POST /api/virtual-market/[accountId]/refresh
 *
 * 실제 KRX 시세 기반 가상 계좌 새로고침:
 * 1. 추적 종목 실제 가격 조회 (Python /market/prices)
 * 2. 전략 시그널 평가 (Python /market/signals)
 * 3. 리스크 관리: 손절/익절/트레일링스톱/최대보유일 평가
 * 4. 같은 날 중복 매매 방지
 * 5. auto 모드 시 신호에 따라 자동 매매 실행
 * 6. PENDING 지정가 주문 자동 체결
 * 7. 보유 포지션 현재가/최고가 갱신
 * 8. lastRefreshed 업데이트
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
  isPendingFillable,
} from "@/lib/order-engine";
import koreaStocks from "@/data/korea-stocks.json";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";

const stockNameMap: Record<string, string> = Object.fromEntries(
  (koreaStocks as Array<{ symbol: string; name: string }>).map((s) => [s.symbol, s.name])
);

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

function summarizeFetchError(error: unknown): string {
  if (!(error instanceof Error)) {
    return "unknown fetch error";
  }

  const cause = error.cause;
  if (
    cause &&
    typeof cause === "object" &&
    "code" in cause &&
    typeof (cause as { code?: unknown }).code === "string"
  ) {
    return `${error.message} (${(cause as { code: string }).code})`;
  }

  return error.message;
}

export async function POST(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const warnings: string[] = [];
    // 1. 마켓 상태 + 계좌 로드
    const state = await prisma.virtualMarketState.findUnique({
      where: { accountId: params.accountId },
    });
    if (!state || state.status !== "running") {
      return NextResponse.json({ refreshed: false, reason: "not running" });
    }

    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.accountId },
      include: { VirtualPosition: true },
    });
    if (!account) {
      return NextResponse.json({ refreshed: false, reason: "account not found" });
    }

    const symbols: string[] = JSON.parse(state.symbols);

    // 2. KIS WebSocket 구독 보장 (서버 재시작 후 구독 초기화 대비)
    fetch(`${BACKEND_URL}/market/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols }),
    }).catch(() => {}); // fire-and-forget, 실패해도 무시

    // 3. 실제 가격 조회
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
    }

    // 3. 전략 DSL 파싱 (진입/청산 조건 + 리스크 파라미터)
    let entryConditions: Array<Record<string, unknown>> = [];
    let exitConditions: Array<Record<string, unknown>> = [];
    let positionSizePct = 10;
    let maxPositions = 5;
    let stopLossPct = 0;
    let takeProfitPct = 0;
    let trailingStopPct = 0;
    let maxHoldingDays = 0;

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
        stopLossPct = risk.stop_loss_pct || 0;
        takeProfitPct = risk.take_profit_pct || 0;
        trailingStopPct = risk.trailing_stop_pct || 0;
        maxHoldingDays = risk.max_holding_days || 0;
      }
    }

    // 4. 전략 시그널 평가
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
          signal: AbortSignal.timeout(3000),
          body: JSON.stringify({
            symbols,
            quotes: priceMap,
            entry_conditions: entryConditions,
            exit_conditions: exitConditions,
          }),
        });
        if (sigRes.ok) {
          const sigData = await sigRes.json();
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
        const summary = summarizeFetchError(e);
        warnings.push(`Signal evaluation unavailable: ${summary}`);
        console.warn(`Signal evaluation unavailable via ${BACKEND_URL}/market/signals: ${summary}`);
      }
    }

    // 5. 리스크 관리: 보유 포지션에 대해 손절/익절/TS/최대보유일 평가
    const riskExits: Map<string, string> = new Map(); // symbol → reason
    const freshPositions = account.VirtualPosition;

    for (const pos of freshPositions) {
      const currentPrice = priceMap[pos.symbol]?.close ?? pos.currentPrice;
      if (!currentPrice) continue;

      const pnlPct = ((currentPrice - pos.avgPrice) / pos.avgPrice) * 100;

      // 손절 (Stop Loss)
      if (stopLossPct > 0 && pnlPct <= -stopLossPct) {
        riskExits.set(pos.symbol, `손절 (${pnlPct.toFixed(1)}% ≤ -${stopLossPct}%)`);
        continue;
      }

      // 익절 (Take Profit)
      if (takeProfitPct > 0 && pnlPct >= takeProfitPct) {
        riskExits.set(pos.symbol, `익절 (${pnlPct.toFixed(1)}% ≥ +${takeProfitPct}%)`);
        continue;
      }

      // 트레일링 스톱 (Trailing Stop)
      if (trailingStopPct > 0) {
        const peakPrice = pos.peakPrice ?? pos.avgPrice;
        const drawdownPct = ((currentPrice - peakPrice) / peakPrice) * 100;
        if (drawdownPct <= -trailingStopPct) {
          riskExits.set(
            pos.symbol,
            `트레일링스톱 (최고가 ${peakPrice.toLocaleString()}원 대비 ${drawdownPct.toFixed(1)}% 하락)`
          );
          continue;
        }
      }

      // 최대 보유일
      if (maxHoldingDays > 0) {
        const holdingDays = Math.floor(
          (Date.now() - new Date(pos.openedAt).getTime()) / (1000 * 60 * 60 * 24)
        );
        if (holdingDays >= maxHoldingDays) {
          riskExits.set(pos.symbol, `최대보유일 초과 (${holdingDays}일 ≥ ${maxHoldingDays}일)`);
          continue;
        }
      }
    }

    // 리스크 종료 신호를 시그널에 병합 (기존 exit 신호와 OR)
    for (const sig of signals) {
      if (riskExits.has(sig.symbol)) {
        sig.exit_signal = true;
        const riskReason = riskExits.get(sig.symbol)!;
        sig.exit_reason = sig.exit_reason
          ? `${sig.exit_reason} + ${riskReason}`
          : riskReason;
      }
    }
    // 리스크 종료 대상인데 signals 배열에 없는 종목 추가
    riskExits.forEach((reason, symbol) => {
      if (!signals.find((s) => s.symbol === symbol)) {
        const price = priceMap[symbol]?.close;
        signals.push({
          symbol,
          close: price,
          entry_signal: false,
          exit_signal: true,
          exit_reason: reason,
        });
      }
    });

    // 6. 같은 날 중복 매매 방지를 위한 오늘 실행 이력 조회
    const today = new Date().toISOString().split("T")[0];
    const todayLogs = await prisma.virtualMarketLog.findMany({
      where: {
        accountId: params.accountId,
        date: today,
      },
    });
    const loggedToday = new Set(
      todayLogs.map((log) => `${log.symbol}_${log.signalType}`)
    );

    // 7. 시그널에 따른 매매 실행
    const logs: Array<Record<string, unknown>> = [];

    for (const sig of signals) {
      if (sig.error || !sig.close) continue;

      const freshAccount = await prisma.virtualAccount.findUnique({
        where: { id: params.accountId },
        include: { VirtualPosition: true },
      });
      if (!freshAccount) break;

      // ── 청산 먼저 (리스크 종료 포함) ───────────────────────────────────
      if (sig.exit_signal) {
        if (loggedToday.has(`${sig.symbol}_exit`)) {
          continue;
        }

        const existingPos = freshAccount.VirtualPosition.find((p) => p.symbol === sig.symbol);
        if (!existingPos) continue;

        if (freshAccount.tradingMode === "auto") {
          const result = await executeSell(params.accountId, sig.symbol, sig.close, existingPos.quantity);
          if (result) {
            await logSignal(params.accountId, today, sig, "exit", "auto_executed", result.orderId);
            loggedToday.add(`${sig.symbol}_exit`);
            logs.push({ symbol: sig.symbol, type: "exit", action: "auto_executed", price: sig.close, quantity: existingPos.quantity, reason: sig.exit_reason });
          }
        } else {
          await logSignal(params.accountId, today, sig, "exit", "notified");
          loggedToday.add(`${sig.symbol}_exit`);
          logs.push({ symbol: sig.symbol, type: "exit", action: "notified", price: sig.close, reason: sig.exit_reason });
        }
      }

      // ── 진입 ───────────────────────────────────────────────────────────
      if (sig.entry_signal) {
        if (loggedToday.has(`${sig.symbol}_entry`)) {
          continue;
        }

        // 최신 상태 다시 조회 (청산으로 포지션 변경되었을 수 있음)
        const latestAccount = await prisma.virtualAccount.findUnique({
          where: { id: params.accountId },
          include: { VirtualPosition: true },
        });
        if (!latestAccount) break;

        const existingPos = latestAccount.VirtualPosition.find((p) => p.symbol === sig.symbol);
        const positionCount = latestAccount.VirtualPosition.length;

        if (existingPos) {
          await logSignal(params.accountId, today, sig, "entry", "skipped");
          loggedToday.add(`${sig.symbol}_entry`);
          logs.push({ symbol: sig.symbol, type: "entry", action: "skipped", reason: "이미 보유 중" });
        } else if (positionCount >= maxPositions) {
          await logSignal(params.accountId, today, sig, "entry", "skipped");
          loggedToday.add(`${sig.symbol}_entry`);
          logs.push({ symbol: sig.symbol, type: "entry", action: "skipped", reason: "최대 보유 종목 초과" });
        } else if (latestAccount.tradingMode === "auto") {
          const result = await executeBuy(params.accountId, sig.symbol, sig.close, latestAccount.currentCash, positionSizePct);
          if (result) {
            await logSignal(params.accountId, today, sig, "entry", "auto_executed", result.orderId);
            loggedToday.add(`${sig.symbol}_entry`);
            logs.push({ symbol: sig.symbol, type: "entry", action: "auto_executed", price: sig.close, quantity: result.quantity });
          } else {
            await logSignal(params.accountId, today, sig, "entry", "skipped");
            loggedToday.add(`${sig.symbol}_entry`);
            logs.push({ symbol: sig.symbol, type: "entry", action: "skipped", reason: "잔액 부족" });
          }
        } else {
          await logSignal(params.accountId, today, sig, "entry", "notified");
          loggedToday.add(`${sig.symbol}_entry`);
          logs.push({ symbol: sig.symbol, type: "entry", action: "notified", price: sig.close, reason: sig.entry_reason });
        }
      }
    }

    // 8. PENDING 지정가 주문 자동 체결
    const pendingOrders = await prisma.virtualOrder.findMany({
      where: { accountId: params.accountId, status: "PENDING" },
    });
    for (const order of pendingOrders) {
      const currentPrice = priceMap[order.symbol]?.close;
      if (!currentPrice) continue;

      const side = order.side as "BUY" | "SELL";
      if (!isPendingFillable(side, order.price, currentPrice)) continue;

      if (side === "BUY") {
        const pendingAccount = await prisma.virtualAccount.findUnique({
          where: { id: params.accountId },
        });
        if (!pendingAccount) break;

        const filledPrice = order.price; // 지정가로 체결
        const fee = calcFee(filledPrice, order.quantity);
        const cost = calcBuyCost(filledPrice, order.quantity);

        // 예약금은 이미 차감되었으므로 잔액 확인 불필요 — 바로 체결
        await prisma.virtualOrder.update({
          where: { id: order.id },
          data: { status: "FILLED", filledPrice, fee, filledAt: new Date() },
        });

        const name = stockNameMap[order.symbol] || order.symbol;
        const existing = await prisma.virtualPosition.findUnique({
          where: { accountId_symbol: { accountId: params.accountId, symbol: order.symbol } },
        });
        if (existing) {
          const newQty = existing.quantity + order.quantity;
          const newAvg = (existing.avgPrice * existing.quantity + filledPrice * order.quantity) / newQty;
          await prisma.virtualPosition.update({
            where: { accountId_symbol: { accountId: params.accountId, symbol: order.symbol } },
            data: { quantity: newQty, avgPrice: newAvg, currentPrice, peakPrice: Math.max(newAvg, currentPrice), updatedAt: new Date() },
          });
        } else {
          await prisma.virtualPosition.create({
            data: {
              id: crypto.randomUUID(),
              accountId: params.accountId, symbol: order.symbol, name, quantity: order.quantity,
              avgPrice: filledPrice, currentPrice, peakPrice: Math.max(filledPrice, currentPrice),
              updatedAt: new Date(),
            },
          });
        }

        logs.push({ symbol: order.symbol, type: "pending_fill", action: "filled", side: "BUY", price: filledPrice, quantity: order.quantity });
      } else {
        // SELL PENDING 체결
        const pos = await prisma.virtualPosition.findUnique({
          where: { accountId_symbol: { accountId: params.accountId, symbol: order.symbol } },
        });
        if (!pos || pos.quantity < order.quantity) continue;

        const filledPrice = order.price;
        const fee = calcFee(filledPrice, order.quantity);
        const tax = calcTransactionTax(filledPrice, order.quantity);
        const proceeds = calcSellProceeds(filledPrice, order.quantity);
        const realizedPnl = calcRealizedPnl(filledPrice, pos.avgPrice, order.quantity, fee, tax);

        await prisma.virtualOrder.update({
          where: { id: order.id },
          data: { status: "FILLED", filledPrice, fee, tax, avgBuyPrice: pos.avgPrice, realizedPnl, filledAt: new Date() },
        });

        await prisma.virtualAccount.update({
          where: { id: params.accountId },
          data: { currentCash: { increment: proceeds }, updatedAt: new Date() },
        });

        const newQty = pos.quantity - order.quantity;
        if (newQty === 0) {
          await prisma.virtualPosition.delete({
            where: { accountId_symbol: { accountId: params.accountId, symbol: order.symbol } },
          });
        } else {
          await prisma.virtualPosition.update({
            where: { accountId_symbol: { accountId: params.accountId, symbol: order.symbol } },
            data: { quantity: newQty, updatedAt: new Date() },
          });
        }

        logs.push({ symbol: order.symbol, type: "pending_fill", action: "filled", side: "SELL", price: filledPrice, quantity: order.quantity });
      }
    }

    // 9. 포지션 현재가 + peakPrice 갱신
    const currentPositions = await prisma.virtualPosition.findMany({
      where: { accountId: params.accountId },
    });
    for (const pos of currentPositions) {
      const price = priceMap[pos.symbol]?.close;
      if (price) {
        const highPrice = priceMap[pos.symbol]?.high ?? price;
        const newPeak = Math.max(pos.peakPrice ?? pos.avgPrice, highPrice);
        await prisma.virtualPosition.update({
          where: { accountId_symbol: { accountId: params.accountId, symbol: pos.symbol } },
          data: { currentPrice: price, peakPrice: newPeak, updatedAt: new Date() },
        });
      }
    }

    // 10. lastRefreshed 갱신
    await prisma.virtualMarketState.update({
      where: { accountId: params.accountId },
      data: { lastRefreshed: today, updatedAt: new Date() },
    });

    return NextResponse.json({ refreshed: true, date: today, signals, logs, prices: priceMap, warnings });
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
      data: { quantity: newQty, avgPrice: newAvg, peakPrice: Math.max(existing.peakPrice ?? newAvg, price), updatedAt: new Date() },
    });
  } else {
    await prisma.virtualPosition.create({
      data: {
        id: crypto.randomUUID(),
        accountId, symbol, name, quantity,
        avgPrice: filledPrice,
        peakPrice: Math.max(filledPrice, price),
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
