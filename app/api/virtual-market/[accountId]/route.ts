import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { loadStockList } from "@/lib/krx-stocks";

let stockNameCache: Record<string, string> | null = null;

async function getStockNameMap(): Promise<Record<string, string>> {
  if (stockNameCache) return stockNameCache;
  const stocks = await loadStockList();
  stockNameCache = Object.fromEntries(stocks.map((s) => [s.symbol, s.name]));
  return stockNameCache;
}

// GET: 가상시장 상태 조회
export async function GET(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const state = await prisma.virtualMarketState.findUnique({
      where: { accountId: params.accountId },
    });
    if (!state) {
      return NextResponse.json(null);
    }
    const symbols: string[] = JSON.parse(state.symbols);
    const nameMap = await getStockNameMap();
    const symbolNames: Record<string, string> = {};
    symbols.forEach((sym) => {
      if (nameMap[sym]) symbolNames[sym] = nameMap[sym];
    });
    return NextResponse.json({
      ...state,
      symbols,
      symbolNames,
    });
  } catch (error) {
    console.error("Failed to get market state:", error);
    return NextResponse.json(
      { error: "Failed to get market state" },
      { status: 500 }
    );
  }
}

// POST: 가상시장 시작 (생성)
export async function POST(
  request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const { symbols, scenario, speed, startDate } = await request.json();

    if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
      return NextResponse.json(
        { error: "symbols array is required" },
        { status: 400 }
      );
    }

    // 계좌 확인 & 전략 연결 확인
    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.accountId },
    });
    if (!account) {
      return NextResponse.json(
        { error: "Account not found" },
        { status: 404 }
      );
    }
    if (!account.strategyId) {
      return NextResponse.json(
        { error: "전략이 연결되지 않은 계좌입니다" },
        { status: 400 }
      );
    }

    const date = startDate || "2023-01-02";

    // upsert: 이미 존재하면 업데이트
    const state = await prisma.virtualMarketState.upsert({
      where: { accountId: params.accountId },
      create: {
        accountId: params.accountId,
        virtualDate: date,
        startDate: date,
        scenario: scenario || "realistic",
        speed: speed || 10,
        status: "running",
        symbols: JSON.stringify(symbols),
      },
      update: {
        virtualDate: date,
        startDate: date,
        scenario: scenario || "realistic",
        speed: speed || 10,
        status: "running",
        symbols: JSON.stringify(symbols),
      },
    });

    const parsedSymbols: string[] = JSON.parse(state.symbols);
    const nameMap = await getStockNameMap();
    const symbolNames: Record<string, string> = {};
    parsedSymbols.forEach((sym) => {
      if (nameMap[sym]) symbolNames[sym] = nameMap[sym];
    });
    return NextResponse.json({
      ...state,
      symbols: parsedSymbols,
      symbolNames,
    });
  } catch (error) {
    console.error("Failed to start virtual market:", error);
    return NextResponse.json(
      { error: "Failed to start virtual market" },
      { status: 500 }
    );
  }
}

// PATCH: 상태 변경 (pause/resume/speed)
export async function PATCH(
  request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const body = await request.json();
    const data: Record<string, unknown> = {};

    if (body.status !== undefined) data.status = body.status;
    if (body.speed !== undefined) data.speed = body.speed;
    if (body.scenario !== undefined) data.scenario = body.scenario;
    if (body.symbols !== undefined)
      data.symbols = JSON.stringify(body.symbols);

    const state = await prisma.virtualMarketState.update({
      where: { accountId: params.accountId },
      data,
    });

    const patchedSymbols: string[] = JSON.parse(state.symbols);
    const patchNameMap = await getStockNameMap();
    const patchSymbolNames: Record<string, string> = {};
    patchedSymbols.forEach((sym) => {
      if (patchNameMap[sym]) patchSymbolNames[sym] = patchNameMap[sym];
    });
    return NextResponse.json({
      ...state,
      symbols: patchedSymbols,
      symbolNames: patchSymbolNames,
    });
  } catch (error) {
    console.error("Failed to update market state:", error);
    return NextResponse.json(
      { error: "Failed to update market state" },
      { status: 500 }
    );
  }
}

// DELETE: 가상시장 중지 & 정리
export async function DELETE(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    await prisma.virtualMarketState.deleteMany({
      where: { accountId: params.accountId },
    });
    return NextResponse.json({ message: "Virtual market stopped" });
  } catch (error) {
    console.error("Failed to delete market state:", error);
    return NextResponse.json(
      { error: "Failed to delete market state" },
      { status: 500 }
    );
  }
}
