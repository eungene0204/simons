"use client";

import { useState, useEffect, useRef } from "react";
import { XMarkIcon, MagnifyingGlassIcon, StarIcon } from "@heroicons/react/24/outline";
import { StarIcon as StarIconSolid } from "@heroicons/react/24/solid";
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
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-[#1a1a1a] rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[80vh] flex flex-col border border-gray-800">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">
            종목 검색
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-300 transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Search Input */}
        <div className="p-4 border-b border-gray-800">
          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              ref={inputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-700 rounded-lg bg-[#0f0f0f] text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="종목명 또는 종목 코드를 입력하세요"
            />
          </div>
          {error && (
            <p className="mt-2 text-sm text-red-400">
              {error}
            </p>
          )}
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center py-8">
              <p className="text-gray-400">검색 중...</p>
            </div>
          ) : searchQuery.trim().length < 1 ? (
            <div className="text-center py-8">
              <p className="text-gray-400">
                종목명 또는 종목 코드를 입력하세요
              </p>
            </div>
          ) : results.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-400">
                검색 결과가 없습니다
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {results.map((stock) => {
                const isSelected = selectedSymbols.has(stock.symbol);
                return (
                  <button
                    key={stock.symbol}
                    onClick={() => handleToggleSelect(stock.symbol, stock.name)}
                    className={`w-full p-3 text-left rounded-lg transition-colors border ${
                      isSelected
                        ? "bg-blue-800/20 border-blue-50000"
                        : "bg-[#0f0f0f] hover:bg-[#252525] border-gray-800"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {!singleSelect && (
                          <>
                            {isSelected ? (
                              <StarIconSolid className="w-5 h-5 text-yellow-500 flex-shrink-0" />
                            ) : (
                              <StarIcon className="w-5 h-5 text-gray-400 flex-shrink-0" />
                            )}
                          </>
                        )}
                        <div>
                          <p className="text-sm font-semibold text-white">
                            {stock.name}
                          </p>
                          <p className="text-xs text-gray-400 mt-1">
                            {stock.symbol} ·{" "}
                            {stock.region === "KR" ? stock.type : stock.region} ·{" "}
                            {stock.region === "KR" ? "한국" : stock.type}
                            {stock.sector &&
                              stock.region === "KR" &&
                              ` · ${stock.sector}`}
                          </p>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer with Add Button - 다중 선택 모드일 때만 표시 */}
        {!singleSelect && selectedSymbols.size > 0 && (
          <div className="p-4 border-t border-gray-800 flex items-center justify-between animate-fade-in-up">
            <span className="text-sm text-gray-400">
              {selectedSymbols.size}개 종목 선택됨
            </span>
            <button
              onClick={handleAdd}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-600 transition-all duration-200 text-sm font-semibold transform hover:scale-105 active:scale-95 shadow-md hover:shadow-lg"
            >
              추가하기
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
