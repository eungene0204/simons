import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  calcMarketFilledPrice,
  calcFee,
  calcBuyCost,
} from "@/lib/order-engine";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// POST: 가상시장 1일 진행
export async function POST(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    // 1. 마켓 상태 + 계좌 + 전략 로드
    const state = await prisma.virtualMarketState.findUnique({
      where: { accountId: params.accountId },
    });
    if (!state || state.status !== "running") {
      return NextResponse.json({
        stepped: false,
        reason: "market not running",
      });
    }

    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.accountId },
      include: { positions: true },
    });
    if (!account || !account.strategyId) {
      return NextResponse.json({
        stepped: false,
        reason: "account or strategy not found",
      });
    }

    const strategy = await prisma.strategy.findUnique({
      where: { id: account.strategyId },
    });
    if (!strategy) {
      return NextResponse.json({
        stepped: false,
        reason: "strategy not found",
      });
    }

    // 2. 전략 DSL 파싱
    const dsl = JSON.parse(strategy.settings);
    const entryConditions = dsl.entry?.conditions || [];
    const exitConditions = dsl.exit?.conditions || [];
    const risk = dsl.risk || {};
    const positionSizePct = risk.position_size_pct || 10;
    const maxPositions = risk.max_positions || 5;

    const symbols: string[] = JSON.parse(state.symbols);

    // 3. Python 백엔드 호출
    const backendRes = await fetch(`${BACKEND_URL}/virtual-market/step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbols,
        entry_conditions: entryConditions,
        exit_conditions: exitConditions,
        virtual_date: state.virtualDate,
        scenario: state.scenario,
        history_days: 60,
      }),
    });

    if (!backendRes.ok) {
      const err = await backendRes.text();
      console.error("Backend step error:", err);
      return NextResponse.json(
        { error: "Backend step failed", detail: err },
        { status: 500 }
      );
    }

    const stepResult = await backendRes.json();

    // 4. 시그널 처리
    const logs: Array<Record<string, unknown>> = [];
    const executedTrades: Array<Record<string, unknown>> = [];

    for (const sig of stepResult.signals) {
      if (sig.error) continue;

      // Entry 시그널 처리
      if (sig.entry_signal) {
        const existingPos = account.positions.find(
          (p) => p.symbol === sig.symbol
        );
        const currentPositionCount = account.positions.length;

        if (existingPos) {
          // 이미 보유 중 → 스킵
          await createLog(params.accountId, state.virtualDate, sig, "entry", "skipped");
          logs.push({
            symbol: sig.symbol,
            type: "entry",
            action: "skipped",
            reason: "이미 보유 중",
          });
        } else if (currentPositionCount >= maxPositions) {
          await createLog(params.accountId, state.virtualDate, sig, "entry", "skipped");
          logs.push({
            symbol: sig.symbol,
            type: "entry",
            action: "skipped",
            reason: "최대 보유 종목 초과",
          });
        } else if (account.tradingMode === "auto") {
          // 자동매매: 주문 실행
          const tradeResult = await executeAutoTrade(
            params.accountId,
            "BUY",
            sig.symbol,
            sig.close,
            account.currentCash,
            positionSizePct
          );
          if (tradeResult) {
            const log = await createLog(
              params.accountId,
              state.virtualDate,
              sig,
              "entry",
              "auto_executed",
              tradeResult.orderId
            );
            executedTrades.push(tradeResult);
            logs.push({
              symbol: sig.symbol,
              type: "entry",
              action: "auto_executed",
              price: sig.close,
              quantity: tradeResult.quantity,
            });
          } else {
            await createLog(params.accountId, state.virtualDate, sig, "entry", "skipped");
            logs.push({
              symbol: sig.symbol,
              type: "entry",
              action: "skipped",
              reason: "잔액 부족",
            });
          }
        } else {
          // 수동 모드: 알림만
          await createLog(params.accountId, state.virtualDate, sig, "entry", "notified");
          logs.push({
            symbol: sig.symbol,
            type: "entry",
            action: "notified",
            price: sig.close,
            reason: sig.entry_reason,
          });
        }
      }

      // Exit 시그널 처리
      if (sig.exit_signal) {
        const existingPos = account.positions.find(
          (p) => p.symbol === sig.symbol
        );

        if (!existingPos) {
          // 보유 종목 없음 → 무시
          continue;
        }

        if (account.tradingMode === "auto") {
          // 자동매매: 매도 실행
          const tradeResult = await executeAutoSell(
            params.accountId,
            sig.symbol,
            sig.close,
            existingPos.quantity
          );
          if (tradeResult) {
            await createLog(
              params.accountId,
              state.virtualDate,
              sig,
              "exit",
              "auto_executed",
              tradeResult.orderId
            );
            executedTrades.push(tradeResult);
            logs.push({
              symbol: sig.symbol,
              type: "exit",
              action: "auto_executed",
              price: sig.close,
              quantity: existingPos.quantity,
            });
          }
        } else {
          await createLog(params.accountId, state.virtualDate, sig, "exit", "notified");
          logs.push({
            symbol: sig.symbol,
            type: "exit",
            action: "notified",
            price: sig.close,
            reason: sig.exit_reason,
          });
        }
      }
    }

    // 5. 가상 날짜 다음 영업일로 진행
    const nextDate = getNextBusinessDay(state.virtualDate);
    await prisma.virtualMarketState.update({
      where: { accountId: params.accountId },
      data: { virtualDate: nextDate },
    });

    return NextResponse.json({
      stepped: true,
      date: state.virtualDate,
      nextDate,
      signals: stepResult.signals,
      logs,
      executedTrades,
    });
  } catch (error) {
    console.error("Virtual market step error:", error);
    return NextResponse.json(
      { error: "Step failed" },
      { status: 500 }
    );
  }
}

// ─── 헬퍼 함수들 ──────────────────────────────────────────────────────

async function createLog(
  accountId: string,
  virtualDate: string,
  sig: Record<string, unknown>,
  signalType: string,
  action: string,
  orderId?: string
) {
  return prisma.virtualMarketLog.create({
    data: {
      accountId,
      virtualDate,
      symbol: sig.symbol as string,
      signalType,
      reason:
        signalType === "entry"
          ? (sig.entry_reason as string) || null
          : (sig.exit_reason as string) || null,
      price: sig.close as number,
      action,
      orderId: orderId || null,
    },
  });
}

async function executeAutoTrade(
  accountId: string,
  side: string,
  symbol: string,
  price: number,
  currentCash: number,
  positionSizePct: number
): Promise<{ orderId: string; quantity: number } | null> {
  const investAmount = currentCash * (positionSizePct / 100);
  const filledPrice = calcMarketFilledPrice(price, side as "BUY" | "SELL");
  const quantity = Math.floor(investAmount / filledPrice);

  if (quantity <= 0) return null;

  const cost = calcBuyCost(filledPrice, quantity);
  if (cost > currentCash) return null;

  // 주문 생성 (즉시 체결)
  const order = await prisma.virtualOrder.create({
    data: {
      accountId,
      symbol,
      name: symbol,
      side: "BUY",
      type: "MARKET",
      quantity,
      price,
      filledPrice,
      status: "FILLED",
      filledAt: new Date(),
    },
  });

  // 잔액 차감 + 포지션 생성/업데이트
  await prisma.virtualAccount.update({
    where: { id: accountId },
    data: { currentCash: { decrement: cost } },
  });

  const existingPos = await prisma.virtualPosition.findUnique({
    where: { accountId_symbol: { accountId, symbol } },
  });
  if (existingPos) {
    const newQty = existingPos.quantity + quantity;
    const newAvgPrice =
      (existingPos.avgPrice * existingPos.quantity + filledPrice * quantity) / newQty;
    await prisma.virtualPosition.update({
      where: { accountId_symbol: { accountId, symbol } },
      data: { quantity: newQty, avgPrice: newAvgPrice },
    });
  } else {
    await prisma.virtualPosition.create({
      data: { accountId, symbol, name: symbol, quantity, avgPrice: filledPrice },
    });
  }

  return { orderId: order.id, quantity };
}

async function executeAutoSell(
  accountId: string,
  symbol: string,
  price: number,
  quantity: number
): Promise<{ orderId: string; quantity: number } | null> {
  const filledPrice = calcMarketFilledPrice(price, "SELL");
  const fee = calcFee(filledPrice, quantity);
  const proceeds = filledPrice * quantity - fee;

  const order = await prisma.virtualOrder.create({
    data: {
      accountId,
      symbol,
      name: symbol,
      side: "SELL",
      type: "MARKET",
      quantity,
      price,
      filledPrice,
      status: "FILLED",
      filledAt: new Date(),
    },
  });

  // 잔액 추가
  await prisma.virtualAccount.update({
    where: { id: accountId },
    data: { currentCash: { increment: proceeds } },
  });

  // 포지션 삭제
  await prisma.virtualPosition.deleteMany({
    where: { accountId, symbol },
  });

  return { orderId: order.id, quantity };
}

function getNextBusinessDay(dateStr: string): string {
  const date = new Date(dateStr);
  date.setDate(date.getDate() + 1);
  // 주말 스킵
  while (date.getDay() === 0 || date.getDay() === 6) {
    date.setDate(date.getDate() + 1);
  }
  return date.toISOString().split("T")[0];
}
