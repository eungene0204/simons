"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bank,
  ChartLineUp,
  MagnifyingGlass,
  TrendUp,
  X,
} from "phosphor-react";
import type { QuickSearchResponse } from "@/types/quick-search";

interface QuickSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type QuickSearchItem =
  | {
      id: string;
      kind: "stock";
      title: string;
      subtitle: string;
      href: string;
      icon: typeof TrendUp;
    }
  | {
      id: string;
      kind: "strategy";
      title: string;
      subtitle: string;
      href: string;
      icon: typeof ChartLineUp;
    }
  | {
      id: string;
      kind: "virtualAccount";
      title: string;
      subtitle: string;
      href: string;
      icon: typeof Bank;
    };

export default function QuickSearchModal({
  isOpen,
  onClose,
}: QuickSearchModalProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [stockResults, setStockResults] = useState<QuickSearchResponse["stocks"]>([]);
  const [strategyResults, setStrategyResults] = useState<QuickSearchResponse["strategies"]>([]);
  const [virtualAccountResults, setVirtualAccountResults] = useState<
    QuickSearchResponse["virtualAccounts"]
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (!isOpen) {
      setQuery("");
      setStockResults([]);
      setStrategyResults([]);
      setVirtualAccountResults([]);
      setError("");
      setLoading(false);
      setActiveIndex(0);
      return;
    }

    const focusTimer = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 0);

    return () => window.clearTimeout(focusTimer);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const trimmedQuery = query.trim();
    if (!trimmedQuery) {
      setStockResults([]);
      setStrategyResults([]);
      setVirtualAccountResults([]);
      setLoading(false);
      setError("");
      return;
    }

    let isCancelled = false;
    const debounceTimer = window.setTimeout(async () => {
      setLoading(true);
      setError("");

      try {
        const quickSearchResponse = await fetch(
          `/api/quick-search?q=${encodeURIComponent(trimmedQuery)}`
        );

        if (isCancelled) {
          return;
        }

        const quickJson = quickSearchResponse.ok
          ? ((await quickSearchResponse.json()) as QuickSearchResponse)
          : { stocks: [], strategies: [], virtualAccounts: [] };

        setStockResults(quickJson.stocks ?? []);
        setStrategyResults(quickJson.strategies ?? []);
        setVirtualAccountResults(quickJson.virtualAccounts ?? []);

        if (!quickSearchResponse.ok) {
          setError("검색 중 오류가 발생했습니다.");
        }
      } catch (searchError) {
        if (!isCancelled) {
          console.error("Quick search error:", searchError);
          setStockResults([]);
          setStrategyResults([]);
          setVirtualAccountResults([]);
          setError("검색 중 오류가 발생했습니다.");
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
          setActiveIndex(0);
        }
      }
    }, 250);

    return () => {
      isCancelled = true;
      window.clearTimeout(debounceTimer);
    };
  }, [isOpen, query]);

  const items = useMemo<QuickSearchItem[]>(() => {
    const stocks: QuickSearchItem[] = stockResults.map((stock) => ({
      id: `stock-${stock.symbol}`,
      kind: "stock",
      title: stock.name,
      subtitle: `${stock.symbol} · ${stock.region === "KR" ? stock.type : stock.region}`,
      href: `/stock-order?symbol=${encodeURIComponent(stock.symbol)}&name=${encodeURIComponent(stock.name)}`,
      icon: TrendUp,
    }));

    const strategies: QuickSearchItem[] = strategyResults.map((strategy) => ({
      id: `strategy-${strategy.id}`,
      kind: "strategy",
      title: strategy.name,
      subtitle: [strategy.strategyType, strategy.universe, strategy.description]
        .filter(Boolean)
        .join(" · "),
      href: `/analytics/${strategy.id}`,
      icon: ChartLineUp,
    }));

    const accounts: QuickSearchItem[] = virtualAccountResults.map((account) => ({
      id: `virtual-account-${account.id}`,
      kind: "virtualAccount",
      title: account.name,
      subtitle: [
        account.strategyName || "전략 미연결",
        account.tradingMode === "auto" ? "자동매매" : "수동매매",
      ].join(" · "),
      href: `/virtual-account/${account.id}`,
      icon: Bank,
    }));

    return [...stocks, ...strategies, ...accounts];
  }, [stockResults, strategyResults, virtualAccountResults]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (items.length === 0) {
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((current) => (current + 1) % items.length);
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((current) => (current - 1 + items.length) % items.length);
      }

      if (event.key === "Enter") {
        event.preventDefault();
        const selectedItem = items[activeIndex];
        if (selectedItem) {
          router.push(selectedItem.href);
          onClose();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, isOpen, items, onClose, router]);

  if (!isOpen) {
    return null;
  }

  const renderSection = (
    title: string,
    sectionItems: QuickSearchItem[],
    offset: number
  ) => {
    if (sectionItems.length === 0) {
      return null;
    }

    return (
      <section>
        <div className="mb-2 flex items-center justify-between px-2">
          <p className="text-[10px] font-black uppercase tracking-[0.24em] text-gray-500">
            {title}
          </p>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-gray-600">
            {sectionItems.length}개
          </p>
        </div>
        <div className="space-y-2">
          {sectionItems.map((item, index) => {
            const Icon = item.icon;
            const isActive = activeIndex === offset + index;

            return (
              <button
                key={item.id}
                type="button"
                onMouseEnter={() => setActiveIndex(offset + index)}
                onClick={() => {
                  router.push(item.href);
                  onClose();
                }}
                className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition-all ${
                  isActive
                    ? "border-sky-400/40 bg-sky-400/10 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]"
                    : "border-white/[0.06] bg-white/[0.03] hover:border-white/[0.12] hover:bg-white/[0.05]"
                }`}
              >
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04]">
                  <Icon size={18} className="text-sky-300" weight="fill" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-black text-white">
                      {item.title}
                    </p>
                    <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.16em] text-gray-500">
                      {item.kind === "stock"
                        ? "종목"
                        : item.kind === "strategy"
                          ? "전략"
                          : "가상계좌"}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs font-medium text-gray-500">
                    {item.subtitle}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </section>
    );
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center bg-black/72 px-4 py-[10vh] backdrop-blur-md">
      <div className="w-full max-w-3xl overflow-hidden rounded-[28px] border border-white/[0.08] bg-[#0c0c0d] shadow-2xl shadow-black/40">
        <div className="border-b border-white/[0.08] px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-black tracking-tight text-white">
                  Quick Search
                </h2>
                <span className="rounded-full border border-white/[0.08] bg-white/[0.04] px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.2em] text-gray-500">
                  /
                </span>
              </div>
              <p className="mt-1 text-xs font-medium text-gray-500">
                종목, 전략, 가상계정을 한 번에 찾습니다.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-white/[0.08] p-2 text-gray-500 transition-colors hover:border-white/[0.16] hover:text-white"
              aria-label="퀵서치 닫기"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="border-b border-white/[0.08] px-5 py-4">
          <div className="relative">
            <MagnifyingGlass
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
            />
            <input
              ref={inputRef}
              type="text"
              name="quick-search-query"
              inputMode="search"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="종목명, 전략명, 가상계좌명을 입력하세요"
              className="w-full rounded-2xl border border-white/[0.08] bg-white/[0.03] py-3 pl-10 pr-4 text-sm font-medium text-white placeholder:text-gray-600 outline-none transition-colors focus:border-sky-400/30 focus:bg-white/[0.05]"
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-gray-500">
              종목
            </span>
            <span className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-gray-500">
              전략
            </span>
            <span className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-gray-500">
              가상계좌
            </span>
          </div>
          {error && (
            <p className="mt-3 text-xs font-bold text-[var(--main-blue)]">
              {error}
            </p>
          )}
        </div>

        <div className="max-h-[60vh] overflow-y-auto px-4 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-sm text-gray-500">
              검색 중...
            </div>
          ) : !query.trim() ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <MagnifyingGlass size={22} className="text-gray-500" />
              </div>
              <p className="text-sm font-black text-white">검색어를 입력하세요</p>
              <p className="mt-1 text-xs text-gray-500">
                `/`로 열고, 방향키와 Enter로 바로 이동할 수 있습니다.
              </p>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <X size={22} className="text-gray-500" />
              </div>
              <p className="text-sm font-black text-white">
                검색 결과가 없습니다
              </p>
              <p className="mt-1 text-xs text-gray-500">
                다른 키워드로 다시 검색해보세요.
              </p>
            </div>
          ) : (
            <div className="space-y-5">
              {renderSection("Stocks", items.filter((item) => item.kind === "stock"), 0)}
              {renderSection(
                "Strategies",
                items.filter((item) => item.kind === "strategy"),
                items.filter((item) => item.kind === "stock").length
              )}
              {renderSection(
                "Virtual Accounts",
                items.filter((item) => item.kind === "virtualAccount"),
                items.filter((item) => item.kind !== "virtualAccount").length
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
