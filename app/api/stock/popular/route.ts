import { NextResponse } from "next/server";
import { fetchStockPriceSnapshots } from "@/lib/server/stock-prices";

// 고정된 인기 검색 종목 목록 (한국 대형주 위주)
const POPULAR_STOCKS = [
  { symbol: "005930", name: "삼성전자" },
  { symbol: "000660", name: "SK하이닉스" },
  { symbol: "373220", name: "LG에너지솔루션" },
  { symbol: "005380", name: "현대차" },
  { symbol: "068270", name: "셀트리온" },
  { symbol: "035420", name: "NAVER" },
  { symbol: "035720", name: "카카오" },
  { symbol: "005490", name: "POSCO홀딩스" },
  { symbol: "105560", name: "KB금융" },
  { symbol: "207940", name: "삼성바이오로직스" },
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
    const symbols = POPULAR_STOCKS.map((s) => s.symbol);
    const data = await fetchStockPriceSnapshots(symbols, {
      subscribe: true,
      mode: "realtime",
    });

    const stocks: PopularStockItem[] = POPULAR_STOCKS.slice(0, 5).map(
      (stock, index) => {
        const q = data[stock.symbol];
        // price > 0 일 때만 신뢰할 수 있는 등락률 (0은 데이터 없음과 구분 불가)
        const changePercent = q && q.price > 0 ? q.changePercent : null;

        return {
          rank: index + 1,
          symbol: stock.symbol,
          name: stock.name,
          changePercent,
        };
      }
    );

    return NextResponse.json({ stocks, updatedAt } satisfies PopularStocksResponse);
  } catch {
    // 백엔드 오류 시 등락률 null 반환 (0과 "데이터 없음" 구분)
    const stocks: PopularStockItem[] = POPULAR_STOCKS.slice(0, 5).map(
      (stock, index) => ({
        rank: index + 1,
        symbol: stock.symbol,
        name: stock.name,
        changePercent: null,
      })
    );

    return NextResponse.json({ stocks, updatedAt } satisfies PopularStocksResponse);
  }
}
