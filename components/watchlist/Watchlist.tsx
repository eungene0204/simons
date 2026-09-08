"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  CaretUp,
  CaretDown,
  Star,
  MagnifyingGlass,
  X,
} from "phosphor-react";
import StockSearchModal from "@/components/stock/StockSearchModal";
import { addMultipleToWatchlist, removeFromWatchlist } from "@/lib/watchlist";
import { useWatchlistMarket } from "@/lib/hooks/useWatchlistMarket";
import { t } from "@/lib/i18n";
import { useRegionHref } from "@/lib/geo/useRegion";

// 관심종목 — UI_GUIDELINES §12 그리드 기반 테이블(행 보더 금지, divide + hover), flat 패널.
// 2026-09-08 이전에는 라이트 테마용 `<table>`·흰 카드·행마다 보더·파란 CTA가 남아 있었다.
const GRID_COLS = "grid-cols-[minmax(0,1fr)_110px_110px_110px_120px]";
const HEADER_CLASS = "text-xs font-bold uppercase tracking-widest text-[var(--text-label)]";

function directionClass(value: number): string {
  if (value > 0) return "text-[var(--main-red)]";
  if (value < 0) return "text-[var(--main-blue)]";
  return "text-white";
}

export default function Watchlist() {
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const router = useRouter();
  const regionHref = useRegionHref();
  const { items, loading, refetch } = useWatchlistMarket(3000);

  const handleAddToWatchlist = async (items: Array<{ symbol: string; name: string }>) => {
    const addedCount = await addMultipleToWatchlist(items);
    if (addedCount > 0) {
      await refetch();
      setIsSearchOpen(false);
    }
  };

  const handleRemoveFromWatchlist = async (symbol: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ok = await removeFromWatchlist(symbol);
    if (ok) {
      await refetch();
    }
  };

  const formatNumber = (value: number) => new Intl.NumberFormat("ko-KR").format(value);

  const header = (
    <div className="flex items-center justify-between px-5 py-4">
      <div className="flex items-center gap-2">
        <Star size={20} weight="fill" className="text-white" />
        <h1 className="text-base font-black text-white font-outfit">{t("관심종목")}</h1>
      </div>
      <button
        type="button"
        onClick={() => setIsSearchOpen(true)}
        className="flex items-center gap-2 rounded-xl bg-[var(--chat-accent)] px-4 py-2 text-sm font-black text-[var(--chat-accent-ink)] transition-colors hover:brightness-110 active:translate-y-[1px]"
      >
        <MagnifyingGlass size={16} weight="bold" />
        {t("종목 검색")}
      </button>
    </div>
  );

  if (loading) {
    return (
      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">
          {header}
          <div className="space-y-2 p-5 animate-pulse motion-reduce:animate-none">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 rounded-xl bg-white/[0.04]" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">
          {header}

          <div className="overflow-x-auto p-3">
            <div className="min-w-[640px]">
              {/* 헤더 행 */}
              <div className={`grid ${GRID_COLS} gap-2 px-2 mb-2`}>
                <span className={HEADER_CLASS}>{t("종목")}</span>
                <span className={`${HEADER_CLASS} text-right`}>{t("현재가")}</span>
                <span className={`${HEADER_CLASS} text-right`}>{t("등락률")}</span>
                <span className={`${HEADER_CLASS} text-right`}>{t("등락액")}</span>
                <span className={`${HEADER_CLASS} text-right`}>{t("거래량(주)")}</span>
              </div>
              <div className="border-t border-white/[0.05] mb-1" />

              {items.length === 0 ? (
                <div className="px-2 py-10 text-center">
                  <p className="text-sm font-bold text-gray-400">{t("관심종목이 없습니다.")}</p>
                  <button
                    type="button"
                    onClick={() => setIsSearchOpen(true)}
                    className="mt-3 text-xs font-bold text-[var(--chat-accent)] hover:underline"
                  >
                    {t("종목 검색")}
                  </button>
                </div>
              ) : (
                <div className="divide-y divide-white/[0.04]">
                  {items.map((item) => (
                    <div
                      key={item.symbol}
                      role="link"
                      tabIndex={0}
                      onClick={() => router.push(regionHref(`/stock/${item.symbol}`))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          router.push(regionHref(`/stock/${item.symbol}`));
                        }
                      }}
                      className={`grid ${GRID_COLS} items-center gap-2 rounded-xl px-2 py-3 transition-colors duration-150 hover:bg-white/[0.02] cursor-pointer`}
                    >
                      {/* 종목 (로고 + 이름) */}
                      <div className="flex min-w-0 items-center gap-2">
                        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-white/[0.06]">
                          {item.logo ? (
                            <img
                              src={item.logo}
                              alt={item.name}
                              className="h-8 w-8 rounded-full object-cover"
                            />
                          ) : (
                            <span className="text-xs font-bold text-gray-400">
                              {item.name.charAt(0)}
                            </span>
                          )}
                        </div>
                        <div className="flex min-w-0 flex-col">
                          <span className="truncate text-sm font-bold text-white">{item.name}</span>
                          <span className="text-xs font-bold text-[var(--text-label)]">{item.symbol}</span>
                        </div>
                        <button
                          type="button"
                          onClick={(e) => handleRemoveFromWatchlist(item.symbol, e)}
                          className="ml-auto rounded-md p-1.5 text-gray-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                          title={t("관심종목에서 제거")}
                          aria-label={t("관심종목에서 제거")}
                        >
                          <X size={16} />
                        </button>
                      </div>

                      {/* 현재가 */}
                      <span className={`text-right text-sm font-bold tabular-nums font-outfit ${directionClass(item.changePercent)}`}>
                        {formatNumber(item.currentPrice)}
                      </span>

                      {/* 등락률 */}
                      <div className={`flex items-center justify-end gap-0.5 ${directionClass(item.changePercent)}`}>
                        {item.changePercent > 0 ? (
                          <CaretUp size={10} weight="fill" />
                        ) : item.changePercent < 0 ? (
                          <CaretDown size={10} weight="fill" />
                        ) : null}
                        <span className="text-sm font-bold tabular-nums font-outfit">
                          {item.changePercent >= 0 ? "+" : ""}
                          {item.changePercent.toFixed(2)}%
                        </span>
                      </div>

                      {/* 등락액 */}
                      <span className={`text-right text-sm font-bold tabular-nums font-outfit ${directionClass(item.change)}`}>
                        {item.change >= 0 ? "+" : ""}
                        {formatNumber(item.change)}
                      </span>

                      {/* 거래량 */}
                      <span className="text-right text-xs font-bold tabular-nums text-gray-400">
                        {formatNumber(item.volume)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Stock Search Modal */}
      <StockSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelect={handleAddToWatchlist}
      />
    </>
  );
}
