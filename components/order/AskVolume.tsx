"use client";

interface PriceRow {
  price: number;
  sellQuantity?: number;
  buyQuantity?: number;
  type: "sell" | "buy" | "current";
}

interface AskVolumeProps {
  priceList: PriceRow[];
  maxSellQty: number;
  formatQuantity: (quantity: number) => string;
}

export default function AskVolume({
  priceList,
  maxSellQty,
  formatQuantity,
}: AskVolumeProps) {
  return (
    <div className="flex flex-col">
      <div>
        {priceList.map((row, index) => {
          if (row.type === "current" || !row.sellQuantity) return null;
          const pct = Math.min(
            100,
            Math.max(0, (row.sellQuantity / maxSellQty) * 100)
          );
          return (
            <div
              key={`ask-bar-${index}`}
              className="relative h-[36px] flex items-center"
            >
              <div
                className="absolute left-0 top-1/2 -translate-y-1/2 h-[24px] bg-blue-600/30 rounded-md"
                style={{ width: `${pct}%` }}
              />
              <div className="relative z-10 w-full text-right px-3 text-sm text-blue-400 tabular-nums tracking-tight">
                {formatQuantity(row.sellQuantity)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
