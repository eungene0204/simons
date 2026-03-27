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
  getHoldingsByAccount,
  getTransactionsByAccount,
  executeTrade,
  refreshAccountValue,
  updateTradingMode,
  deleteAccount,
} from "@/lib/portfolio";
import { MagnifyingGlass, Robot, Bell, Trash } from "phosphor-react";
import StockSearchModal from "@/components/stock/StockSearchModal";
import OrderBook from "@/components/order/OrderBook";
import { generateStockPriceData } from "@/lib/mock-stock-data";
import PortfolioPerformanceChart, { PerformancePoint } from "@/components/portfolio/PortfolioPerformanceChart";
import { getStrategyByName } from "@/lib/strategy-groups";

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

  useEffect(() => {
    if (accountId) loadAccountData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    const updateHoldings = async () => {
      const result = await refreshAccountValue(accountId);
      if (!result) return;
      setAccount(result.account);
      setHoldings(result.holdings);
    };
    updateHoldings();
    const interval = setInterval(updateHoldings, 3000);
    return () => clearInterval(interval);
  }, [accountId]);

  useEffect(() => {
    if (!selectedSymbol) return;
    const updatePrice = () => {
      const priceData = generateStockPriceData(selectedSymbol);
      setCurrentPrice(priceData.currentPrice);
      if (isAutoPrice && !selectedOrderPrice) {
        setPrice(priceData.currentPrice.toString());
      }
    };
    updatePrice();
    const interval = setInterval(updatePrice, 1000);
    return () => clearInterval(interval);
  }, [selectedSymbol, isAutoPrice, selectedOrderPrice]);

  const loadAccountData = async () => {
    const [acc, h, t] = await Promise.all([
      getAccount(accountId),
      getHoldingsByAccount(accountId),
      getTransactionsByAccount(accountId),
    ]);
    if (!acc) { router.push("/virtual-account"); return; }
    setAccount(acc);
    setHoldings(h);
    setTransactions(t.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()));
    if (acc.strategyId) {
      fetch(`/api/strategy/${acc.strategyId}`)
        .then((r) => r.ok ? r.json() : null)
        .then((s) => setDbStrategyDescription(s?.description ?? null))
        .catch(() => setDbStrategyDescription(null));
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
    const todayPnl = Math.abs(account.totalValue * 0.0214);
    const todayPnlPct = 2.14;
    const startDate = new Date(account.createdAt);
    const days = Math.max(1, Math.round((Date.now() - startDate.getTime()) / 86400000));
    const performanceData = generatePerformanceData(startDate, Math.min(days, 150), pp);
    return { profit: p, profitPercent: pp, todayPnl, todayPnlPct, performanceData };
  }, [account]);

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
    ? [{ name: account.strategyName, status: "active" as const, dailyPnl: 4.82, allocated: account.currentBalance * 0.5 }]
    : [
        { name: "모멘텀 헌터 v4", status: "active" as const, dailyPnl: 4.82, allocated: 450000 },
        { name: "변동성 조절 차익거래", status: "standby" as const, dailyPnl: 0, allocated: 200000, lastRun: "05-01 15:30" },
      ];

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
                  <div className="w-8 h-8 rounded-lg bg-[#1a1a1a] flex items-center justify-center text-emerald-500">
                    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
                  </div>
                </div>
                <p className="text-2xl font-bold text-emerald-400">+{formatPrice(todayPnl)}</p>
                <p className="text-xs text-emerald-500 mt-1">+{todayPnlPct.toFixed(2)}% ▲</p>
              </div>

              <div className="bg-[#111111] border border-[#222] rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wide">누적 수익률</p>
                  <div className={`w-8 h-8 rounded-lg bg-[#1a1a1a] flex items-center justify-center ${profitPercent >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                    <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12h18M3 6h18M3 18h18"/><path d="M5 9v6M9 7v8M13 8v7M17 6v9"/></svg>
                  </div>
                </div>
                <p className={`text-2xl font-bold ${profitPercent >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {profitPercent >= 0 ? "+" : ""}{profitPercent.toFixed(2)}%
                </p>
                <div className="mt-3 h-1.5 bg-[#222] rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${profitPercent >= 0 ? "bg-emerald-500" : "bg-red-500"}`} style={{ width: `${Math.min(100, Math.abs(profitPercent) * 2)}%` }} />
                </div>
              </div>
            </div>

            {/* 차트 + 전략 */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
              {/* 전략 성과 현황 */}
              <div className="bg-[#111111] border border-[#222] rounded-xl p-6">
                <div className="flex items-start justify-between mb-1">
                  <div>
                    <h2 className="text-base font-semibold text-white">전략 성과 현황</h2>
                    <p className="text-xs text-gray-500 mt-0.5">성과 분석 및 벤치마크 대비 추이</p>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-gray-400">
                    <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-gray-500 inline-block" />벤치마크 (KOSPI 200)</span>
                  </div>
                </div>
                <div className="h-72 mt-4">
                  <PortfolioPerformanceChart data={performanceData} />
                </div>
              </div>

              {/* 운용 중인 전략 */}
              <div className="bg-[#111111] border border-[#222] rounded-xl p-6 flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-base font-semibold text-white">운용 중인 전략</h2>
                  <span className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 px-2.5 py-1 rounded-full">
                    <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />실시간 AI 처리 중
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
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${strategy.status === "active" ? "bg-emerald-400/10 text-emerald-400 border border-emerald-400/20" : "bg-gray-700/50 text-gray-400 border border-gray-600/30"}`}>
                          {strategy.status === "active" ? "● 활성" : "대기"}
                        </span>
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
                              <td className={`py-4 px-4 text-right font-semibold ${isPos ? "text-emerald-400" : "text-red-400"}`}>
                                {isPos ? "+" : ""}{h.profitPercent.toFixed(2)}%
                              </td>
                              <td className={`py-4 pl-4 text-right font-semibold ${isPos ? "text-emerald-400" : "text-red-400"}`}>
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
                                <span className={`font-semibold ${t.realizedPnl>=0?"text-emerald-400":"text-red-400"}`}>
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
                <VirtualTradingDashboard accountId={accountId} initialAmount={account.initialAmount} />
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
      </div>
    </DashboardLayout>
  );
}
