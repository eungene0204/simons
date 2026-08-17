"use client";

import { X } from "phosphor-react";
import type { StockPriceSnapshot as BatchQuoteItem } from "@/lib/stock-prices";
import { getStatusBadge, getStatusBadgeClasses } from "@/lib/listing-status";
import type { ListingStatusValue } from "@/lib/listing-status";
import { t } from "@/lib/i18n";

type DelistStatus = "delisted" | "warning" | null;

interface TrackedSymbolRowProps {
  symbol: string;
  name: string;
  quote?: Pick<BatchQuoteItem, "price" | "changePercent" | "volume">;
  hasHolding: boolean;
  delistStatus?: DelistStatus;
  listingStatus?: ListingStatusValue | string;
  onSelect: (symbol: string, name: string) => void;
  onRemove: (symbol: string) => void;
  formatPrice: (price: number) => string;
}

export default function TrackedSymbolRow({
  symbol,
  name,
  quote,
  hasHolding,
  delistStatus,
  listingStatus,
  onSelect,
  onRemove,
  formatPrice,
}: TrackedSymbolRowProps) {
  // listingStatus가 있으면 우선 사용, 없으면 delistStatus로 폴백
  const effectiveStatus = listingStatus ?? (
    delistStatus === "delisted" ? "DELISTED" :
    delistStatus === "warning"  ? "WARNING"  : "NORMAL"
  );
  const statusBadge = getStatusBadge(effectiveStatus);

  const hasPrice = !!quote && quote.price > 0;
  const changePercent = quote?.changePercent ?? 0;
  const changeColor = changePercent === 0 ? "text-white" : changePercent > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]";
  const changeLabel = changePercent === 0 ? "0.00%" : `${changePercent > 0 ? "+" : ""}${changePercent.toFixed(2)}%`;

  return (
    <div
      className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 items-center px-1 py-2.5 hover:bg-white/[0.02] transition-colors duration-150 group cursor-pointer"
      onClick={() => onSelect(symbol, name)}
    >
      <div className="flex items-center gap-2 min-w-0">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <p className="text-xs font-bold text-white truncate">{name}</p>
            {statusBadge && (
              <span className={`shrink-0 text-[9px] font-black tracking-wide px-1 py-0.5 rounded ${getStatusBadgeClasses(statusBadge.variant)}`}>
                {statusBadge.label}
              </span>
            )}
          </div>
          <p className="text-[10px] font-bold text-gray-500">{symbol}</p>
        </div>
      </div>
      <p className="text-xs font-bold text-right text-white tabular-nums">
        {hasPrice ? formatPrice(quote.price) : <span className="text-gray-600">-</span>}
      </p>
      <p
        className={`text-xs font-bold text-right tabular-nums ${
          hasPrice
            ? changeColor
            : "text-gray-600"
        }`}
      >
        {hasPrice ? changeLabel : "-"}
      </p>
      <p className="text-xs font-bold text-right text-gray-400 tabular-nums">
        {hasPrice ? quote.volume.toLocaleString("ko-KR") : <span className="text-gray-600">-</span>}
      </p>
      <div className="flex items-center justify-center text-center">
        {hasHolding ? (
          <span className="text-[10px] font-bold text-orange-400 bg-orange-400/10 px-1.5 py-0.5 rounded-md">
            {t("보유중")}
          </span>
        ) : (
          <span className="text-[10px] font-bold text-gray-600">{t("대기")}</span>
        )}
      </div>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onRemove(symbol);
        }}
        className="flex items-center justify-center text-gray-600 opacity-100 transition-all duration-200 hover:text-[var(--main-red)] lg:opacity-0 lg:group-hover:opacity-100"
        aria-label={t("{0} 추적 제거", name)}
        title={t("추적 제거")}
      >
        <X size={12} />
      </button>
    </div>
  );
}
