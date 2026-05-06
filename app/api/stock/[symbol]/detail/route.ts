import { NextRequest, NextResponse } from 'next/server'
import { cache } from '@/lib/cache'
import { loadStockList } from '@/lib/krx-stocks'
import { fetchStockPriceSnapshots } from '@/lib/server/stock-prices'
import { prisma } from '@/lib/prisma'
import {
  buildStockInfoProfileFromDetail,
  hasStoredInfoProfile,
  persistStockInfoProfile,
  readStoredStockInfoProfile,
  type StockInfoProfileDetailResponse,
} from '@/app/api/stocks/profile-store'

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
  listingDate?: string;
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
  companyBasic?: Record<string, string | number | null> | null;
  summaryFinancials?: Record<string, string | number | null> | null;
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

interface MarketDetailResponse extends StockInfoProfileDetailResponse {
  symbol: string;
  name?: string;
  volume?: number;
  marketCap?: number;
  source?: string;
  profileSource?: string;
  listingDate?: string;
  description?: string;
  sector?: string;
  industry?: string;
  companyBasic?: Record<string, string | number | null> | null;
  summaryFinancials?: Record<string, string | number | null> | null;
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
const BACKEND_STOCK_DETAIL_TIMEOUT_MS = 5000;
const MARKET_CAP_CACHE_TTL_SECONDS = 60 * 60 * 6;

function pickPositiveNumber(...values: Array<number | undefined>): number {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return value;
    }
  }
  return 0;
}

function pickStockName(symbol: string, ...values: Array<string | undefined>): string | undefined {
  const normalizedSymbol = symbol.trim();

  for (const value of values) {
    if (typeof value !== "string") {
      continue;
    }

    const normalizedValue = value.trim();
    if (normalizedValue && normalizedValue !== normalizedSymbol) {
      return normalizedValue;
    }
  }

  return undefined;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ symbol: string }> | { symbol: string } }
) {
  try {
    const resolvedParams = await Promise.resolve(params);
    const symbol = resolvedParams.symbol;
    const useStockMetadataStore = process.env.NODE_ENV !== "test";

    // Check cache first
    const cacheKey = `stock:detail:${symbol}`;
    const cached = cache.get(cacheKey);
    if (cached) {
      console.log(`Returning cached stock detail for ${symbol}`);
      return NextResponse.json(cached);
    }

    console.log(`Generating stock detail for ${symbol}...`);


    // 한국 종목 목록에서 이름, 섹터, 업종 정보 가져오기
    let stockName = "";
    let stockSector = "";
    let stockMarket: "KOSPI" | "KOSDAQ" | undefined;
    const storedStock = useStockMetadataStore
      ? await prisma.stock.findUnique({
          where: { symbol },
          select: {
            name: true,
            market: true,
            sector: true,
            listingDate: true,
            profileSource: true,
            profileUpdatedAt: true,
          },
        }).catch(() => null)
      : null;
    const storedProfile = useStockMetadataStore
      ? await readStoredStockInfoProfile(symbol)
      : null;

    try {
      const koreaStocks = await loadStockList();
      const stock = koreaStocks.find((s) => s.symbol === symbol);
      if (stock) {
        stockName = stock.name;
        stockSector = stock.sector || "";
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
    const companyNameForLookup = pickStockName(
      symbol,
      stockName,
      storedStock?.name ?? undefined,
    );
    const hasPersistedInfo = hasStoredInfoProfile(
      storedProfile,
    );
    try {
      const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
      const detailUrl = new URL(`${BACKEND_URL}/market/stock-detail/${symbol}`);
      detailUrl.searchParams.set("include_profile", "false");
      detailUrl.searchParams.set("include_listing", storedStock?.listingDate ? "false" : "true");
      detailUrl.searchParams.set("include_public_info", hasPersistedInfo ? "false" : "true");
      if (companyNameForLookup) {
        detailUrl.searchParams.set("company_name", companyNameForLookup);
      }

      const detailRes = await fetch(detailUrl.toString(), {
        signal: AbortSignal.timeout(BACKEND_STOCK_DETAIL_TIMEOUT_MS),
        cache: "no-store",
      });
      if (detailRes.ok) {
        realDetail = await detailRes.json();
      }
    } catch {
      realDetail = null;
    }

    const marketCapCacheKey = `stock:detail:market-cap:${symbol}`;
    const cachedMarketCap = cache.get<number>(marketCapCacheKey) ?? undefined;
    const currentPrice = pickPositiveNumber(quote?.price, realLastClose);
    const previousClose = pickPositiveNumber(quote?.previousClose, realLastClose);
    const change = currentPrice - previousClose;
    const changePercent =
      quote?.changePercent ??
      (previousClose > 0 ? (change / previousClose) * 100 : 0);
    const resolvedMarketCap = pickPositiveNumber(
      realDetail?.marketCap,
      cachedMarketCap,
    );

    const resolvedPer = typeof realDetail?.per === "number" ? realDetail.per : undefined;
    const resolvedPbr = typeof realDetail?.pbr === "number" ? realDetail.pbr : undefined;
    const resolvedDebtRatio = typeof realDetail?.debtRatio === "number" ? realDetail.debtRatio : undefined;

    if (resolvedMarketCap > 0) {
      cache.set(marketCapCacheKey, resolvedMarketCap, MARKET_CAP_CACHE_TTL_SECONDS);
    }
    
    const resolvedName = pickStockName(
      symbol,
      storedStock?.name ?? undefined,
      stockName,
      realDetail?.name,
    ) || symbol;
    const resolvedMarket = stockMarket || (storedStock?.market as "KOSPI" | "KOSDAQ" | undefined);
    const resolvedDescription = realDetail?.description || "";
    const resolvedIndustry = realDetail?.industry || "";
    const resolvedSector = storedStock?.sector || realDetail?.sector || "";
    const resolvedListingDate = storedStock?.listingDate || realDetail?.listingDate || "";
    const resolvedCompanyBasic = storedProfile?.companyBasic ?? realDetail?.companyBasic ?? null;
    const resolvedSummaryFinancials = storedProfile?.summaryFinancials ?? realDetail?.summaryFinancials ?? null;
    const resolvedDebtRatioFromSummary =
      typeof resolvedSummaryFinancials?.debtRatio === "number"
        ? resolvedSummaryFinancials.debtRatio
        : undefined;
    const effectivePe = storedProfile?.pe ?? resolvedPer ?? null;
    const effectivePbr = storedProfile?.pbr ?? resolvedPbr ?? null;
    const effectiveDebtRatio = storedProfile?.debtRatio ?? resolvedDebtRatioFromSummary ?? resolvedDebtRatio ?? null;

    const detail: StockDetail = {
      symbol,
      name: resolvedName,
      market: resolvedMarket,
      isKospi200,
      logo: undefined,
      currentPrice,
      changePercent,
      change,
      open: pickPositiveNumber(quote?.open),
      high: pickPositiveNumber(quote?.high),
      low: pickPositiveNumber(quote?.low),
      volume: pickPositiveNumber(quote?.volume, realDetail?.volume),
      marketCap: resolvedMarketCap,
      previousClose,
      pe: effectivePe,
      pbr: effectivePbr,
      debtRatio: effectiveDebtRatio,
      week52High: realDetail?.week52High ?? null,
      week52HighDate: realDetail?.week52HighDate ?? null,
      week52HighChangePercent: realDetail?.week52HighChangePercent ?? null,
      week52Low: realDetail?.week52Low ?? null,
      week52LowDate: realDetail?.week52LowDate ?? null,
      week52LowChangePercent: realDetail?.week52LowChangePercent ?? null,
      newHighLowCode: realDetail?.newHighLowCode ?? null,
      isNew52WeekHigh: realDetail?.isNew52WeekHigh ?? false,
      isNew52WeekLow: realDetail?.isNew52WeekLow ?? false,
      description: resolvedDescription,
      sector: resolvedSector,
      industry: resolvedIndustry,
      companyBasic: resolvedCompanyBasic,
      summaryFinancials: resolvedSummaryFinancials,
      listingDate: resolvedListingDate,
      timeSeries: undefined,
      candleData: undefined,
      realLastClose: realLastClose ?? null,
    };

    if (useStockMetadataStore && !hasPersistedInfo) {
      try {
        const fetchedProfile = realDetail
          ? buildStockInfoProfileFromDetail(
              {
                symbol,
                name: stockName || storedStock?.name || undefined,
                market: resolvedMarket,
                sector: stockSector || storedStock?.sector || undefined,
              },
              realDetail,
            )
          : null;

        if (fetchedProfile) {
          await persistStockInfoProfile(
            {
              symbol,
              name: stockName || storedStock?.name || undefined,
              market: resolvedMarket,
              sector: stockSector || storedStock?.sector || undefined,
            },
            fetchedProfile,
          );
        }
      } catch (error) {
        console.error("Failed to persist stock info profile:", error);
      }
    } else if (useStockMetadataStore && !storedStock) {
      await prisma.stock.upsert({
        where: { symbol },
        create: {
          symbol,
          name: resolvedName,
          market: resolvedMarket ?? null,
          sector: resolvedSector || null,
          listingDate: resolvedListingDate || null,
          profileSource: storedProfile?.source || null,
          profileUpdatedAt: storedProfile?.updatedAt || null,
          updatedAt: new Date(),
        },
        update: {
          name: resolvedName,
          market: resolvedMarket ?? null,
          sector: resolvedSector || null,
          listingDate: resolvedListingDate || null,
          updatedAt: new Date(),
        },
      }).catch((error) => {
        console.error("Failed to persist stock seed metadata:", error);
      });
    }

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
