import { NextRequest, NextResponse } from 'next/server'
import { cache } from '@/lib/cache'
import { loadStockList } from '@/lib/krx-stocks'
import { getBasePrice, generateStockPriceData, generateCandleData, generateTimeSeries } from '@/lib/mock-stock-data'

interface StockDetail {
  symbol: string;
  name: string;
  logo?: string;
  currentPrice: number;
  changePercent: number;
  change: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  marketCap: number;
  previousClose: number;
  pe: number;
  pbr: number;
  description: string;
  sector: string;
  industry: string;
  timeSeries?: Array<{ date: string; value: number }>;
  candleData?: Array<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ symbol: string }> | { symbol: string } }
) {
  try {
    const resolvedParams = await Promise.resolve(params);
    const symbol = resolvedParams.symbol;

    // Check cache first
    const cacheKey = `stock:detail:${symbol}`;
    const cached = cache.get(cacheKey);
    if (cached) {
      console.log(`Returning cached stock detail for ${symbol}`);
      return NextResponse.json(cached);
    }

    console.log(`Generating mock stock detail for ${symbol}...`);

    // Base prices for generating dynamic mock data
    const baseData: Record<string, Partial<StockDetail>> = {
      "005930": {
        name: "삼성전자",
        currentPrice: 72500,
        open: 72000,
        high: 72800,
        low: 71800,
        previousClose: 70770,
        volume: 12500000,
        marketCap: 432000000000000,
        pe: 12.5,
        pbr: 1.2,
        description: "삼성전자는 반도체, 디스플레이, 스마트폰 등 다양한 IT 분야에서 세계적인 기업입니다.",
        sector: "정보기술",
        industry: "반도체",
      },
      "000660": {
        name: "SK하이닉스",
        currentPrice: 142000,
        open: 141000,
        high: 143500,
        low: 140500,
        previousClose: 143746,
        volume: 3200000,
        marketCap: 102000000000000,
        pe: 8.3,
        pbr: 1.5,
        description: "SK하이닉스는 메모리 반도체를 생산하는 세계적인 기업입니다.",
        sector: "정보기술",
        industry: "반도체",
      },
      "035420": {
        name: "NAVER",
        currentPrice: 198500,
        open: 197000,
        high: 200000,
        low: 196500,
        previousClose: 192430,
        volume: 2100000,
        marketCap: 31500000000000,
        pe: 28.5,
        pbr: 2.8,
        description: "NAVER는 대한민국 대표 인터넷 포털 및 IT 기업입니다.",
        sector: "정보기술",
        industry: "인터넷 서비스",
      },
      "035720": {
        name: "카카오",
        currentPrice: 54600,
        open: 54000,
        high: 55000,
        low: 53800,
        previousClose: 53610,
        volume: 5800000,
        marketCap: 24500000000000,
        pe: 35.2,
        pbr: 1.8,
        description: "카카오는 모바일 플랫폼과 디지털 콘텐츠 서비스를 제공하는 기업입니다.",
        sector: "정보기술",
        industry: "인터넷 서비스",
      },
    };

    // 한국 종목 목록에서 이름, 섹터, 업종 정보 가져오기
    let stockName = "";
    let stockSector = "";
    let stockIndustry = "";
    try {
      const koreaStocks = await loadStockList();
      const stock = koreaStocks.find((s) => s.symbol === symbol);
      if (stock) {
        stockName = stock.name;
        stockSector = stock.sector || "";
        stockIndustry = stock.industry || "";
      }
    } catch (error) {
      console.error("Failed to load stock list:", error);
    }

    const base = baseData[symbol] || {};
    const basePrice = base.currentPrice || getBasePrice(symbol);
    const priceData = generateStockPriceData(symbol, basePrice);
    
    // 캔들 데이터 생성
    const candleData = generateCandleData(symbol, basePrice, 365);
    const timeSeries = generateTimeSeries(symbol, basePrice, 365);

    const detail: StockDetail = {
      symbol,
      name: stockName || base.name || symbol,
      logo: undefined,
      currentPrice: priceData.currentPrice,
      changePercent: priceData.changePercent,
      change: priceData.change,
      open: priceData.open,
      high: priceData.high,
      low: priceData.low,
      volume: priceData.volume,
      marketCap: base.marketCap || 0,
      previousClose: priceData.previousClose,
      pe: (base.pe || 0) + (Math.random() * 2 - 1),
      pbr: (base.pbr || 0) + (Math.random() * 0.2 - 0.1),
      description: base.description || "",
      sector: stockSector || base.sector || "",
      industry: stockIndustry || base.industry || "",
      timeSeries: timeSeries,
      candleData: candleData,
    };

    const response = {
      ...detail,
    };

    // Cache for 2 seconds (for real-time updates)
    cache.set(cacheKey, response, 2);
    return NextResponse.json(response);
  } catch (error) {
    console.error('Stock detail API error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch stock detail', detail: null },
      { status: 500 }
    );
  }
}

