import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { loadStockList } from "@/lib/krx-stocks";
import { resolveTrackedSymbolsForStrategy } from "@/lib/strategy-tracked-symbols";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";

// POST: 전략 자동 실행 시작
export async function POST(
  _request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const { userId } = await getOwnershipContext();
    const account = await prisma.virtualAccount.findFirst({
      where: withOwnership({ id: params.id }, userId),
    });
    if (!account) {
      return NextResponse.json({ error: "Account not found" }, { status: 404 });
    }
    if (!account.strategyId) {
      return NextResponse.json(
        { error: "전략이 연결되지 않은 계좌입니다. 계좌에 전략을 연결하세요." },
        { status: 400 }
      );
    }

    const strategy = await prisma.strategy.findFirst({
      where: withOwnership({ id: account.strategyId }, userId),
    });
    if (!strategy) {
      return NextResponse.json(
        { error: "연결된 전략을 찾을 수 없습니다." },
        { status: 404 }
      );
    }

    const resolved = await resolveTrackedSymbolsForStrategy({
      strategyId: account.strategyId!,
      strategyName: strategy.name,
      strategySettings: strategy.settings,
    });
    const symbols = resolved.symbols;
    const symbolSource = resolved.source;

    if (symbols.length === 0) {
      return NextResponse.json(
        { error: "전략 유니버스에서 종목을 가져올 수 없습니다." },
        { status: 400 }
      );
    }

    // tradingMode를 auto로 설정
    await prisma.virtualAccount.update({
      where: { id: params.id },
      data: { tradingMode: "auto", updatedAt: new Date() },
    });

    const today = new Date().toISOString().split("T")[0];

    // 가상 계좌 상태 생성/업데이트 (running)
    const state = await prisma.virtualMarketState.upsert({
      where: { accountId: params.id },
      create: {
        id: crypto.randomUUID(),
        accountId: params.id,
        startDate: today,
        status: "running",
        symbols: JSON.stringify(symbols),
        updatedAt: new Date(),
      },
      update: {
        startDate: today,
        status: "running",
        symbols: JSON.stringify(symbols),
        updatedAt: new Date(),
      },
    });

    // 종목명 맵 조회
    const stocks = await loadStockList();
    const nameMap = Object.fromEntries(stocks.map((s) => [s.symbol, s.name]));
    const symbolNames: Record<string, string> = {};
    symbols.forEach((sym) => {
      if (nameMap[sym]) symbolNames[sym] = nameMap[sym];
    });

    console.log(
      `[전략 자동 실행] 계좌=${params.id} 전략="${strategy.name}" 종목=${symbols.length}개 시작 (출처: ${symbolSource})`,
      symbols
    );

    return NextResponse.json({
      ...state,
      symbols,
      symbolNames,
      strategyName: strategy.name,
      symbolSource, // "backtest" | "universe"
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Strategy start error:", error);
    return NextResponse.json(
      { error: "전략 자동 실행 시작에 실패했습니다." },
      { status: 500 }
    );
  }
}
