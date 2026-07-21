"use client";

import { useState, useEffect, useRef } from "react";
import { X, MagnifyingGlass } from "phosphor-react";
import type { StockSearchResult } from "@/types/stock";

interface StockSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (symbols: Array<{ symbol: string; name: string }>) => void;
  singleSelect?: boolean; // 단일 선택 모드
  universeId?: string | null;
}

type SearchUniverse = "etf" | "kospi" | "kosdaq" | "kospi200";

const UNIVERSE_LABELS: Record<SearchUniverse, string> = {
  etf: "ETF",
  kospi: "KOSPI",
  kosdaq: "KOSDAQ",
  kospi200: "KOSPI200",
};

function normalizeUniverseId(universeId?: string | null): SearchUniverse | null {
  const normalized = universeId?.toLowerCase().replace(/[\s_-]/g, "") ?? "";
  if (normalized.includes("etf")) return "etf";
  if (normalized.includes("kospi200")) return "kospi200";
  if (normalized.includes("kosdaq")) return "kosdaq";
  if (normalized.includes("kospi")) return "kospi";
  return null;
}

function filterUniverseStocks(stocks: StockSearchResult[], query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return stocks;

  return stocks.filter((stock) =>
    [stock.symbol, stock.name, stock.sector, stock.industry]
      .filter(Boolean)
      .some((value) => value!.toLowerCase().includes(normalizedQuery))
  );
}

export default function StockSearchModal({
  isOpen,
  onClose,
  onSelect,
  singleSelect = false,
  universeId,
}: StockSearchModalProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const restrictedUniverse = normalizeUniverseId(universeId);
  const restrictedUniverseLabel = restrictedUniverse
    ? UNIVERSE_LABELS[restrictedUniverse]
    : null;
  const [universeStocks, setUniverseStocks] = useState<StockSearchResult[]>([]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
    // Reset selected symbols when modal opens
    if (isOpen) {
      setSelectedSymbols(new Set());
      setSearchQuery("");
      setResults([]);
      setUniverseStocks([]);
      setError("");
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !restrictedUniverse) return;

    let isMounted = true;
    setLoading(true);
    setError("");

    Promise.all([
      fetch("/api/stocks/names").then((response) => {
        if (!response.ok) throw new Error("Failed to load stock names");
        return response.json() as Promise<Record<string, { name?: string; sector?: string }>>;
      }),
      fetch("/api/universe/data").then((response) => {
        if (!response.ok) throw new Error("Failed to load universe data");
        return response.json() as Promise<{ universes?: Partial<Record<SearchUniverse, string[]>> }>;
      }),
    ])
      .then(([metadata, universeData]) => {
        if (!isMounted) return;

        const symbols = restrictedUniverse === "etf"
          ? Object.entries(metadata)
              .filter(([, item]) => item.sector?.toUpperCase() === "ETF")
              .map(([symbol]) => symbol)
          : universeData.universes?.[restrictedUniverse] ?? [];
        const stocks = symbols
          .map((symbol): StockSearchResult | null => {
            const item = metadata[symbol];
            if (!item?.name) return null;
            return {
              symbol,
              name: item.name,
              type: restrictedUniverseLabel ?? "KR",
              region: "KR",
              currency: "KRW",
              sector: item.sector,
            };
          })
          .filter((stock): stock is StockSearchResult => stock !== null)
          .sort((a, b) => a.name.localeCompare(b.name, "ko"));

        setUniverseStocks(stocks);
        setResults(stocks);
      })
      .catch(() => {
        if (!isMounted) return;
        setUniverseStocks([]);
        setResults([]);
        setError(`${restrictedUniverseLabel} 유니버스 종목을 불러오지 못했습니다.`);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, restrictedUniverse, restrictedUniverseLabel]);

  useEffect(() => {
    if (restrictedUniverse) {
      setResults(filterUniverseStocks(universeStocks, searchQuery));
      return;
    }

    if (searchQuery.trim().length >= 1) {
      const debounceTimer = setTimeout(() => {
        searchStocks(searchQuery);
      }, 300);

      return () => clearTimeout(debounceTimer);
    } else {
      setResults([]);
    }
  }, [restrictedUniverse, searchQuery, universeStocks]);

  const searchStocks = async (query: string) => {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response = await fetch(
        `/api/stock/search?q=${encodeURIComponent(query)}`
      );
      if (response.ok) {
        const data = await response.json();
        // API가 배열을 직접 반환하거나 results 속성을 가질 수 있음
        const results = Array.isArray(data) ? data : data.results || [];
        setResults(results);
      } else {
        setError("검색 중 오류가 발생했습니다.");
      }
    } catch (error) {
      console.error("Stock search error:", error);
      setError("검색 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleSelect = (symbol: string, name: string) => {
    if (singleSelect) {
      // 단일 선택 모드: 바로 선택하고 닫기
      onSelect([{ symbol, name }]);
      setSelectedSymbols(new Set());
      setSearchQuery("");
      setResults([]);
      onClose();
    } else {
      // 다중 선택 모드: 체크박스처럼 동작
      const newSelected = new Set(selectedSymbols);
      if (newSelected.has(symbol)) {
        newSelected.delete(symbol);
      } else {
        newSelected.add(symbol);
      }
      setSelectedSymbols(newSelected);
    }
  };

  const handleAdd = () => {
    const selectedItems = results
      .filter((stock) => selectedSymbols.has(stock.symbol))
      .map((stock) => ({ symbol: stock.symbol, name: stock.name }));
    
    if (selectedItems.length > 0) {
      onSelect(selectedItems);
      setSelectedSymbols(new Set());
      setSearchQuery("");
      setResults([]);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm px-4 py-6">
      <div className="flex w-full max-w-2xl max-h-[86vh] flex-col overflow-hidden rounded-3xl border border-white/[0.08] bg-[#0f0f10] shadow-2xl shadow-black/40">
        {/* Header */}
        <div className="border-b border-white/[0.08] bg-white/[0.02] px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-black tracking-tight text-white">
                  {restrictedUniverseLabel ? `${restrictedUniverseLabel} 종목 검색` : "종목 검색"}
                </h2>
              </div>
            </div>
            <button
              onClick={onClose}
              className="rounded-xl border border-white/[0.08] p-2 text-gray-500 transition-colors hover:border-white/[0.16] hover:text-white"
              aria-label="종목 검색 닫기"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Search Input */}
        <div className="border-b border-white/[0.08] px-5 py-4">
          <div className="relative flex items-center bg-white/[0.06] rounded-2xl px-4 py-3">
            <MagnifyingGlass
              size={16}
              className="shrink-0 text-gray-500 mr-3"
            />
            <input
              ref={inputRef}
              type="text"
              name="stock-search-query"
              inputMode="search"
              autoComplete="new-password"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent text-sm font-medium text-white placeholder:text-gray-500 outline-none ring-0 focus:ring-0 focus:outline-none"
              placeholder={restrictedUniverseLabel
                ? `${restrictedUniverseLabel} 유니버스 종목만 검색됩니다`
                : "종목명 또는 종목 코드를 입력하세요"}
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} className="shrink-0 ml-3 text-gray-500 hover:text-gray-300 transition-colors">
                <X size={14} />
              </button>
            )}
          </div>
          {error && (
            <p className="mt-3 text-xs font-bold text-[var(--main-blue)]">
              {error}
            </p>
          )}
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-4">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-sm text-gray-500">
              검색 중...
            </div>
          ) : searchQuery.trim().length < 1 && !restrictedUniverse ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <MagnifyingGlass size={22} className="text-gray-500" />
              </div>
              <p className="text-sm font-bold text-white">
                검색어를 입력하세요
              </p>
              <p className="mt-1 text-xs text-gray-500">
                종목명, 코드, 또는 일부 키워드로 찾을 수 있습니다.
              </p>
            </div>
          ) : results.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <X size={22} className="text-gray-500" />
              </div>
              <p className="text-sm font-bold text-white">
                검색 결과가 없습니다
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {restrictedUniverseLabel
                  ? `${restrictedUniverseLabel} 유니버스 안에서 다른 키워드로 검색해보세요.`
                  : "입력한 키워드를 바꿔 다시 검색해보세요."}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="mb-2 flex items-center justify-between px-2">
                <p className="text-xs font-bold uppercase tracking-widest text-gray-500">
                  검색 결과
                </p>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-600">
                  {results.length}개
                </p>
              </div>
              {results.map((stock) => {
                const isSelected = selectedSymbols.has(stock.symbol);
                return (
                  <button
                    key={stock.symbol}
                    onClick={() => handleToggleSelect(stock.symbol, stock.name)}
                    className={`group w-full rounded-2xl border px-4 py-3 text-left transition-all duration-200 ${
                      isSelected
                        ? "border-sky-400/40 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]"
                        : "border-white/[0.06] bg-white/[0.03] hover:border-white/[0.12] hover:bg-white/[0.05]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-bold text-white">
                            {stock.name}
                          </p>
                          <p className="mt-1 text-xs text-gray-500">
                            <span className="font-bold text-gray-400">{stock.symbol}</span>
                            {" "}
                            · {stock.region === "KR" ? stock.type : stock.region}
                            {" "}
                            · {stock.region === "KR" ? "한국" : stock.type}
                            {stock.sector && stock.region === "KR" ? ` · ${stock.sector}` : ""}
                          </p>
                        </div>
                      </div>
                      <span className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${
                        isSelected
                          ? "bg-sky-400/15 text-[var(--main-blue)]"
                          : "bg-white/[0.04] text-gray-500 group-hover:text-gray-300"
                      }`}>
                        {singleSelect ? "선택" : isSelected ? "선택됨" : "추가"}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer with Add Button - 다중 선택 모드일 때만 표시 */}
        {!singleSelect && selectedSymbols.size > 0 && (
          <div className="border-t border-white/[0.08] bg-white/[0.02] px-5 py-4 animate-fade-in-up">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-gray-400">
                <span className="font-bold text-white">{selectedSymbols.size}개</span> 종목 선택됨
              </span>
              <button
                onClick={handleAdd}
                className="rounded-xl bg-white px-4 py-2 text-sm font-black text-black transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98]"
              >
                추가하기
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
