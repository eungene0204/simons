"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Play,
  Pause,
  Stop,
  CalendarBlank,
  Lightning,
  TrendUp,
  Gauge,
  MagnifyingGlass,
  Trash,
} from "phosphor-react";
import {
  VirtualMarketState,
  VirtualMarketLog,
  TickResult,
  getMarketState,
  startVirtualMarket,
  updateMarketState,
  stopVirtualMarket,
  tickVirtualMarket,
  getMarketLogs,
  startStrategyExecution,
  stopStrategyExecution,
} from "@/lib/virtual-market";
import SignalLog from "./SignalLog";
import StockSearchModal from "@/components/stock/StockSearchModal";

interface VirtualMarketPanelProps {
  accountId: string;
  strategyId?: string;
  strategyName?: string;
  onTradeExecuted?: () => void; // 거래 실행 후 부모 새로고침
}

const SCENARIOS = [
  { value: "realistic", label: "혼합 (현실적)" },
  { value: "bull", label: "상승장" },
  { value: "bear", label: "하락장" },
  { value: "sideways", label: "횡보장" },
  { value: "volatile", label: "고변동성" },
  { value: "crash_recovery", label: "급락 후 회복" },
];

const SPEED_OPTIONS = [
  { value: 3, label: "3초/일 (고속)" },
  { value: 5, label: "5초/일 (빠름)" },
  { value: 10, label: "10초/일 (보통)" },
  { value: 30, label: "30초/일 (느림)" },
];

const DEFAULT_STOCKS = [
  { symbol: "005930", name: "삼성전자" },
  { symbol: "000660", name: "SK하이닉스" },
  { symbol: "035720", name: "카카오" },
  { symbol: "035420", name: "NAVER" },
  { symbol: "005380", name: "현대차" },
];

export default function VirtualMarketPanel({
  accountId,
  strategyId,
  strategyName,
  onTradeExecuted,
}: VirtualMarketPanelProps) {
  const [marketState, setMarketState] =
    useState<VirtualMarketState | null>(null);
  const [logs, setLogs] = useState<VirtualMarketLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [lastTickResult, setLastTickResult] = useState<TickResult | null>(null);

  // 설정 (시작 전)
  const [scenario, setScenario] = useState("realistic");
  const [speed, setSpeed] = useState(10);
  const [selectedStocks, setSelectedStocks] = useState<{ symbol: string; name: string }[]>(DEFAULT_STOCKS);
  const [positionSymbols, setPositionSymbols] = useState<Set<string>>(new Set());
  const [symbolNameMap, setSymbolNameMap] = useState<Record<string, string>>(
    Object.fromEntries(DEFAULT_STOCKS.map((s) => [s.symbol, s.name]))
  );
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);

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
      setSelectedStocks((prev) => {
        const existing = new Set(prev.map((s) => s.symbol));
        const toAdd = positions.filter((p) => !existing.has(p.symbol));
        return toAdd.length > 0 ? [...prev, ...toAdd] : prev;
      });
    } catch {
      // 무시
    }
  }, [accountId]);

  // 초기 로드
  useEffect(() => {
    // 전체 종목 이름 맵 로드
    fetch("/api/stocks/names")
      .then((r) => r.ok ? r.json() : {})
      .then((namesRes: Record<string, { name: string }>) => {
        setSymbolNameMap((prev) => {
          const next = { ...prev };
          Object.entries(namesRes).forEach(([sym, meta]) => {
            next[sym] = meta.name;
          });
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
    if (state) {
      setScenario(state.scenario);
      setSpeed(state.speed);
      // 서버에서 받은 symbolNames를 symbolNameMap에 반영
      if (state.symbolNames) {
        setSymbolNameMap((prev) => ({ ...prev, ...state.symbolNames }));
      }
    }
    setLoading(false);
  };

  // 폴링 중 날짜 전환 시 로딩 플래시 없이 조용히 상태 갱신
  const refreshState = async () => {
    const state = await getMarketState(accountId);
    setMarketState(state);
    if (state) {
      setScenario(state.scenario);
      setSpeed(state.speed);
      if (state.symbolNames) {
        setSymbolNameMap((prev) => ({ ...prev, ...state.symbolNames }));
      }
    }
  };

  const loadLogs = async () => {
    const l = await getMarketLogs(accountId);
    setLogs(l);
  };

  // 폴링 타이머
  useEffect(() => {
    if (marketState?.status === "running") {
      intervalRef.current = setInterval(async () => {
        try {
          const result = await tickVirtualMarket(accountId);
          setLastTickResult(result);
          if (result.stepped) {
            // 상태 + 로그 새로고침 (로딩 플래시 없이)
            await refreshState();
            await loadLogs();
            if (
              result.logs &&
              result.logs.some((l) => l.action === "auto_executed")
            ) {
              await loadPositions();
              onTradeExecuted?.();
            }
          }
        } catch {
          // 에러 무시
        }
      }, 2000);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketState?.status, accountId]);

  const handleStart = async () => {
    if (selectedStocks.length === 0) {
      setStartError("최소 1개 이상의 종목을 선택하세요");
      return;
    }
    setStarting(true);
    setStartError(null);
    try {
      const state = await startVirtualMarket(accountId, {
        symbols: selectedStocks.map((s) => s.symbol),
        scenario,
        speed,
        startDate: "2023-01-02",
      });
      setMarketState(state);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "가상시장 시작에 실패했습니다");
    } finally {
      setStarting(false);
    }
  };

  // 전략 유니버스로 자동 시작
  const handleStrategyStart = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const state = await startStrategyExecution(accountId, {
        scenario,
        speed,
        startDate: "2023-01-02",
      });
      setMarketState(state);
      if (state.symbolNames) {
        setSymbolNameMap((prev) => ({ ...prev, ...state.symbolNames }));
      }
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "전략 자동 실행 시작에 실패했습니다");
    } finally {
      setStarting(false);
    }
  };

  // 전략 자동 실행 중지
  const handleStrategyStop = async () => {
    await stopStrategyExecution(accountId);
    setMarketState(null);
    setLastTickResult(null);
  };

  const handleStocksSelected = (stocks: { symbol: string; name: string }[]) => {
    const newStocks = stocks.filter(
      (s) => !selectedStocks.some((existing) => existing.symbol === s.symbol)
    );
    setSelectedStocks((prev) => [...prev, ...newStocks]);
    setSymbolNameMap((prev) => {
      const next = { ...prev };
      stocks.forEach((s) => { next[s.symbol] = s.name; });
      return next;
    });
  };

  const handleRemoveStock = (symbol: string) => {
    if (positionSymbols.has(symbol)) return; // 보유 중인 종목은 제거 불가
    setSelectedStocks((prev) => prev.filter((s) => s.symbol !== symbol));
  };

  const handlePause = async () => {
    const state = await updateMarketState(accountId, {
      status: "paused",
    });
    setMarketState(state);
  };

  const handleResume = async () => {
    const state = await updateMarketState(accountId, {
      status: "running",
    });
    setMarketState(state);
  };

  const handleStop = async () => {
    await stopVirtualMarket(accountId);
    setMarketState(null);
    setLastTickResult(null);
  };

  const handleSpeedChange = async (newSpeed: number) => {
    setSpeed(newSpeed);
    if (marketState) {
      const state = await updateMarketState(accountId, {
        speed: newSpeed,
      });
      setMarketState(state);
    }
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
          <h3 className="text-sm font-semibold text-white">
            가상 주식시장
          </h3>
          {isRunning && (
            <span className="flex items-center gap-1 px-2 py-0.5 bg-green-900/40 text-green-400 rounded-full text-xs font-medium">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
              실행중
            </span>
          )}
          {isPaused && (
            <span className="px-2 py-0.5 bg-yellow-900/40 text-yellow-400 rounded-full text-xs font-medium">
              일시정지
            </span>
          )}
        </div>

        {/* 컨트롤 버튼 */}
        <div className="flex items-center gap-1.5">
          {!isActive && strategyId && (
            <button
              onClick={handleStrategyStart}
              disabled={starting}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              <Lightning size={14} weight="fill" />
              {starting ? "시작중..." : "전략 자동 실행"}
            </button>
          )}
          {!isActive && (
            <button
              onClick={handleStart}
              disabled={starting}
              className="flex items-center gap-1 px-3 py-1.5 bg-[#252525] text-gray-300 rounded-lg text-xs font-medium hover:bg-[#2e2e2e] disabled:opacity-50 transition-colors"
            >
              <Play size={14} weight="fill" />
              {starting ? "시작중..." : "수동 시작"}
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
        {/* 에러 메시지 */}
        {startError && (
          <div className="mb-3 px-3 py-2 bg-red-900/30 rounded-lg text-xs text-red-400">
            {startError}
          </div>
        )}
        {/* 활성 상태: 가상 날짜 + 통계 */}
        {isActive && marketState && (
          <div className="space-y-4">
            {/* 상태 정보 그리드 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-[#111111] rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <CalendarBlank
                    size={14}
                    className="text-gray-400"
                  />
                  <span className="text-xs text-gray-400">
                    가상 날짜
                  </span>
                </div>
                <p
                  key={marketState.virtualDate}
                  className="text-sm font-semibold text-white animate-fadeIn"
                >
                  {marketState.virtualDate}
                </p>
              </div>

              <div className="bg-[#111111] rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <TrendUp size={14} className="text-gray-400" />
                  <span className="text-xs text-gray-400">
                    시나리오
                  </span>
                </div>
                <p className="text-sm font-semibold text-white">
                  {
                    SCENARIOS.find(
                      (s) => s.value === marketState.scenario
                    )?.label
                  }
                </p>
              </div>

              <div className="bg-[#111111] rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <Gauge size={14} className="text-gray-400" />
                  <span className="text-xs text-gray-400">
                    속도
                  </span>
                </div>
                <select
                  value={speed}
                  onChange={(e) =>
                    handleSpeedChange(parseInt(e.target.value))
                  }
                  className="text-sm font-semibold text-white bg-transparent border-none p-0 focus:ring-0 cursor-pointer"
                >
                  {SPEED_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="bg-[#111111] rounded-lg p-3">
                <div className="flex items-center gap-1.5 mb-1">
                  <Lightning size={14} className="text-gray-400" />
                  <span className="text-xs text-gray-400">
                    시그널 수
                  </span>
                </div>
                <p className="text-sm font-semibold text-white">
                  {logs.length}건
                </p>
              </div>
            </div>

            {/* 추적 종목 */}
            <div>
              <p className="text-xs text-gray-400 mb-1.5">
                추적 종목
              </p>
              <div className="flex flex-wrap gap-1.5">
                {marketState.symbols.map((sym) => {
                  const isHeld = positionSymbols.has(sym);
                  return (
                    <span
                      key={sym}
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                        isHeld
                          ? "bg-green-900/20 text-green-400"
                          : "bg-blue-900/20 text-blue-400"
                      }`}
                    >
                      {isHeld && <span className="text-[10px]">●</span>}
                      {symbolNameMap[sym] ?? sym}
                      {isHeld && <span className="text-[10px] opacity-60">보유</span>}
                    </span>
                  );
                })}
              </div>
            </div>

            {/* 시그널 로그 */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-xs text-gray-400">
                  시그널 히스토리
                </p>
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
          </div>
        )}

        {/* 비활성 상태: 설정 폼 */}
        {!isActive && (
          <div className="space-y-3">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-gray-300">
                  추적 종목
                </label>
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
                          isHeld
                            ? "bg-green-900/20 text-green-400"
                            : "bg-blue-900/20 text-blue-400"
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

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  시나리오
                </label>
                <select
                  value={scenario}
                  onChange={(e) => setScenario(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm rounded-lg bg-[#252525] text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {SCENARIOS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1">
                  속도
                </label>
                <select
                  value={speed}
                  onChange={(e) => setSpeed(parseInt(e.target.value))}
                  className="w-full px-3 py-1.5 text-sm rounded-lg bg-[#252525] text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {SPEED_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {strategyId ? (
              <div className="px-3 py-2.5 bg-blue-950/40 border border-blue-900/40 rounded-lg">
                <p className="text-xs text-blue-300 font-medium mb-0.5">
                  전략 자동 실행 모드
                </p>
                <p className="text-xs text-blue-400/80">
                  <span className="font-medium">[전략 자동 실행]</span>을 누르면{" "}
                  {strategyName ? `"${strategyName}" 전략의 ` : "연결된 전략의 "}
                  유니버스 종목이 자동으로 선택되고, {speed}초마다 1거래일씩 진행되며
                  시그널 발생 시 자동매매됩니다.
                </p>
              </div>
            ) : (
              <p className="text-xs text-gray-400">
                가상 시장을 시작하면 {speed}초마다 1거래일이 진행됩니다.
                전략 시그널 발생 시 연결된 전략에 따라 자동매매 또는 알림이 실행됩니다.
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
