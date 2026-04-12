import { NextRequest, NextResponse } from 'next/server'
import { cache } from '@/lib/cache'
import { loadStockList } from '@/lib/krx-stocks'
import { getBasePrice, generateStockPriceData, generateCandleData, generateTimeSeries } from '@/lib/mock-stock-data'
import { fetchStockPriceSnapshots } from '@/lib/server/stock-prices'

interface StockDetail {
  symbol: string;
  name: string;
  market?: "KOSPI" | "KOSDAQ";
  isKospi200?: boolean;
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
  pe: number | null;
  pbr: number | null;
  debtRatio?: number | null;
  week52High?: number | null;
  week52HighDate?: string | null;
  week52HighChangePercent?: number | null;
  week52Low?: number | null;
  week52LowDate?: string | null;
  week52LowChangePercent?: number | null;
  newHighLowCode?: string | null;
  isNew52WeekHigh?: boolean;
  isNew52WeekLow?: boolean;
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
  realLastClose?: number | null;
}

interface MarketDetailResponse {
  symbol: string;
  name?: string;
  volume?: number;
  marketCap?: number;
  source?: string;
  per?: number;
  pbr?: number;
  debtRatio?: number | null;
  week52High?: number | null;
  week52HighDate?: string | null;
  week52HighChangePercent?: number | null;
  week52Low?: number | null;
  week52LowDate?: string | null;
  week52LowChangePercent?: number | null;
  newHighLowCode?: string | null;
  isNew52WeekHigh?: boolean;
  isNew52WeekLow?: boolean;
}

const DETAIL_CACHE_TTL_SECONDS = 2;
const MARKET_CAP_CACHE_TTL_SECONDS = 60 * 60 * 6;

function pickPositiveNumber(...values: Array<number | undefined>): number {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return value;
    }
  }
  return 0;
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

    console.log(`Generating stock detail for ${symbol}...`);

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
    let stockMarket: "KOSPI" | "KOSDAQ" | undefined;
    try {
      const koreaStocks = await loadStockList();
      const stock = koreaStocks.find((s) => s.symbol === symbol);
      if (stock) {
        stockName = stock.name;
        stockSector = stock.sector || "";
        stockIndustry = stock.industry || "";
        stockMarket = stock.market;
      }
    } catch (error) {
      console.error("Failed to load stock list:", error);
    }

    let isKospi200 = false;
    try {
      const fs = await import("fs/promises");
      const path = await import("path");
      const cachePath = path.join(process.cwd(), "data", "kospi200-cache.json");
      const raw = await fs.readFile(cachePath, "utf-8");
      const parsed = JSON.parse(raw) as { symbols?: string[] };
      isKospi200 = Array.isArray(parsed.symbols) && parsed.symbols.includes(symbol);
    } catch {
      isKospi200 = false;
    }

    // 파케이 실제 lastClose 조회 (백엔드 가용 시 우선 사용)
    let realLastClose: number | undefined;
    try {
      const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
      const ohlcvRes = await fetch(`${BACKEND_URL}/stock/${symbol}/ohlcv?limit=2`, {
        signal: AbortSignal.timeout(800),
      });
      if (ohlcvRes.ok) {
        const ohlcvData = await ohlcvRes.json();
        realLastClose = ohlcvData.lastClose;
      }
    } catch { /* 백엔드 미실행 시 무시 */ }

    const priceSnapshots = await fetchStockPriceSnapshots([symbol], {
      subscribe: true,
      mode: "realtime",
    });
    const quote = priceSnapshots[symbol];

    let realDetail: MarketDetailResponse | null = null;
    try {
      const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
      const detailRes = await fetch(`${BACKEND_URL}/market/stock-detail/${symbol}`, {
        signal: AbortSignal.timeout(1500),
        cache: "no-store",
      });
      if (detailRes.ok) {
        realDetail = await detailRes.json();
      }
    } catch {
      realDetail = null;
    }

    const base = baseData[symbol] || {};
    const marketCapCacheKey = `stock:detail:market-cap:${symbol}`;
    const cachedMarketCap = cache.get<number>(marketCapCacheKey) ?? undefined;
    const basePrice =
      realLastClose ||
      quote?.price ||
      base.currentPrice ||
      getBasePrice(symbol);
    const priceData = generateStockPriceData(symbol, basePrice);
    const currentPrice = pickPositiveNumber(quote?.price, priceData.currentPrice);
    const previousClose = pickPositiveNumber(quote?.previousClose, priceData.previousClose);
    const change = currentPrice - previousClose;
    const changePercent =
      quote?.changePercent ??
      (previousClose > 0 ? (change / previousClose) * 100 : priceData.changePercent);
    const resolvedMarketCap = pickPositiveNumber(
      realDetail?.marketCap,
      cachedMarketCap,
      base.marketCap,
    );

    const resolvedPer = typeof realDetail?.per === "number" ? realDetail.per : undefined;
    const resolvedPbr = typeof realDetail?.pbr === "number" ? realDetail.pbr : undefined;
    const resolvedDebtRatio = typeof realDetail?.debtRatio === "number" ? realDetail.debtRatio : undefined;

    if (resolvedMarketCap > 0) {
      cache.set(marketCapCacheKey, resolvedMarketCap, MARKET_CAP_CACHE_TTL_SECONDS);
    }
    
    // 캔들 데이터 생성
    const candleData = generateCandleData(symbol, basePrice, 365);
    const timeSeries = generateTimeSeries(symbol, basePrice, 365);

    const detail: StockDetail = {
      symbol,
      name: realDetail?.name || stockName || base.name || symbol,
      market: stockMarket,
      isKospi200,
      logo: undefined,
      currentPrice,
      changePercent,
      change,
      open: pickPositiveNumber(quote?.open, priceData.open),
      high: pickPositiveNumber(quote?.high, priceData.high),
      low: pickPositiveNumber(quote?.low, priceData.low),
      volume: pickPositiveNumber(quote?.volume, realDetail?.volume, base.volume),
      marketCap: resolvedMarketCap,
      previousClose,
      pe: resolvedPer ?? null,
      pbr: resolvedPbr ?? null,
      debtRatio: resolvedDebtRatio ?? null,
      week52High: realDetail?.week52High ?? null,
      week52HighDate: realDetail?.week52HighDate ?? null,
      week52HighChangePercent: realDetail?.week52HighChangePercent ?? null,
      week52Low: realDetail?.week52Low ?? null,
      week52LowDate: realDetail?.week52LowDate ?? null,
      week52LowChangePercent: realDetail?.week52LowChangePercent ?? null,
      newHighLowCode: realDetail?.newHighLowCode ?? null,
      isNew52WeekHigh: realDetail?.isNew52WeekHigh ?? false,
      isNew52WeekLow: realDetail?.isNew52WeekLow ?? false,
      description: base.description || "",
      sector: stockSector || base.sector || "",
      industry: stockIndustry || base.industry || "",
      timeSeries: timeSeries,
      candleData: candleData,
      realLastClose: realLastClose ?? null,
    };

    const response = {
      ...detail,
    };

    // Cache for 2 seconds (for real-time updates)
    cache.set(cacheKey, response, DETAIL_CACHE_TTL_SECONDS);
    return NextResponse.json(response);
  } catch (error) {
    console.error('Stock detail API error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch stock detail', detail: null },
      { status: 500 }
    );
  }
}
