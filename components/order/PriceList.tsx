"use client";

import { useEffect, useState } from "react";
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
}: PriceListProps) {
  const [pulsingPrice, setPulsingPrice] = useState<number | undefined>(undefined);

  // 가격 변화 감지 및 펄스 애니메이션 (150-250ms)
  useEffect(() => {
    if (currentPrice && previousPrice !== undefined && currentPrice !== previousPrice) {
      setPulsingPrice(currentPrice);
      const timer = setTimeout(() => setPulsingPrice(undefined), 200);
      return () => clearTimeout(timer);
    }
  }, [currentPrice, previousPrice]);

  // 매도와 매수 분리
  const sellRows = priceList.filter((row) => row.type === "sell");
  const buyRows = priceList.filter((row) => row.type === "buy");

  return (
    <div className="flex flex-col relative h-full" aria-live="polite" aria-atomic="true">
      {/* 매도 호가 (위) */}
      <div>
        {sellRows.map((row, index) => {
          if (typeof row.price !== "number") {
            return <div key={`sell-${index}`} className="h-[36px] px-3" />;
          }
          const pctChange = percentChange(row.price);
          const side = "ask";
          const isCurrent = currentPrice ? Math.abs(row.price - currentPrice) < 1 : false;
          const isPulsing = pulsingPrice === row.price && isCurrent;
          return (
            <div key={`sell-${index}`} className="h-[36px] flex items-center px-3">
              <PriceRow
                price={row.price}
                changePct={pctChange}
                side={side}
                isCurrent={isCurrent}
                isPulsing={isPulsing}
                onPriceSelect={onPriceSelect}
                formatPrice={formatPrice}
              />
            </div>
          );
        })}
      </div>

      {/* 매수 호가 (아래) */}
      <div>
        {buyRows.map((row, index) => {
          if (typeof row.price !== "number") {
            return <div key={`buy-${index}`} className="h-[36px] px-3" />;
          }
          const pctChange = percentChange(row.price);
          const side = "bid";
          const isCurrent = currentPrice ? Math.abs(row.price - currentPrice) < 1 : false;
          const isPulsing = pulsingPrice === row.price && isCurrent;
          return (
            <div key={`buy-${index}`} className="h-[36px] flex items-center px-3">
              <PriceRow
                price={row.price}
                changePct={pctChange}
                side={side}
                isCurrent={isCurrent}
                isPulsing={isPulsing}
                onPriceSelect={onPriceSelect}
                formatPrice={formatPrice}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
