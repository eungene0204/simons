"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter, useParams } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import VirtualTradingDashboard from "@/components/dashboard/VirtualTradingDashboard";
import {
  VirtualAccount,
  PortfolioHolding,
  Transaction,
} from "@/types/portfolio";
import {
  getAccount,
  getTransactionsByAccount,
  executeTrade,
  refreshAccountValue,
  updateTradingMode,
  updateAccountStrategy,
  deleteAccount,
} from "@/lib/portfolio";
import { getMarketLogs, type VirtualMarketLog } from "@/lib/virtual-market";
import { MagnifyingGlass, Robot, Bell, Trash } from "phosphor-react";
import StockSearchModal from "@/components/stock/StockSearchModal";
import OrderBook from "@/components/order/OrderBook";
import PortfolioPerformanceChart, { PerformancePoint } from "@/components/portfolio/PortfolioPerformanceChart";
import { getStrategyByName } from "@/lib/strategy-groups";
import { TrendUp } from "phosphor-react";
import StrategyReplaceModal from "@/components/ui/StrategyReplaceModal";
import TrackedSymbolRow from "@/components/virtual-account/TrackedSymbolRow";
import TrackedSymbolsSkeleton from "@/components/virtual-account/TrackedSymbolsSkeleton";
import SignalLog from "@/components/virtual-market/SignalLog";
import { useStockPrices } from "@/lib/hooks/useStockPrices";
import { buildStrategySummaryFromDsl } from "@/lib/strategy-summary";
import type { StockPriceSnapshot as BatchQuoteItem } from "@/lib/stock-prices";
import type { StrategyDSL } from "@/types/strategy";

const formatPrice = (price: number) =>
  new Intl.NumberFormat("ko-KR").format(Math.round(price));

const formatCompact = (val: number) => {
  if (Math.abs(val) >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (Math.abs(val) >= 1_000) return `${(val / 1_000).toFixed(0)}k`;
  return String(val);
};

function generatePerformanceData(startDate: Date, days: number, cumulativeReturn: number): PerformancePoint[] {
  const data: PerformancePoint[] = [];
  const step = Math.max(1, Math.floor(days / 60));
  for (let i = 0; i <= days; i += step) {
    const d = new Date(startDate);
    d.setDate(d.getDate() + i);
    const time = d.toISOString().slice(0, 10);
    const t = i / Math.max(1, days);
    const benchmark = +(100 * (1 + (cumulativeReturn * 0.3 / 100) * t)).toFixed(2);
    data.push({ time, portfolio: benchmark, benchmark });
  }
  return data;
}

export default function VirtualAccountDetailPage() {
  const router = useRouter();
  const params = useParams();
  const accountId = params.id as string;

  const [account, setAccount] = useState<VirtualAccount | null>(null);
  const [holdings, setHoldings] = useState<PortfolioHolding[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [selectedStockName, setSelectedStockName] = useState("");
  const [stockInfo, setStockInfo] = useState<any>(null);
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [currentPrice, setCurrentPrice] = useState<number | undefined>(undefined);
  const [selectedOrderPrice, setSelectedOrderPrice] = useState<number | undefined>(undefined);
  const [transactionType, setTransactionType] = useState<"buy" | "sell">("buy");
  const [orderTab, setOrderTab] = useState<"buy" | "sell" | "amend" | "unfilled" | "balance">("buy");
  const [paymentType, setPaymentType] = useState<"cash" | "credit">("cash");
  const [orderType, setOrderType] = useState<"limit" | "market">("limit");
  const [isMarketPrice, setIsMarketPrice] = useState(false);
  const [isAutoPrice, setIsAutoPrice] = useState(true);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [showOrderPage, setShowOrderPage] = useState(false);
  const [activeTab, setActiveTab] = useState<"holdings" | "transactions" | "performance">("holdings");
  const [dbStrategyDescription, setDbStrategyDescription] = useState<string | null>(null);
  const [dbStrategySettings, setDbStrategySettings] = useState<StrategyDSL | null>(null);
  const [trackedSymbols, setTrackedSymbols] = useState<{ symbol: string; name: string }[]>([]);
  const [trackedPrices, setTrackedPrices] = useState<Record<string, BatchQuoteItem>>({});
  const [isTrackedSymbolsLoading, setIsTrackedSymbolsLoading] = useState(true);
  const [signalLogs, setSignalLogs] = useState<VirtualMarketLog[]>([]);
  const [isTrackSearchOpen, setIsTrackSearchOpen] = useState(false);
  const [isStrategyReplaceOpen, setIsStrategyReplaceOpen] = useState(false);
  const [isPromptVisible, setIsPromptVisible] = useState(false);
  const trackedSymbolsList = trackedSymbols.map((s) => s.symbol);
  const { data: trackedPriceSnapshots } = useStockPrices(trackedSymbolsList, {
    enabled: trackedSymbolsList.length > 0,
    refetchInterval: 2000,
  });
  const { data: selectedSymbolSnapshots } = useStockPrices(
    selectedSymbol ? [selectedSymbol] : [],
    {
      enabled: !!selectedSymbol,
      refetchInterval: 2000,
    }
  );

  useEffect(() => {
    if (accountId) loadAccountData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    const interval = setInterval(async () => {
      const result = await refreshAccountValue(accountId);
      if (!result) return;
      setAccount(result.account);
      setHoldings(result.holdings);
    }, 3000);
    return () => clearInterval(interval);
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    loadSignalLogs();
    const interval = setInterval(() => {
      loadSignalLogs();
    }, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  useEffect(() => {
    if (!trackedPriceSnapshots) return;
    setTrackedPrices((prev) => {
      const merged = { ...prev };
      for (const [sym, item] of Object.entries(trackedPriceSnapshots)) {
        if (item.price > 0) {
          merged[sym] = item;
        }
      }
      return merged;
    });
  }, [trackedPriceSnapshots]);

  useEffect(() => {
    const quote = selectedSymbol ? selectedSymbolSnapshots?.[selectedSymbol] : undefined;
    if (!quote || quote.price <= 0) return;
    setCurrentPrice(quote.price);
    if (isAutoPrice && !selectedOrderPrice) {
      setPrice(quote.price.toString());
    }
  }, [selectedSymbol, selectedSymbolSnapshots, isAutoPrice, selectedOrderPrice]);

  useEffect(() => {
    if (!selectedSymbol) {
      setStockInfo(null);
      return;
    }

    fetch(`/api/stock/${selectedSymbol}/detail`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data) return;
        setStockInfo(data);
        if (data.name) {
          setSelectedStockName(data.name);
        }
      })
      .catch(() => {});
  }, [selectedSymbol]);

  useEffect(() => {
    setIsPromptVisible(false);
  }, [account?.strategyId]);

  const loadAccountData = async () => {
    const [acc, t] = await Promise.all([
      getAccount(accountId),
      getTransactionsByAccount(accountId),
    ]);
    if (!acc) { router.push("/virtual-account"); return; }
    setAccount(acc);
    setHoldings((acc as any).holdings ?? []);
    setTransactions(t.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()));
    if (acc.strategyId) {
      fetch(`/api/strategy/${acc.strategyId}`)
        .then((r) => r.ok ? r.json() : null)
        .then((s) => {
          setDbStrategyDescription(s?.description ?? null);
          setDbStrategySettings((s?.settings as StrategyDSL | null) ?? null);
        })
        .catch(() => {
          setDbStrategyDescription(null);
          setDbStrategySettings(null);
        });
    } else {
      setDbStrategyDescription(null);
      setDbStrategySettings(null);
    }
    setIsTrackedSymbolsLoading(true);
    fetch(`/api/virtual-market/${accountId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((state) => {
        const nextTrackedSymbols = state?.symbols?.length
          ? state.symbols.map((sym: string) => ({
              symbol: sym,
              name: state.symbolNames?.[sym] || sym,
            }))
          : [];
        setTrackedSymbols(nextTrackedSymbols);
      })
      .catch(() => {
        setTrackedSymbols([]);
      })
      .finally(() => {
        setIsTrackedSymbolsLoading(false);
      });
  };

  const loadSignalLogs = async () => {
    const logs = await getMarketLogs(accountId, 30);
    setSignalLogs(
      [...logs].sort(
        (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      )
    );
  };

  const handleAddTrackedSymbols = async (selected: Array<{ symbol: string; name: string }>) => {
    const newSymbols = selected.filter(
      (s) => !trackedSymbols.some((t) => t.symbol === s.symbol)
    );
    if (newSymbols.length === 0) return;
    const merged = [...trackedSymbols, ...newSymbols];
    const symbolList = merged.map((s) => s.symbol);
    try {
      const checkRes = await fetch(`/api/virtual-market/${accountId}`);
      const existing = checkRes.ok ? await checkRes.json() : null;
      if (existing) {
        await fetch(`/api/virtual-market/${accountId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: symbolList }),
        });
      } else {
        await fetch(`/api/virtual-market/${accountId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: symbolList }),
        });
      }
      setTrackedSymbols(merged);
    } catch (e) {
      console.error("Failed to add tracked symbols:", e);
    }
  };

  const handleRemoveTrackedSymbol = async (symbol: string) => {
    const merged = trackedSymbols.filter((s) => s.symbol !== symbol);
    const symbolList = merged.map((s) => s.symbol);
    try {
      await fetch(`/api/virtual-market/${accountId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: symbolList }),
      });
      setTrackedSymbols(merged);
    } catch (e) {
      console.error("Failed to remove tracked symbol:", e);
    }
  };

  const handleStockSelect = (symbol: string, name: string) => {
    router.push(`/stock-order?symbol=${symbol}&name=${encodeURIComponent(name)}`);
  };

  const handleTransaction = async () => {
    if (!account || !selectedSymbol || !quantity || !price) return;
    const qty = parseInt(quantity);
    const prc = parseFloat(price);
    if (isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0) return;
    let stockName = selectedStockName || selectedSymbol;
    try {
      const response = await fetch(`/api/stock/${selectedSymbol}/detail`);
      if (response.ok) { const data = await response.json(); stockName = data.name || stockName; }
    } catch {}
    const result = await executeTrade(accountId, transactionType, selectedSymbol, stockName, qty, prc);
    if (!result.success) { alert(result.error ?? "거래에 실패했습니다."); return; }
    setSelectedSymbol(""); setQuantity(""); setPrice(""); setSelectedOrderPrice(undefined);
    await loadAccountData();
    if (transactionType === "buy") {
      setShowOrderPage(false);
      const url = new URL(window.location.href);
      url.searchParams.delete("symbol");
      window.history.pushState({}, "", url.toString());
    }
  };

  const { profit, profitPercent, todayPnl, todayPnlPct, performanceData } = useMemo(() => {
    if (!account) return { profit: 0, profitPercent: 0, todayPnl: 0, todayPnlPct: 0, performanceData: [] };
    const p = account.totalValue - account.initialAmount;
    const pp = (p / account.initialAmount) * 100;
    const todayStr = new Date().toISOString().slice(0, 10);
    const todayPnl = transactions
      .filter((t) => t.type === "sell" && t.status === "FILLED" && t.filledAt?.startsWith(todayStr))
      .reduce((sum, t) => sum + (t.realizedPnl ?? 0), 0);
    const todayPnlPct = account.initialAmount > 0 ? (todayPnl / account.initialAmount) * 100 : 0;
    const startDate = new Date(account.createdAt);
    const days = Math.max(1, Math.round((Date.now() - startDate.getTime()) / 86400000));
    const performanceData = generatePerformanceData(startDate, Math.min(days, 150), pp);
    return { profit: p, profitPercent: pp, todayPnl, todayPnlPct, performanceData };
  }, [account, transactions]);

  if (!account) {
    return (
      <DashboardLayout userName="사용자">
        <div className="p-4 md:p-5 lg:p-6 flex flex-col items-center justify-center min-h-48 gap-3">
          <p className="text-sm font-bold text-gray-500">계좌를 불러오는 중...</p>
        </div>
      </DashboardLayout>
    );
  }

  const shouldShowOrderPage = showOrderPage || selectedSymbol;
  const strategySummary = buildStrategySummaryFromDsl(dbStrategySettings);
  const strategySummaryChips = strategySummary
    ? [
        `유니버스 ${strategySummary.universeName}`,
        ...strategySummary.exitBlocks,
        strategySummary.positionText,
        strategySummary.rebalancingText,
        strategySummary.riskText ? `리스크 관리 ${strategySummary.riskText}` : undefined,
      ].filter((value): value is string => Boolean(value))
    : [];

  const strategies = account.strategyName
    ? [{ name: account.strategyName, status: "active" as const }]
    : [];

  return (
    <DashboardLayout userName="사용자">
      <div className="w-full min-w-0">

        {/* ── 주문 페이지 (종목 선택 시) ── */}
        {shouldShowOrderPage && (
          <div className="space-y-5">
            {selectedSymbol && (
              <div className="flat-card p-5">
                <div className="flex items-center gap-4">
                  <div>
                    <h2 className="text-base font-black text-white">{stockInfo?.name || selectedStockName || selectedSymbol}</h2>
                    <p className="text-xs font-bold text-gray-500">{selectedSymbol}</p>
                  </div>
                  <button
                    onClick={() => { setSelectedSymbol(""); setShowOrderPage(false); }}
                    className="ml-auto text-xs font-bold text-gray-500 hover:text-gray-300 transition-colors duration-200"
                  >
                    ← 돌아가기
                  </button>
                </div>
              </div>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <OrderBook
                symbol={selectedSymbol}
                currentPrice={currentPrice}
                previousClose={stockInfo?.previousClose}
                onPriceSelect={(p) => { setPrice(p.toString()); setSelectedOrderPrice(p); }}
              />
              <div className="flat-card flex flex-col overflow-hidden">
                {/* 탭 */}
                <div className="flex border-b border-white/[0.05]">
                  {(["buy", "sell", "amend", "unfilled", "balance"] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => { setOrderTab(tab); if (tab === "buy" || tab === "sell") setTransactionType(tab); }}
                      className={`px-4 py-3 text-xs font-bold transition-colors duration-200 ${
                        orderTab === tab
                          ? tab === "sell"
                            ? "text-[var(--main-blue)] border-b-2 border-[var(--main-blue)]"
                            : "text-[var(--main-red)] border-b-2 border-[var(--main-red)]"
                          : "text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {tab === "buy" ? "매수" : tab === "sell" ? "매도" : tab === "amend" ? "정정/취소" : tab === "unfilled" ? "미체결" : "잔고"}
                    </button>
                  ))}
                </div>
                <div className="p-5 space-y-4 flex-1 flex flex-col">
                  {/* 현금/신용 */}
                  <div className="flex gap-2">
                    {(["cash", "credit"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setPaymentType(t)}
                        className={`flex-1 px-3 py-1.5 text-xs font-bold rounded-xl transition-all duration-200 ${
                          paymentType === t
                            ? "bg-white/10 text-white"
                            : "bg-white/[0.03] text-gray-400 hover:text-gray-300"
                        }`}
                      >
                        {t === "cash" ? "현금" : "신용"}
                      </button>
                    ))}
                  </div>
                  {/* 주문 유형 */}
                  <select
                    value={orderType}
                    onChange={(e) => setOrderType(e.target.value as any)}
                    className="w-full px-3 py-1.5 text-xs font-bold rounded-xl bg-white/[0.05] text-white border border-white/[0.05] focus:outline-none"
                  >
                    <option value="limit">보통(지정가)</option>
                    <option value="market">시장가</option>
                  </select>
                  {/* 수량 */}
                  <div>
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-widest mb-1.5">수량</label>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setQuantity(q => String(Math.max(0, parseInt(q || "0") - 1)))}
                        className="px-2.5 py-1.5 text-xs font-bold bg-white/[0.05] text-gray-300 rounded-lg hover:bg-white/10 transition-all duration-200"
                      >-</button>
                      <input
                        type="number"
                        value={quantity}
                        onChange={(e) => setQuantity(e.target.value)}
                        className="flex-1 px-3 py-1.5 text-sm font-bold rounded-xl bg-white/[0.05] text-white border border-white/[0.05] focus:outline-none tabular-nums"
                        placeholder="0"
                        min="1"
                      />
                      <button
                        onClick={() => setQuantity(q => String(parseInt(q || "0") + 1))}
                        className="px-2.5 py-1.5 text-xs font-bold bg-white/[0.05] text-gray-300 rounded-lg hover:bg-white/10 transition-all duration-200"
                      >+</button>
                    </div>
                  </div>
                  {/* 가격 */}
                  <div>
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-widest mb-1.5">가격</label>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => { const p = parseFloat(price || "0"); const np = Math.max(0, p - p * 0.01); setPrice(np.toFixed(0)); setSelectedOrderPrice(np); }}
                        className="px-2.5 py-1.5 text-xs font-bold bg-white/[0.05] text-gray-300 rounded-lg hover:bg-white/10 transition-all duration-200"
                      >-</button>
                      <input
                        id="order-price-input"
                        type="number"
                        value={price}
                        onChange={(e) => { setPrice(e.target.value); const np = parseFloat(e.target.value); setSelectedOrderPrice(!isNaN(np) && np > 0 ? np : undefined); }}
                        className="flex-1 px-3 py-1.5 text-sm font-bold rounded-xl bg-white/[0.05] text-white border border-white/[0.05] focus:outline-none tabular-nums"
                        placeholder="0"
                      />
                      <span className="text-xs font-bold text-gray-500">원</span>
                      <button
                        onClick={() => { const p = parseFloat(price || "0"); const np = p + p * 0.01; setPrice(np.toFixed(0)); setSelectedOrderPrice(np); }}
                        className="px-2.5 py-1.5 text-xs font-bold bg-white/[0.05] text-gray-300 rounded-lg hover:bg-white/10 transition-all duration-200"
                      >+</button>
                    </div>
                  </div>
                  {/* 총 거래금액 */}
                  <div className="bg-white/[0.03] rounded-xl p-4 border border-white/[0.05]">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">총 거래금액</span>
                      <span className="text-lg font-black text-white tabular-nums">
                        {quantity && price ? formatPrice(parseFloat(quantity) * parseFloat(price)) : "0"}원
                      </span>
                    </div>
                  </div>
                  {/* 매수/매도 버튼 */}
                  <div className="mt-auto pt-2">
                    <button
                      onClick={handleTransaction}
                      disabled={!selectedSymbol || !quantity || !price}
                      className={`w-full px-4 py-3 rounded-xl text-sm font-bold text-white transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${
                        transactionType === "buy"
                          ? "bg-gradient-to-r from-blue-600 to-blue-500 hover:shadow-[0_0_15px_rgba(59,130,246,0.4)]"
                          : "bg-gradient-to-r from-red-600 to-red-500 hover:shadow-[0_0_15px_rgba(239,68,68,0.4)]"
                      }`}
                    >
                      {paymentType === "cash" ? "현금" : "신용"}{transactionType === "buy" ? "매수" : "매도"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── 메인 대시보드 ── */}
        {!shouldShowOrderPage && (
          <div className="border border-white/[0.08] divide-y divide-white/[0.08]">
            {/* 헤더 */}
            <div className="flex items-center justify-between px-5 py-4">
              <h1 className="text-2xl font-black text-white">{account.name}</h1>
              <button
                onClick={async () => {
                  if (!confirm(`'${account.name}' 계좌를 삭제하시겠습니까?`)) return;
                  await deleteAccount(accountId);
                  router.push("/virtual-account");
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-gray-500 border border-white/[0.08] rounded-xl text-xs font-bold hover:text-[var(--main-red)] hover:border-[var(--main-red)]/30 transition-all duration-200"
              >
                <Trash size={13} />
                삭제
              </button>
            </div>

            {/* 4개 KPI 카드 */}
            <div className="grid grid-cols-2 lg:grid-cols-4 border-t border-l border-white/[0.08]">
              {/* 총 자산 */}
              <div className="border-r border-b border-white/[0.08] p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">총 자산</span>
                  <div className="w-7 h-7 rounded-lg bg-white/[0.05] flex items-center justify-center text-gray-500">
                    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>
                  </div>
                </div>
                <p className="text-2xl font-black text-white tabular-nums leading-none">{formatPrice(account.totalValue)}</p>
                <p className="text-xs font-bold text-gray-500 mt-1">원</p>
              </div>

              {/* 주문 가능 금액 */}
              <div className="border-r border-b border-white/[0.08] p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">주문 가능</span>
                  <div className="w-7 h-7 rounded-lg bg-white/[0.05] flex items-center justify-center text-gray-500">
                    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
                  </div>
                </div>
                <p className="text-2xl font-black text-white tabular-nums leading-none">{formatPrice(account.currentBalance)}</p>
                <p className="text-xs font-bold text-gray-500 mt-1">원</p>
              </div>

              {/* 당일 손익 */}
              <div className="border-r border-b border-white/[0.08] p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">당일 손익</span>
                  <div className="w-7 h-7 rounded-lg bg-white/[0.05] flex items-center justify-center text-gray-500">
                    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
                  </div>
                </div>
                <p className={`text-2xl font-black tabular-nums leading-none ${todayPnl >= 0 ? "text-white" : "text-[var(--main-blue)]"}`}>
                  {todayPnl >= 0 ? "+" : ""}{formatPrice(todayPnl)}
                </p>
                <p className={`text-xs font-bold mt-1 tabular-nums ${todayPnl >= 0 ? "text-gray-500" : "text-[var(--main-blue)]"}`}>
                  {todayPnlPct >= 0 ? "+" : ""}{todayPnlPct.toFixed(2)}% {todayPnl >= 0 ? "▲" : "▼"}
                </p>
              </div>

              {/* 누적 수익률 */}
              <div className="border-r border-b border-white/[0.08] p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-bold text-white uppercase tracking-widest">누적 수익률</span>
                  <div className="w-7 h-7 rounded-lg bg-white/[0.05] flex items-center justify-center text-white">
                    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12h18M3 6h18M3 18h18"/><path d="M5 9v6M9 7v8M13 8v7M17 6v9"/></svg>
                  </div>
                </div>
                <p className="text-2xl font-black tabular-nums leading-none text-white">
                  {profitPercent >= 0 ? "+" : ""}{profitPercent.toFixed(2)}%
                </p>
              </div>

            </div>

            {/* 추적 종목 + 전략 */}
            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px_320px] divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
              {/* 추적 종목 */}
              <div className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="text-base font-black uppercase tracking-widest text-white">추적 종목</span>
                    <p className="text-xs font-bold text-gray-500 mt-0.5">전략이 시그널을 모니터링 중인 종목</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                      {trackedSymbols.length}개
                    </span>
                    <button
                      onClick={() => setIsTrackSearchOpen(true)}
                      className="flex items-center gap-1 text-xs font-bold text-[var(--main-blue)] hover:text-[var(--main-blue)] border border-sky-400/20 px-2.5 py-1 rounded-lg transition-colors duration-200"
                    >
                      <span className="text-sm leading-none">+</span> 종목 추가
                    </button>
                  </div>
                </div>
                {isTrackedSymbolsLoading ? (
                  <TrackedSymbolsSkeleton />
                ) : trackedSymbols.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 gap-3">
                    <TrendUp size={32} className="text-gray-700" weight="thin" />
                    <p className="text-sm font-bold text-gray-600">추적 중인 종목이 없습니다</p>
                    <button
                      onClick={() => setIsTrackSearchOpen(true)}
                      className="text-xs font-bold text-[var(--main-blue)] hover:text-[var(--main-blue)] underline underline-offset-2 transition-colors duration-200"
                    >
                      종목을 직접 추가하기
                    </button>
                  </div>
                ) : (
                  <div>
                    {/* 테이블 헤더 */}
                    <div className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 px-2 py-2 bg-white/[0.06] rounded-lg text-xs font-bold text-gray-400 uppercase tracking-widest">
                      <span>종목</span>
                      <span className="text-right">현재가</span>
                      <span className="text-right">등락률</span>
                      <span className="text-right">거래량</span>
                      <span className="text-center">상태</span>
                      <span />
                    </div>
                    {/* 테이블 행 */}
                    <div className="max-h-64 overflow-y-auto scrollbar-hide">
                      {trackedSymbols.map(({ symbol, name }) => {
                        const q = trackedPrices[symbol];
                        const holding = holdings.find((h) => h.symbol === symbol);
                        return (
                          <TrackedSymbolRow
                            key={symbol}
                            symbol={symbol}
                            name={name}
                            quote={q}
                            hasHolding={!!holding}
                            onSelect={handleStockSelect}
                            onRemove={handleRemoveTrackedSymbol}
                            formatPrice={formatPrice}
                          />
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* 운용 중인 전략 */}
              <div className="p-5 flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-base font-black uppercase tracking-widest text-white">운용 전략</span>
                </div>

                {account.strategyName && (
                  <div className="mb-3">
                    <div className="p-3 bg-white/[0.03] border border-white/[0.05] rounded-xl">
                      <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2">매매 방식</p>
                      <div className="flex gap-2">
                        <button
                          onClick={async () => { const u = await updateTradingMode(accountId, "auto"); setAccount(prev => prev ? { ...prev, tradingMode: u.tradingMode } : prev); }}
                          className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-lg text-xs font-bold transition-all duration-200 ${account.tradingMode === "auto" ? "bg-white/10 text-white" : "bg-white/[0.03] text-gray-400 hover:text-gray-300"}`}
                        >
                          <Robot size={13} />자동매매
                        </button>
                        <button
                          onClick={async () => { const u = await updateTradingMode(accountId, "manual"); setAccount(prev => prev ? { ...prev, tradingMode: u.tradingMode } : prev); }}
                          className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-lg text-xs font-bold transition-all duration-200 ${account.tradingMode !== "auto" ? "bg-white/10 text-white" : "bg-white/[0.03] text-gray-400 hover:text-gray-300"}`}
                        >
                          <Bell size={13} />신호 알림
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="flex-1 space-y-3">
                  {strategies.map((strategy, idx) => {
                    const isAccountStrategy = strategy.name === account.strategyName;
                    const description = isAccountStrategy
                      ? dbStrategyDescription
                      : (getStrategyByName(strategy.name)?.description ?? null);
                    return (
                      <div key={idx} className="bg-white/[0.03] border border-white/[0.05] rounded-xl p-4">
                        <div className="flex items-center justify-between gap-3 mb-3">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-sm font-bold text-white truncate max-w-[140px]">{strategy.name}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            {description && (
                              <button
                                type="button"
                                onClick={() => setIsPromptVisible((prev) => !prev)}
                                className="shrink-0 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[11px] font-bold text-gray-300 transition-all duration-200 hover:bg-white/[0.08] hover:text-white"
                              >
                                {isPromptVisible ? "프롬프트 숨기기" : "프롬프트 보기"}
                              </button>
                            )}
                            {strategy.status !== "active" && (
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white/[0.05] text-gray-500">
                                대기
                              </span>
                            )}
                          </div>
                        </div>
                        {strategySummaryChips.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {strategySummaryChips.map((chip) => (
                              <span
                                key={chip}
                                className="rounded-xl border border-[#2b4471] bg-[#1a2233] px-3 py-2 text-xs font-bold text-gray-200"
                              >
                                {chip}
                              </span>
                            ))}
                          </div>
                        )}
                        {isPromptVisible && description && (
                          <div className="mt-3 rounded-xl border border-white/[0.05] bg-black/10 p-3">
                            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">사용자 프롬프트</p>
                            <p className="text-xs font-bold text-gray-500 leading-6 whitespace-pre-wrap">{description}</p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <button
                  onClick={() => setIsStrategyReplaceOpen(true)}
                  className="mt-4 w-full py-2.5 text-xs font-bold text-white bg-white/[0.06] border border-white/[0.08] rounded-xl hover:bg-white/[0.1] hover:border-white/[0.15] transition-all duration-200"
                >
                  전략 교체
                </button>
              </div>

              <div className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="text-base font-black uppercase tracking-widest text-white">매매 신호</span>
                    <p className="text-xs font-bold text-gray-500 mt-0.5">최근 발생한 전략 신호</p>
                  </div>
                  <span className="text-xs font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                    {signalLogs.length}건
                  </span>
                </div>
                <div className="max-h-[420px] overflow-y-auto pr-1 scrollbar-hide">
                  <SignalLog logs={signalLogs} />
                </div>
              </div>
            </div>

            {/* 보유 자산 / 거래내역 / 성과분석 탭 */}
            <div className="p-5">
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1">
                    {(["holdings", "transactions", "performance"] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all duration-200 ${
                          activeTab === tab
                            ? "bg-white/[0.08] text-white"
                            : "text-gray-500 hover:text-gray-300"
                        }`}
                      >
                        {tab === "holdings" ? "보유 종목" : tab === "transactions" ? "거래 내역" : "성과 분석"}
                      </button>
                    ))}
                  </div>
                  {activeTab === "holdings" && (
                    <span className="text-[10px] font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                      {holdings.length}개 포지션 활성
                    </span>
                  )}
                </div>
                <button
                  onClick={() => setIsSearchOpen(true)}
                  className="flex items-center gap-1.5 text-xs font-bold text-[var(--main-blue)] hover:text-[var(--main-blue)] transition-colors duration-200"
                >
                  <MagnifyingGlass size={13} />종목 검색
                </button>
              </div>

              {/* 보유 자산 */}
              {activeTab === "holdings" && (
                holdings.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-3">
                    <p className="text-sm font-bold text-gray-600">보유 중인 종목이 없습니다.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="bg-white/[0.06] rounded-lg">
                          <th className="text-left text-xs font-bold text-gray-400 uppercase tracking-widest py-2 pr-4 pl-2 rounded-l-lg">종목명 / 티커</th>
                          <th className="text-right text-xs font-bold text-gray-400 uppercase tracking-widest py-2 px-4">평균 단가</th>
                          <th className="text-right text-xs font-bold text-gray-400 uppercase tracking-widest py-2 px-4">현재가</th>
                          <th className="text-right text-xs font-bold text-gray-400 uppercase tracking-widest py-2 px-4">수량</th>
                          <th className="text-right text-xs font-bold text-gray-400 uppercase tracking-widest py-2 px-4">수익률</th>
                          <th className="text-right text-xs font-bold text-gray-400 uppercase tracking-widest py-2 pl-4 pr-2 rounded-r-lg">평가 손익</th>
                        </tr>
                      </thead>
                      <tbody>
                        {holdings.map((h, idx) => {
                          const isPos = h.profitPercent >= 0;
                          return (
                            <tr
                              key={h.symbol}
                              onClick={() => handleStockSelect(h.symbol, h.name || h.symbol)}
                              className="hover:bg-white/[0.02] cursor-pointer transition-colors duration-150"
                            >
                              <td className="py-4 pr-4">
                                <div className="flex items-center">
                                  <div>
                                    <p className="text-sm font-bold text-white">{h.name || h.symbol}</p>
                                    <p className="text-[10px] font-bold text-gray-500">{h.symbol}</p>
                                  </div>
                                </div>
                              </td>
                              <td className="py-4 px-4 text-right text-sm font-bold text-gray-400 tabular-nums">{formatPrice(h.averagePrice)}</td>
                              <td className="py-4 px-4 text-right text-sm font-black text-white tabular-nums">{formatPrice(h.currentPrice)}</td>
                              <td className="py-4 px-4 text-right text-sm font-bold text-gray-400 tabular-nums">{h.quantity.toLocaleString()}</td>
                              <td className={`py-4 px-4 text-right text-sm font-black tabular-nums ${isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                {isPos ? "+" : ""}{h.profitPercent.toFixed(2)}%
                              </td>
                              <td className={`py-4 pl-4 text-right text-sm font-black tabular-nums ${isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                {isPos ? "+" : "-"}{formatPrice(Math.abs(h.profit))}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )
              )}

              {/* 거래 내역 */}
              {activeTab === "transactions" && (
                transactions.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-3">
                    <p className="text-sm font-bold text-gray-600">거래 내역이 없습니다.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="bg-white/[0.06]">
                          {["종목", "구분", "체결가", "수량", "거래금액", "수수료", "실현손익", "체결시각"].map((h, i, arr) => (
                            <th key={h} className={`text-xs font-bold text-gray-400 uppercase tracking-widest py-2 px-3 first:pl-2 last:pr-2 text-right first:text-left ${i === 0 ? "rounded-l-lg" : ""} ${i === arr.length - 1 ? "rounded-r-lg" : ""}`}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {transactions.map((t) => (
                          <tr key={t.id} className="hover:bg-white/[0.02] transition-colors duration-150">
                            <td className="py-3 pl-0 pr-3">
                              <p className="text-sm font-bold text-white">{t.name}</p>
                              <p className="text-[10px] font-bold text-gray-500">{t.symbol}</p>
                            </td>
                            <td className="py-3 px-3 text-right">
                              <span className={`text-[10px] font-black px-2 py-0.5 rounded-md ${
                                t.type === "buy"
                                  ? "bg-sky-500/15 text-[var(--main-blue)]"
                                  : "bg-[var(--main-blue)]/10 text-[var(--main-blue)]"
                              }`}>
                                {t.type === "buy" ? "매수" : "매도"}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-right text-sm font-bold text-white tabular-nums">{formatPrice(t.filledPrice ?? t.price)}</td>
                            <td className="py-3 px-3 text-right text-sm font-bold text-gray-400 tabular-nums">{t.quantity}주</td>
                            <td className="py-3 px-3 text-right text-sm font-bold text-white tabular-nums">{formatPrice(t.totalAmount)}</td>
                            <td className="py-3 px-3 text-right text-sm font-bold text-gray-500 tabular-nums">{t.fee != null ? `-${formatPrice(t.fee)}` : "-"}</td>
                            <td className="py-3 px-3 text-right">
                              {t.realizedPnl != null ? (
                                <span className={`text-sm font-black tabular-nums ${t.realizedPnl >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                  {t.realizedPnl >= 0 ? "+" : ""}{formatPrice(Math.round(t.realizedPnl))}
                                </span>
                              ) : <span className="text-sm font-bold text-gray-600">-</span>}
                            </td>
                            <td className="py-3 pl-3 pr-0 text-right text-[10px] font-bold text-gray-500">
                              {new Date(t.filledAt ?? t.timestamp).toLocaleString("ko-KR")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              )}

              {/* 성과 분석 */}
              {activeTab === "performance" && (
                <div className="space-y-6">
                  <div>
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <span className="text-base font-black uppercase tracking-widest text-white block">전략 성과 현황</span>
                        <p className="text-xs font-bold text-gray-500 mt-0.5">성과 분석 및 벤치마크 대비 추이</p>
                      </div>
                      <span className="flex items-center gap-1.5 text-xs font-bold text-gray-500">
                        <span className="w-2 h-2 rounded-full bg-gray-600 inline-block" />벤치마크 (KOSPI 200)
                      </span>
                    </div>
                    <div className="h-64">
                      <PortfolioPerformanceChart data={performanceData} />
                    </div>
                  </div>
                  <div className="border-t border-white/[0.05]" />
                  <VirtualTradingDashboard accountId={accountId} initialAmount={account.initialAmount} />
                </div>
              )}
            </div>
          </div>
        )}

        <StockSearchModal
          isOpen={isSearchOpen}
          onClose={() => setIsSearchOpen(false)}
          onSelect={(items) => { if (items.length > 0) { handleStockSelect(items[0].symbol, items[0].name); setIsSearchOpen(false); } }}
          singleSelect={true}
        />

        <StockSearchModal
          isOpen={isTrackSearchOpen}
          onClose={() => setIsTrackSearchOpen(false)}
          onSelect={handleAddTrackedSymbols}
        />

        <StrategyReplaceModal
          isOpen={isStrategyReplaceOpen}
          currentStrategyId={account?.strategyId}
          currentStrategyName={account?.strategyName}
          onClose={() => setIsStrategyReplaceOpen(false)}
          onReplace={async (strategy) => {
            const updated = await updateAccountStrategy(accountId, strategy.id, strategy.name);
            setAccount((prev) =>
              prev
                ? {
                    ...prev,
                    strategyId: updated.strategyId,
                    strategyName: updated.strategyName,
                  }
                : prev
            );
            setDbStrategyDescription(strategy.description ?? null);
            setDbStrategySettings(strategy as StrategyDSL);
            setIsPromptVisible(false);
            await loadAccountData();
          }}
        />
      </div>
    </DashboardLayout>
  );
}
