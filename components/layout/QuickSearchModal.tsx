"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  Bank,
  ChartLineUp,
  MagnifyingGlass,
  TrendUp,
  ArrowUpRight,
  X,
  CaretUp,
  CaretDown,
  Minus,
} from "phosphor-react";
import type { QuickSearchResponse } from "@/types/quick-search";
import type { PopularStocksResponse } from "@/app/api/stock/popular/route"; // FALLBACK_POPULAR_STOCKS 타입용
import type { StockPriceSnapshot } from "@/lib/stock-prices";

interface QuickSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const RECENT_SEARCHES_KEY = "quick-search:recent";
const MAX_RECENT_SEARCHES = 5;

// 종목 심볼 → 브랜드 색상
const STOCK_AVATAR_COLORS: Record<string, string> = {
  "005930": "#1428A0", // 삼성전자
  "000660": "#E8231A", // SK하이닉스
  "373220": "#A50034", // LG에너지솔루션
  "005380": "#002C5F", // 현대차
  "068270": "#0057A8", // 셀트리온
  "035420": "#03C75A", // NAVER
  "035720": "#FFCD00", // 카카오
  "005490": "#005BAA", // POSCO홀딩스
  "105560": "#FFC220", // KB금융
  "207940": "#1560BD", // 삼성바이오로직스
};

// API 응답 전 또는 실패 시 표시할 정적 폴백
const FALLBACK_POPULAR_STOCKS: PopularStocksResponse["stocks"] = [
  { rank: 1, symbol: "005930", name: "삼성전자", changePercent: 0 },
  { rank: 2, symbol: "000660", name: "SK하이닉스", changePercent: 0 },
  { rank: 3, symbol: "373220", name: "LG에너지솔루션", changePercent: 0 },
  { rank: 4, symbol: "005380", name: "현대차", changePercent: 0 },
  { rank: 5, symbol: "068270", name: "셀트리온", changePercent: 0 },
];
const POPULAR_STOCKS = FALLBACK_POPULAR_STOCKS.map((stock) => ({
  symbol: stock.symbol,
  name: stock.name,
}));
const POPULAR_STREAM_URL = "/api/stock/popular-stream";
const POPULAR_QUERY_KEY = ["quick-search", "popular-stocks"] as const;

interface QuickSearchPopularStock {
  rank: number;
  symbol: string;
  name: string;
  changePercent: number | null;
}

interface PopularQueryData {
  stocks: QuickSearchPopularStock[];
  updatedAt: string;
}

function formatPopularUpdatedAt() {
  return new Date().toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  });
}

function createFallbackPopularResponse(): PopularQueryData {
  return {
    stocks: FALLBACK_POPULAR_STOCKS.map((stock) => ({
      ...stock,
      changePercent: null,
    })),
    updatedAt: "",
  };
}

function hasRealtimeSnapshot(snapshot?: StockPriceSnapshot) {
  return Boolean(snapshot && snapshot.price > 0);
}

interface PopularStreamQuote {
  close?: number;
  open?: number;
  prev_close?: number;
  change_rate?: number;
}

function toPopularSnapshots(
  payload: Record<string, PopularStreamQuote>
): Record<string, StockPriceSnapshot> {
  return Object.fromEntries(
    Object.entries(payload).map(([symbol, quote]) => {
      const price = quote.close ?? 0;

      if (price <= 0) {
        return [symbol, { price: 0, changePercent: 0, volume: 0 }];
      }

      const hasChangeRate =
        quote.change_rate !== undefined && quote.change_rate !== 0;
      const base =
        quote.prev_close && quote.prev_close > 0
          ? quote.prev_close
          : quote.open && quote.open > 0
            ? quote.open
            : null;

      // change_rate도 없고 base price도 없으면 등락률 계산 불가
      // → price=0으로 표시해 hasRealtimeSnapshot이 false가 되도록 해 이전 값 유지
      if (!hasChangeRate && base === null) {
        return [symbol, { price: 0, changePercent: 0, volume: 0 }];
      }

      const changePercent = hasChangeRate
        ? quote.change_rate!
        : Math.round(((price - base!) / base!) * 10000) / 100;

      return [
        symbol,
        {
          price,
          changePercent,
          volume: 0,
          open: quote.open,
          previousClose: quote.prev_close,
        },
      ];
    })
  );
}

export function mergePopularStocks(
  current: QuickSearchPopularStock[],
  snapshots: Record<string, StockPriceSnapshot> | undefined
): QuickSearchPopularStock[] {
  return POPULAR_STOCKS.map((stock, index) => {
    const snapshot = snapshots?.[stock.symbol];
    const previous = current.find((item) => item.symbol === stock.symbol);

    return {
      rank: index + 1,
      symbol: stock.symbol,
      name: stock.name,
      changePercent: hasRealtimeSnapshot(snapshot)
        ? snapshot.changePercent
        : previous?.changePercent ?? null,
    };
  });
}

function mergePopularStocksResponse(
  current: PopularQueryData | undefined,
  snapshots: Record<string, StockPriceSnapshot> | undefined
): PopularQueryData {
  const base = current ?? createFallbackPopularResponse();

  return {
    stocks: mergePopularStocks(base.stocks, snapshots),
    updatedAt: formatPopularUpdatedAt(),
  };
}

async function fetchPopularStocks(): Promise<PopularQueryData> {
  const response = await fetch("/api/stock/popular");

  if (!response.ok) {
    throw new Error("Failed to fetch popular stocks");
  }

  const json = (await response.json()) as PopularStocksResponse;

  return {
    stocks: json.stocks.map((stock) => ({
      ...stock,
      changePercent:
        typeof stock.changePercent === "number" ? stock.changePercent : null,
    })),
    updatedAt: json.updatedAt ?? "",
  };
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
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [stockResults, setStockResults] = useState<QuickSearchResponse["stocks"]>([]);
  const [strategyResults, setStrategyResults] = useState<QuickSearchResponse["strategies"]>([]);
  const [virtualAccountResults, setVirtualAccountResults] = useState<
    QuickSearchResponse["virtualAccounts"]
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const trimmedQuery = query.trim();
  const { data: popularData } = useQuery({
    queryKey: POPULAR_QUERY_KEY,
    queryFn: fetchPopularStocks,
    enabled: isOpen,
    placeholderData: (previousData) =>
      previousData ?? createFallbackPopularResponse(),
    staleTime: 1000,
    refetchOnWindowFocus: false,
  });

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

    try {
      const stored = window.localStorage.getItem(RECENT_SEARCHES_KEY);
      setRecentSearches(stored ? (JSON.parse(stored) as string[]) : []);
    } catch {
      setRecentSearches([]);
    }

    const focusTimer = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 0);

    return () => {
      window.clearTimeout(focusTimer);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    const eventSource = new EventSource(POPULAR_STREAM_URL);

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as Record<string, PopularStreamQuote>;
        const snapshots = toPopularSnapshots(payload);

        queryClient.setQueryData<PopularQueryData>(POPULAR_QUERY_KEY, (current) =>
          mergePopularStocksResponse(current, snapshots)
        );
      } catch (streamError) {
        console.error("Popular stream parse error:", streamError);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [isOpen, queryClient]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) {
        onClose();
      }
    };

    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

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
  }, [isOpen, trimmedQuery]);

  const incrementSearchCount = (symbol: string, name: string) => {
    fetch("/api/stock/popular", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, name }),
    }).catch(() => {});
  };

  const persistRecentSearch = (term: string) => {
    const normalized = term.trim();
    if (!normalized) {
      return;
    }

    setRecentSearches((current) => {
      const next = [
        normalized,
        ...current.filter((entry) => entry !== normalized),
      ].slice(0, MAX_RECENT_SEARCHES);

      try {
        window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
      } catch {}

      return next;
    });
  };

  const removeRecentSearch = (term: string) => {
    setRecentSearches((current) => {
      const next = current.filter((entry) => entry !== term);
      try {
        window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });
  };

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

  const groupedItems = useMemo(
    () => ({
      stocks: items.filter((item) => item.kind === "stock"),
      strategies: items.filter((item) => item.kind === "strategy"),
      virtualAccounts: items.filter((item) => item.kind === "virtualAccount"),
    }),
    [items]
  );

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
          persistRecentSearch(selectedItem.title);
          if (selectedItem.kind === "stock") {
            const stockResult = stockResults.find(
              (s) => `stock-${s.symbol}` === selectedItem.id
            );
            if (stockResult) {
              incrementSearchCount(stockResult.symbol, stockResult.name);
            }
          }
          router.push(selectedItem.href);
        }
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, isOpen, items, onClose, router]);

  if (!isOpen) {
    return null;
  }

  const stockCount = groupedItems.stocks.length;
  const strategyCount = groupedItems.strategies.length;
  const popularStocks = popularData?.stocks ?? createFallbackPopularResponse().stocks;
  const popularUpdatedAt = popularData?.updatedAt ?? "";

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
        <div className="space-y-0.5">
          {sectionItems.map((item, index) => {
            const Icon = item.icon;
            const isActive = activeIndex === offset + index;

            return (
              <button
                key={item.id}
                type="button"
                onMouseEnter={() => setActiveIndex(offset + index)}
                onClick={() => {
                  persistRecentSearch(item.title);
                  if (item.kind === "stock") {
                    const stockResult = stockResults.find(
                      (s) => `stock-${s.symbol}` === item.id
                    );
                    if (stockResult) {
                      incrementSearchCount(stockResult.symbol, stockResult.name);
                    }
                  }
                  router.push(item.href);
                  onClose();
                }}
                className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2 text-left transition-all ${
                  isActive
                    ? "border-sky-400/20 bg-sky-400/8"
                    : "border-transparent hover:bg-white/[0.04]"
                }`}
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/[0.06]">
                  <Icon size={14} className="text-sky-400" weight="fill" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-semibold text-white">
                      {item.title}
                    </p>
                    <span className="rounded-full border border-white/[0.06] bg-white/[0.03] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-gray-600">
                      {item.kind === "stock"
                        ? "종목"
                        : item.kind === "strategy"
                          ? "전략"
                          : "가상계좌"}
                    </span>
                  </div>
                  <p className="truncate text-xs text-gray-500">
                    {item.subtitle}
                  </p>
                </div>
                <ArrowUpRight size={13} className="shrink-0 text-gray-600" />
              </button>
            );
          })}
        </div>
      </section>
    );
  };

  return (
    <div
      className="fixed left-1/2 z-[70] -translate-x-1/2 px-3"
      style={{
        top: "calc(var(--top-menu-bar-height, 72px) + 8px)",
        width: "min(640px, calc(100vw - 24px))",
      }}
    >
      <div
        ref={panelRef}
        className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[#1e1f27]/95 shadow-[0_16px_48px_rgba(0,0,0,0.5)] backdrop-blur-2xl"
      >
        <div className="px-4 pb-3 pt-4">
          <div className="relative">
            <MagnifyingGlass
              size={18}
              className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500"
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
              placeholder="종목, 전략, 계좌, 백테스트를 검색하세요"
              className="w-full rounded-xl border border-white/0 bg-white/[0.06] py-2.5 pl-10 pr-10 text-sm font-bold text-white placeholder:text-gray-500 outline-none transition-colors focus:bg-white/[0.10]"
            />
            <button
              type="button"
              onClick={onClose}
              className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-white/[0.06] hover:text-white"
              aria-label="퀵서치 닫기"
            >
              <X size={14} />
            </button>
          </div>
          {error && (
            <p className="mt-2 text-xs font-bold text-[var(--main-blue)]">
              {error}
            </p>
          )}
        </div>

        <div className="h-[380px] overflow-y-auto px-4 pb-4 pt-1">
          {loading ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-500">
              검색 중...
            </div>
          ) : !query.trim() ? (
            <div className="space-y-4 py-2">
              {/* 최근 검색 */}
              <section>
                <div className="mb-2.5 flex items-center justify-between">
                  <h3 className="text-xs font-black uppercase tracking-widest text-gray-500">
                    최근 검색
                  </h3>
                </div>
                {recentSearches.length === 0 ? (
                  <p className="text-sm font-medium text-gray-500">
                    아직 최근 검색이 없습니다.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {recentSearches.map((recent) => (
                      <div
                        key={recent}
                        className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.06] px-4 py-2"
                      >
                        <button
                          type="button"
                          onClick={() => setQuery(recent)}
                          className="text-sm font-bold text-gray-100"
                        >
                          {recent}
                        </button>
                        <button
                          type="button"
                          onClick={() => removeRecentSearch(recent)}
                          className="text-gray-500 transition-colors hover:text-gray-200"
                          aria-label={`${recent} 최근 검색 삭제`}
                        >
                          <X size={13} weight="bold" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* 인기 검색 */}
              <section>
                <div className="mb-2.5 flex items-center justify-between">
                  <h3 className="text-xs font-black uppercase tracking-widest text-gray-500">
                    인기 검색
                  </h3>
                  {popularUpdatedAt && (
                    <p className="text-[10px] font-medium text-gray-600">
                      {popularUpdatedAt} 업데이트
                    </p>
                  )}
                </div>
                <div className="space-y-0.5">
                  {popularStocks.map((stock) => {
                    const avatarBg = STOCK_AVATAR_COLORS[stock.symbol] ?? "#334155";
                    const hasChangePercent = typeof stock.changePercent === "number";
                    const isPositive = hasChangePercent && stock.changePercent > 0;
                    const isNegative = hasChangePercent && stock.changePercent < 0;
                    const changeColor = isPositive
                      ? "text-[#FF4D4F]"
                      : isNegative
                        ? "text-[#4096FF]"
                        : "text-gray-400";
                    const changeSign = isPositive ? "+" : "";

                    return (
                      <button
                        key={stock.symbol}
                        type="button"
                        onClick={() => {
                          persistRecentSearch(stock.name);
                          incrementSearchCount(stock.symbol, stock.name);
                          router.push(
                            `/stock-order?symbol=${encodeURIComponent(stock.symbol)}&name=${encodeURIComponent(stock.name)}`
                          );
                          onClose();
                        }}
                        className="flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-white/[0.04]"
                      >
                        {/* 순위 */}
                        <span className="w-4 text-center text-xs font-black text-sky-500">
                          {stock.rank}
                        </span>

                        {/* 로고 아바타 */}
                        <div
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-black text-white"
                          style={{ backgroundColor: avatarBg }}
                        >
                          {stock.name.slice(0, 2)}
                        </div>

                        {/* 종목명 */}
                        <span className="flex-1 text-sm font-semibold text-gray-100">
                          {stock.name}
                        </span>

                        {/* 등락률 */}
                        <span className={`flex items-center gap-0.5 text-xs font-black tabular-nums ${changeColor}`}>
                          {isPositive && <CaretUp size={10} weight="fill" />}
                          {isNegative && <CaretDown size={10} weight="fill" />}
                          {!isPositive && !isNegative && <Minus size={10} />}
                          {hasChangePercent
                            ? `${changeSign}${Math.abs(stock.changePercent).toFixed(2)}%`
                            : "--"}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <X size={20} className="mb-2 text-gray-600" />
              <p className="text-sm font-bold text-gray-400">검색 결과가 없습니다</p>
              <p className="mt-1 text-xs text-gray-600">다른 키워드로 다시 검색해보세요.</p>
            </div>
          ) : (
            <div className="space-y-5">
              {renderSection("Stocks", groupedItems.stocks, 0)}
              {renderSection(
                "Strategies",
                groupedItems.strategies,
                stockCount
              )}
              {renderSection(
                "Virtual Accounts",
                groupedItems.virtualAccounts,
                stockCount + strategyCount
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
