"use client";

interface PriceRow {
  price: number;
  sellQuantity?: number;
  buyQuantity?: number;
  type: "sell" | "buy" | "current";
}

interface BidVolumeProps {
  priceList: PriceRow[];
  maxBuyQty: number;
  formatQuantity: (quantity: number) => string;
}

export default function BidVolume({
  priceList,
  maxBuyQty,
  formatQuantity,
}: BidVolumeProps) {
  return (
    <div className="flex flex-col">
      <div>
        {priceList.map((row, index) => {
          if (row.type === "current" || !row.buyQuantity) return null;
          const pct = Math.min(
            100,
            Math.max(0, (row.buyQuantity / maxBuyQty) * 100)
          );
          return (
            <div
              key={`bid-bar-${index}`}
              className="relative h-[36px] flex items-center"
            >
              <div
                className="absolute right-0 top-1/2 -translate-y-1/2 h-[24px] bg-red-500/30 rounded-md"
                style={{ width: `${pct}%` }}
              />
              <div className="relative z-10 w-full text-left px-3 text-sm text-red-400 tabular-nums tracking-tight">
                {formatQuantity(row.buyQuantity)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
