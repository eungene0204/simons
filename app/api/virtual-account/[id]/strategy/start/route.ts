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
const MIN_BACKTEST_SYMBOLS = 3; // 백테스트 종목이 이보다 적으면 유니버스 폴백

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

/**
 * perAssetStats JSON에서 수익률 상위 종목 추출 (공통 헬퍼)
 */
function rankSymbolsByReturn(
  perAssetStats: Record<string, { totalReturn: number; trades: number }>
): string[] {
  return Object.entries(perAssetStats)
    .filter(([, stat]) => stat.trades > 0)
    .sort(([, a], [, b]) => b.totalReturn - a.totalReturn)
    .slice(0, MAX_SYMBOLS)
    .map(([symbol]) => symbol);
}

/**
 * 전략의 최근 백테스트 결과에서 수익률 상위 종목 추출.
 *
 * Source of truth 우선순위:
 *  1. BacktestResult (strategyId FK — "전략 저장" 시 생성된 정식 저장본)
 *  2. BacktestHistory (strategyName 매칭 — 자동 저장된 실행 로그, 폴백)
 */
async function getBestBacktestSymbols(
  strategyId: string,
  strategyName: string
): Promise<{ symbols: string[]; source: "backtest" } | null> {
  // 1순위: 정식 저장본 (BacktestResult)
  const savedResult = await prisma.backtestResult.findFirst({
    where: { strategyId },
    orderBy: { createdAt: "desc" },
  });

  if (savedResult) {
    try {
      const summary = JSON.parse(savedResult.summary);
      const perAssetStats = summary.perAssetStats as
        | Record<string, { totalReturn: number; trades: number }>
        | undefined;
      if (perAssetStats && Object.keys(perAssetStats).length >= MIN_BACKTEST_SYMBOLS) {
        const ranked = rankSymbolsByReturn(perAssetStats);
        if (ranked.length >= MIN_BACKTEST_SYMBOLS) {
          return { symbols: ranked, source: "backtest" };
        }
      }
    } catch {
      // 파싱 실패 시 폴백으로 진행
    }
  }

  // 2순위: 실행 로그 폴백 (BacktestHistory)
  const latestHistory = await prisma.backtestHistory.findFirst({
    where: { strategyName },
    orderBy: { createdAt: "desc" },
  });
  if (!latestHistory) return null;

  try {
    const metrics = JSON.parse(latestHistory.metrics);
    const perAssetStats = metrics.perAssetStats as
      | Record<string, { totalReturn: number; trades: number }>
      | undefined;
    if (!perAssetStats || Object.keys(perAssetStats).length < MIN_BACKTEST_SYMBOLS) return null;

    const ranked = rankSymbolsByReturn(perAssetStats);
    if (ranked.length < MIN_BACKTEST_SYMBOLS) return null;

    return { symbols: ranked, source: "backtest" };
  } catch {
    return null;
  }
}

// POST: 전략 자동 실행 시작
export async function POST(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    await request.json().catch(() => ({}));

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

    // 1) 백테스트 수익률 상위 종목 우선 사용
    let symbolSource = "universe";
    const backtestBest = await getBestBacktestSymbols(account.strategyId!, strategy.name);
    let symbols: string[];

    if (backtestBest) {
      symbols = backtestBest.symbols;
      symbolSource = "backtest";
    } else {
      symbols = await resolveUniverseSymbols(
        universe.id || "kospi200",
        universe.filters || {}
      );
    }

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
    console.error("Strategy start error:", error);
    return NextResponse.json(
      { error: "전략 자동 실행 시작에 실패했습니다." },
      { status: 500 }
    );
  }
}
