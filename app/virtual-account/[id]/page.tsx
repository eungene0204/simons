"use client";

import { useState, useEffect } from "react";
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
import VirtualMarketPanel from "@/components/virtual-market/VirtualMarketPanel";
import OrderBook from "@/components/order/OrderBook";
import CurrentPriceDisplay from "@/components/stock/CurrentPriceDisplay";
import { getBasePrice, generateStockPriceData } from "@/lib/mock-stock-data";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

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

  useEffect(() => {
    if (accountId) {
      loadAccountData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  // 보유 종목의 가격을 주기적으로 업데이트 (실제 주가처럼 변동)
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


  const handleStockSelect = (symbol: string, name: string) => {
    // 주문 페이지로 이동 (차트, 호가창, 주문창이 있는 페이지)
    router.push(`/stock-order?symbol=${symbol}&name=${encodeURIComponent(name)}`);
  };


  // 선택된 종목의 가격을 주기적으로 업데이트 (실제 주가처럼 변동)
  useEffect(() => {
    if (!selectedSymbol) return;

    // 즉시 가격 업데이트
    const updatePrice = () => {
      const priceData = generateStockPriceData(selectedSymbol);
      setCurrentPrice(priceData.currentPrice);
      
      // 자동 가격 모드이고 가격이 설정되어 있으면 업데이트
      if (isAutoPrice && !selectedOrderPrice) {
        setPrice(priceData.currentPrice.toString());
      }
    };

    updatePrice();

    // 1초마다 가격 업데이트
    const interval = setInterval(updatePrice, 1000);

    return () => clearInterval(interval);
  }, [selectedSymbol, isAutoPrice, selectedOrderPrice]);

  const loadAccountData = async () => {
    const [acc, h, t] = await Promise.all([
      getAccount(accountId),
      getHoldingsByAccount(accountId),
      getTransactionsByAccount(accountId),
    ]);

    if (!acc) {
      router.push("/virtual-account");
      return;
    }

    setAccount(acc);
    setHoldings(h);
    setTransactions(
      t.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    );
  };

  const handleTransaction = async () => {
    if (!account || !selectedSymbol || !quantity || !price) return;

    const qty = parseInt(quantity);
    const prc = parseFloat(price);
    if (isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0) return;

    // 종목 이름 가져오기
    let stockName = selectedStockName || selectedSymbol;
    try {
      const response = await fetch(`/api/stock/${selectedSymbol}/detail`);
      if (response.ok) {
        const data = await response.json();
        stockName = data.name || stockName;
      }
    } catch {
      // 이름 가져오기 실패 시 기존 이름 유지
    }

    const result = await executeTrade(accountId, transactionType, selectedSymbol, stockName, qty, prc);
    if (!result.success) {
      alert(result.error ?? "거래에 실패했습니다.");
      return;
    }

    setSelectedSymbol("");
    setQuantity("");
    setPrice("");
    setSelectedOrderPrice(undefined);
    await loadAccountData();

    if (transactionType === "buy") {
      setShowOrderPage(false);
      const url = new URL(window.location.href);
      url.searchParams.delete("symbol");
      window.history.pushState({}, "", url.toString());
    }
  };

  if (!account) {
    return (
      <DashboardLayout userName="사용자">
        <div className="p-4 sm:p-6">
          <p className="text-gray-400">계좌를 불러오는 중...</p>
        </div>
      </DashboardLayout>
    );
  }

  const profit = account.totalValue - account.initialAmount;
  const profitPercent = (profit / account.initialAmount) * 100;

  // 주문 페이지 표시 여부 결정
  const shouldShowOrderPage = showOrderPage || selectedSymbol;

  // 주문 페이지가 아닐 때 탭 메뉴 표시
  const shouldShowTabs = !shouldShowOrderPage;

  return (
    <DashboardLayout userName="사용자">
      <div className="p-4 sm:p-6 max-w-7xl mx-auto overflow-x-hidden w-full">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">
              {account.name}
            </h1>
            <p className="text-sm text-gray-400">
              생성일: {new Date(account.createdAt).toLocaleDateString("ko-KR")}
            </p>
          </div>
          <button
            onClick={async () => {
              if (!confirm(`'${account.name}' 계좌를 삭제하시겠습니까?\n보유 종목, 거래내역이 모두 삭제됩니다.`)) return;
              await deleteAccount(accountId);
              router.push("/virtual-account");
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1a1a1a] text-white border border-red-600 rounded-lg text-sm font-medium hover:bg-[#252525] transition-colors"
          >
            <Trash size={15} weight="bold" />
            계좌 삭제
          </button>
        </div>

        {/* 전략 연동 & 매매 모드 */}
        {account.strategyName && (
          <div className="bg-[#1a1a1a] rounded-lg p-4 mb-6">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <p className="text-xs text-gray-400 mb-0.5">연결된 전략</p>
                <p className="text-sm font-semibold text-white">{account.strategyName}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-2">매매 방식</p>
                <div className="flex gap-2">
                  <button
                    onClick={async () => {
                      const updated = await updateTradingMode(accountId, "auto");
                      setAccount((prev) => prev ? { ...prev, tradingMode: updated.tradingMode } : prev);
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                      account.tradingMode === "auto"
                        ? "bg-blue-600 text-white"
                        : "bg-[#252525] text-gray-300 hover:text-white"
                    }`}
                  >
                    <Robot size={16} weight={account.tradingMode === "auto" ? "fill" : "regular"} />
                    자동매매
                  </button>
                  <button
                    onClick={async () => {
                      const updated = await updateTradingMode(accountId, "manual");
                      setAccount((prev) => prev ? { ...prev, tradingMode: updated.tradingMode } : prev);
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                      account.tradingMode === "manual" || !account.tradingMode
                        ? "bg-blue-600 text-white"
                        : "bg-[#252525] text-gray-300 hover:text-white"
                    }`}
                  >
                    <Bell size={16} weight={(account.tradingMode === "manual" || !account.tradingMode) ? "fill" : "regular"} />
                    신호 알림만
                  </button>
                </div>
              </div>
            </div>
            {account.tradingMode === "auto" && (
              <div className="mt-3 flex items-start gap-2 p-2.5 bg-blue-900/20 rounded-lg">
                <Robot size={16} className="text-blue-500 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-blue-300">
                  전략 신호 발생 시 자동으로 주문이 실행됩니다. 신호가 없을 때는 수동 매매를 이용하세요.
                </p>
              </div>
            )}
            {(account.tradingMode === "manual" || !account.tradingMode) && (
              <div className="mt-3 flex items-start gap-2 p-2.5 bg-[#252525] rounded-lg">
                <Bell size={16} className="text-gray-400 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-gray-400">
                  전략 신호 발생 시 알림을 받습니다. 직접 매매 여부를 결정하고 수동으로 주문하세요.
                </p>
              </div>
            )}
          </div>
        )}

        {/* 가상 주식시장 패널 — 전략이 연결된 계좌에만 표시 */}
        {account.strategyName && (
          <VirtualMarketPanel
            accountId={accountId}
            strategyId={account.strategyId}
            strategyName={account.strategyName}
            onTradeExecuted={loadAccountData}
          />
        )}

        {/* Account Summary */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-[#1a1a1a] p-4 rounded-lg">
            <p className="text-xs text-gray-400 mb-1">총 자산</p>
            <p className="text-xl font-bold text-white">
              {formatPrice(account.totalValue)} 원
            </p>
          </div>
          <div className="bg-[#1a1a1a] p-4 rounded-lg">
            <p className="text-xs text-gray-400 mb-1">현재 잔액</p>
            <p className="text-xl font-bold text-white">
              {formatPrice(account.currentBalance)} 원
            </p>
          </div>
          <div className="bg-[#1a1a1a] p-4 rounded-lg">
            <p className="text-xs text-gray-400 mb-1">손익</p>
            <p
              className={`text-xl font-bold ${
                profit >= 0
                  ? "text-red-400"
                  : "text-blue-400"
              }`}
            >
              {profit >= 0 ? "+" : ""}
              {formatPrice(profit)} 원
            </p>
          </div>
          <div className="bg-[#1a1a1a] p-4 rounded-lg">
            <p className="text-xs text-gray-400 mb-1">수익률</p>
            <p
              className={`text-xl font-bold ${
                profitPercent >= 0
                  ? "text-red-400"
                  : "text-blue-400"
              }`}
            >
              {profitPercent >= 0 ? "+" : ""}
              {profitPercent.toFixed(2)}%
            </p>
          </div>
        </div>

        {/* Tabs: 보유종목, 거래내역 */}
        {shouldShowTabs && (
          <div className="mb-6">
            {/* Tab Navigation */}
            <div className="flex gap-2 mb-4 ">
              <button
                onClick={() => setActiveTab("holdings")}
                className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
                  activeTab === "holdings"
                    ? "text-white bg-[#252525]"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                보유종목
              </button>
              <button
                onClick={() => setActiveTab("transactions")}
                className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
                  activeTab === "transactions"
                    ? "text-white bg-[#252525]"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                거래내역
              </button>
              <button
                onClick={() => setActiveTab("performance")}
                className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
                  activeTab === "performance"
                    ? "text-white bg-[#252525]"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                성과 분석
              </button>
            </div>

            {/* Tab Content */}
            <div>
              {/* 보유종목 */}
              {activeTab === "holdings" && (
                <div>
                  {holdings.length === 0 ? (
                    <div className="bg-[#1a1a1a] p-8 rounded-lg text-center">
                      <p className="text-gray-400 mb-4">
                        보유종목이 없습니다.
                      </p>
                      <button
                        onClick={() => setIsSearchOpen(true)}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-600 transition-colors text-sm font-medium"
                      >
                        종목 검색
                      </button>
                    </div>
                  ) : (
                    <div className="bg-[#1a1a1a] rounded-lg overflow-hidden">
                      <div className="overflow-x-auto">
                        <table className="w-full">
                          <thead>
                            <tr className="bg-[#111111] ">
                              <th className="text-left py-3 px-4 text-xs font-semibold text-gray-400">
                                종목명
                              </th>
                              <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">
                                매입가
                              </th>
                              <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">
                                현재가
                              </th>
                              <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">
                                평가손익
                              </th>
                              <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">
                                수익률
                              </th>
                              <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">
                                가능수량
                              </th>
                              <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">
                                보유수량
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {holdings.map((holding) => (
                              <tr
                                key={holding.symbol}
                                onClick={() => handleStockSelect(holding.symbol, holding.name || holding.symbol)}
                                className=" hover:bg-[#252525] cursor-pointer transition-colors"
                              >
                                <td className="py-3 px-4">
                                  <div>
                                    <p className="text-sm font-semibold text-white">
                                      {holding.name || holding.symbol}
                                    </p>
                                    <p className="text-xs text-gray-400">
                                      {holding.symbol}
                                    </p>
                                  </div>
                                </td>
                                <td className="text-right py-3 px-4 text-sm text-white">
                                  {formatPrice(holding.averagePrice)} 원
                                </td>
                                <td className="text-right py-3 px-4 text-sm text-white">
                                  {formatPrice(holding.currentPrice)} 원
                                </td>
                                <td className="text-right py-3 px-4">
                                  <span
                                    className={`text-sm font-semibold ${
                                      holding.profit >= 0
                                        ? "text-red-400"
                                        : "text-blue-400"
                                    }`}
                                  >
                                    {holding.profit >= 0 ? "+" : ""}
                                    {formatPrice(holding.profit)} 원
                                  </span>
                                </td>
                                <td className="text-right py-3 px-4">
                                  <span
                                    className={`text-sm font-semibold ${
                                      holding.profitPercent >= 0
                                        ? "text-red-400"
                                        : "text-blue-400"
                                    }`}
                                  >
                                    {holding.profitPercent >= 0 ? "+" : ""}
                                    {holding.profitPercent.toFixed(2)}%
                                  </span>
                                </td>
                                <td className="text-right py-3 px-4 text-sm text-white">
                                  {formatPrice(holding.quantity)}주
                                </td>
                                <td className="text-right py-3 px-4 text-sm text-white">
                                  {formatPrice(holding.quantity)}주
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 성과 분석 */}
              {activeTab === "performance" && (
                <VirtualTradingDashboard
                  accountId={accountId}
                  initialAmount={account.initialAmount}
                />
              )}

              {/* 거래내역 */}
              {activeTab === "transactions" && (
                <div>
                  {transactions.length === 0 ? (
                    <div className="bg-[#1a1a1a] p-8 rounded-lg text-center">
                      <p className="text-gray-400">거래 내역이 없습니다.</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {/* 정산 요약 */}
                      {(() => {
                        const sells = transactions.filter(t => t.type === "sell" && t.status === "FILLED");
                        if (sells.length === 0) return null;
                        const totalFee = transactions
                          .filter(t => t.status === "FILLED")
                          .reduce((s, t) => s + (t.fee ?? 0), 0);
                        const totalTax = sells.reduce((s, t) => s + (t.tax ?? 0), 0);
                        const totalRealizedPnl = sells.reduce((s, t) => s + (t.realizedPnl ?? 0), 0);
                        return (
                          <div className="bg-[#1a1a1a] rounded-lg p-4">
                            <p className="text-xs font-semibold text-gray-400 mb-3">정산 요약</p>
                            <div className="grid grid-cols-3 gap-4">
                              <div>
                                <p className="text-xs text-gray-500 mb-0.5">총 수수료</p>
                                <p className="text-sm font-bold text-gray-300">
                                  -{formatPrice(Math.round(totalFee))} 원
                                </p>
                              </div>
                              <div>
                                <p className="text-xs text-gray-500 mb-0.5">총 증권거래세</p>
                                <p className="text-sm font-bold text-gray-300">
                                  -{formatPrice(Math.round(totalTax))} 원
                                </p>
                              </div>
                              <div>
                                <p className="text-xs text-gray-500 mb-0.5">총 실현 손익</p>
                                <p className={`text-sm font-bold ${totalRealizedPnl >= 0 ? "text-red-400" : "text-blue-400"}`}>
                                  {totalRealizedPnl >= 0 ? "+" : ""}{formatPrice(Math.round(totalRealizedPnl))} 원
                                </p>
                              </div>
                            </div>
                          </div>
                        );
                      })()}

                      {/* 거래 목록 */}
                      <div className="bg-[#1a1a1a] rounded-lg overflow-hidden">
                        <div className="overflow-x-auto">
                          <table className="w-full">
                            <thead>
                              <tr className="bg-[#111111]">
                                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-400">종목</th>
                                <th className="text-center py-3 px-4 text-xs font-semibold text-gray-400">구분</th>
                                <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">체결가</th>
                                <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">수량</th>
                                <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">거래금액</th>
                                <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">수수료</th>
                                <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">세금</th>
                                <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">실현 손익</th>
                                <th className="text-right py-3 px-4 text-xs font-semibold text-gray-400">체결 시각</th>
                              </tr>
                            </thead>
                            <tbody>
                              {transactions.map((t) => (
                                <tr key={t.id} className="hover:bg-[#252525] transition-colors">
                                  <td className="py-3 px-4">
                                    <p className="text-sm font-semibold text-white">{t.name}</p>
                                    <p className="text-xs text-gray-400">{t.symbol}</p>
                                  </td>
                                  <td className="py-3 px-4 text-center">
                                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                                      t.type === "buy" ? "bg-blue-900/40 text-blue-400" : "bg-red-900/40 text-red-400"
                                    }`}>
                                      {t.type === "buy" ? "매수" : "매도"}
                                    </span>
                                  </td>
                                  <td className="py-3 px-4 text-right text-sm text-white">
                                    {formatPrice(t.filledPrice ?? t.price)} 원
                                  </td>
                                  <td className="py-3 px-4 text-right text-sm text-white">
                                    {formatPrice(t.quantity)}주
                                  </td>
                                  <td className="py-3 px-4 text-right text-sm text-white">
                                    {formatPrice(t.totalAmount)} 원
                                  </td>
                                  <td className="py-3 px-4 text-right text-xs text-gray-400">
                                    {t.fee != null ? `-${formatPrice(t.fee)} 원` : "-"}
                                  </td>
                                  <td className="py-3 px-4 text-right text-xs text-gray-400">
                                    {t.tax != null ? `-${formatPrice(t.tax)} 원` : "-"}
                                  </td>
                                  <td className="py-3 px-4 text-right">
                                    {t.realizedPnl != null ? (
                                      <span className={`text-sm font-semibold ${t.realizedPnl >= 0 ? "text-red-400" : "text-blue-400"}`}>
                                        {t.realizedPnl >= 0 ? "+" : ""}{formatPrice(Math.round(t.realizedPnl))} 원
                                      </span>
                                    ) : (
                                      <span className="text-xs text-gray-600">-</span>
                                    )}
                                  </td>
                                  <td className="py-3 px-4 text-right text-xs text-gray-400">
                                    {new Date(t.filledAt ?? t.timestamp).toLocaleString("ko-KR")}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Order Page */}
        {shouldShowOrderPage && (
          <div className="animate-fade-in-up">
            {/* Stock Info Header */}
            {selectedSymbol && (
              <div className="bg-[#1a1a1a] p-4 rounded-lg mb-6 animate-slide-in">
                <div className="flex items-center gap-4">
                  <div>
                    <h2 className="text-lg font-bold text-white">
                      {stockInfo?.name || selectedStockName || selectedSymbol}
                    </h2>
                    <p className="text-sm text-gray-400">
                      {selectedSymbol} · {stockInfo?.sector || ""} · {stockInfo?.industry || ""}
                    </p>
                  </div>
                  <div className="ml-auto flex items-center gap-4 text-sm">
                    <div>
                      <span className="text-gray-400">시가총액: </span>
                      <span className="font-semibold text-white">
                        {stockInfo?.marketCap ? formatPrice(stockInfo.marketCap) : "-"} 원
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">PER: </span>
                      <span className="font-semibold text-white">
                        {stockInfo?.pe ? stockInfo.pe.toFixed(2) : "-"}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">PBR: </span>
                      <span className="font-semibold text-white">
                        {stockInfo?.pbr ? stockInfo.pbr.toFixed(2) : "-"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-fade-in">
          {/* Order Book - Left Side */}
          <div className="lg:col-span-1 animate-slide-in">
            <OrderBook
              symbol={selectedSymbol}
              currentPrice={currentPrice}
              onPriceSelect={(selectedPrice) => {
                // 호가창에서 가격 선택 시 주문 가격 업데이트
                setPrice(selectedPrice.toString());
                setSelectedOrderPrice(selectedPrice);
                // 가격 입력 필드에 포커스
                setTimeout(() => {
                  const priceInput = document.getElementById('order-price-input') as HTMLInputElement;
                  if (priceInput) {
                    priceInput.focus();
                    priceInput.select();
                  }
                }, 100);
              }}
            />
          </div>

          {/* Order Section - Right Side */}
          <div className="lg:col-span-1 h-full flex flex-col animate-slide-in-right" style={{ animationDelay: '0.15s', animationFillMode: 'both' }}>
            <div className="bg-[#1a1a1a] rounded-lg h-full flex flex-col">
              {/* Order Tabs */}
              <div className="flex ">
                <button
                  onClick={() => {
                    setOrderTab("buy");
                    setTransactionType("buy");
                  }}
                  className={`px-4 py-2 text-xs font-medium transition-colors ${
                    orderTab === "buy"
                      ? "text-blue-400"
                      : "text-gray-400 hover:text-gray-300"
                  }`}
                >
                  매수
                </button>
                <button
                  onClick={() => {
                    setOrderTab("sell");
                    setTransactionType("sell");
                  }}
                  className={`px-4 py-2 text-xs font-medium transition-colors ${
                    orderTab === "sell"
                      ? "text-red-400"
                      : "text-gray-400 hover:text-gray-300"
                  }`}
                >
                  매도
                </button>
                <button
                  onClick={() => setOrderTab("amend")}
                  className={`px-4 py-2 text-xs font-medium transition-colors ${
                    orderTab === "amend"
                      ? "text-blue-400"
                      : "text-gray-400 hover:text-gray-300"
                  }`}
                >
                  정정/취소
                </button>
                <button
                  onClick={() => setOrderTab("unfilled")}
                  className={`px-4 py-2 text-xs font-medium transition-colors ${
                    orderTab === "unfilled"
                      ? "text-blue-400"
                      : "text-gray-400 hover:text-gray-300"
                  }`}
                >
                  미체결
                </button>
                <button
                  onClick={() => setOrderTab("balance")}
                  className={`px-4 py-2 text-xs font-medium transition-colors ${
                    orderTab === "balance"
                      ? "text-blue-400"
                      : "text-gray-400 hover:text-gray-300"
                  }`}
                >
                  잔고
                </button>
              </div>

              {/* Order Form */}
              <div className="p-4 space-y-4 flex-1 flex flex-col">
                {/* Payment Type Toggle */}
                <div className="flex gap-2">
                  <button
                    onClick={() => setPaymentType("cash")}
                    className={`flex-1 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                      paymentType === "cash"
                        ? "bg-blue-600 text-white"
                        : "bg-[#252525] text-gray-300"
                    }`}
                  >
                    현금
                  </button>
                  <button
                    onClick={() => setPaymentType("credit")}
                    className={`flex-1 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                      paymentType === "credit"
                        ? "bg-blue-600 text-white"
                        : "bg-[#252525] text-gray-300"
                    }`}
                  >
                    신용
                  </button>
                </div>

                {/* Order Type Dropdown and Balance Button */}
                <div className="flex gap-2">
                  <select
                    value={orderType}
                    onChange={(e) => setOrderType(e.target.value as "limit" | "market")}
                    className="flex-1 px-3 py-1.5 text-xs rounded bg-[#252525] text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="limit">보통(지정가)</option>
                    <option value="market">시장가</option>
                  </select>
                  <button className="px-3 py-1.5 text-xs font-medium bg-[#252525] text-gray-300 rounded hover:bg-[#333333]">
                    잔고
                  </button>
                </div>

                {/* Quantity Input with +/- buttons */}
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    수량
                  </label>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => {
                        const qty = parseInt(quantity || "0");
                        if (qty > 0) {
                          setQuantity((qty - 1).toString());
                        }
                      }}
                      className="px-2 py-1 text-xs font-medium bg-[#252525] text-gray-300 rounded hover:bg-[#333333]"
                    >
                      -
                    </button>
                    <input
                      type="number"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      className="flex-1 px-3 py-1.5 text-sm rounded bg-[#252525] text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="0"
                      min="1"
                    />
                    <button
                      onClick={() => {
                        const qty = parseInt(quantity || "0");
                        setQuantity((qty + 1).toString());
                      }}
                      className="px-2 py-1 text-xs font-medium bg-[#252525] text-gray-300 rounded hover:bg-[#333333]"
                    >
                      +
                    </button>
                  </div>
                  <div className="flex gap-1.5 mt-1.5">
                    <select className="px-2 py-1 text-xs rounded bg-[#252525] text-white">
                      <option>%</option>
                      <option>25%</option>
                      <option>50%</option>
                      <option>75%</option>
                      <option>100%</option>
                    </select>
                    <button className="px-3 py-1 text-xs font-medium bg-[#252525] text-gray-300 rounded hover:bg-[#333333]">
                      가능
                    </button>
                  </div>
                </div>

                {/* Price Input with +/- buttons */}
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-1">
                    가격
                  </label>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => {
                        const p = parseFloat(price || "0");
                        if (p > 0) {
                          const newPrice = Math.max(0, p - (p * 0.01));
                          setPrice(newPrice.toFixed(0));
                          setSelectedOrderPrice(newPrice);
                        }
                      }}
                      className="px-2 py-1 text-xs font-medium bg-[#252525] text-gray-300 rounded hover:bg-[#333333]"
                    >
                      -
                    </button>
                    <input
                      id="order-price-input"
                      type="number"
                      value={price}
                      onChange={(e) => {
                        setPrice(e.target.value);
                        const newPrice = parseFloat(e.target.value);
                        if (!isNaN(newPrice) && newPrice > 0) {
                          setSelectedOrderPrice(newPrice);
                        } else {
                          setSelectedOrderPrice(undefined);
                        }
                      }}
                      className="flex-1 px-3 py-1.5 text-sm rounded bg-[#252525] text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="0"
                      min="0"
                      step="1"
                    />
                    <span className="text-xs text-gray-400">원</span>
                    <button
                      onClick={() => {
                        const p = parseFloat(price || "0");
                        const newPrice = p + (p * 0.01);
                        setPrice(newPrice.toFixed(0));
                        setSelectedOrderPrice(newPrice);
                      }}
                      className="px-2 py-1 text-xs font-medium bg-[#252525] text-gray-300 rounded hover:bg-[#333333]"
                    >
                      +
                    </button>
                  </div>
                  <div className="flex items-center gap-3 mt-1.5">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isMarketPrice}
                        onChange={(e) => {
                          setIsMarketPrice(e.target.checked);
                          if (e.target.checked) {
                            setIsAutoPrice(false);
                          }
                        }}
                        className="w-3.5 h-3.5 text-blue-500 rounded focus:ring-blue-500"
                      />
                      <span className="text-xs text-gray-300">시장가</span>
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isAutoPrice}
                        onChange={(e) => {
                          setIsAutoPrice(e.target.checked);
                          if (e.target.checked) {
                            setIsMarketPrice(false);
                            if (currentPrice) {
                              setPrice(currentPrice.toFixed(0));
                              setSelectedOrderPrice(currentPrice);
                            }
                          }
                        }}
                        className="w-3.5 h-3.5 text-blue-500 rounded focus:ring-blue-500"
                      />
                      <span className="text-xs text-gray-300">가격 자동(현재가)</span>
                    </label>
                    <button className="px-2 py-1 text-xs font-medium bg-[#252525] text-gray-300 rounded hover:bg-[#333333]">
                      호가
                    </button>
                  </div>
                </div>

                {/* Total Amount Display */}
                <div className="bg-[#111111] rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-gray-400">
                      총 거래금액
                    </span>
                    <span className="text-lg font-bold text-white">
                      {quantity && price && !isNaN(parseFloat(quantity)) && !isNaN(parseFloat(price))
                        ? formatPrice(parseFloat(quantity) * parseFloat(price))
                        : "0"} 원
                    </span>
                  </div>
                  {quantity && price && !isNaN(parseFloat(quantity)) && !isNaN(parseFloat(price)) && (
                    <div className="text-xs text-gray-400">
                      {formatPrice(parseFloat(quantity))}주 × {formatPrice(parseFloat(price))}원
                    </div>
                  )}
                </div>

                {/* Submit Button */}
                <div className="mt-auto pt-4">
                  <button
                    onClick={handleTransaction}
                    disabled={!selectedSymbol || !quantity || !price}
                    className={`w-full px-4 py-3 rounded-lg text-sm font-bold text-white transition-colors ${
                      transactionType === "buy"
                        ? "bg-blue-600 hover:bg-blue-600 disabled:bg-gray-400"
                        : "bg-red-600 hover:bg-red-700 disabled:bg-gray-400"
                    }`}
                  >
                    {paymentType === "cash" ? "현금" : "신용"}
                    {transactionType === "buy" ? "매수" : "매도"}
                  </button>
                </div>
              </div>
            </div>
          </div>

            </div>
          </div>
        )}

        {/* Stock Search Modal */}
        <StockSearchModal
          isOpen={isSearchOpen}
          onClose={() => {
            setIsSearchOpen(false);
          }}
          onSelect={(items) => {
            if (items.length > 0) {
              handleStockSelect(items[0].symbol, items[0].name);
              setIsSearchOpen(false);
            }
          }}
          singleSelect={true}
        />
      </div>
    </DashboardLayout>
  );
}

