"use client";

import { useState, useEffect } from "react";
import {
  generateOrderBook,
  generateStockPriceData,
  getBasePrice,
  type OrderBookItem,
} from "@/lib/mock-stock-data";

// seeded PRNG — Math.random() 대신 심볼 기반 재현 가능한 난수
function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function symbolHash(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}
import PriceList from "./PriceList";
import MarketSummary from "./MarketSummary";
import TradeList from "./TradeList";
import AskVolume from "./AskVolume";
import BidVolume from "./BidVolume";

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
}

interface TradeExecution {
  price: number;
  quantity: number;
  type: "buy" | "sell";
  timestamp: Date;
}

interface PriceRow {
  price: number;
  sellQuantity?: number;
  buyQuantity?: number;
  type: "sell" | "buy" | "current";
}

export default function OrderBook({
  symbol,
  currentPrice,
  onPriceSelect,
  marketStats,
}: OrderBookProps) {
  const [orderBookData, setOrderBookData] = useState<{
    sellOrders: OrderBookItem[];
    buyOrders: OrderBookItem[];
  } | null>(null);
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

  useEffect(() => {
    if (symbol) {
      // 현재가가 없으면 mock 데이터로 생성
      let price = currentPrice;
      if (!price) {
        const basePrice = getBasePrice(symbol);
        const priceData = generateStockPriceData(symbol, basePrice);
        price = priceData.currentPrice;
      }

      // 현재가를 호가 단위에 맞춰 조정
      const roundedPrice = roundToTick(price);
      setPreviousPrice(actualCurrentPrice);
      setActualCurrentPrice(roundedPrice);

      // 호가 데이터 생성
      const data = generateOrderBook(symbol, roundedPrice, 30);

      // 현재가가 호가에 포함되도록 수정
      const sellOrders = [...data.sellOrders];
      const buyOrders = [...data.buyOrders];

      const isInSellOrders = sellOrders.some(
        (order) => Math.abs(order.price - roundedPrice) < 1
      );
      const isInBuyOrders = buyOrders.some(
        (order) => Math.abs(order.price - roundedPrice) < 1
      );

      if (!isInSellOrders && !isInBuyOrders && roundedPrice) {
        const rngFallback = mulberry32(symbolHash(symbol) ^ Math.floor(Date.now() / 1000));
        const lowestSellPrice =
          sellOrders.length > 0
            ? Math.min(...sellOrders.map((o) => o.price))
            : roundedPrice + 1000;
        const highestBuyPrice =
          buyOrders.length > 0
            ? Math.max(...buyOrders.map((o) => o.price))
            : roundedPrice - 1000;

        if (roundedPrice >= (lowestSellPrice + highestBuyPrice) / 2) {
          sellOrders.push({
            price: roundedPrice,
            quantity: Math.floor(rngFallback() * 10000) + 1000,
          });
          sellOrders.sort((a, b) => b.price - a.price);
        } else {
          buyOrders.push({
            price: roundedPrice,
            quantity: Math.floor(rngFallback() * 10000) + 1000,
          });
          buyOrders.sort((a, b) => a.price - b.price);
        }
      }

      setOrderBookData({ sellOrders, buyOrders });

      // 최근 체결 내역 생성 (seeded PRNG 기반)
      const generateRecentTrades = (basePrice: number) => {
        const rng = mulberry32(symbolHash(symbol) ^ Math.floor(Date.now() / 60000));
        const trades: TradeExecution[] = [];
        for (let i = 0; i < 16; i++) {
          const priceOffset = (rng() - 0.5) * basePrice * 0.01;
          const tradePrice = Math.round(basePrice + priceOffset);
          const quantity = Math.floor(rng() * 500) + 1;
          const type = rng() > 0.5 ? "buy" : "sell";
          trades.push({
            price: tradePrice,
            quantity,
            type,
            timestamp: new Date(Date.now() - i * 1000),
          });
        }
        return trades;
      };

      if (price) {
        setRecentTrades(generateRecentTrades(price));
      }

      const interval = setInterval(() => {
        let updatedPrice = price;
        if (!currentPrice) {
          const basePrice = getBasePrice(symbol);
          const priceData = generateStockPriceData(symbol, basePrice);
          updatedPrice = priceData.currentPrice;
        }

        const roundedUpdatedPrice = roundToTick(updatedPrice);
        setPreviousPrice(actualCurrentPrice);
        setActualCurrentPrice(roundedUpdatedPrice);

        const updatedData = generateOrderBook(symbol, roundedUpdatedPrice, 30);
        const sellOrders = [...updatedData.sellOrders];
        const buyOrders = [...updatedData.buyOrders];

        if (roundedUpdatedPrice) {
          const isInSellOrders = sellOrders.some(
            (order) => Math.abs(order.price - roundedUpdatedPrice) < 1
          );
          const isInBuyOrders = buyOrders.some(
            (order) => Math.abs(order.price - roundedUpdatedPrice) < 1
          );

          if (!isInSellOrders && !isInBuyOrders) {
            const rngFallback = mulberry32(symbolHash(symbol) ^ Math.floor(Date.now() / 1000));
            const lowestSellPrice =
              sellOrders.length > 0
                ? Math.min(...sellOrders.map((o) => o.price))
                : roundedUpdatedPrice + 1000;
            const highestBuyPrice =
              buyOrders.length > 0
                ? Math.max(...buyOrders.map((o) => o.price))
                : roundedUpdatedPrice - 1000;

            if (
              roundedUpdatedPrice >=
              (lowestSellPrice + highestBuyPrice) / 2
            ) {
              sellOrders.push({
                price: roundedUpdatedPrice,
                quantity: Math.floor(rngFallback() * 10000) + 1000,
              });
              sellOrders.sort((a, b) => b.price - a.price);
            } else {
              buyOrders.push({
                price: roundedUpdatedPrice,
                quantity: Math.floor(rngFallback() * 10000) + 1000,
              });
              buyOrders.sort((a, b) => a.price - b.price);
            }
          }
        }

        setOrderBookData({ sellOrders, buyOrders });

        if (roundedUpdatedPrice) {
          const rng = mulberry32(symbolHash(symbol) ^ Math.floor(Date.now() / 1000));
          const newTrade: TradeExecution = {
            price: Math.round(roundedUpdatedPrice + (rng() - 0.5) * roundedUpdatedPrice * 0.01),
            quantity: Math.floor(rng() * 500) + 1,
            type: rng() > 0.5 ? "buy" : "sell",
            timestamp: new Date(),
          };
          setRecentTrades((prev) => [newTrade, ...prev.slice(0, 15)]);
        }
      }, 1000);

      return () => clearInterval(interval);
    } else {
      setOrderBookData(null);
      setRecentTrades([]);
    }
  }, [symbol, currentPrice]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const formatQuantity = (quantity: number) => {
    return new Intl.NumberFormat("ko-KR").format(quantity);
  };

  if (!symbol) {
    return (
      <div className="bg-[#1a1a1a] p-4 rounded-lg border border-gray-800 h-full flex items-center justify-center">
        <div className="text-center py-8">
          <p className="text-base text-gray-500 dark:text-gray-400">
            종목을 선택하면 호가가 표시됩니다
          </p>
        </div>
      </div>
    );
  }

  if (!orderBookData) {
    return (
      <div className="bg-[#1a1a1a] p-4 rounded-lg border border-gray-800 h-full flex items-center justify-center">
        <div className="text-center py-8">
          <p className="text-base text-gray-500 dark:text-gray-400">
            호가를 불러오는 중...
          </p>
        </div>
      </div>
    );
  }

  const { sellOrders, buyOrders } = orderBookData;
  const totalSellVolume = sellOrders.reduce(
    (sum, order) => sum + order.quantity,
    0
  );
  const totalBuyVolume = buyOrders.reduce(
    (sum, order) => sum + order.quantity,
    0
  );
  const maxSellQty = Math.max(...sellOrders.map((o) => o.quantity), 1);
  const maxBuyQty = Math.max(...buyOrders.map((o) => o.quantity), 1);

  // 전일 종가: 실제 데이터 우선, 없으면 현재가 기반 추정
  const previousClose = marketStats?.previousClose ?? (actualCurrentPrice ? actualCurrentPrice * 0.98 : 0);
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
  const tradeStrength = (totalBuyVolume / Math.max(1, totalSellVolume)) * 100;

  // 상승VI / 하강VI (±10% from 전일종가, 한국 동적VI 기준)
  const upVI = Math.round(previousClose * 1.1);
  const downVI = Math.round(previousClose * 0.9);

  // 가격 리스트 생성: 현재가를 중심으로 위=매도, 아래=매수
  const sortedSellOrders = [...sellOrders].sort((a, b) => b.price - a.price);
  const sortedBuyOrders = [...buyOrders].sort((a, b) => b.price - a.price);

  // 현재가를 기준으로 매도(위)와 매수(아래) 분리
  // 현재가는 항상 중앙에 위치하며, 매도 중 가장 낮은 가격 = 매수 중 가장 높은 가격
  const sellPriceList: PriceRow[] = sortedSellOrders
    .filter((order) => {
      if (!actualCurrentPrice) return true;
      // 현재가보다 높은 가격만 포함 (현재가는 제외)
      return order.price > actualCurrentPrice;
    })
    .slice(0, 10) // 정확히 10개
    .map((order) => ({
      price: order.price,
      sellQuantity: order.quantity,
      type: "sell" as const,
    }));

  const buyPriceList: PriceRow[] = sortedBuyOrders
    .filter((order) => {
      if (!actualCurrentPrice) return true;
      // 현재가보다 낮은 가격만 포함 (현재가는 제외)
      return order.price < actualCurrentPrice;
    })
    .slice(0, 10) // 정확히 10개
    .map((order) => ({
      price: order.price,
      buyQuantity: order.quantity,
      type: "buy" as const,
    }));

  // 최종 가격 리스트: 매도(위) + 매수(아래) - 현재가는 PriceList에서 스티키로 중앙에 표시
  const priceList: PriceRow[] = [...sellPriceList, ...buyPriceList];

  // 스프레드 계산 (최우선 매도 - 최우선 매수)
  const bestAsk =
    sellPriceList.length > 0
      ? sellPriceList[sellPriceList.length - 1].price
      : null;
  const bestBid = buyPriceList.length > 0 ? buyPriceList[0].price : null;
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

  return (
    <section
      className={[
        "mx-auto w-full h-full flex flex-col",
        "rounded-2xl",
        "bg-[#1a1a1a] shadow-lg border border-gray-800",
        "text-gray-900 dark:text-gray-200",
        "overflow-hidden",
      ].join(" ")}
      aria-label="Order book"
    >
      {/* Header */}
      <div className="px-3 pt-3 pb-1">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          호가
        </h2>
      </div>

      {/* Order Book Content */}
      <div className="flex-1 overflow-y-auto thin-scrollbar px-3 pt-1 pb-3">
        <div
          className={[
            // 2x3 grid: 왼쪽상단(매도), 중앙(가격리스트-세로), 오른쪽상단(시세), 왼쪽하단(체결), 오른쪽하단(매수)
            "grid grid-cols-[1.1fr_1fr_1.1fr] grid-rows-[auto_auto]",
            "gap-0",
            "rounded-xl",
          ].join(" ")}
        >
          {/* 1️⃣ 왼쪽 상단: 매도 영역 (Ask Panel) */}
          <div className="px-3 pt-3 pb-1 flex flex-col">
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
            />
          </div>

          {/* 3️⃣ 오른쪽 상단: 시세 요약 영역 (Market Summary Panel) */}
          <div className="p-0 flex flex-col pt-3 pb-4">
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
          <div className="pt-1 flex flex-col border-t border-gray-200 dark:border-gray-700">
            <TradeList
              tradeStrength={tradeStrength}
              recentTrades={recentTrades}
              formatPrice={formatPrice}
              formatQuantity={formatQuantity}
            />
          </div>

          {/* 5️⃣ 오른쪽 하단: 매수 영역 (Bid Panel) */}
          <div className="p-0 pb-2 pt-0 -mt-1 flex flex-col border-t border-gray-200 dark:border-gray-700">
            <BidVolume
              priceList={buyPriceList}
              maxBuyQty={maxBuyQty}
              formatQuantity={formatQuantity}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
