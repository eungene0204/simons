import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { loadStockList } from "@/lib/krx-stocks";

const KOSPI200_TOP = [
  "005930", "000660", "373220", "207940", "005380",
  "000270", "068270", "005490", "051910", "003670",
  "035420", "035720", "105560", "055550", "034730",
  "017670", "011200", "010130", "009150", "012330",
];

const MAX_SYMBOLS = 20;

async function resolveUniverseSymbols(
  universeId: string,
  filters: Record<string, any>
): Promise<string[]> {
  if (universeId === "kospi200") {
    return KOSPI200_TOP.slice(0, MAX_SYMBOLS);
  }

  const stocks = await loadStockList();
  let filtered = stocks;

  if (universeId === "kospi") {
    filtered = stocks.filter((s) => s.market === "KOSPI");
  } else if (universeId === "kosdaq") {
    filtered = stocks.filter((s) => s.market === "KOSDAQ");
  }

  // 섹터 필터 적용
  if (filters?.selectedSectors?.length > 0) {
    filtered = filtered.filter(
      (s) => s.sector && filters.selectedSectors.includes(s.sector)
    );
  }

  // 거래량/시가총액 기준 상위 종목만 (단순히 앞에서 MAX_SYMBOLS개)
  return filtered.slice(0, MAX_SYMBOLS).map((s) => s.symbol);
}

// POST: 전략 자동 실행 시작
export async function POST(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const body = await request.json().catch(() => ({}));
    const {
      scenario = "realistic",
      speed = 10,
      startDate = "2023-01-02",
    } = body;

    const account = await prisma.virtualAccount.findUnique({
      where: { id: params.id },
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

    const strategy = await prisma.strategy.findUnique({
      where: { id: account.strategyId },
    });
    if (!strategy) {
      return NextResponse.json(
        { error: "연결된 전략을 찾을 수 없습니다." },
        { status: 404 }
      );
    }

    // 전략 DSL에서 유니버스 정보 파싱
    const dsl = JSON.parse(strategy.settings);
    const universe = dsl.universe || { id: "kospi200", filters: {} };

    const symbols = await resolveUniverseSymbols(
      universe.id || "kospi200",
      universe.filters || {}
    );

    if (symbols.length === 0) {
      return NextResponse.json(
        { error: "전략 유니버스에서 종목을 가져올 수 없습니다." },
        { status: 400 }
      );
    }

    // tradingMode를 auto로 설정
    await prisma.virtualAccount.update({
      where: { id: params.id },
      data: { tradingMode: "auto" },
    });

    // 가상시장 상태 생성/업데이트 (running)
    const state = await prisma.virtualMarketState.upsert({
      where: { accountId: params.id },
      create: {
        accountId: params.id,
        virtualDate: startDate,
        startDate,
        scenario,
        speed,
        status: "running",
        symbols: JSON.stringify(symbols),
      },
      update: {
        virtualDate: startDate,
        startDate,
        scenario,
        speed,
        status: "running",
        symbols: JSON.stringify(symbols),
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
      `[전략 자동 실행] 계좌=${params.id} 전략="${strategy.name}" 종목=${symbols.length}개 시작`,
      symbols
    );

    return NextResponse.json({
      ...state,
      symbols,
      symbolNames,
      strategyName: strategy.name,
    });
  } catch (error) {
    console.error("Strategy start error:", error);
    return NextResponse.json(
      { error: "전략 자동 실행 시작에 실패했습니다." },
      { status: 500 }
    );
  }
}
