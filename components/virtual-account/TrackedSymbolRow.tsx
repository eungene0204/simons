"use client";

import { X } from "phosphor-react";
import type { BatchQuoteItem } from "@/app/api/stock/batch-quotes/route";

interface TrackedSymbolRowProps {
  symbol: string;
  name: string;
  quote?: Pick<BatchQuoteItem, "price" | "changePercent" | "volume">;
  hasHolding: boolean;
  onSelect: (symbol: string, name: string) => void;
  onRemove: (symbol: string) => void;
  formatPrice: (price: number) => string;
}

export default function TrackedSymbolRow({
  symbol,
  name,
  quote,
  hasHolding,
  onSelect,
  onRemove,
  formatPrice,
}: TrackedSymbolRowProps) {
  const hasPrice = !!quote && quote.price > 0;
  const isUp = (quote?.changePercent ?? 0) >= 0;

  return (
    <div
      className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 items-center px-1 py-2.5 hover:bg-white/[0.02] transition-colors duration-150 group cursor-pointer"
      onClick={() => onSelect(symbol, name)}
    >
      <div className="flex items-center gap-2 min-w-0">
        <div className="min-w-0">
          <p className="text-xs font-bold text-white truncate">{name}</p>
          <p className="text-[10px] font-bold text-gray-500">{symbol}</p>
        </div>
      </div>
      <p className="text-xs font-bold text-right text-white tabular-nums">
        {hasPrice ? formatPrice(quote.price) : <span className="text-gray-600">-</span>}
      </p>
      <p
        className={`text-xs font-bold text-right tabular-nums ${
          hasPrice
            ? isUp
              ? "text-[var(--main-red)]"
              : "text-[var(--main-blue)]"
            : "text-gray-600"
        }`}
      >
        {hasPrice ? `${isUp ? "+" : ""}${quote.changePercent.toFixed(2)}%` : "-"}
      </p>
      <p className="text-xs font-bold text-right text-gray-400 tabular-nums">
        {hasPrice ? quote.volume.toLocaleString("ko-KR") : <span className="text-gray-600">-</span>}
      </p>
      <div className="flex justify-end">
        {hasHolding ? (
          <span className="text-[10px] font-bold text-[var(--main-blue)] bg-sky-400/10 px-1.5 py-0.5 rounded-md">
            보유중
          </span>
        ) : (
          <span className="text-[10px] font-bold text-gray-600">대기</span>
        )}
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRemove(symbol);
        }}
        className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-[var(--main-red)] transition-all duration-200 flex items-center justify-center"
        title="추적 제거"
      >
        <X size={12} />
      </button>
    </div>
  );
}
