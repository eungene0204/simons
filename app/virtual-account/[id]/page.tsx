"use client";

import { useState, useEffect, useMemo, useRef } from "react";
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
import { MagnifyingGlass, Robot, Bell, Trash, TrendUp, ArrowUpRight, ArrowDownRight } from "phosphor-react";
import StockSearchModal from "@/components/stock/StockSearchModal";
import OrderBook from "@/components/order/OrderBook";
import PortfolioPerformanceChart, { PerformancePoint } from "@/components/portfolio/PortfolioPerformanceChart";
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
  const [promptPos, setPromptPos] = useState<{ top: number; right: number } | null>(null);
  const promptButtonRef = useRef<HTMLButtonElement>(null);

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
    if (!isPromptVisible) return;
    const close = () => setIsPromptVisible(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [isPromptVisible]);

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
        if (data.name) setSelectedStockName(data.name);
      })
      .catch(() => {});
  }, [selectedSymbol]);

  useEffect(() => {
    setIsPromptVisible(false);
  }, [account?.strategyId]);

  const loadAccountData = async () => {
    const [acc, t, marketState] = await Promise.all([
      getAccount(accountId),
      getTransactionsByAccount(accountId),
      fetch(`/api/virtual-market/${accountId}`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ]);
    if (!acc) { router.push("/virtual-account"); return; }
    setAccount(acc);
    setHoldings((acc as any).holdings ?? []);
    setTransactions(t.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()));

    const nextTrackedSymbols = marketState?.symbols?.length
      ? marketState.symbols.map((sym: string) => ({
          symbol: sym,
          name: marketState.symbolNames?.[sym] || sym,
        }))
      : [];
    setTrackedSymbols(nextTrackedSymbols);
    setIsTrackedSymbolsLoading(false);

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

  const {
    profit,
    profitPercent,
    todayPnl,
    todayPnlPct,
    performanceData,
    activeDays,
    investedValue,
    cashRatio,
    filledTradeCount,
  } = useMemo(() => {
    if (!account) {
      return {
        profit: 0, profitPercent: 0, todayPnl: 0, todayPnlPct: 0,
        performanceData: [], activeDays: 0, investedValue: 0, cashRatio: 0, filledTradeCount: 0,
      };
    }
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
    const investedValue = Math.max(0, account.totalValue - account.currentBalance);
    const cashRatio = account.totalValue > 0 ? (account.currentBalance / account.totalValue) * 100 : 0;
    const filledTradeCount = transactions.filter((t) => t.status === "FILLED").length;
    return { profit: p, profitPercent: pp, todayPnl, todayPnlPct, performanceData, activeDays: days, investedValue, cashRatio, filledTradeCount };
  }, [account, transactions]);

  if (!account) {
    return (
      <DashboardLayout userName="사용자">
        <div className="p-4 flex flex-col items-center justify-center min-h-48 gap-3">
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

  const HOLDINGS_COLS = "grid-cols-[minmax(0,1fr)_100px_100px_56px_88px_110px]";
  const TXN_COLS = "grid-cols-[minmax(0,1fr)_56px_100px_56px_110px_88px_100px_130px]";

  return (
    <DashboardLayout userName="사용자">
      <div className="w-full min-w-0">

        {/* ── 주문 패널 ── */}
        {shouldShowOrderPage && (
          <div className="w-full min-w-0 border border-white/[0.08]">
            <div className="divide-y divide-white/[0.08]">
              {/* 종목 헤더 */}
              {selectedSymbol && (
                <div className="flex items-center justify-between px-5 py-4">
                  <div>
                    <h2 className="text-base font-black text-white font-outfit">
                      {stockInfo?.name || selectedStockName || selectedSymbol}
                    </h2>
                    <p className="text-xs font-bold text-gray-500 mt-0.5">{selectedSymbol}</p>
                  </div>
                  <button
                    onClick={() => { setSelectedSymbol(""); setShowOrderPage(false); }}
                    className="text-xs font-bold text-gray-500 hover:text-gray-300 transition-colors duration-200"
                  >
                    ← 돌아가기
                  </button>
                </div>
              )}
              {/* 주문 패널 본문 */}
              <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
                <div className="lg:col-span-6 p-5">
                  <OrderBook
                    symbol={selectedSymbol}
                    currentPrice={currentPrice}
                    previousClose={stockInfo?.previousClose}
                    onPriceSelect={(p) => { setPrice(p.toString()); setSelectedOrderPrice(p); }}
                  />
                </div>
                <div className="lg:col-span-4 flex flex-col">
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
                        <span className="text-lg font-black text-white tabular-nums font-outfit">
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
          </div>
        )}

        {/* ── 메인 대시보드 ── */}
        {!shouldShowOrderPage && (
          <div className="w-full min-w-0 border border-white/[0.08]">
            <div className="divide-y divide-white/[0.08]">

              {/* 헤더 */}
              <div className="flex items-center justify-between px-5 py-4">
                <div className="flex items-center gap-4">
                  <h1 className="text-2xl font-black text-white font-outfit">{account.name}</h1>
                  <div className="flex items-center border border-white/[0.08] rounded-lg overflow-hidden">
                    <button
                      onClick={async () => {
                        const u = await updateTradingMode(accountId, "auto");
                        setAccount(prev => prev ? { ...prev, tradingMode: u.tradingMode } : prev);
                      }}
                      className={`flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold transition-colors duration-200 ${
                        account.tradingMode === "auto"
                          ? "bg-white/[0.08] text-white"
                          : "bg-transparent text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      <Robot size={11} weight="bold" />
                      자동매매
                    </button>
                    <div className="w-px h-4 bg-white/[0.08]" />
                    <button
                      onClick={async () => {
                        const u = await updateTradingMode(accountId, "manual");
                        setAccount(prev => prev ? { ...prev, tradingMode: u.tradingMode } : prev);
                      }}
                      className={`flex items-center gap-1 px-2.5 py-1 text-[11px] font-bold transition-colors duration-200 ${
                        account.tradingMode !== "auto"
                          ? "bg-white/[0.08] text-white"
                          : "bg-transparent text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      <Bell size={11} weight="bold" />
                      신호 알림
                    </button>
                  </div>
                  <span className="text-[11px] font-bold text-gray-600">
                    개설 {new Date(account.createdAt).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" })}
                  </span>
                </div>
                <button
                  onClick={async () => {
                    if (!confirm(`'${account.name}' 계좌를 삭제하시겠습니까?`)) return;
                    await deleteAccount(accountId);
                    router.push("/virtual-account");
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 border border-white/[0.08] rounded-xl text-xs font-bold text-gray-500 hover:text-[var(--main-red)] hover:border-[var(--main-red)]/30 transition-all duration-200"
                >
                  <Trash size={13} />
                  삭제
                </button>
              </div>

              {/* KPI 4개 */}
              <div className="grid grid-cols-2 lg:grid-cols-4 border-t border-l border-white/[0.08]">
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">총 자산</span>
                  <p className="mt-2 text-2xl font-black text-white tabular-nums font-outfit leading-none">
                    {formatPrice(account.totalValue)}
                  </p>
                  <p className="mt-1 text-[10px] font-bold text-gray-500">원</p>
                </div>
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">주문 가능</span>
                  <p className="mt-2 text-2xl font-black text-white tabular-nums font-outfit leading-none">
                    {formatPrice(account.currentBalance)}
                  </p>
                  <p className="mt-1 text-[10px] font-bold text-gray-500">원</p>
                </div>
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">당일 손익</span>
                  <p className={`mt-2 text-2xl font-black tabular-nums font-outfit leading-none ${todayPnl >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                    {todayPnl >= 0 ? "+" : ""}{formatPrice(todayPnl)}
                  </p>
                  <p className={`mt-1 text-[10px] font-bold tabular-nums ${todayPnl >= 0 ? "text-gray-500" : "text-[var(--main-blue)]"}`}>
                    {todayPnlPct >= 0 ? "+" : ""}{todayPnlPct.toFixed(2)}%
                  </p>
                </div>
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">누적 수익률</span>
                  <p className={`mt-2 text-2xl font-black tabular-nums font-outfit leading-none ${profitPercent >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                    {profitPercent >= 0 ? "+" : ""}{profitPercent.toFixed(2)}%
                  </p>
                  <p className="mt-1 text-[10px] font-bold text-gray-500">초기 자본 대비</p>
                </div>
              </div>

              {/* 추적 종목 + 운용 전략 + 매매 신호 */}
              <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.3fr)_280px_minmax(0,0.7fr)] divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">

                {/* 추적 종목 */}
                <div className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">추적 종목</h2>
                      <p className="text-xs text-gray-500 mt-0.5">전략이 시그널을 모니터링 중인 종목</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                        {trackedSymbols.length}개
                      </span>
                      <button
                        onClick={() => setIsTrackSearchOpen(true)}
                        className="flex items-center gap-1 text-xs font-bold text-[var(--main-blue)] border border-sky-400/20 px-2.5 py-1 rounded-lg hover:border-sky-400/40 transition-colors duration-200"
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
                        className="text-xs font-bold text-[var(--main-blue)] underline underline-offset-2 transition-colors duration-200"
                      >
                        종목을 직접 추가하기
                      </button>
                    </div>
                  ) : (
                    <div>
                      {/* 테이블 헤더 */}
                      <div className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 px-1 mb-1">
                        {["종목", "현재가", "등락률", "거래량", "상태", ""].map((h) => (
                          <span key={h} className={`text-xs font-bold uppercase tracking-widest text-gray-600 ${h === "현재가" || h === "등락률" || h === "거래량" ? "text-right" : h === "상태" ? "text-center" : ""}`}>
                            {h}
                          </span>
                        ))}
                      </div>
                      <div className="border-t border-white/[0.05] mb-1" />
                      {/* 테이블 행 */}
                      <div className="max-h-64 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                        <div className="divide-y divide-white/[0.04]">
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
                    </div>
                  )}
                </div>

                {/* 운용 전략 */}
                <div className="p-5 flex flex-col">
                  <div className="flex items-center justify-between mb-5">
                    <div>
                      <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">운용 전략</h2>
                      <p className="text-xs text-gray-500 mt-0.5">현재 계좌에 적용된 매매 전략</p>
                    </div>
                    <button
                      onClick={() => setIsStrategyReplaceOpen(true)}
                      className="text-xs font-bold text-gray-400 hover:text-white transition-colors duration-200"
                    >
                      전략 교체
                    </button>
                  </div>
                  <div className="flex-1 min-h-0 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent space-y-3">
                    {strategies.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full gap-2">
                        <p className="text-sm font-bold text-gray-600">연결된 전략이 없습니다</p>
                        <button
                          onClick={() => setIsStrategyReplaceOpen(true)}
                          className="text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          전략 연결하기
                        </button>
                      </div>
                    ) : (
                      strategies.map((strategy, idx) => {
                        const isAccountStrategy = strategy.name === account.strategyName;
                        const description = isAccountStrategy ? dbStrategyDescription : null;
                        return (
                          <div key={idx} className="py-3">
                            {description && (
                              <div className="flex justify-start mb-3">
                                <div className="relative shrink-0">
                                  <button
                                    ref={promptButtonRef}
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      if (!isPromptVisible && promptButtonRef.current) {
                                        const rect = promptButtonRef.current.getBoundingClientRect();
                                        setPromptPos({ top: rect.bottom + 8, right: window.innerWidth - rect.right });
                                      }
                                      setIsPromptVisible((prev) => !prev);
                                    }}
                                    className="inline-flex items-center rounded-md bg-white/[0.06] hover:bg-white/[0.1] px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-gray-400 hover:text-gray-200 transition-colors duration-200"
                                  >
                                    프롬프트
                                  </button>
                                </div>
                              </div>
                            )}
                            {strategySummaryChips.length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {strategySummaryChips.map((chip) => (
                                  <span
                                    key={chip}
                                    className="inline-flex items-center rounded-md bg-white/[0.06] px-2.5 py-1 text-xs font-bold text-yellow-500"
                                  >
                                    {chip}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* 매매 신호 */}
                <div className="p-5 flex flex-col max-h-[385px]">
                  <div className="flex items-center justify-between mb-4 shrink-0">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">매매 신호</h2>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">최근 발생한 전략 신호</p>
                    </div>
                    <span className="text-xs font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                      {signalLogs.length}건
                    </span>
                  </div>
                  <div className="overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                    <SignalLog logs={signalLogs} />
                  </div>
                </div>
              </div>

              {/* 보유 종목 / 거래 내역 / 성과 분석 탭 */}
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
                        {holdings.length}개 포지션
                      </span>
                    )}
                    {activeTab === "transactions" && (
                      <span className="text-[10px] font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                        {transactions.length}건
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => setIsSearchOpen(true)}
                    className="flex items-center gap-1.5 text-xs font-bold text-[var(--main-blue)] hover:text-sky-300 transition-colors duration-200"
                  >
                    <MagnifyingGlass size={13} weight="bold" />종목 검색
                  </button>
                </div>

                {/* 보유 종목 */}
                {activeTab === "holdings" && (
                  holdings.length === 0 ? (
                    <div className="py-12 text-center">
                      <p className="text-sm font-bold text-gray-600">보유 중인 종목이 없습니다.</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      {/* 헤더 */}
                      <div className={`grid ${HOLDINGS_COLS} gap-2 px-2 mb-1`}>
                        {["종목", "평균 단가", "현재가", "수량", "수익률", "평가 손익"].map((h, i) => (
                          <span key={h} className={`text-xs font-bold uppercase tracking-widest text-gray-600 ${i > 0 ? "text-right" : ""}`}>
                            {h}
                          </span>
                        ))}
                      </div>
                      <div className="border-t border-white/[0.05] mb-1" />
                      {/* 행 */}
                      <div className="max-h-[360px] overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                        <div className="divide-y divide-white/[0.04]">
                          {holdings.map((h) => {
                            const isPos = h.profitPercent >= 0;
                            return (
                              <div
                                key={h.symbol}
                                onClick={() => handleStockSelect(h.symbol, h.name || h.symbol)}
                                className={`grid ${HOLDINGS_COLS} gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors duration-150 cursor-pointer`}
                              >
                                <div className="min-w-0">
                                  <p className="text-sm font-bold text-white truncate">{h.name || h.symbol}</p>
                                  <p className="text-[10px] font-bold text-gray-500">{h.symbol}</p>
                                </div>
                                <p className="text-sm font-bold text-gray-400 tabular-nums text-right">{formatPrice(h.averagePrice)}</p>
                                <p className="text-sm font-black text-white tabular-nums text-right">{formatPrice(h.currentPrice)}</p>
                                <p className="text-sm font-bold text-gray-400 tabular-nums text-right">{h.quantity.toLocaleString()}</p>
                                <div className={`flex items-center justify-end gap-0.5 ${isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                  {isPos ? <ArrowUpRight size={11} weight="bold" /> : <ArrowDownRight size={11} weight="bold" />}
                                  <span className="text-xs font-black tabular-nums font-outfit">{isPos ? "+" : ""}{h.profitPercent.toFixed(2)}%</span>
                                </div>
                                <p className={`text-sm font-black tabular-nums text-right ${isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                  {isPos ? "+" : "-"}{formatPrice(Math.abs(h.profit))}
                                </p>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )
                )}

                {/* 거래 내역 */}
                {activeTab === "transactions" && (
                  transactions.length === 0 ? (
                    <div className="py-12 text-center">
                      <p className="text-sm font-bold text-gray-600">거래 내역이 없습니다.</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      {/* 헤더 */}
                      <div className={`grid ${TXN_COLS} gap-2 px-2 mb-1`}>
                        {["종목", "구분", "체결가", "수량", "거래금액", "수수료", "실현손익", "체결시각"].map((h, i) => (
                          <span key={h} className={`text-xs font-bold uppercase tracking-widest text-gray-600 ${i > 0 ? "text-right" : ""}`}>
                            {h}
                          </span>
                        ))}
                      </div>
                      <div className="border-t border-white/[0.05] mb-1" />
                      {/* 행 */}
                      <div className="max-h-[360px] overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                        <div className="divide-y divide-white/[0.04]">
                          {transactions.map((t) => (
                            <div
                              key={t.id}
                              className={`grid ${TXN_COLS} gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors duration-150`}
                            >
                              <div className="min-w-0">
                                <p className="text-sm font-bold text-white truncate">{t.name}</p>
                                <p className="text-[10px] font-bold text-gray-500">{t.symbol}</p>
                              </div>
                              <div className="text-right">
                                <span className={`text-xs font-black px-1.5 py-0.5 rounded-md ${
                                  t.type === "buy"
                                    ? "bg-[var(--main-red)]/15 text-[var(--main-red)]"
                                    : "bg-[var(--main-blue)]/15 text-[var(--main-blue)]"
                                }`}>
                                  {t.type === "buy" ? "매수" : "매도"}
                                </span>
                              </div>
                              <p className="text-sm font-bold text-white tabular-nums text-right">{formatPrice(t.filledPrice ?? t.price)}</p>
                              <p className="text-sm font-bold text-gray-400 tabular-nums text-right">{t.quantity}</p>
                              <p className="text-sm font-bold text-white tabular-nums text-right">{formatPrice(t.totalAmount)}</p>
                              <p className="text-sm font-bold text-gray-500 tabular-nums text-right">{t.fee != null ? `-${formatPrice(t.fee)}` : "—"}</p>
                              <div className="text-right">
                                {t.realizedPnl != null ? (
                                  <span className={`text-sm font-black tabular-nums ${t.realizedPnl >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                    {t.realizedPnl >= 0 ? "+" : ""}{formatPrice(Math.round(t.realizedPnl))}
                                  </span>
                                ) : (
                                  <span className="text-sm font-bold text-gray-600">—</span>
                                )}
                              </div>
                              <p className="text-xs font-bold text-gray-500 text-right">
                                {new Date(t.filledAt ?? t.timestamp).toLocaleString("ko-KR")}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )
                )}

                {/* 성과 분석 */}
                {activeTab === "performance" && (
                  <div className="border border-white/[0.08]">
                    <div className="divide-y divide-white/[0.08]">
                      {/* 성과 KPI 6개 */}
                      <div className="grid grid-cols-2 xl:grid-cols-6 border-l border-t border-white/[0.08]">
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">누적 평가손익</p>
                          <p className={`mt-2 text-2xl font-black font-outfit tabular-nums leading-none ${profit >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {profit >= 0 ? "+" : "-"}{formatPrice(Math.abs(profit))}
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">초기 자본 대비</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">누적 수익률</p>
                          <p className={`mt-2 text-2xl font-black font-outfit tabular-nums leading-none ${profitPercent >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {profitPercent >= 0 ? "+" : ""}{profitPercent.toFixed(2)}%
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">현재 총 자산 기준</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">당일 실현손익</p>
                          <p className={`mt-2 text-2xl font-black font-outfit tabular-nums leading-none ${todayPnl >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {todayPnl >= 0 ? "+" : "-"}{formatPrice(Math.abs(todayPnl))}
                          </p>
                          <p className={`mt-1 text-[10px] font-bold tabular-nums ${todayPnl >= 0 ? "text-gray-500" : "text-[var(--main-blue)]"}`}>
                            {todayPnlPct >= 0 ? "+" : ""}{todayPnlPct.toFixed(2)}%
                          </p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">운용 기간</p>
                          <p className="mt-2 text-2xl font-black font-outfit tabular-nums leading-none text-white">
                            {formatCompact(activeDays)}
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">일 기준</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">체결 거래</p>
                          <p className="mt-2 text-2xl font-black font-outfit tabular-nums leading-none text-white">
                            {formatCompact(filledTradeCount)}
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">누적 체결 건수</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">현금 비중</p>
                          <p className="mt-2 text-2xl font-black font-outfit tabular-nums leading-none text-white">
                            {cashRatio.toFixed(1)}%
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">주문 가능 금액</p>
                        </div>
                      </div>

                      {/* 성과 차트 + 분석 요약 */}
                      <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
                        <div className="lg:col-span-7 p-5">
                          <div className="flex items-start justify-between gap-4 mb-5">
                            <div>
                              <h2 className="text-base font-black uppercase tracking-widest font-outfit text-white">성과 추이</h2>
                              <p className="mt-0.5 text-xs font-bold text-gray-500">계좌 개설 이후 누적 성과 흐름</p>
                            </div>
                          </div>
                          <div className="h-72">
                            <PortfolioPerformanceChart data={performanceData} />
                          </div>
                        </div>
                        <div className="lg:col-span-3 p-5">
                          <div className="mb-5">
                            <h2 className="text-base font-black uppercase tracking-widest font-outfit text-white">분석 요약</h2>
                            <p className="mt-0.5 text-xs font-bold text-gray-500">성과 해석에 필요한 현재 상태</p>
                          </div>
                          <div className="divide-y divide-white/[0.08] border-y border-white/[0.08]">
                            <div className="py-3">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-600">계좌 개설일</p>
                              <p className="mt-1 text-sm font-black text-white">{new Date(account.createdAt).toLocaleDateString("ko-KR")}</p>
                            </div>
                            <div className="py-3">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-600">초기 투자금</p>
                              <p className="mt-1 text-sm font-black font-outfit tabular-nums text-white">{formatPrice(account.initialAmount)}원</p>
                            </div>
                            <div className="py-3">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-600">현재 투자 금액</p>
                              <p className="mt-1 text-sm font-black font-outfit tabular-nums text-white">{formatPrice(investedValue)}원</p>
                            </div>
                            <div className="py-3">
                              <p className="text-xs font-bold uppercase tracking-widest text-gray-600">보유 종목 수</p>
                              <p className="mt-1 text-sm font-black font-outfit tabular-nums text-white">{holdings.length}개</p>
                            </div>
                          </div>
                          <div className="mt-5 space-y-2">
                            <span className="inline-flex items-center rounded-md bg-white/[0.06] px-2.5 py-1 text-xs font-bold text-gray-400">
                              벤치마크: KOSPI 200
                            </span>
                            <p className="text-xs font-bold leading-5 text-gray-500">
                              성과 차트는 계좌 개설일부터 누적 흐름을 기준으로 표시됩니다.
                            </p>
                          </div>
                        </div>
                      </div>

                      {/* 세부 성과 리포트 */}
                      <div className="p-5">
                        <div className="flex items-start justify-between gap-4 mb-4">
                          <div>
                            <h2 className="text-base font-black uppercase tracking-widest font-outfit text-white">세부 성과 리포트</h2>
                            <p className="mt-0.5 text-xs font-bold text-gray-500">실현 손익, 승률, 일별 PnL, 종목별 성과</p>
                          </div>
                          <span className="inline-flex items-center rounded-md bg-white/[0.06] px-2.5 py-1 text-xs font-bold text-gray-400">
                            DETAIL
                          </span>
                        </div>
                        <VirtualTradingDashboard accountId={accountId} initialAmount={account.initialAmount} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
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
        {isPromptVisible && promptPos && dbStrategyDescription && (
          <div
            className="fixed z-[100] w-64 rounded-xl border border-white/[0.08] bg-[#1c1c1c] p-3 shadow-2xl"
            style={{ top: promptPos.top, right: promptPos.right }}
          >
            <p className="text-xs font-bold leading-5 text-gray-400 whitespace-pre-wrap">{dbStrategyDescription}</p>
            <div className="absolute -top-[5px] right-3.5 w-2.5 h-2.5 rotate-45 bg-[#1c1c1c] border-l border-t border-white/[0.08]" />
          </div>
        )}
        <StrategyReplaceModal
          isOpen={isStrategyReplaceOpen}
          currentStrategyId={account?.strategyId}
          currentStrategyName={account?.strategyName}
          onClose={() => setIsStrategyReplaceOpen(false)}
          onReplace={async (strategy) => {
            const updated = await updateAccountStrategy(accountId, strategy.id, strategy.name);
            setAccount((prev) =>
              prev
                ? { ...prev, strategyId: updated.strategyId, strategyName: updated.strategyName }
                : prev
            );
            setDbStrategyDescription(strategy.description ?? null);
            setDbStrategySettings(strategy as unknown as StrategyDSL);
            setIsPromptVisible(false);
            await loadAccountData();
          }}
        />
      </div>
    </DashboardLayout>
  );
}
