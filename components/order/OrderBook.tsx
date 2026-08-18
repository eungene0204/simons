"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type OrderBookItem } from "@/lib/mock-stock-data";
import PriceList from "./PriceList";
import MarketSummary from "./MarketSummary";
import TradeList from "./TradeList";
import AskVolume from "./AskVolume";
import BidVolume from "./BidVolume";
import { getStaticVIPrices } from "@/lib/vi-price";
import {
  buildDisplayRows,
  ORDERBOOK_DEPTH,
  type DisplayPriceRow,
} from "@/lib/orderbook-display";
import { t } from "@/lib/i18n";

export interface MarketStats {
  open: number;
  high: number;
  low: number;
  volume: number;
  previousClose: number;
  week52High: number;
  week52Low: number;
}

interface OrderBookProps {
  symbol: string;
  currentPrice?: number;
  onPriceSelect?: (price: number) => void;
  marketStats?: MarketStats;
  previousClose?: number;
}

interface VIDisplay {
  upper: number;
  lower: number;
  referencePrice: number;
  triggeredPrice: number;
  kind: "static" | "dynamic";
  rate: number;
}

interface TradeExecution {
  price: number;
  quantity: number;
  type: "buy" | "sell";
  timestamp: Date;
}

export default function OrderBook({
  symbol,
  currentPrice,
  onPriceSelect,
  marketStats,
  previousClose: previousCloseProp,
}: OrderBookProps) {
  const [orderBookData, setOrderBookData] = useState<{
    sellOrders: OrderBookItem[];
    buyOrders: OrderBookItem[];
    vi?: VIDisplay | null;
    totalAskQty?: number;
    totalBidQty?: number;
  } | null>(null);
  const [isOrderBookLoading, setIsOrderBookLoading] = useState(true);
  const [orderBookError, setOrderBookError] = useState<string | null>(null);
  const [tradeStrength, setTradeStrength] = useState<number | null>(null);
  const [recentTrades, setRecentTrades] = useState<TradeExecution[]>([]);
  const [actualCurrentPrice, setActualCurrentPrice] = useState<
    number | undefined
  >(currentPrice);
  const [previousPrice, setPreviousPrice] = useState<number | undefined>(
    undefined
  );

  // 호가 단위에 맞춰 가격 조정
  const roundToTick = (price: number): number => {
    const getTickSize = (p: number): number => {
      if (p < 1000) return 1;
      if (p < 5000) return 5;
      if (p < 10000) return 10;
      if (p < 50000) return 50;
      if (p < 100000) return 100;
      if (p < 500000) return 500;
      return 1000;
    };
    const tickSize = getTickSize(price);
    return Math.floor(price / tickSize) * tickSize;
  };

  const syncDisplayedPrice = useCallback((nextPrice?: number) => {
    if (!nextPrice || nextPrice <= 0) return;
    const roundedPrice = roundToTick(nextPrice);
    setActualCurrentPrice((prev) => {
      if (prev === roundedPrice) return prev;
      setPreviousPrice(prev);
      return roundedPrice;
    });
  }, []);

  useEffect(() => {
    if (!symbol) {
      setOrderBookData(null);
      setIsOrderBookLoading(false);
      setOrderBookError(null);
      setTradeStrength(null);
      setRecentTrades([]);
      setActualCurrentPrice(undefined);
      setPreviousPrice(undefined);
      return;
    }
    setOrderBookData(null);
    setIsOrderBookLoading(true);
    setOrderBookError(null);
    setTradeStrength(null);
    setRecentTrades([]);
    setActualCurrentPrice(undefined);
    setPreviousPrice(undefined);
  }, [symbol]);

  // prop 값을 ref에 보관 — SSE useEffect가 prop 변화로 재실행되어 끊기는 것 방지
  const currentPriceRef = useRef<number | undefined>(currentPrice);
  useEffect(() => {
    currentPriceRef.current = currentPrice;
  }, [currentPrice]);

  // 최초 prop 값으로 초기 박스 표시 (stream 연결 전 fallback)
  useEffect(() => {
    if (!symbol || !currentPrice || currentPrice <= 0) return;
    syncDisplayedPrice(currentPrice);
    // symbol만 의존성에 둔다 — currentPrice 변화로는 재실행하지 않음
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  useEffect(() => {
    if (!symbol) return;
    let isCancelled = false;
    let pollInterval: ReturnType<typeof setInterval> | null = null;
    let eventSource: EventSource | null = null;

    const applyOrderbookData = (data: any) => {
      if (isCancelled) return;
      // 우선순위: 가장 최근 체결가(recentTrades[0]) → stream currentPrice → prop fallback
      const tradePrice =
        Array.isArray(data.recentTrades) && data.recentTrades.length > 0
          ? Number(data.recentTrades[0]?.price) || 0
          : 0;
      const streamPrice = Number(data.currentPrice) || 0;
      const propPrice = currentPriceRef.current && currentPriceRef.current > 0
        ? currentPriceRef.current
        : 0;
      const resolvedPrice =
        tradePrice > 0 ? tradePrice :
        streamPrice > 0 ? streamPrice :
        propPrice > 0 ? propPrice :
        undefined;

      syncDisplayedPrice(resolvedPrice);
      setOrderBookData({
        sellOrders: Array.isArray(data.sellOrders) ? data.sellOrders : [],
        buyOrders: Array.isArray(data.buyOrders) ? data.buyOrders : [],
        vi: data.vi ?? null,
        totalAskQty: typeof data.totalAskQty === "number" ? data.totalAskQty : undefined,
        totalBidQty: typeof data.totalBidQty === "number" ? data.totalBidQty : undefined,
      });
      setRecentTrades(
        Array.isArray(data.recentTrades)
          ? data.recentTrades
              .map((trade: any) => ({
                price: Number(trade.price) || 0,
                quantity: Number(trade.quantity) || 0,
                type: trade.type === "sell" ? "sell" : "buy",
                timestamp: new Date(
                  typeof trade.timestamp === "number"
                    ? trade.timestamp * 1000
                    : trade.timestamp
                ),
              }))
              .filter((trade: TradeExecution) => trade.price > 0 && trade.quantity > 0)
          : []
      );
      setTradeStrength(
        typeof data.tradeStrength === "number" && Number.isFinite(data.tradeStrength)
          ? data.tradeStrength
          : null
      );
      setOrderBookError(null);
      setIsOrderBookLoading(false);
    };

    const loadOrderbook = async () => {
      // 백그라운드 탭에서는 250ms 폴백 폴링을 쉬게 한다(화면에 보이지 않는 데이터).
      if (document.hidden) return;
      try {
        const res = await fetch(`/api/stock/${symbol}/orderbook`, { cache: "no-store" });
        if (!res.ok) {
          const errorBody = await res.json().catch(() => null);
          throw new Error(errorBody?.detail || errorBody?.error || "orderbook fetch failed");
        }
        const data = await res.json();
        applyOrderbookData(data);
      } catch (error) {
        if (isCancelled) return;
        setOrderBookError(error instanceof Error ? error.message : t("실제 호가 데이터를 아직 받지 못했습니다"));
      } finally {
        if (!isCancelled) {
          setIsOrderBookLoading(false);
        }
      }
    };

    const startPolling = () => {
      if (pollInterval) return;
      loadOrderbook();
      pollInterval = setInterval(loadOrderbook, 250);
    };

    if (typeof EventSource !== "undefined") {
      eventSource = new EventSource(`/api/stock/${symbol}/orderbook-stream`);
      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data?.error) {
          setOrderBookError(data.error);
          setIsOrderBookLoading(false);
          return;
        }
        applyOrderbookData(data);
      };
      eventSource.onerror = () => {
        eventSource?.close();
        eventSource = null;
        startPolling();
      };
    } else {
      startPolling();
    }

    return () => {
      isCancelled = true;
      if (eventSource) eventSource.close();
      if (pollInterval) clearInterval(pollInterval);
    };
    // symbol만 의존성 — currentPrice는 ref로 읽으므로 재실행 불필요
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const formatQuantity = (quantity: number) => {
    return new Intl.NumberFormat("ko-KR").format(quantity);
  };

  if (!symbol) {
    return (
      <div className="bg-[var(--background)] p-4 h-full flex items-center justify-center">
        <div className="text-center py-8">
          <p className="text-base text-gray-500 dark:text-gray-400">
            {t("종목을 선택하면 호가가 표시됩니다")}
          </p>
        </div>
      </div>
    );
  }

  if (isOrderBookLoading) {
    return (
      <div className="bg-[var(--background)] p-4 h-full flex items-center justify-center">
        <div className="text-center py-8">
          <p className="text-base text-gray-500 dark:text-gray-400">{t("호가 정보 불러오는중...")}</p>
        </div>
      </div>
    );
  }

  const sellOrders = orderBookData?.sellOrders ?? [];
  const buyOrders = orderBookData?.buyOrders ?? [];
  const vi = orderBookData?.vi;
  // 화면에 보이는 10단계 합계가 아니라 거래소가 알려주는 "전체 잔량"이 우선
  const totalSellVolume = orderBookData?.totalAskQty ?? sellOrders.reduce(
    (sum, order) => sum + order.quantity,
    0
  );
  const totalBuyVolume = orderBookData?.totalBidQty ?? buyOrders.reduce(
    (sum, order) => sum + order.quantity,
    0
  );
  const totalsSum = totalSellVolume + totalBuyVolume;
  const sellRatio = totalsSum > 0 ? (totalSellVolume / totalsSum) * 100 : 50;
  const buyRatio = totalsSum > 0 ? (totalBuyVolume / totalsSum) * 100 : 50;
  const maxSellQty = Math.max(...sellOrders.map((o) => o.quantity), 1);
  const maxBuyQty = Math.max(...buyOrders.map((o) => o.quantity), 1);

  // 전일 종가: 실제 데이터 우선, 없으면 현재가 기반 추정
  const previousClose = previousCloseProp
    ?? marketStats?.previousClose
    ?? (actualCurrentPrice ? actualCurrentPrice * 0.98 : 0);
  const percentChange = (priceValue: number) => {
    if (!previousClose || previousClose === 0) return 0;
    return ((priceValue - previousClose) / previousClose) * 100;
  };

  // 보조 지표: 실제 데이터 우선
  const base = actualCurrentPrice || 0;
  const upperLimit = Math.max(0, Math.round(previousClose * 1.3));
  const lowerLimit = Math.max(0, Math.round(previousClose * 0.7));
  const week52High = marketStats?.week52High ?? Math.max(0, Math.round(base * 1.045));
  const week52Low = marketStats?.week52Low ?? Math.max(0, Math.round(base * 0.255));
  const openPrice = marketStats?.open ?? Math.max(0, Math.round(base * 1.0));
  const highPrice = marketStats?.high ?? Math.max(0, Math.round(base * 1.045));
  const lowPrice = marketStats?.low ?? Math.max(0, Math.round(base * 0.978));
  const volumeTotal = marketStats?.volume ?? Math.round((totalBuyVolume + totalSellVolume) * 7.5);
  const yesterdayRatio = previousClose > 0
    ? ((base - previousClose) / previousClose) * 100
    : 0;
  const viReferencePrice = marketStats?.open && marketStats.open > 0
    ? marketStats.open
    : previousClose;
  const fallbackVI = getStaticVIPrices(viReferencePrice);
  const upVI = vi?.upper ?? fallbackVI.upVI;
  const downVI = vi?.lower ?? fallbackVI.downVI;

  // 가격 리스트 생성: 현재가와 무관하게 표시 깊이를 항상 10단으로 고정
  const sortedSellOrders = [...sellOrders].sort((a, b) => b.price - a.price);
  const sortedBuyOrders = [...buyOrders].sort((a, b) => b.price - a.price);

  const sellPriceList: DisplayPriceRow[] = buildDisplayRows(
    sortedSellOrders,
    "sell",
    ORDERBOOK_DEPTH
  );

  const buyPriceList: DisplayPriceRow[] = buildDisplayRows(
    sortedBuyOrders,
    "buy",
    ORDERBOOK_DEPTH
  );

  // 최종 가격 리스트: 매도(위) + 매수(아래) - 현재가는 PriceList에서 스티키로 중앙에 표시
  const priceList: DisplayPriceRow[] = [...sellPriceList, ...buyPriceList];

  const pricedSellRows = sellPriceList.filter(
    (row): row is DisplayPriceRow & { price: number } => typeof row.price === "number"
  );
  const pricedBuyRows = buyPriceList.filter(
    (row): row is DisplayPriceRow & { price: number } => typeof row.price === "number"
  );

  // 스프레드 계산 (최우선 매도 - 최우선 매수)
  const bestAsk =
    pricedSellRows.length > 0
      ? pricedSellRows[pricedSellRows.length - 1].price
      : null;
  const bestBid = pricedBuyRows.length > 0 ? pricedBuyRows[0].price : null;
  const spread = bestAsk && bestBid ? bestAsk - bestBid : 0;
  const midPrice =
    bestAsk && bestBid ? (bestAsk + bestBid) / 2 : actualCurrentPrice || 0;

  // 틱사이즈 계산
  const getTickSize = (p: number): number => {
    if (p < 1000) return 1;
    if (p < 5000) return 5;
    if (p < 10000) return 10;
    if (p < 50000) return 50;
    if (p < 100000) return 100;
    if (p < 500000) return 500;
    return 1000;
  };
  const tickSize = actualCurrentPrice ? getTickSize(actualCurrentPrice) : 1;
  const rowHeight = 36;
  const topSectionHeight = ORDERBOOK_DEPTH * rowHeight + 12;

  return (
    <section
      className={[
        "mx-auto w-full h-full flex flex-col",
        "bg-[var(--background)]",
        "text-gray-900 dark:text-gray-200",
        "overflow-hidden",
      ].join(" ")}
      aria-label="Order book"
    >
      {/* Header */}
      <div className="px-3 pt-3 pb-1 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {t("호가")}
        </h2>
        {bestAsk && bestBid ? (
          <div className="text-[11px] tabular-nums text-gray-400">
            {t("스프레드 ")}<span className="text-white">{formatPrice(spread)}</span>
            <span className="mx-1 text-gray-600">·</span>
            {t("중간 ")}<span className="text-white">{formatPrice(Math.round(midPrice))}</span>
          </div>
        ) : null}
      </div>


      {/* Order Book Content */}
      <div className="flex-1 overflow-y-auto orderbook-scrollbar px-3 pt-1 pb-3">
        <div
          className={[
            // 2x3 grid: 왼쪽상단(매도), 중앙(가격리스트-세로), 오른쪽상단(시세), 왼쪽하단(체결), 오른쪽하단(매수)
            "grid grid-cols-[1.1fr_1fr_1.1fr] grid-rows-[auto_auto]",
            "gap-0",
          ].join(" ")}
          style={{ gridTemplateRows: `${topSectionHeight}px minmax(0, 1fr)` }}
        >
          {/* 1️⃣ 왼쪽 상단: 매도 영역 (Ask Panel) */}
          <div className="px-3 pt-3 pb-0 flex flex-col overflow-hidden">
            <AskVolume
              priceList={sellPriceList}
              maxSellQty={maxSellQty}
              formatQuantity={formatQuantity}
            />
          </div>

          {/* 2️⃣ 중앙 (세로): 가격 리스트 영역 (Price List Panel) */}
          <div className="p-0 flex flex-col row-span-2 pt-3">
            <PriceList
              priceList={priceList}
              currentPrice={actualCurrentPrice}
              previousPrice={previousPrice}
              onPriceSelect={onPriceSelect}
              formatPrice={formatPrice}
              percentChange={percentChange}
              maxSellQty={maxSellQty}
              maxBuyQty={maxBuyQty}
              formatQuantity={formatQuantity}
              spread={spread}
              midPrice={midPrice}
              tickSize={tickSize}
              previousClose={previousClose}
              latestTradeType={recentTrades[0]?.type}
              latestTradePrice={recentTrades[0]?.price}
            />
          </div>

          {/* 3️⃣ 오른쪽 상단: 시세 요약 영역 (Market Summary Panel) */}
          <div className="p-0 flex flex-col pt-3 pb-0 min-h-0 overflow-hidden">
            <MarketSummary
              week52High={week52High}
              week52Low={week52Low}
              upperLimit={upperLimit}
              lowerLimit={lowerLimit}
              upVI={upVI}
              downVI={downVI}
              openPrice={openPrice}
              highPrice={highPrice}
              lowPrice={lowPrice}
              volumeTotal={volumeTotal}
              yesterdayRatio={yesterdayRatio}
              formatPrice={formatPrice}
              formatQuantity={formatQuantity}
            />
          </div>

          {/* 4️⃣ 왼쪽 하단: 체결 내역 영역 (Trade List Panel) */}
          <div className="pt-1 min-h-0 flex flex-col border-t border-gray-200 dark:border-gray-700">
            <TradeList
              tradeStrength={tradeStrength}
              recentTrades={recentTrades}
              formatPrice={formatPrice}
              formatQuantity={formatQuantity}
            />
          </div>

          {/* 5️⃣ 오른쪽 하단: 매수 영역 (Bid Panel) */}
          <div className="p-0 pb-2 pt-0 min-h-0 flex flex-col border-t border-gray-200 dark:border-gray-700">
            <BidVolume
              priceList={buyPriceList}
              maxBuyQty={maxBuyQty}
              formatQuantity={formatQuantity}
            />
          </div>
        </div>

        {/* 총잔량 푸터: 총매도 ━ 비율바 ━ 총매수 */}
        <div className="mt-2 px-1">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-[11px] tabular-nums">
            <div className="text-right text-blue-400">
              {t("판매대기 {0}", formatQuantity(totalSellVolume))}
            </div>
            <div className="text-[10px] text-gray-500">{t("잔량")}</div>
            <div className="text-left text-red-400">
              {t("구매대기 {0}", formatQuantity(totalBuyVolume))}
            </div>
          </div>
          <div className="mt-1 h-[6px] w-full overflow-hidden rounded-full bg-gray-800 flex">
            <div
              className="h-full bg-blue-500/70"
              style={{ width: `${sellRatio}%` }}
              aria-label={t("매도 비율 {0}%", sellRatio.toFixed(1))}
            />
            <div
              className="h-full bg-red-500/70"
              style={{ width: `${buyRatio}%` }}
              aria-label={t("매수 비율 {0}%", buyRatio.toFixed(1))}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
