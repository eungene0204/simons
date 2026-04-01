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
  deleteAccount,
} from "@/lib/portfolio";
import { MagnifyingGlass, Robot, Bell, Trash, X } from "phosphor-react";
import StockSearchModal from "@/components/stock/StockSearchModal";
import OrderBook from "@/components/order/OrderBook";
import type { BatchQuoteItem } from "@/app/api/stock/batch-quotes/route";
import PortfolioPerformanceChart, { PerformancePoint } from "@/components/portfolio/PortfolioPerformanceChart";
import { getStrategyByName } from "@/lib/strategy-groups";
import { TrendUp } from "phosphor-react";

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
  const [trackedSymbols, setTrackedSymbols] = useState<{ symbol: string; name: string }[]>([]);
  const [trackedPrices, setTrackedPrices] = useState<Record<string, BatchQuoteItem>>({});
  const [isTrackSearchOpen, setIsTrackSearchOpen] = useState(false);

  const fetchTrackedPrices = async (symbols: string[]) => {
    if (symbols.length === 0) return;
    try {
      const res = await fetch("/api/stock/batch-quotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols }),
      });
      if (res.ok) {
        const data: Record<string, BatchQuoteItem> = await res.json();
        // price>0인 항목만 업데이트, 0이면 마지막 가격 유지
        setTrackedPrices((prev) => {
          const merged = { ...prev };
          for (const [sym, item] of Object.entries(data)) {
            if (item.price > 0) merged[sym] = item;
          }
          return merged;
        });
      }
    } catch {}
  };

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

  // 추적 종목 가격 동기화: 종목 변경 시 즉시 + 5초마다 갱신
  useEffect(() => {
    const symbols = trackedSymbols.map((s) => s.symbol);
    fetchTrackedPrices(symbols);
    const interval = setInterval(() => fetchTrackedPrices(symbols), 2000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackedSymbols]);

  useEffect(() => {
    if (!selectedSymbol) return;
    const updatePrice = async () => {
      try {
        const res = await fetch("/api/stock/batch-quotes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: [selectedSymbol] }),
        });
        if (res.ok) {
          const data: Record<string, BatchQuoteItem> = await res.json();
          const q = data[selectedSymbol];
          if (q?.price > 0) {
            setCurrentPrice(q.price);
            if (isAutoPrice && !selectedOrderPrice) {
              setPrice(q.price.toString());
            }
          }
        }
      } catch {}
    };
    updatePrice();
    const interval = setInterval(updatePrice, 2000);
    return () => clearInterval(interval);
  }, [selectedSymbol, isAutoPrice, selectedOrderPrice]);

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
        .then((s) => setDbStrategyDescription(s?.description ?? null))
        .catch(() => setDbStrategyDescription(null));
    }
    fetch(`/api/virtual-market/${accountId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((state) => {
        if (state?.symbols?.length) {
          setTrackedSymbols(
            state.symbols.map((sym: string) => ({
              symbol: sym,
              name: state.symbolNames?.[sym] || sym,
            }))
          );
        }
      })
      .catch(() => {});
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
        <div className="p-4 sm:p-6">
          <p className="text-gray-400">계좌를 불러오는 중...</p>
        </div>
      </DashboardLayout>
    );
  }

  const shouldShowOrderPage = showOrderPage || selectedSymbol;

  const strategies = account.strategyName
    ? [{ name: account.strategyName, status: "active" as const }]
    : [];

  return (
    <DashboardLayout userName="사용자">
      <div className="p-4 sm:p-6 max-w-7xl mx-auto w-full">

        {/* ── 주문 페이지 (종목 선택 시) ── */}
        {shouldShowOrderPage && (
          <div>
            {selectedSymbol && (
              <div className="bg-[#1a1a1a] p-4 rounded-lg mb-6">
                <div className="flex items-center gap-4">
                  <div>
                    <h2 className="text-lg font-bold text-white">{stockInfo?.name || selectedStockName || selectedSymbol}</h2>
                    <p className="text-sm text-gray-400">{selectedSymbol}</p>
                  </div>
                  <button onClick={() => { setSelectedSymbol(""); setShowOrderPage(false); }} className="ml-auto text-sm text-gray-400 hover:text-white">← 돌아가기</button>
                </div>
              </div>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <OrderBook symbol={selectedSymbol} currentPrice={currentPrice} onPriceSelect={(p) => { setPrice(p.toString()); setSelectedOrderPrice(p); }} />
              <div className="bg-[#1a1a1a] rounded-lg flex flex-col">
                <div className="flex">
                  {(["buy","sell","amend","unfilled","balance"] as const).map((tab) => (
                    <button key={tab} onClick={() => { setOrderTab(tab); if (tab === "buy" || tab === "sell") setTransactionType(tab); }}
                      className={`px-4 py-2 text-xs font-medium transition-colors ${orderTab === tab ? (tab === "sell" ? "text-red-400" : "text-blue-400") : "text-gray-400 hover:text-gray-300"}`}>
                      {tab === "buy" ? "매수" : tab === "sell" ? "매도" : tab === "amend" ? "정정/취소" : tab === "unfilled" ? "미체결" : "잔고"}
                    </button>
                  ))}
                </div>
                <div className="p-4 space-y-4 flex-1 flex flex-col">
                  <div className="flex gap-2">
                    {(["cash","credit"] as const).map((t) => (
                      <button key={t} onClick={() => setPaymentType(t)} className={`flex-1 px-3 py-1.5 text-xs font-medium rounded ${paymentType === t ? "bg-blue-600 text-white" : "bg-[#252525] text-gray-300"}`}>
                        {t === "cash" ? "현금" : "신용"}
                      </button>
                    ))}
                  </div>
                  <select value={orderType} onChange={(e) => setOrderType(e.target.value as any)} className="w-full px-3 py-1.5 text-xs rounded bg-[#252525] text-white focus:outline-none">
                    <option value="limit">보통(지정가)</option>
                    <option value="market">시장가</option>
                  </select>
                  <div>
                    <label className="block text-xs font-medium text-gray-300 mb-1">수량</label>
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => setQuantity(q => String(Math.max(0, parseInt(q || "0") - 1)))} className="px-2 py-1 text-xs bg-[#252525] text-gray-300 rounded">-</button>
                      <input type="number" value={quantity} onChange={(e) => setQuantity(e.target.value)} className="flex-1 px-3 py-1.5 text-sm rounded bg-[#252525] text-white focus:outline-none" placeholder="0" min="1" />
                      <button onClick={() => setQuantity(q => String(parseInt(q || "0") + 1))} className="px-2 py-1 text-xs bg-[#252525] text-gray-300 rounded">+</button>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-300 mb-1">가격</label>
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => { const p = parseFloat(price||"0"); const np = Math.max(0,p-p*0.01); setPrice(np.toFixed(0)); setSelectedOrderPrice(np); }} className="px-2 py-1 text-xs bg-[#252525] text-gray-300 rounded">-</button>
                      <input id="order-price-input" type="number" value={price} onChange={(e) => { setPrice(e.target.value); const np=parseFloat(e.target.value); setSelectedOrderPrice(!isNaN(np)&&np>0?np:undefined); }} className="flex-1 px-3 py-1.5 text-sm rounded bg-[#252525] text-white focus:outline-none" placeholder="0" />
                      <span className="text-xs text-gray-400">원</span>
                      <button onClick={() => { const p=parseFloat(price||"0"); const np=p+p*0.01; setPrice(np.toFixed(0)); setSelectedOrderPrice(np); }} className="px-2 py-1 text-xs bg-[#252525] text-gray-300 rounded">+</button>
                    </div>
                  </div>
                  <div className="bg-[#111111] rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-400">총 거래금액</span>
                      <span className="text-lg font-bold text-white">{quantity&&price?formatPrice(parseFloat(quantity)*parseFloat(price)):"0"}원</span>
                    </div>
                  </div>
                  <div className="mt-auto pt-4">
                    <button onClick={handleTransaction} disabled={!selectedSymbol||!quantity||!price}
                      className={`w-full px-4 py-3 rounded-lg text-sm font-bold text-white ${transactionType==="buy"?"bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600":"bg-red-600 hover:bg-red-700 disabled:bg-gray-600"}`}>
                      {paymentType==="cash"?"현금":"신용"}{transactionType==="buy"?"매수":"매도"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── 메인 대시보드 ── */}
        {!shouldShowOrderPage && (
          <div className="space-y-6">
            {/* 헤더 */}
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-3xl font-bold text-white">
                  {account.name}
                </h1>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={async () => {
                    if (!confirm(`'${account.name}' 계좌를 삭제하시겠습니까?`)) return;
                    await deleteAccount(accountId);
                    router.push("/virtual-account");
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-gray-400 border border-gray-700 rounded-lg text-sm hover:text-red-400 hover:border-red-700 transition-colors"
                >
                  <Trash size={14} />
                  삭제
                </button>
              </div>
            </div>

            {/* 4개 지표 카드 */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-[#111111] border border-[#222] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">총 자산</p>
                  <div className="w-8 h-8 rounded-lg bg-[#1a1a1a] flex items-center justify-center text-gray-400">
                    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>
                  </div>
                </div>
                <p className="text-2xl font-bold text-white">{formatPrice(account.totalValue)}</p>
                <p className="text-xs text-gray-500 mt-1">원</p>
              </div>

              <div className="bg-[#111111] border border-[#222] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">주문 가능 금액</p>
                  <div className="w-8 h-8 rounded-lg bg-[#1a1a1a] flex items-center justify-center text-gray-400">
                    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
                  </div>
                </div>
                <p className="text-2xl font-bold text-white">{formatPrice(account.currentBalance)}</p>
                <p className="text-xs text-gray-500 mt-1">원</p>
              </div>

              <div className="bg-[#111111] border border-[#222] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">당일 손익</p>
                  <div className="w-8 h-8 rounded-lg bg-[#1a1a1a] flex items-center justify-center text-gray-400">
                    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
                  </div>
                </div>
                <p className={`text-2xl font-bold ${todayPnl >= 0 ? "text-white" : "text-blue-400"}`}>
                  {todayPnl >= 0 ? "+" : ""}{formatPrice(todayPnl)}
                </p>
                <p className={`text-xs mt-1 ${todayPnl >= 0 ? "text-gray-400" : "text-blue-400"}`}>
                  {todayPnlPct >= 0 ? "+" : ""}{todayPnlPct.toFixed(2)}% {todayPnl >= 0 ? "▲" : "▼"}
                </p>
              </div>

              <div className="bg-[#111111] border border-[#222] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">누적 수익률</p>
                  <div className={`w-8 h-8 rounded-lg bg-[#1a1a1a] flex items-center justify-center ${profitPercent >= 0 ? "text-gray-400" : "text-red-500"}`}>
                    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12h18M3 6h18M3 18h18"/><path d="M5 9v6M9 7v8M13 8v7M17 6v9"/></svg>
                  </div>
                </div>
                <p className={`text-2xl font-bold ${profitPercent >= 0 ? "text-white" : "text-red-400"}`}>
                  {profitPercent >= 0 ? "+" : ""}{profitPercent.toFixed(2)}%
                </p>
                <div className="mt-3 h-1.5 bg-[#222] rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${profitPercent >= 0 ? "bg-blue-500" : "bg-red-500"}`} style={{ width: `${Math.min(100, Math.abs(profitPercent) * 2)}%` }} />
                </div>
              </div>
            </div>

            {/* 추적 종목 + 전략 */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
              {/* 추적 종목 */}
              <div className="bg-[#111111] border border-[#222] rounded-xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-base font-semibold text-white">추적 종목</h2>
                    <p className="text-xs text-gray-500 mt-0.5">전략이 시그널을 모니터링 중인 종목 목록</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 bg-[#1a1a1a] border border-[#2a2a2a] px-2.5 py-0.5 rounded-full">
                      {trackedSymbols.length}개
                    </span>
                    <button
                      onClick={() => setIsTrackSearchOpen(true)}
                      className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 border border-blue-400/20 px-2.5 py-1 rounded-full transition-colors"
                    >
                      <span className="text-base leading-none">+</span> 종목 추가
                    </button>
                  </div>
                </div>
                {trackedSymbols.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-48 gap-3 text-gray-600">
                    <TrendUp size={32} weight="thin" />
                    <p className="text-sm">추적 중인 종목이 없습니다</p>
                    <button
                      onClick={() => setIsTrackSearchOpen(true)}
                      className="text-xs text-blue-400 hover:text-blue-300 underline underline-offset-2 transition-colors"
                    >
                      종목을 직접 추가하기
                    </button>
                  </div>
                ) : (
                  <div>
                    {/* 헤더 */}
                    <div className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 px-1 pb-2 border-b border-[#1e1e1e] text-[11px] text-gray-600 uppercase tracking-wide">
                      <span>종목</span>
                      <span className="text-right">현재가</span>
                      <span className="text-right">등락률</span>
                      <span className="text-right">거래량</span>
                      <span className="text-right">상태</span>
                      <span />
                    </div>
                    {/* 행 */}
                    <div className="max-h-64 overflow-y-auto divide-y divide-[#161616]">
                      {trackedSymbols.map(({ symbol, name }) => {
                        const q = trackedPrices[symbol];
                        const hasPrice = q && q.price > 0;
                        const holding = holdings.find((h) => h.symbol === symbol);
                        const isUp = (q?.changePercent ?? 0) >= 0;
                        return (
                          <div
                            key={symbol}
                            className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 items-center px-1 py-2.5 hover:bg-[#161616] transition-colors group cursor-pointer"
                            onClick={() => handleStockSelect(symbol, name)}
                          >
                            {/* 종목명 */}
                            <div className="flex items-center gap-2 min-w-0">
                              <div className="w-7 h-7 rounded-lg bg-[#252525] flex-shrink-0 flex items-center justify-center">
                                <span className="text-[10px] font-bold text-gray-400">{symbol.slice(0, 2)}</span>
                              </div>
                              <div className="min-w-0">
                                <p className="text-xs font-medium text-white truncate">{name}</p>
                                <p className="text-[10px] text-gray-500">{symbol}</p>
                              </div>
                            </div>
                            {/* 현재가 */}
                            <p className="text-xs text-right text-white font-medium tabular-nums">
                              {hasPrice ? formatPrice(q.price) : <span className="text-gray-600">-</span>}
                            </p>
                            {/* 등락률 */}
                            <p className={`text-xs text-right font-semibold tabular-nums ${hasPrice ? (isUp ? "text-red-400" : "text-blue-400") : "text-gray-600"}`}>
                              {hasPrice ? `${isUp ? "+" : ""}${q.changePercent.toFixed(2)}%` : "-"}
                            </p>
                            {/* 거래량 */}
                            <p className="text-xs text-right text-gray-400 tabular-nums">
                              {hasPrice ? q.volume.toLocaleString("ko-KR") : <span className="text-gray-600">-</span>}
                            </p>
                            {/* 상태 */}
                            <div className="flex justify-end">
                              {holding ? (
                                <span className="text-[10px] text-blue-400 bg-blue-400/10 px-1.5 py-0.5 rounded">보유중</span>
                              ) : (
                                <span className="text-[10px] text-gray-600">대기</span>
                              )}
                            </div>
                            {/* 삭제 */}
                            <button
                              onClick={(e) => { e.stopPropagation(); handleRemoveTrackedSymbol(symbol); }}
                              className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-red-400 transition-all flex items-center justify-center"
                              title="추적 제거"
                            >
                              <X size={12} />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* 운용 중인 전략 */}
              <div className="bg-[#111111] border border-[#222] rounded-xl p-6 flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-base font-semibold text-white">운용 중인 전략</h2>
                  <span className="flex items-center gap-1.5 text-xs text-gray-400 bg-gray-400/10 border border-gray-400/20 px-2.5 py-1 rounded-full">
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-pulse" />실시간 AI 처리 중
                  </span>
                </div>

                {account.strategyName && (
                  <div className="mb-3 space-y-3">
                    <div className="p-3 bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl">
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-xs text-gray-500">매매 방식</p>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={async () => { const u = await updateTradingMode(accountId, "auto"); setAccount(prev => prev ? { ...prev, tradingMode: u.tradingMode } : prev); }}
                          className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-lg text-xs font-medium ${account.tradingMode==="auto" ? "bg-blue-600 text-white" : "bg-[#252525] text-gray-300 hover:text-white"}`}>
                          <Robot size={13} />자동매매
                        </button>
                        <button onClick={async () => { const u = await updateTradingMode(accountId, "manual"); setAccount(prev => prev ? { ...prev, tradingMode: u.tradingMode } : prev); }}
                          className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-lg text-xs font-medium ${account.tradingMode!=="auto" ? "bg-blue-600 text-white" : "bg-[#252525] text-gray-300 hover:text-white"}`}>
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
                    <div key={idx} className="bg-[#1a1a1a] border border-[#2a2a2a] rounded-xl p-4">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-sm">{strategy.status === "active" ? "🚀" : "⏸"}</span>
                          <span className="text-sm font-medium text-white truncate max-w-[140px]">{strategy.name}</span>
                        </div>
                        {strategy.status !== "active" && (
                          <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-700/50 text-gray-400 border border-gray-600/30">
                            대기
                          </span>
                        )}
                      </div>
                      {description && (
                        <p className="text-xs text-gray-400">{description}</p>
                      )}
                    </div>
                    );
                  })}
                </div>
                <button className="mt-4 w-full py-2.5 text-sm text-gray-400 border border-dashed border-[#333] rounded-xl hover:text-white hover:border-[#444] transition-all">
                  + 포워드 테스트 추가
                </button>
              </div>
            </div>

            {/* 보유 자산 현황 / 거래내역 / 성과분석 탭 */}
            <div className="bg-[#111111] border border-[#222] rounded-xl p-6">
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className="flex gap-1">
                    {(["holdings","transactions","performance"] as const).map((tab) => (
                      <button key={tab} onClick={() => setActiveTab(tab)}
                        className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${activeTab === tab ? "bg-[#1e1e1e] text-white font-medium" : "text-gray-500 hover:text-gray-300"}`}>
                        {tab === "holdings" ? "보유 자산 현황" : tab === "transactions" ? "거래 내역" : "성과 분석"}
                      </button>
                    ))}
                  </div>
                  {activeTab === "holdings" && (
                    <span className="text-xs text-gray-400 bg-[#1a1a1a] border border-[#2a2a2a] px-2.5 py-0.5 rounded-full">
                      {holdings.length}개 포지션 활성
                    </span>
                  )}
                </div>
                <button onClick={() => setIsSearchOpen(true)} className="flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300 transition-colors">
                  <MagnifyingGlass size={14} />종목 검색
                </button>
              </div>

              {/* 보유 자산 */}
              {activeTab === "holdings" && (
                holdings.length === 0 ? (
                  <p className="text-center text-sm text-gray-500 py-8">보유 중인 종목이 없습니다.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-[#1e1e1e]">
                          <th className="text-left text-xs text-gray-500 font-normal pb-3 pr-4">종목명 / 티커</th>
                          <th className="text-right text-xs text-gray-500 font-normal pb-3 px-4">평균 단가</th>
                          <th className="text-right text-xs text-gray-500 font-normal pb-3 px-4">현재가</th>
                          <th className="text-right text-xs text-gray-500 font-normal pb-3 px-4">수량</th>
                          <th className="text-right text-xs text-gray-500 font-normal pb-3 px-4">수익률</th>
                          <th className="text-right text-xs text-gray-500 font-normal pb-3 pl-4">평가 손익</th>
                        </tr>
                      </thead>
                      <tbody>
                        {holdings.map((h, idx) => {
                          const isPos = h.profitPercent >= 0;
                          return (
                            <tr key={h.symbol} onClick={() => handleStockSelect(h.symbol, h.name || h.symbol)}
                              className={`border-b border-[#151515] hover:bg-[#161616] cursor-pointer transition-colors ${idx === holdings.length - 1 ? "border-b-0" : ""}`}>
                              <td className="py-4 pr-4">
                                <div className="flex items-center gap-3">
                                  <div className="w-8 h-8 rounded-lg bg-[#1e1e1e] flex items-center justify-center">
                                    <span className="text-[10px] font-bold text-gray-300">{h.symbol.slice(0,2)}</span>
                                  </div>
                                  <div>
                                    <p className="font-medium text-white">{h.symbol}</p>
                                    <p className="text-[11px] text-gray-500">{h.name}</p>
                                  </div>
                                </div>
                              </td>
                              <td className="py-4 px-4 text-right text-gray-300">{formatPrice(h.averagePrice)}</td>
                              <td className="py-4 px-4 text-right text-white font-medium">{formatPrice(h.currentPrice)}</td>
                              <td className="py-4 px-4 text-right text-gray-300">{h.quantity.toLocaleString()}</td>
                              <td className={`py-4 px-4 text-right font-semibold ${isPos ? "text-white" : "text-red-400"}`}>
                                {isPos ? "+" : ""}{h.profitPercent.toFixed(2)}%
                              </td>
                              <td className={`py-4 pl-4 text-right font-semibold ${isPos ? "text-white" : "text-red-400"}`}>
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
                  <p className="text-center text-sm text-gray-500 py-8">거래 내역이 없습니다.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-[#1e1e1e]">
                          {["종목","구분","체결가","수량","거래금액","수수료","실현손익","체결시각"].map(h => (
                            <th key={h} className="text-xs text-gray-500 font-normal pb-3 px-3 first:pl-0 last:pr-0 text-right first:text-left">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {transactions.map((t) => (
                          <tr key={t.id} className="border-b border-[#151515] hover:bg-[#161616] transition-colors">
                            <td className="py-3 pl-0 pr-3">
                              <p className="font-medium text-white">{t.name}</p>
                              <p className="text-[11px] text-gray-500">{t.symbol}</p>
                            </td>
                            <td className="py-3 px-3 text-right">
                              <span className={`text-xs font-bold px-2 py-0.5 rounded ${t.type==="buy"?"bg-blue-900/40 text-blue-400":"bg-red-900/40 text-red-400"}`}>
                                {t.type==="buy"?"매수":"매도"}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-right text-gray-200">{formatPrice(t.filledPrice??t.price)}</td>
                            <td className="py-3 px-3 text-right text-gray-200">{t.quantity}주</td>
                            <td className="py-3 px-3 text-right text-gray-200">{formatPrice(t.totalAmount)}</td>
                            <td className="py-3 px-3 text-right text-gray-500">{t.fee!=null?`-${formatPrice(t.fee)}`:"-"}</td>
                            <td className="py-3 px-3 text-right">
                              {t.realizedPnl!=null ? (
                                <span className={`font-semibold ${t.realizedPnl>=0?"text-white":"text-red-400"}`}>
                                  {t.realizedPnl>=0?"+":""}{formatPrice(Math.round(t.realizedPnl))}
                                </span>
                              ) : <span className="text-gray-600">-</span>}
                            </td>
                            <td className="py-3 pl-3 pr-0 text-right text-gray-500 text-xs">
                              {new Date(t.filledAt??t.timestamp).toLocaleString("ko-KR")}
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
                  {/* 전략 성과 현황 차트 */}
                  <div>
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <h3 className="text-sm font-semibold text-white">전략 성과 현황</h3>
                        <p className="text-xs text-gray-500 mt-0.5">성과 분석 및 벤치마크 대비 추이</p>
                      </div>
                      <span className="flex items-center gap-1.5 text-xs text-gray-500">
                        <span className="w-2.5 h-2.5 rounded-full bg-gray-600 inline-block" />벤치마크 (KOSPI 200)
                      </span>
                    </div>
                    <div className="h-64">
                      <PortfolioPerformanceChart data={performanceData} />
                    </div>
                  </div>
                  <div className="border-t border-[#1e1e1e]" />
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
      </div>
    </DashboardLayout>
  );
}
