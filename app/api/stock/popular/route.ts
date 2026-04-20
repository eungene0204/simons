import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";

// DB에 데이터가 없거나 부족할 때 사용하는 폴백 목록
const FALLBACK_STOCKS = [
  { symbol: "005930", name: "삼성전자" },
  { symbol: "000660", name: "SK하이닉스" },
  { symbol: "373220", name: "LG에너지솔루션" },
  { symbol: "005380", name: "현대차" },
  { symbol: "068270", name: "셀트리온" },
];

export interface PopularStockItem {
  rank: number;
  symbol: string;
  name: string;
  changePercent: number | null; // null = 데이터 없음 (UI에서 "--" 표시)
}

export interface PopularStocksResponse {
  stocks: PopularStockItem[];
  updatedAt: string;
}

export async function GET() {
  const updatedAt = new Date().toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  });

  try {
    // DB에서 검색 카운트 top 5 조회
    const topSearched = await prisma.searchCount.findMany({
      orderBy: { count: "desc" },
      take: 5,
    });

    // DB 데이터가 5개 미만이면 폴백으로 채움
    const topStocks =
      topSearched.length >= 5
        ? topSearched.map((s) => ({ symbol: s.symbol, name: s.name }))
        : (() => {
            const dbSymbols = new Set(topSearched.map((s) => s.symbol));
            const fallbackFill = FALLBACK_STOCKS.filter(
              (s) => !dbSymbols.has(s.symbol)
            );
            return [
              ...topSearched.map((s) => ({ symbol: s.symbol, name: s.name })),
              ...fallbackFill,
            ].slice(0, 5);
          })();

    const symbols = topStocks.map((s) => s.symbol);
    const data = await fetchStockPriceSnapshots(symbols, {
      subscribe: true,
      mode: "realtime",
    });

    const stocks: PopularStockItem[] = topStocks.map((stock, index) => {
      const q = data[stock.symbol];
      const changePercent = q && q.price > 0 ? q.changePercent : null;

      return {
        rank: index + 1,
        symbol: stock.symbol,
        name: stock.name,
        changePercent,
      };
    });

    return NextResponse.json({ stocks, updatedAt } satisfies PopularStocksResponse);
  } catch {
    // 오류 시 폴백 반환
    const stocks: PopularStockItem[] = FALLBACK_STOCKS.map((stock, index) => ({
      rank: index + 1,
      symbol: stock.symbol,
      name: stock.name,
      changePercent: null,
    }));

    return NextResponse.json({ stocks, updatedAt } satisfies PopularStocksResponse);
  }
}

// 종목 검색/클릭 시 카운트 증가
export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as { symbol?: string; name?: string };
    const { symbol, name } = body;

    if (!symbol || typeof symbol !== "string" || !name || typeof name !== "string") {
      return NextResponse.json({ error: "symbol과 name이 필요합니다." }, { status: 400 });
    }

    await prisma.searchCount.upsert({
      where: { symbol },
      update: { count: { increment: 1 }, name },
      create: { symbol, name, count: 1 },
    });

    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "카운트 업데이트에 실패했습니다." }, { status: 500 });
  }
}
