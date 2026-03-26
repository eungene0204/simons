"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Play,
  Pause,
  Stop,
  ArrowClockwise,
  Lightning,
  TrendUp,
  MagnifyingGlass,
  Trash,
} from "phosphor-react";
import {
  VirtualMarketState,
  VirtualMarketLog,
  RefreshResult,
  getMarketState,
  startVirtualMarket,
  updateMarketState,
  stopVirtualMarket,
  refreshMarket,
  getMarketLogs,
  startStrategyExecution,
} from "@/lib/virtual-market";
import SignalLog from "./SignalLog";
import StockSearchModal from "@/components/stock/StockSearchModal";

interface VirtualMarketPanelProps {
  accountId: string;
  strategyId?: string;
  strategyName?: string;
  onTradeExecuted?: () => void;
}

const DEFAULT_STOCKS = [
  { symbol: "005930", name: "삼성전자" },
  { symbol: "000660", name: "SK하이닉스" },
  { symbol: "035720", name: "카카오" },
  { symbol: "035420", name: "NAVER" },
  { symbol: "005380", name: "현대차" },
];

// 자동 새로고침 간격 (분 단위)
const AUTO_REFRESH_MINUTES = 5;

export default function VirtualMarketPanel({
  accountId,
  strategyId,
  strategyName,
  onTradeExecuted,
}: VirtualMarketPanelProps) {
  const [marketState, setMarketState] = useState<VirtualMarketState | null>(null);
  const [logs, setLogs] = useState<VirtualMarketLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<RefreshResult | null>(null);

  const [selectedStocks, setSelectedStocks] = useState<{ symbol: string; name: string }[]>(DEFAULT_STOCKS);
  const [positionSymbols, setPositionSymbols] = useState<Set<string>>(new Set());
  const [symbolNameMap, setSymbolNameMap] = useState<Record<string, string>>(
    Object.fromEntries(DEFAULT_STOCKS.map((s) => [s.symbol, s.name]))
  );
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const autoRefreshRef = useRef<NodeJS.Timeout | null>(null);
  const isRefreshingRef = useRef(false);

  const loadPositions = useCallback(async () => {
    try {
      const res = await fetch(`/api/virtual-account/${accountId}/positions`);
      if (!res.ok) return;
      const positions: { symbol: string; name: string }[] = await res.json();
      if (positions.length === 0) return;
      setPositionSymbols(new Set(positions.map((p) => p.symbol)));
      setSymbolNameMap((prev) => {
        const next = { ...prev };
        positions.forEach((p) => { next[p.symbol] = p.name; });
        return next;
      });
    } catch { /* 무시 */ }
  }, [accountId]);

  useEffect(() => {
    fetch("/api/stocks/names")
      .then((r) => r.ok ? r.json() : {})
      .then((namesRes: Record<string, { name: string }>) => {
        setSymbolNameMap((prev) => {
          const next = { ...prev };
          Object.entries(namesRes).forEach(([sym, meta]) => { next[sym] = meta.name; });
          return next;
        });
      })
      .catch(() => {});
    loadState();
    loadLogs();
    loadPositions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  const loadState = async () => {
    setLoading(true);
    const state = await getMarketState(accountId);
    setMarketState(state);
    if (state?.symbolNames) {
      setSymbolNameMap((prev) => ({ ...prev, ...state.symbolNames }));
    }
    setLoading(false);
  };

  const loadLogs = async () => {
    const l = await getMarketLogs(accountId);
    setLogs(l);
  };

  // 자동 새로고침 (running 상태일 때 5분마다)
  useEffect(() => {
    if (marketState?.status === "running") {
      autoRefreshRef.current = setInterval(() => {
        if (!isRefreshingRef.current) {
          handleRefresh();
        }
      }, AUTO_REFRESH_MINUTES * 60 * 1000);
    }
    return () => {
      if (autoRefreshRef.current) {
        clearInterval(autoRefreshRef.current);
        autoRefreshRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketState?.status, accountId]);

  const handleRefresh = async () => {
    if (isRefreshingRef.current) return;
    isRefreshingRef.current = true;
    setRefreshing(true);
    try {
      const result = await refreshMarket(accountId);
      setLastResult(result);
      const state = await getMarketState(accountId);
      setMarketState(state);
      if (state?.symbolNames) {
        setSymbolNameMap((prev) => ({ ...prev, ...state.symbolNames }));
      }
      await loadLogs();
      if (result.logs?.some((l) => l.action === "auto_executed")) {
        await loadPositions();
        onTradeExecuted?.();
      }
    } catch { /* 무시 */ }
    finally {
      setRefreshing(false);
      isRefreshingRef.current = false;
    }
  };

  const handleStart = async () => {
    setStarting(true);
    setStartError(null);
    try {
      let state: VirtualMarketState;
      if (strategyId) {
        state = await startStrategyExecution(accountId);
      } else {
        if (selectedStocks.length === 0) {
          setStartError("최소 1개 이상의 종목을 선택하세요");
          setStarting(false);
          return;
        }
        state = await startVirtualMarket(accountId, selectedStocks.map((s) => s.symbol));
      }
      setMarketState(state);
      if (state.symbolNames) {
        setSymbolNameMap((prev) => ({ ...prev, ...state.symbolNames }));
      }
      // 시작 직후 바로 새로고침
      setTimeout(() => handleRefresh(), 500);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "시작에 실패했습니다");
    } finally {
      setStarting(false);
    }
  };

  const handlePause = async () => {
    const state = await updateMarketState(accountId, { status: "paused" });
    setMarketState(state);
  };

  const handleResume = async () => {
    const state = await updateMarketState(accountId, { status: "running" });
    setMarketState(state);
  };

  const handleStop = async () => {
    await stopVirtualMarket(accountId);
    setMarketState(null);
    setLastResult(null);
  };

  const handleStocksSelected = (stocks: { symbol: string; name: string }[]) => {
    const newStocks = stocks.filter((s) => !selectedStocks.some((e) => e.symbol === s.symbol));
    setSelectedStocks((prev) => [...prev, ...newStocks]);
    setSymbolNameMap((prev) => {
      const next = { ...prev };
      stocks.forEach((s) => { next[s.symbol] = s.name; });
      return next;
    });
  };

  const handleRemoveStock = (symbol: string) => {
    if (positionSymbols.has(symbol)) return;
    setSelectedStocks((prev) => prev.filter((s) => s.symbol !== symbol));
  };

  if (loading) {
    return (
      <div className="bg-[#1a1a1a] rounded-lg p-4 mb-6">
        <div className="animate-pulse h-24 bg-[#252525] rounded" />
      </div>
    );
  }

  const isRunning = marketState?.status === "running";
  const isPaused = marketState?.status === "paused";
  const isActive = isRunning || isPaused;

  return (
    <div className="bg-[#1a1a1a] rounded-lg mb-6 overflow-hidden">
      {/* 헤더 */}
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Lightning size={18} className="text-yellow-500" weight="fill" />
          <h3 className="text-sm font-semibold text-white">실제 시세 연동</h3>
          {isRunning && (
            <span className="flex items-center gap-1 px-2 py-0.5 bg-green-900/40 text-green-400 rounded-full text-xs font-medium">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
              추적중
            </span>
          )}
          {isPaused && (
            <span className="px-2 py-0.5 bg-yellow-900/40 text-yellow-400 rounded-full text-xs font-medium">
              일시정지
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {isActive && (
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              <ArrowClockwise size={14} className={refreshing ? "animate-spin" : ""} />
              {refreshing ? "조회중..." : "시세 새로고침"}
            </button>
          )}
          {!isActive && (
            <button
              onClick={handleStart}
              disabled={starting}
              className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
            >
              <Play size={14} weight="fill" />
              {starting ? "시작중..." : "시작"}
            </button>
          )}
          {isRunning && (
            <button
              onClick={handlePause}
              className="flex items-center gap-1 px-3 py-1.5 bg-yellow-600 text-white rounded-lg text-xs font-medium hover:bg-yellow-700 transition-colors"
            >
              <Pause size={14} weight="fill" />
              일시정지
            </button>
          )}
          {isPaused && (
            <button
              onClick={handleResume}
              className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700 transition-colors"
            >
              <Play size={14} weight="fill" />
              재개
            </button>
          )}
          {isActive && (
            <button
              onClick={handleStop}
              className="flex items-center gap-1 px-3 py-1.5 bg-red-600 text-white rounded-lg text-xs font-medium hover:bg-red-700 transition-colors"
            >
              <Stop size={14} weight="fill" />
              중지
            </button>
          )}
        </div>
      </div>

      {/* 바디 */}
      <div className="p-4">
        {startError && (
          <div className="mb-3 px-3 py-2 bg-red-900/30 rounded-lg text-xs text-red-400">
            {startError}
          </div>
        )}

        {/* 활성 상태 */}
        {isActive && marketState && (
          <div className="space-y-4">
            {/* 상태 정보 */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div className="bg-[#111111] rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">마지막 조회</p>
                <p className="text-sm font-semibold text-white">
                  {marketState.lastRefreshed ?? "미조회"}
                </p>
              </div>
              <div className="bg-[#111111] rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">추적 시작</p>
                <p className="text-sm font-semibold text-white">{marketState.startDate}</p>
              </div>
              <div className="bg-[#111111] rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">시그널 수</p>
                <p className="text-sm font-semibold text-white">{logs.length}건</p>
              </div>
            </div>

            {/* 실제 가격 현황 */}
            {lastResult?.prices && Object.keys(lastResult.prices).length > 0 && (
              <div>
                <p className="text-xs text-gray-400 mb-1.5">실제 시세 (KRX)</p>
                <div className="flex flex-wrap gap-1.5">
                  {marketState.symbols.map((sym) => {
                    const price = lastResult.prices?.[sym];
                    const isHeld = positionSymbols.has(sym);
                    return (
                      <span
                        key={sym}
                        className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium ${
                          isHeld ? "bg-green-900/20 text-green-400" : "bg-[#252525] text-gray-300"
                        }`}
                      >
                        {isHeld && <span className="text-[10px]">●</span>}
                        <span>{symbolNameMap[sym] ?? sym}</span>
                        {price && (
                          <span className="text-gray-500 font-mono">
                            {price.close.toLocaleString()}원
                          </span>
                        )}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 추적 종목 (가격 없을 때) */}
            {(!lastResult?.prices || Object.keys(lastResult.prices).length === 0) && (
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <p className="text-xs text-gray-400">추적 종목</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {marketState.symbols.map((sym) => {
                    const isHeld = positionSymbols.has(sym);
                    return (
                      <span
                        key={sym}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                          isHeld ? "bg-green-900/20 text-green-400" : "bg-blue-900/20 text-blue-400"
                        }`}
                      >
                        {isHeld && <span className="text-[10px]">●</span>}
                        {symbolNameMap[sym] ?? sym}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 시그널 로그 */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-xs text-gray-400">시그널 히스토리</p>
                {logs.length > 0 && (
                  <button
                    onClick={async () => {
                      if (!confirm("시그널 히스토리를 모두 삭제하시겠습니까?")) return;
                      await fetch(`/api/virtual-market/${accountId}/logs`, { method: "DELETE" });
                      setLogs([]);
                    }}
                    className="flex items-center gap-1 px-2 py-0.5 text-xs text-red-500 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                  >
                    <Trash size={12} />
                    전체 삭제
                  </button>
                )}
              </div>
              <SignalLog logs={logs} symbolNameMap={symbolNameMap} />
            </div>

            <p className="text-xs text-gray-500">
              KRX 실제 시세 기반 · 자동 새로고침 {AUTO_REFRESH_MINUTES}분마다 · 전일 마감가 기준
            </p>
          </div>
        )}

        {/* 비활성 상태: 설정 */}
        {!isActive && (
          <div className="space-y-3">
            {!strategyId && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-medium text-gray-300">추적 종목</label>
                  <button
                    onClick={() => setIsSearchOpen(true)}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-blue-400 hover:bg-blue-900/20 rounded-md transition-colors"
                  >
                    <MagnifyingGlass size={12} />
                    종목 추가
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5 min-h-[32px] p-2 rounded-lg bg-[#252525]">
                  {selectedStocks.length === 0 ? (
                    <span className="text-xs text-gray-400 self-center">종목을 추가하세요</span>
                  ) : (
                    selectedStocks.map((s) => {
                      const isHeld = positionSymbols.has(s.symbol);
                      return (
                        <span
                          key={s.symbol}
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                            isHeld ? "bg-green-900/20 text-green-400" : "bg-blue-900/20 text-blue-400"
                          }`}
                        >
                          {isHeld && <span className="text-[10px]">●</span>}
                          {s.name}
                          {!isHeld && (
                            <button
                              onClick={() => handleRemoveStock(s.symbol)}
                              className="hover:text-blue-200 leading-none"
                            >
                              ×
                            </button>
                          )}
                        </span>
                      );
                    })
                  )}
                </div>
              </div>
            )}

            {strategyId ? (
              <div className="px-3 py-2.5 bg-blue-950/40 border border-blue-900/40 rounded-lg">
                <p className="text-xs text-blue-300 font-medium mb-0.5">전략 자동 실행 모드</p>
                <p className="text-xs text-blue-400/80">
                  {strategyName ? `"${strategyName}" 전략의 ` : "연결된 전략의 "}
                  백테스트 수익률 상위 종목을 추적합니다. KRX 실제 시세 기준으로 전략 시그널을 평가합니다.
                </p>
              </div>
            ) : (
              <p className="text-xs text-gray-400">
                KRX 실제 시세를 조회해 전략 시그널을 평가합니다. 자동 새로고침은 {AUTO_REFRESH_MINUTES}분마다 실행됩니다.
              </p>
            )}
          </div>
        )}
      </div>

      <StockSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelect={handleStocksSelected}
        singleSelect={false}
      />
    </div>
  );
}
