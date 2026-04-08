"use client";

import { useState, useEffect, useRef } from "react";
import { X, MagnifyingGlass, Star } from "phosphor-react";
import type { StockSearchResult } from "@/types/stock";

interface StockSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (symbols: Array<{ symbol: string; name: string }>) => void;
  singleSelect?: boolean; // 단일 선택 모드
}

export default function StockSearchModal({
  isOpen,
  onClose,
  onSelect,
  singleSelect = false,
}: StockSearchModalProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
    // Reset selected symbols when modal opens
    if (isOpen) {
      setSelectedSymbols(new Set());
      setSearchQuery("");
      setResults([]);
    }
  }, [isOpen]);

  useEffect(() => {
    if (searchQuery.trim().length >= 1) {
      const debounceTimer = setTimeout(() => {
        searchStocks(searchQuery);
      }, 300);

      return () => clearTimeout(debounceTimer);
    } else {
      setResults([]);
    }
  }, [searchQuery]);

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
                  종목 검색
                </h2>
                <span className="rounded-full border border-sky-400/20 bg-sky-400/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-[var(--main-blue)]">
                  Live
                </span>
              </div>
              <p className="mt-1 text-xs font-medium text-gray-500">
                종목명이나 티커를 입력해 빠르게 찾고 선택하세요.
              </p>
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
          <div className="relative">
            <MagnifyingGlass
              size={18}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
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
              className="w-full rounded-2xl border border-white/[0.08] bg-white/[0.03] py-3 pl-10 pr-4 text-sm font-medium text-white placeholder:text-gray-600 outline-none transition-colors focus:border-sky-400/30 focus:bg-white/[0.05]"
              placeholder="종목명 또는 종목 코드를 입력하세요"
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-gray-500">
              종목명
            </span>
            <span className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-gray-500">
              티커
            </span>
            <span className="rounded-full bg-white/[0.04] px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-gray-500">
              국내 / 해외
            </span>
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
          ) : searchQuery.trim().length < 1 ? (
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
                입력한 키워드를 바꿔 다시 검색해보세요.
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
                        ? "border-sky-400/40 bg-sky-400/10 shadow-[0_0_0_1px_rgba(56,189,248,0.12)]"
                        : "border-white/[0.06] bg-white/[0.03] hover:border-white/[0.12] hover:bg-white/[0.05]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        {!singleSelect && (
                          <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.04]">
                            {isSelected ? (
                              <Star size={11} weight="fill" className="text-yellow-500" />
                            ) : (
                              <Star size={11} className="text-gray-500" />
                            )}
                          </div>
                        )}
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
