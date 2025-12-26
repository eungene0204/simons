import { NextRequest, NextResponse } from "next/server";
import {
  saveStockList,
  fetchKRXStockList,
  StockListItem,
} from "@/lib/krx-stocks";

/**
 * 코스피/코스닥 종목 목록을 동기화하는 API
 * KRX 공개 데이터를 가져와서 파일에 저장합니다
 */
export async function POST(request: NextRequest) {
  try {
    console.log("Starting stock list sync from KRX...");

    // KRX에서 종목 목록 가져오기
    let stocks = await fetchKRXStockList();

    // KRX API가 실패하거나 데이터가 없을 경우 기본 종목 목록 사용
    if (stocks.length === 0) {
      console.log("KRX API returned no data, using fallback list...");

      const kospiStocks: StockListItem[] = [
        {
          symbol: "005930",
          name: "삼성전자",
          market: "KOSPI",
          sector: "정보기술",
          industry: "반도체",
        },
        {
          symbol: "000660",
          name: "SK하이닉스",
          market: "KOSPI",
          sector: "정보기술",
          industry: "반도체",
        },
        {
          symbol: "035420",
          name: "NAVER",
          market: "KOSPI",
          sector: "정보기술",
          industry: "인터넷",
        },
        {
          symbol: "005380",
          name: "현대차",
          market: "KOSPI",
          sector: "소비재",
          industry: "자동차",
        },
        {
          symbol: "051910",
          name: "LG화학",
          market: "KOSPI",
          sector: "소재",
          industry: "화학",
        },
        {
          symbol: "006400",
          name: "삼성SDI",
          market: "KOSPI",
          sector: "소재",
          industry: "전기전자",
        },
        {
          symbol: "035720",
          name: "카카오",
          market: "KOSPI",
          sector: "정보기술",
          industry: "인터넷",
        },
        {
          symbol: "028260",
          name: "삼성물산",
          market: "KOSPI",
          sector: "소비재",
          industry: "유통",
        },
        {
          symbol: "105560",
          name: "KB금융",
          market: "KOSPI",
          sector: "금융",
          industry: "은행",
        },
        {
          symbol: "055550",
          name: "신한지주",
          market: "KOSPI",
          sector: "금융",
          industry: "은행",
        },
        {
          symbol: "032830",
          name: "삼성생명",
          market: "KOSPI",
          sector: "금융",
          industry: "보험",
        },
        {
          symbol: "003670",
          name: "포스코홀딩스",
          market: "KOSPI",
          sector: "소재",
          industry: "철강",
        },
        {
          symbol: "034730",
          name: "SK",
          market: "KOSPI",
          sector: "에너지",
          industry: "정유",
        },
        {
          symbol: "096770",
          name: "SK이노베이션",
          market: "KOSPI",
          sector: "에너지",
          industry: "정유",
        },
        {
          symbol: "017670",
          name: "SK텔레콤",
          market: "KOSPI",
          sector: "통신",
          industry: "통신",
        },
      ];

      const kosdaqStocks: StockListItem[] = [
        {
          symbol: "207940",
          name: "삼성바이오로직스",
          market: "KOSDAQ",
          sector: "헬스케어",
          industry: "바이오",
        },
        {
          symbol: "068270",
          name: "셀트리온",
          market: "KOSDAQ",
          sector: "헬스케어",
          industry: "바이오",
        },
        {
          symbol: "035900",
          name: "JYP Ent.",
          market: "KOSDAQ",
          sector: "소비재",
          industry: "엔터테인먼트",
        },
        {
          symbol: "251270",
          name: "넷마블",
          market: "KOSDAQ",
          sector: "정보기술",
          industry: "게임",
        },
        {
          symbol: "035760",
          name: "CJ ENM",
          market: "KOSDAQ",
          sector: "소비재",
          industry: "미디어",
        },
        {
          symbol: "086790",
          name: "하나금융지주",
          market: "KOSDAQ",
          sector: "금융",
          industry: "은행",
        },
        {
          symbol: "036570",
          name: "엔씨소프트",
          market: "KOSDAQ",
          sector: "정보기술",
          industry: "게임",
        },
        {
          symbol: "066570",
          name: "LG전자",
          market: "KOSDAQ",
          sector: "소비재",
          industry: "가전",
        },
      ];

      stocks = [...kospiStocks, ...kosdaqStocks];
    }

    // 파일에 저장
    await saveStockList(stocks);

    const kospiCount = stocks.filter(
      (s: StockListItem) => s.market === "KOSPI"
    ).length;
    const kosdaqCount = stocks.filter(
      (s: StockListItem) => s.market === "KOSDAQ"
    ).length;

    return NextResponse.json({
      success: true,
      count: stocks.length,
      kospi: kospiCount,
      kosdaq: kosdaqCount,
      message: `Saved ${stocks.length} stocks (${kospiCount} KOSPI, ${kosdaqCount} KOSDAQ)`,
    });
  } catch (error) {
    console.error("Failed to sync stock list:", error);
    return NextResponse.json(
      {
        error: "Failed to sync stock list",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}

/**
 * 저장된 종목 목록을 조회하는 API
 */
export async function GET(request: NextRequest) {
  try {
    const { loadStockList } = await import("@/lib/krx-stocks");
    const stocks = await loadStockList();

    const searchParams = request.nextUrl.searchParams;
    const market = searchParams.get("market"); // KOSPI or KOSDAQ
    const query = searchParams.get("q"); // 검색어

    let filteredStocks = stocks;

    if (market) {
      filteredStocks = filteredStocks.filter(
        (stock: StockListItem) => stock.market === market.toUpperCase()
      );
    }

    if (query) {
      const lowerQuery = query.toLowerCase();
      filteredStocks = filteredStocks.filter(
        (stock: StockListItem) =>
          stock.symbol.includes(query) ||
          stock.name.toLowerCase().includes(lowerQuery)
      );
    }

    return NextResponse.json({
      success: true,
      count: filteredStocks.length,
      stocks: filteredStocks,
    });
  } catch (error) {
    console.error("Failed to load stock list:", error);
    return NextResponse.json(
      {
        error: "Failed to load stock list",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
