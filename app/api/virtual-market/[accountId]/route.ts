import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getStockNameMap } from "@/lib/krx-stocks";

// GET: 가상 계좌 시장 상태 조회
export async function GET(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const state = await prisma.virtualMarketState.findUnique({
      where: { accountId: params.accountId },
    });
    if (!state) return NextResponse.json(null);

    const symbols: string[] = JSON.parse(state.symbols);
    const nameMap = await getStockNameMap();
    const symbolNames: Record<string, string> = {};
    symbols.forEach((sym) => {
      if (nameMap[sym]) symbolNames[sym] = nameMap[sym];
    });
    return NextResponse.json({ ...state, symbols, symbolNames });
  } catch (error) {
    console.error("Failed to get market state:", error);
    return NextResponse.json({ error: "Failed to get market state" }, { status: 500 });
  }
}

// POST: 시장 추적 시작
export async function POST(
  request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const { symbols } = await request.json();

    if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
      return NextResponse.json({ error: "symbols array is required" }, { status: 400 });
    }

    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.accountId },
    });
    if (!account) {
      return NextResponse.json({ error: "Account not found" }, { status: 404 });
    }

    const today = new Date().toISOString().split("T")[0];

    const state = await prisma.virtualMarketState.upsert({
      where: { accountId: params.accountId },
      create: {
        id: crypto.randomUUID(),
        accountId: params.accountId,
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

    const parsedSymbols: string[] = JSON.parse(state.symbols);
    const nameMap = await getStockNameMap();
    const symbolNames: Record<string, string> = {};
    parsedSymbols.forEach((sym) => {
      if (nameMap[sym]) symbolNames[sym] = nameMap[sym];
    });

    // KIS WebSocket 실시간 구독 등록
    try {
      await fetch(`${process.env.BACKEND_URL || "http://localhost:8000"}/market/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: parsedSymbols }),
      });
    } catch (e) {
      console.warn("WebSocket subscribe failed (non-critical):", e);
    }

    return NextResponse.json({ ...state, symbols: parsedSymbols, symbolNames });
  } catch (error) {
    console.error("Failed to start market tracking:", error);
    return NextResponse.json({ error: "Failed to start market tracking" }, { status: 500 });
  }
}

// PATCH: 상태 변경 (pause/resume/symbols)
export async function PATCH(
  request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    const body = await request.json();
    const data: Record<string, unknown> = { updatedAt: new Date() };

    if (body.status !== undefined) data.status = body.status;
    if (body.symbols !== undefined) data.symbols = JSON.stringify(body.symbols);

    const state = await prisma.virtualMarketState.update({
      where: { accountId: params.accountId },
      data,
    });

    const patchedSymbols: string[] = JSON.parse(state.symbols);
    const nameMap = await getStockNameMap();
    const symbolNames: Record<string, string> = {};
    patchedSymbols.forEach((sym) => {
      if (nameMap[sym]) symbolNames[sym] = nameMap[sym];
    });
    return NextResponse.json({ ...state, symbols: patchedSymbols, symbolNames });
  } catch (error) {
    console.error("Failed to update market state:", error);
    return NextResponse.json({ error: "Failed to update market state" }, { status: 500 });
  }
}

// DELETE: 추적 중지
export async function DELETE(
  _request: Request,
  { params }: { params: { accountId: string } }
) {
  try {
    await prisma.virtualMarketState.deleteMany({
      where: { accountId: params.accountId },
    });
    return NextResponse.json({ message: "Market tracking stopped" });
  } catch (error) {
    console.error("Failed to stop market tracking:", error);
    return NextResponse.json({ error: "Failed to stop market tracking" }, { status: 500 });
  }
}
