"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CaretUp, CaretDown } from "phosphor-react";
import { PriceRow } from "./PriceRow";

interface PriceRowData {
  price?: number;
  sellQuantity?: number;
  buyQuantity?: number;
  type: "sell" | "buy";
}

interface PriceListProps {
  priceList: PriceRowData[];
  currentPrice: number | undefined;
  previousPrice: number | undefined;
  onPriceSelect?: (price: number) => void;
  formatPrice: (price: number) => string;
  percentChange: (price: number) => number;
  maxSellQty: number;
  maxBuyQty: number;
  formatQuantity: (quantity: number) => string;
  spread: number;
  midPrice: number;
  tickSize: number;
  previousClose: number;
  latestTradeType?: "buy" | "sell";
  latestTradePrice?: number;
}

export default function PriceList({
  priceList,
  currentPrice,
  previousPrice,
  onPriceSelect,
  formatPrice,
  percentChange,
  maxSellQty,
  maxBuyQty,
  formatQuantity,
  spread,
  midPrice,
  tickSize,
  previousClose,
  latestTradeType,
  latestTradePrice,
}: PriceListProps) {
  const [pulsingPrice, setPulsingPrice] = useState<number | undefined>(undefined);
  const [priceTick, setPriceTick] = useState<"up" | "down" | null>(null);
  const prevPriceRef = useRef<number | undefined>(undefined);

  // 표시 가격: 최근 체결가 우선, 없으면 currentPrice
  const boxPrice =
    typeof latestTradePrice === "number" && latestTradePrice > 0
      ? latestTradePrice
      : currentPrice;

  useEffect(() => {
    if (boxPrice && previousPrice !== undefined && boxPrice !== previousPrice) {
      setPulsingPrice(boxPrice);
      const timer = setTimeout(() => setPulsingPrice(undefined), 200);
      return () => clearTimeout(timer);
    }
  }, [boxPrice, previousPrice]);

  useEffect(() => {
    if (!boxPrice) return;
    if (prevPriceRef.current !== undefined && prevPriceRef.current !== boxPrice) {
      setPriceTick(boxPrice > prevPriceRef.current ? "up" : "down");
    }
    prevPriceRef.current = boxPrice;
  }, [boxPrice]);

  const sellRows = priceList.filter((row) => row.type === "sell");
  const buyRows = priceList.filter((row) => row.type === "buy");

  // 박스를 표시할 통합 인덱스 (0..sellRows.length-1 = 매도, sellRows.length.. = 매수)
  const targetIndex = useMemo(() => {
    if (!boxPrice || boxPrice <= 0) return -1;
    const allRows = [...sellRows, ...buyRows];

    // 1차: 가격 정확 매칭
    const exact = allRows.findIndex(
      (r) => typeof r.price === "number" && Math.abs(r.price - boxPrice) < 1
    );
    if (exact >= 0) return exact;

    // 2차: 체결 type fallback
    // buy 체결 → 매도 1호가 (sellRows의 마지막 유효 행)
    if (latestTradeType === "buy") {
      for (let i = sellRows.length - 1; i >= 0; i--) {
        if (typeof sellRows[i].price === "number") return i;
      }
    }
    // sell 체결 → 매수 1호가 (buyRows의 첫 유효 행)
    if (latestTradeType === "sell") {
      for (let i = 0; i < buyRows.length; i++) {
        if (typeof buyRows[i].price === "number") return sellRows.length + i;
      }
    }
    return -1;
  }, [boxPrice, sellRows, buyRows, latestTradeType]);

  // 박스 색상: 체결 type 우선, 없으면 직전 가격 변동 방향
  const isUp = useMemo(() => {
    if (latestTradeType === "buy") return true;
    if (latestTradeType === "sell") return false;
    if (priceTick === "up") return true;
    if (priceTick === "down") return false;
    return boxPrice && previousClose ? boxPrice >= previousClose : true;
  }, [latestTradeType, priceTick, boxPrice, previousClose]);

  const boxColor = isUp
    ? { bg: "bg-red-500/15", text: "text-red-400" }
    : { bg: "bg-blue-500/15", text: "text-blue-400" };

  const boxPct = boxPrice ? percentChange(boxPrice) : 0;
  const isPulsing = pulsingPrice === boxPrice;

  // 각 행 렌더링 — targetIndex와 일치하면 박스, 아니면 일반 PriceRow
  const renderRow = (
    row: PriceRowData,
    indexInList: number,
    type: "sell" | "buy",
    globalIndex: number
  ) => {
    const isBoxRow = globalIndex === targetIndex && boxPrice && boxPrice > 0;

    if (isBoxRow) {
      return (
        <div key={`${type}-${indexInList}`} className="h-[36px] flex items-center px-1">
          <button
            type="button"
            onClick={() => onPriceSelect?.(boxPrice as number)}
            className={[
              "w-full h-full flex items-center justify-between px-3 rounded-md",
              "border-2 border-white transition-colors duration-150",
              boxColor.bg,
              isPulsing ? "animate-pulse" : "",
            ].join(" ")}
            style={isPulsing ? { animationDuration: "200ms" } : undefined}
          >
            <span className={`font-black text-sm tabular-nums tracking-tight ${boxColor.text}`}>
              {formatPrice(boxPrice as number)}
            </span>
            <div className={`flex items-center gap-1 text-[11px] font-bold ${boxColor.text}`}>
              {isUp ? <CaretUp size={11} weight="fill" /> : <CaretDown size={11} weight="fill" />}
              <span className="tabular-nums">
                {boxPct >= 0 ? "+" : ""}{boxPct.toFixed(2)}%
              </span>
            </div>
          </button>
        </div>
      );
    }

    if (typeof row.price !== "number") {
      return <div key={`${type}-${indexInList}`} className="h-[36px] px-3" />;
    }
    const pctChange = percentChange(row.price);
    const side = type === "sell" ? "ask" : "bid";
    return (
      <div key={`${type}-${indexInList}`} className="h-[36px] flex items-center px-3">
        <PriceRow
          price={row.price}
          changePct={pctChange}
          side={side}
          isCurrent={false}
          isPulsing={false}
          onPriceSelect={onPriceSelect}
          formatPrice={formatPrice}
        />
      </div>
    );
  };

  return (
    <div className="flex flex-col relative h-full" aria-live="polite" aria-atomic="true">
      <div>{sellRows.map((row, i) => renderRow(row, i, "sell", i))}</div>
      <div>
        {buyRows.map((row, i) => renderRow(row, i, "buy", sellRows.length + i))}
      </div>
    </div>
  );
}
