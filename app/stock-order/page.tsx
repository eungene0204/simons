"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CaretDown,
  Info,
  CheckCircle,
  Warning,
  X,
  ChartBar,
  FileText,
  Table,
} from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import OrderBook, { MarketStats } from "@/components/order/OrderBook";
import {
  getBasePrice,
  generateStockPriceData,
  generateCandleData,
} from "@/lib/mock-stock-data";
import CandlestickChart, { OHLCV } from "@/components/stock/CandlestickChart";
import { useDrawer } from "@/contexts/DrawerContext";
import {
  getAllAccounts,
  getAccount,
  executeTrade,
  getHoldingsByAccount,
  refreshAccountValue,
  getPendingOrders,
  cancelOrder,
  fillPendingOrders,
} from "@/lib/portfolio";
import type { VirtualAccount, PendingOrder } from "@/types/portfolio";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

const getTickSize = (p: number): number => {
  if (p < 1000) return 1;
  if (p < 5000) return 5;
  if (p < 10000) return 10;
  if (p < 50000) return 50;
  if (p < 100000) return 100;
  if (p < 500000) return 500;
  return 1000;
};

export default function OrderPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const symbol = searchParams.get("symbol") || "";
  const name = searchParams.get("name") || "";
  const { selectedAccountId, setSelectedAccountId } = useDrawer();

  const [selectedStockName, setSelectedStockName] = useState(name);
  const [stockInfo, setStockInfo] = useState<any>(null);
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [currentPrice, setCurrentPrice] = useState<number | undefined>(
    undefined
  );
  const [selectedOrderPrice, setSelectedOrderPrice] = useState<
    number | undefined
  >(undefined);
  const [transactionType, setTransactionType] = useState<
    "buy" | "sell" | "pending"
  >("buy");
  const [orderTab, setOrderTab] = useState<
    "buy" | "sell" | "amend" | "unfilled" | "balance"
  >("buy");
  const [paymentType, setPaymentType] = useState<"cash" | "credit">("cash");
  const [orderType, setOrderType] = useState<"limit" | "market">("limit");
  const [priceType, setPriceType] = useState<"limit" | "market">("limit");
  const [availableAmount, setAvailableAmount] = useState(12); // 구매가능 금액
  const [pendingOrders, setPendingOrders] = useState<PendingOrder[]>([]);
  const [chartPeriod, setChartPeriod] = useState<"day" | "week" | "month">(
    "day"
  );
  const [chartRange, setChartRange] = useState<"1Y" | "3Y" | "5Y">("1Y");
  const [virtualAccounts, setVirtualAccounts] = useState<VirtualAccount[]>([]);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const accountDropdownRef = useRef<HTMLDivElement>(null);
  // ohlcv 실제 데이터 로드 여부 — detail API의 mock 가격이 실제 가격을 덮어쓰는 것 방지
  const hasRealPriceRef = useRef(false);
  const [activeTab, setActiveTab] = useState<
    "chart" | "info" | "news" | "trading" | "community" | "analysis"
  >("chart");
  const [chartTab, setChartTab] = useState<
    "technical" | "flow" | "financial" | "news"
  >("technical");
  const [flowPeriod, setFlowPeriod] = useState<
    "1D" | "1W" | "1M" | "3M" | "1Y"
  >("1M");
  const [realDailyCandles, setRealDailyCandles] = useState<OHLCV[] | null>(null);
  const [realLastClose, setRealLastClose] = useState<number | undefined>(undefined);
  const [orderModal, setOrderModal] = useState<{
    type: "success" | "pending" | "error";
    stockName: string;
    action?: string;
    qty?: number;
    price?: number;
    fee?: number;
    total?: number;
    message?: string;
  } | null>(null);

  // 가상계좌 목록 로드 및 주기적 업데이트
  useEffect(() => {
    const loadAccounts = async () => {
      const updatedAccounts = await getAllAccounts();
      setVirtualAccounts((prevAccounts) => {
        if (prevAccounts.length !== updatedAccounts.length) return updatedAccounts;
        const prevMap = new Map(prevAccounts.map((acc) => [acc.id, acc]));
        const hasChanged = updatedAccounts.some((current) => {
          const prev = prevMap.get(current.id);
          if (!prev) return true;
          return (
            prev.currentBalance !== current.currentBalance ||
            prev.totalValue !== current.totalValue
          );
        });
        return hasChanged ? updatedAccounts : prevAccounts;
      });
    };

    loadAccounts();
    const interval = setInterval(loadAccounts, 3000);
    return () => clearInterval(interval);
  }, []);

  // 초기 로드 시 기본 계좌 선택
  useEffect(() => {
    if (!selectedAccountId) {
      getAllAccounts().then((accounts) => {
        if (accounts.length > 0) setSelectedAccountId(accounts[0].id);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 선택된 계좌 변경 시 잔액 업데이트
  useEffect(() => {
    if (selectedAccountId) {
      getAccount(selectedAccountId).then((account) => {
        setAvailableAmount(account ? account.currentBalance : 0);
      });
    } else {
      setAvailableAmount(0);
    }
  }, [selectedAccountId]);

  // select 옵션 메모이제이션
  const accountOptions = useMemo(() => {
    if (virtualAccounts.length === 0) {
      return <option value="">가상계좌가 없습니다</option>;
    }
    return virtualAccounts.map((account) => (
      <option key={account.id} value={account.id}>
        {account.name} ({formatPrice(account.currentBalance)}원)
      </option>
    ));
  }, [virtualAccounts]);

  // 선택된 계좌 정보
  const selectedAccount = useMemo(() => {
    if (!selectedAccountId) return null;
    return virtualAccounts.find((acc) => acc.id === selectedAccountId);
  }, [selectedAccountId, virtualAccounts]);

  // 외부 클릭 시 dropdown 닫기
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        accountDropdownRef.current &&
        !accountDropdownRef.current.contains(event.target as Node)
      ) {
        setIsAccountDropdownOpen(false);
      }
    };

    if (isAccountDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isAccountDropdownOpen]);

  // 미체결 주문 목록 로드
  const loadPendingOrders = async () => {
    if (!selectedAccountId) return;
    const orders = await getPendingOrders(selectedAccountId);
    setPendingOrders(orders);
  };

  // 매수/매도 주문 처리
  const handleOrder = async () => {
    if (!selectedAccountId) { alert("가상계좌를 선택해주세요."); return; }
    if (!symbol) { alert("종목을 선택해주세요."); return; }
    if (transactionType !== "buy" && transactionType !== "sell") return;
    if (!quantity || !price) { alert("수량과 가격을 입력해주세요."); return; }

    const qty = parseInt(quantity);
    const prc = parseFloat(price);
    if (isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0) {
      alert("올바른 수량과 가격을 입력해주세요.");
      return;
    }

    const orderTypeMapped: "MARKET" | "LIMIT" = priceType === "market" ? "MARKET" : "LIMIT";

    // 종목 이름 확정
    let stockName = selectedStockName || symbol;
    try {
      const res = await fetch(`/api/stock/${symbol}/detail`);
      if (res.ok) {
        const data = await res.json();
        stockName = data.name || stockName;
      }
    } catch { /* 이름 가져오기 실패 시 기존 이름 유지 */ }

    const result = await executeTrade(
      selectedAccountId, transactionType, symbol, stockName, qty, prc, orderTypeMapped
    );
    if (!result.success) {
      setOrderModal({ type: "error", stockName, message: result.error ?? "거래에 실패했습니다." });
      return;
    }

    // 계좌 잔액 갱신
    const updatedAccount = await getAccount(selectedAccountId);
    if (updatedAccount) setAvailableAmount(updatedAccount.currentBalance);
    const updatedAccounts = await getAllAccounts();
    setVirtualAccounts(updatedAccounts);
    await loadPendingOrders();

    const order = result.order;
    const action = transactionType === "buy" ? "매수" : "매도";
    const isPending = order?.status === "PENDING";
    const filledPrc = order?.filledPrice ?? prc;
    const fee = order?.fee ?? 0;

    if (isPending) {
      setOrderModal({ type: "pending", stockName, action, qty, price: prc });
    } else {
      setOrderModal({
        type: "success",
        stockName,
        action,
        qty,
        price: filledPrc,
        fee,
        total: filledPrc * qty + (transactionType === "buy" ? fee : -fee),
      });
    }
    setQuantity("");
  };

  // URL 파라미터에서 name이 변경될 때 selectedStockName 업데이트
  useEffect(() => {
    if (name) {
      setSelectedStockName(name);
    }
  }, [name]);

  useEffect(() => {
    if (symbol) {
      // 종목 정보 가져오기
      fetch(`/api/stock/${symbol}/detail`)
        .then((res) => res.json())
        .then((data) => {
          setStockInfo(data);
          if (data.name) {
            setSelectedStockName(data.name);
          }
          // 백엔드에서 실제 lastClose를 받았으면 즉시 설정 (interval이 undefined로 덮어쓰는 것 방지)
          if (data.realLastClose) {
            setRealLastClose(data.realLastClose);
          }
          // 실제 ohlcv 데이터가 이미 로드됐으면 mock 가격으로 덮어쓰지 않음
          if (!hasRealPriceRef.current && data.currentPrice) {
            setPrice(data.currentPrice.toString());
            setCurrentPrice(data.currentPrice);
          } else if (!hasRealPriceRef.current && !data.currentPrice) {
            const basePrice = getBasePrice(symbol);
            if (basePrice) {
              setCurrentPrice(basePrice);
              setPrice(basePrice.toString());
            }
          }
        })
        .catch((error) => {
          console.error("Failed to fetch stock info:", error);
          if (!hasRealPriceRef.current) {
            const basePrice = getBasePrice(symbol);
            if (basePrice) {
              setCurrentPrice(basePrice);
              setPrice(basePrice.toString());
            }
          }
        });
    }
  }, [symbol]);

  // 주기적으로 가격 업데이트 + 미체결 주문 체결 트리거
  useEffect(() => {
    if (!symbol) return;

    const interval = setInterval(async () => {
      // realLastClose가 아직 로드되지 않았으면 잘못된 base price(50,000원)로 덮어쓰지 않도록 스킵
      if (realLastClose === undefined) return;

      const priceData = generateStockPriceData(symbol, realLastClose);
      const newPrice = priceData.currentPrice;
      setCurrentPrice(newPrice);

      // 지정가가 아니거나 가격이 선택되지 않았을 때만 자동 업데이트
      if (priceType === "market" && !selectedOrderPrice) {
        setPrice(newPrice.toString());
      }

      // PENDING 주문 체결 시도
      if (selectedAccountId) {
        const fillResult = await fillPendingOrders(selectedAccountId, symbol, newPrice);
        if (fillResult.count > 0) {
          // 체결 발생 → 계좌 잔액 + 미체결 목록 갱신
          getAccount(selectedAccountId).then((acc) => {
            if (acc) setAvailableAmount(acc.currentBalance);
          });
          getAllAccounts().then(setVirtualAccounts);
          loadPendingOrders();
        }
      }
    }, 1000);

    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, priceType, selectedOrderPrice, selectedAccountId, realLastClose]);

  // 파케이 실제 OHLCV 데이터 fetch (백엔드 가용 시)
  useEffect(() => {
    if (!symbol) return;
    hasRealPriceRef.current = false;  // symbol 변경 시 리셋
    setRealDailyCandles(null);
    setRealLastClose(undefined);
    fetch(`/api/stock/${symbol}/ohlcv`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data?.candles?.length) return;
        const candles: OHLCV[] = data.candles.map((c: { date: string; open: number; high: number; low: number; close: number; volume: number }) => ({
          time: c.date,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          volume: c.volume,
        }));
        hasRealPriceRef.current = true;  // 실제 데이터 로드 완료
        setRealDailyCandles(candles);
        setRealLastClose(data.lastClose);
        // 실제 마지막 close로 기준가 업데이트
        setCurrentPrice(data.lastClose);
        setPrice(data.lastClose.toString());
      })
      .catch(() => {/* 백엔드 미실행 시 GBM fallback */});
  }, [symbol]);

  // 실제 파케이 데이터 기반 시세 요약 (OrderBook MarketSummary용)
  const realMarketStats = useMemo<MarketStats | undefined>(() => {
    if (!realDailyCandles || realDailyCandles.length < 2) return undefined;
    const last = realDailyCandles[realDailyCandles.length - 1];
    const prev = realDailyCandles[realDailyCandles.length - 2];
    const year252 = realDailyCandles.slice(-252);
    return {
      open: last.open,
      high: last.high,
      low: last.low,
      volume: last.volume,
      previousClose: prev.close,
      week52High: Math.max(...year252.map((c) => c.high)),
      week52Low: Math.min(...year252.map((c) => c.low)),
    };
  }, [realDailyCandles]);

  // 시세 패널용 2년치 일봉 데이터 (최신순)
  const priceHistoryData = useMemo(() => {
    if (!symbol) return [];
    const base = realLastClose ?? getBasePrice(symbol);
    const daily: OHLCV[] = realDailyCandles
      ?? generateCandleData(symbol, base, 504, undefined, "realistic").map((c) => ({
          time: c.date, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume,
        }));
    return daily.slice(-504).reverse();
  }, [symbol, realDailyCandles, realLastClose]);

  // 차트용 캔들 데이터: 실제 파케이 데이터 우선, 없으면 GBM fallback
  const candleData: OHLCV[] = useMemo(() => {
    if (!symbol) return [];

    // 일봉 소스: 실제 데이터 or GBM
    const base = realLastClose ?? getBasePrice(symbol);
    const dailySource: OHLCV[] = realDailyCandles
      ?? generateCandleData(symbol, base, 1260, undefined, "realistic").map((c) => ({
          time: c.date, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume,
        }));

    const dayCount = chartRange === "5Y" ? 1260 : chartRange === "3Y" ? 756 : 252;
    if (chartPeriod === "day") return dailySource.slice(-dayCount);

    // 주봉 집계
    if (chartPeriod === "week") {
      const weekMap = new Map<string, OHLCV[]>();
      for (const c of dailySource.slice(-dayCount)) {
        const d = new Date(c.time);
        const dow = d.getDay();
        const monday = new Date(d);
        monday.setDate(d.getDate() - (dow === 0 ? 6 : dow - 1));
        const key = monday.toISOString().slice(0, 10);
        if (!weekMap.has(key)) weekMap.set(key, []);
        weekMap.get(key)!.push(c);
      }
      return Array.from(weekMap.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([weekStart, candles]) => ({
          time: weekStart,
          open: candles[0].open,
          high: Math.max(...candles.map((c) => c.high)),
          low: Math.min(...candles.map((c) => c.low)),
          close: candles[candles.length - 1].close,
          volume: candles.reduce((sum, c) => sum + c.volume, 0),
        }));
    }

    // 월봉 집계
    const monthMap = new Map<string, OHLCV[]>();
    for (const c of dailySource.slice(-dayCount)) {
      const key = c.time.slice(0, 7);
      if (!monthMap.has(key)) monthMap.set(key, []);
      monthMap.get(key)!.push(c);
    }
    return Array.from(monthMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, candles]) => ({
        time: month + "-01",
        open: candles[0].open,
        high: Math.max(...candles.map((c) => c.high)),
        low: Math.min(...candles.map((c) => c.low)),
        close: candles[candles.length - 1].close,
        volume: candles.reduce((sum, c) => sum + c.volume, 0),
      }));
  }, [symbol, chartPeriod, chartRange, realDailyCandles, realLastClose]);

  if (!symbol) {
    return (
      <DashboardLayout userName="사용자">
        <div className="p-4 sm:p-6 max-w-7xl mx-auto overflow-x-hidden w-full">
          <p className="text-gray-500 dark:text-gray-400">
            종목을 선택해주세요.
          </p>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout userName="사용자">
      {/* 주문 결과 모달 */}
      {orderModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setOrderModal(null)}
        >
          <div
            className="bg-[#1a1a1a] border border-gray-700 rounded-2xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 상단 아이콘 */}
            <div className={`flex flex-col items-center pt-8 pb-4 px-6 ${
              orderModal.type === "success" ? "bg-gradient-to-b from-red-950/40 to-transparent" :
              orderModal.type === "pending" ? "bg-gradient-to-b from-yellow-950/40 to-transparent" :
              "bg-gradient-to-b from-gray-900/60 to-transparent"
            }`}>
              {orderModal.type === "success" && (
                <>
                  <CheckCircle className="w-14 h-14 text-red-400 mb-3" weight="fill" />
                  <p className="text-lg font-bold text-white">{orderModal.action} 체결 완료</p>
                  <p className="text-sm text-gray-400 mt-1">{orderModal.stockName}</p>
                </>
              )}
              {orderModal.type === "pending" && (
                <>
                  <Warning className="w-14 h-14 text-yellow-400 mb-3" weight="fill" />
                  <p className="text-lg font-bold text-white">지정가 대기 중</p>
                  <p className="text-sm text-gray-400 mt-1">{orderModal.stockName}</p>
                </>
              )}
              {orderModal.type === "error" && (
                <>
                  <X className="w-14 h-14 text-gray-400 mb-3" weight="bold" />
                  <p className="text-lg font-bold text-white">주문 실패</p>
                  <p className="text-sm text-gray-400 mt-1">{orderModal.stockName}</p>
                </>
              )}
            </div>

            {/* 내용 */}
            <div className="px-6 pb-6 space-y-3">
              {orderModal.type === "success" && (
                <div className="bg-[#111] rounded-xl p-4 space-y-2.5 mt-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">수량</span>
                    <span className="text-white font-medium">{formatPrice(orderModal.qty ?? 0)}주</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">체결가</span>
                    <span className="text-white font-medium">{formatPrice(orderModal.price ?? 0)}원</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">수수료</span>
                    <span className="text-gray-300">{formatPrice(orderModal.fee ?? 0)}원</span>
                  </div>
                  <div className="border-t border-gray-700 pt-2.5 flex justify-between text-sm font-semibold">
                    <span className="text-gray-300">총액</span>
                    <span className="text-white">{formatPrice(orderModal.total ?? 0)}원</span>
                  </div>
                </div>
              )}
              {orderModal.type === "pending" && (
                <div className="bg-[#111] rounded-xl p-4 space-y-2.5 mt-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">수량</span>
                    <span className="text-white font-medium">{formatPrice(orderModal.qty ?? 0)}주</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">지정가</span>
                    <span className="text-white font-medium">{formatPrice(orderModal.price ?? 0)}원</span>
                  </div>
                  <p className="text-xs text-yellow-400/80 pt-1">가격 도달 시 자동으로 체결됩니다.</p>
                </div>
              )}
              {orderModal.type === "error" && (
                <div className="bg-[#111] rounded-xl p-4 mt-2">
                  <p className="text-sm text-gray-300 text-center">{orderModal.message}</p>
                </div>
              )}

              <button
                onClick={() => setOrderModal(null)}
                className="w-full py-3 rounded-xl font-semibold text-sm text-white bg-gray-700 hover:bg-gray-600 transition-colors mt-1"
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="p-4 sm:p-6 max-w-7xl mx-auto overflow-x-hidden w-full pb-24">
        {/* Header */}
        <div className="flex items-center gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-white">
              {selectedStockName || symbol}
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">{symbol}</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6 flex items-center gap-2 overflow-x-auto">
          <button
            onClick={() => setActiveTab("analysis")}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "analysis"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            종목 분석
          </button>
          <button
            onClick={() => setActiveTab("chart")}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "chart"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            차트 · 호가
          </button>
          <button
            onClick={() => setActiveTab("info")}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "info"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            종목정보
          </button>
          <button
            onClick={() => setActiveTab("news")}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "news"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            뉴스 · 공시
          </button>
          <button
            onClick={() => setActiveTab("trading")}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "trading"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            거래현황
          </button>
          <button
            onClick={() => setActiveTab("community")}
            className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === "community"
                ? "bg-[#252525] text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            커뮤니티
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === "chart" && (
          <>
            {/* Stock Chart + Order Book side by side */}
            {/* Stock Chart 7:3 + 호가창 */}
            <div className="grid gap-4 mb-6 items-start" style={{ gridTemplateColumns: "7fr 3fr" }}>
              {/* Stock Chart */}
              <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-3">
                <div className="flex items-center gap-1 mb-2">
                  {(["1Y", "3Y", "5Y"] as const).map((r) => (
                    <button
                      key={r}
                      onClick={() => setChartRange(r)}
                      className={`px-2.5 py-1 text-xs rounded transition-colors ${
                        chartRange === r
                          ? "bg-gray-600 text-white"
                          : "text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {r}
                    </button>
                  ))}
                  <div className="mx-1 h-3 border-l border-gray-700" />
                  {(["day", "week", "month"] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => setChartPeriod(p)}
                      className={`px-2.5 py-1 text-xs rounded transition-colors ${
                        chartPeriod === p
                          ? "bg-gray-600 text-white"
                          : "text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {p === "day" ? "일" : p === "week" ? "주" : "월"}
                    </button>
                  ))}
                </div>
                <div className="h-[480px]">
                  <CandlestickChart data={candleData} />
                </div>
              </div>

              {/* 호가창 - Right of chart */}
              <div className="animate-slide-in h-[530px]">
                <div className="h-full">
                  <OrderBook
                    symbol={symbol}
                    currentPrice={currentPrice}
                    marketStats={realMarketStats}
                    onPriceSelect={(selectedPrice) => {
                      setSelectedOrderPrice(selectedPrice);
                      setPriceType("limit");
                      setPrice(selectedPrice.toString());
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Order Page: 시세창 + 주문하기 5:5 */}
            <div className="grid grid-cols-2 gap-4 animate-fade-in items-start">
              {/* 시세창 */}
              <div className="flex flex-col bg-[#1a1a1a] rounded-lg border border-gray-800 h-[575px] overflow-hidden">
                <div className="px-3 py-2 border-b border-gray-800 shrink-0">
                  <h2 className="text-lg font-semibold text-white">시세</h2>
                </div>
                <div className="overflow-y-auto flex-1 min-h-0">
                  <table className="w-full text-[13px] border-collapse">
                    <thead className="sticky top-0 bg-[#111] z-10">
                      <tr>
                        <th className="px-1.5 py-1.5 text-left text-gray-500 font-medium whitespace-nowrap">일자</th>
                        <th className="px-1.5 py-1.5 text-right text-gray-500 font-medium whitespace-nowrap">종가</th>
                        <th className="px-1.5 py-1.5 text-right text-gray-500 font-medium whitespace-nowrap">등락률</th>
                        <th className="px-1.5 py-1.5 text-right text-gray-500 font-medium whitespace-nowrap">거래량(주)</th>
                        <th className="px-1.5 py-1.5 text-right text-gray-500 font-medium whitespace-nowrap">시가</th>
                        <th className="px-1.5 py-1.5 text-right text-gray-500 font-medium whitespace-nowrap">고가</th>
                        <th className="px-1.5 py-1.5 text-right text-gray-500 font-medium whitespace-nowrap">저가</th>
                      </tr>
                    </thead>
                    <tbody>
                      {priceHistoryData.map((row, i) => {
                        const prevClose = priceHistoryData[i + 1]?.close;
                        const changeRate = prevClose ? ((row.close - prevClose) / prevClose) * 100 : 0;
                        const isUp = changeRate > 0;
                        const isDown = changeRate < 0;
                        const priceColor = isUp ? "text-red-400" : isDown ? "text-blue-400" : "text-white";
                        return (
                          <tr key={row.time} className="border-t border-gray-800/40 hover:bg-[#252525]">
                            <td className="px-1.5 py-1 text-gray-400 whitespace-nowrap">{row.time.slice(2).replace(/-/g, ".")}</td>
                            <td className={`px-1.5 py-1 text-right font-medium ${priceColor}`}>{formatPrice(row.close)}</td>
                            <td className={`px-1.5 py-1 text-right ${priceColor}`}>
                              {prevClose ? `${isUp ? "+" : ""}${changeRate.toFixed(2)}%` : "-"}
                            </td>
                            <td className="px-1.5 py-1 text-right text-gray-300">{formatPrice(row.volume)}</td>
                            <td className="px-1.5 py-1 text-right text-gray-300">{formatPrice(row.open)}</td>
                            <td className="px-1.5 py-1 text-right text-red-400">{formatPrice(row.high)}</td>
                            <td className="px-1.5 py-1 text-right text-blue-400">{formatPrice(row.low)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Order Form - Right Side */}
              <div className="lg:col-span-1 flex flex-col bg-[#1a1a1a] rounded-lg border border-gray-800 p-3 h-[575px] overflow-y-auto">
                {/* Header */}
                <div className="mb-3">
                  <h2 className="text-lg font-semibold text-white">
                    주문하기
                  </h2>
                </div>

                {/* 가상계좌 선택 */}
                <div
                  className="mb-4 pb-3 border-b border-gray-800 relative"
                  ref={accountDropdownRef}
                >
                  <label className="block text-xs font-medium text-gray-300 mb-2">
                    가상계좌
                  </label>
                  <button
                    onClick={() =>
                      setIsAccountDropdownOpen(!isAccountDropdownOpen)
                    }
                    className="w-full px-3 py-2 border border-gray-700 rounded-md bg-[#1a1a1a] text-white text-sm flex items-center justify-between hover:bg-[#252525] transition-colors"
                  >
                    <span className="text-left">
                      {selectedAccount
                        ? `${selectedAccount.name} (${formatPrice(
                            selectedAccount.currentBalance
                          )}원)`
                        : virtualAccounts.length === 0
                        ? "가상계좌가 없습니다"
                        : "가상계좌를 선택하세요"}
                    </span>
                    <CaretDown className="w-4 h-4" />
                  </button>

                  {/* Dropdown Menu */}
                  {isAccountDropdownOpen && (
                    <div className="absolute top-full left-0 right-0 mt-0 bg-[#1a1a1a] border border-gray-800 rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto">
                      {virtualAccounts.length === 0 ? (
                        <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                          가상계좌가 없습니다
                        </div>
                      ) : (
                        virtualAccounts.map((account) => (
                          <button
                            key={account.id}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setSelectedAccountId(account.id);
                              setIsAccountDropdownOpen(false);
                            }}
                            className={`w-full px-3 py-2 text-xs font-medium text-left hover:bg-gray-900 transition-colors ${
                              selectedAccountId === account.id
                                ? "bg-gray-900 text-blue-400"
                                : "text-gray-300"
                            }`}
                          >
                            {account.name} (
                            {formatPrice(account.currentBalance)}
                            원)
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>

                {/* Tabs */}
                <div className="flex items-center gap-2 mb-4">
                  <button
                    onClick={() => setTransactionType("buy")}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      transactionType === "buy"
                        ? "bg-red-600 text-white"
                        : "bg-gray-900 text-gray-300 hover:bg-gray-800"
                    }`}
                  >
                    매수
                  </button>
                  <button
                    onClick={() => setTransactionType("sell")}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      transactionType === "sell"
                        ? "bg-red-600 text-white"
                        : "bg-gray-900 text-gray-300 hover:bg-gray-800"
                    }`}
                  >
                    매도
                  </button>
                  <button
                    onClick={() => { setTransactionType("pending"); loadPendingOrders(); }}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      transactionType === "pending"
                        ? "bg-yellow-600 text-white"
                        : "bg-gray-900 text-gray-300 hover:bg-gray-800"
                    }`}
                  >
                    미체결{pendingOrders.length > 0 && ` (${pendingOrders.length})`}
                  </button>
                </div>

                {/* 미체결 주문 목록 */}
                {transactionType === "pending" && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-gray-300">미체결 주문</span>
                      <button
                        onClick={loadPendingOrders}
                        className="text-xs text-gray-400 hover:text-white"
                      >
                        새로고침
                      </button>
                    </div>
                    {pendingOrders.length === 0 ? (
                      <p className="text-xs text-gray-500 py-4 text-center">미체결 주문이 없습니다.</p>
                    ) : (
                      pendingOrders.map((order) => (
                        <div
                          key={order.id}
                          className="flex items-center justify-between p-3 rounded-md bg-[#111] border border-gray-800"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`text-xs font-bold ${order.type === "buy" ? "text-red-400" : "text-blue-400"}`}>
                                {order.type === "buy" ? "매수" : "매도"}
                              </span>
                              <span className="text-xs text-white truncate">{order.name}</span>
                            </div>
                            <div className="text-xs text-gray-400 mt-0.5">
                              {formatPrice(order.price)}원 × {order.quantity}주
                            </div>
                            <div className="text-xs text-gray-500">
                              {new Date(order.timestamp).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                            </div>
                          </div>
                          <button
                            onClick={async () => {
                              const res = await cancelOrder(selectedAccountId!, order.id);
                              if (res.success) {
                                await loadPendingOrders();
                                const acc = await getAccount(selectedAccountId!);
                                if (acc) setAvailableAmount(acc.currentBalance);
                                getAllAccounts().then(setVirtualAccounts);
                              } else {
                                alert(res.error ?? "취소 실패");
                              }
                            }}
                            className="ml-3 px-2 py-1 text-xs rounded border border-gray-600 text-gray-400 hover:border-red-500 hover:text-red-400 transition-colors"
                          >
                            취소
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* Order Form */}
                {transactionType !== "pending" && <div className="space-y-2.5">
                  {/* 주문 가격 유형 */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="text-xs font-medium text-gray-300">
                        {transactionType === "buy" ? "매수" : "매도"} 가격
                      </label>
                      <div className="flex items-center gap-3">
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name="priceType"
                            checked={priceType === "limit"}
                            onChange={() => setPriceType("limit")}
                            className="w-3.5 h-3.5 text-red-600 border-gray-300 focus:ring-red-500"
                          />
                          <span className="text-xs text-gray-300">지정가</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="radio"
                            name="priceType"
                            checked={priceType === "market"}
                            onChange={() => {
                              setPriceType("market");
                              if (currentPrice) setPrice(currentPrice.toString());
                            }}
                            className="w-3.5 h-3.5 text-red-600 border-gray-300 focus:ring-red-500"
                          />
                          <span className="text-xs text-gray-300">시장가</span>
                        </label>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={priceType === "market" ? "" : (price ? Number(price).toLocaleString("ko-KR") : "")}
                        onChange={(e) => {
                          const raw = e.target.value.replace(/,/g, "");
                          if (raw === "" || /^\d+$/.test(raw)) setPrice(raw);
                        }}
                        disabled={priceType === "market"}
                        className="flex-1 px-1 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-white text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                        placeholder={priceType === "market" ? "시장가 자동" : "619,000"}
                      />
                      <span className="text-base font-bold text-gray-300 px-3">
                        원
                      </span>
                      <button
                        onClick={() =>
                          setPrice((prev) => { const cur = Number(prev.replace(/,/g, "") || 0); return Math.max(0, cur - getTickSize(cur)).toString(); })
                        }
                        className="px-5 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 text-base font-bold"
                      >
                        -
                      </button>
                      <button
                        onClick={() =>
                          setPrice((prev) => { const cur = Number(prev.replace(/,/g, "") || 0); return (cur + getTickSize(cur)).toString(); })
                        }
                        className="px-5 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 text-base font-bold"
                      >
                        +
                      </button>
                    </div>
                  </div>

                  {/* 수량 */}
                  <div>
                    <label className="block text-xs font-medium text-gray-300 mb-2">
                      수량
                    </label>
                    <div className="flex items-center gap-2 mb-2">
                      <input
                        type="number"
                        min={0}
                        value={quantity}
                        onChange={(e) => setQuantity(Math.floor(Number(e.target.value)).toString())}
                        step={1}
                        className="flex-1 px-1 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-white text-sm [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                        placeholder="최대 0주 가능"
                      />
                      <button
                        onClick={() =>
                          setQuantity((prev) =>
                            Math.max(0, Number(prev || 0) - 1).toString()
                          )
                        }
                        className="px-5 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 text-base font-bold"
                      >
                        -
                      </button>
                      <button
                        onClick={() =>
                          setQuantity((prev) =>
                            (Number(prev || 0) + 1).toString()
                          )
                        }
                        className="px-5 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 text-base font-bold"
                      >
                        +
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          const maxQty = Math.floor(
                            availableAmount / Number(price || 1)
                          );
                          setQuantity(Math.floor(maxQty * 0.1).toString());
                        }}
                        className="px-2 py-1 text-xs border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600"
                      >
                        10%
                      </button>
                      <button
                        onClick={() => {
                          const maxQty = Math.floor(
                            availableAmount / Number(price || 1)
                          );
                          setQuantity(Math.floor(maxQty * 0.25).toString());
                        }}
                        className="px-2 py-1 text-xs border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600"
                      >
                        25%
                      </button>
                      <button
                        onClick={() => {
                          const maxQty = Math.floor(
                            availableAmount / Number(price || 1)
                          );
                          setQuantity(Math.floor(maxQty * 0.5).toString());
                        }}
                        className="px-2 py-1 text-xs border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600"
                      >
                        50%
                      </button>
                      <button
                        onClick={() => {
                          const maxQty = Math.floor(
                            availableAmount / Number(price || 1)
                          );
                          setQuantity(maxQty.toString());
                        }}
                        className="px-2 py-1 text-xs border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600"
                      >
                        최대
                      </button>
                    </div>
                  </div>


                  {/* 구매가능 금액 */}
                  <div className="flex items-center justify-between py-1.5 border-top border-gray-800">
                    <span className="text-xs font-medium text-gray-300">
                      구매가능 금액
                    </span>
                    <span className="text-sm font-semibold text-white">
                      {formatPrice(availableAmount)}원
                    </span>
                  </div>

                  {/* 총 주문 금액 + 수수료 */}
                  <div className="space-y-1 pt-1 border-t border-gray-800">
                    <div className="flex items-center justify-between py-1">
                      <span className="text-xs text-gray-400">주문금액</span>
                      <span className="text-xs text-gray-300">
                        {formatPrice(Number(price || 0) * Number(quantity || 0))}원
                      </span>
                    </div>
                    <div className="flex items-center justify-between py-1">
                      <span className="text-xs text-gray-400">예상 수수료 (0.015%)</span>
                      <span className="text-xs text-gray-300">
                        {formatPrice(Math.floor(Number(price || 0) * Number(quantity || 0) * 0.00015))}원
                      </span>
                    </div>
                    <div className="flex items-center justify-between py-1">
                      <span className="text-xs font-medium text-gray-300">
                        {transactionType === "buy" ? "총 필요금액" : "예상 수령금액"}
                      </span>
                      <span className="text-sm font-semibold text-white">
                        {(() => {
                          const amt = Number(price || 0) * Number(quantity || 0);
                          const fee = Math.floor(amt * 0.00015);
                          return formatPrice(transactionType === "buy" ? amt + fee : amt - fee);
                        })()}원
                      </span>
                    </div>
                  </div>

                  {/* Submit Button */}
                  <button
                    onClick={handleOrder}
                    className={`w-full py-3 rounded-md font-semibold text-white text-sm transition-colors ${
                      transactionType === "buy"
                        ? "bg-red-600 hover:bg-red-700"
                        : "bg-blue-600 hover:bg-blue-700"
                    }`}
                  >
                    {transactionType === "buy"
                      ? priceType === "market" ? "시장가 매수" : "지정가 매수"
                      : priceType === "market" ? "시장가 매도" : "지정가 매도"}
                  </button>
                </div>}
              </div>
            </div>
          </>
        )}

        {activeTab === "info" && (
          <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold text-white mb-4">종목정보</h2>
            {stockInfo ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 className="text-sm font-medium text-gray-400 mb-3">
                    기본 정보
                  </h3>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">종목명</span>
                      <span className="text-sm text-white">
                        {stockInfo.name || selectedStockName}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">종목코드</span>
                      <span className="text-sm text-white">{symbol}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">섹터</span>
                      <span className="text-sm text-white">
                        {stockInfo.sector || "-"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">업종</span>
                      <span className="text-sm text-white">
                        {stockInfo.industry || "-"}
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-medium text-gray-400 mb-3">
                    재무 정보
                  </h3>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">시가총액</span>
                      <span className="text-sm text-white">
                        {stockInfo.marketCap
                          ? formatPrice(stockInfo.marketCap)
                          : "-"}
                        원
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">PER</span>
                      <span className="text-sm text-white">
                        {stockInfo.pe ? stockInfo.pe.toFixed(2) : "-"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">PBR</span>
                      <span className="text-sm text-white">
                        {stockInfo.pbr ? stockInfo.pbr.toFixed(2) : "-"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-gray-400">현재가</span>
                      <span className="text-sm text-white">
                        {currentPrice ? formatPrice(currentPrice) : "-"}원
                      </span>
                    </div>
                  </div>
                </div>
                {stockInfo.description && (
                  <div className="md:col-span-2">
                    <h3 className="text-sm font-medium text-gray-400 mb-3">
                      기업 개요
                    </h3>
                    <p className="text-sm text-gray-300 leading-relaxed">
                      {stockInfo.description}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-gray-400">종목 정보를 불러오는 중...</p>
              </div>
            )}
          </div>
        )}

        {activeTab === "news" && (
          <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold text-white mb-4">
              뉴스 · 공시
            </h2>
            <div className="space-y-4">
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-medium text-white">주요 공시</h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {selectedStockName || symbol} 관련 주요 공시사항이 없습니다.
                </p>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-medium text-white">최신 뉴스</h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {selectedStockName || symbol} 관련 최신 뉴스가 없습니다.
                </p>
              </div>
            </div>
          </div>
        )}

        {activeTab === "trading" && (
          <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold text-white mb-4">거래현황</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">일일 거래량</div>
                  <div className="text-lg font-semibold text-white">
                    {stockInfo?.volume ? formatPrice(stockInfo.volume) : "-"}
                  </div>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">거래대금</div>
                  <div className="text-lg font-semibold text-white">
                    {currentPrice && stockInfo?.volume
                      ? formatPrice(currentPrice * stockInfo.volume)
                      : "-"}
                    원
                  </div>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">고가</div>
                  <div className="text-lg font-semibold text-red-400">
                    {stockInfo?.high ? formatPrice(stockInfo.high) : "-"}원
                  </div>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">저가</div>
                  <div className="text-lg font-semibold text-blue-400">
                    {stockInfo?.low ? formatPrice(stockInfo.low) : "-"}원
                  </div>
                </div>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <h3 className="text-sm font-medium text-white mb-3">
                  최근 거래 내역
                </h3>
                <div className="text-sm text-gray-400">
                  최근 거래 내역이 없습니다.
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "community" && (
          <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold text-white mb-4">커뮤니티</h2>
            <div className="space-y-4">
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-medium text-white">
                    인기 게시글
                  </h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {selectedStockName || symbol} 관련 커뮤니티 게시글이 없습니다.
                </p>
              </div>
              <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-medium text-white">토론</h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {selectedStockName || symbol} 관련 토론이 없습니다.
                </p>
              </div>
            </div>
          </div>
        )}

        {activeTab === "analysis" && (
          <div className="space-y-6">
            {/* Stock Header */}
            <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h1 className="text-2xl font-bold text-white mb-1">
                    {selectedStockName || symbol}
                  </h1>
                  <p className="text-sm text-gray-400">{symbol}</p>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-white mb-1">
                    {currentPrice ? formatPrice(currentPrice) : "-"}원
                  </div>
                  <div
                    className={`text-sm font-medium ${
                      currentPrice && stockInfo?.previousClose
                        ? currentPrice >= stockInfo.previousClose
                          ? "text-red-400"
                          : "text-blue-400"
                        : "text-gray-400"
                    }`}
                  >
                    {currentPrice && stockInfo?.previousClose
                      ? `${
                          currentPrice >= stockInfo.previousClose ? "+" : ""
                        }${(
                          ((currentPrice - stockInfo.previousClose) /
                            stockInfo.previousClose) *
                          100
                        ).toFixed(2)}%`
                      : "-"}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-gray-800">
                <div>
                  <div className="text-xs text-gray-400 mb-1">시가총액</div>
                  <div className="text-sm font-semibold text-white">
                    {stockInfo?.marketCap
                      ? formatPrice(stockInfo.marketCap)
                      : "-"}
                    원
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">거래량</div>
                  <div className="text-sm font-semibold text-white">
                    {stockInfo?.volume ? formatPrice(stockInfo.volume) : "-"}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">시장</div>
                  <div className="text-sm font-semibold text-white">
                    {stockInfo?.sector || "코스피"}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-400 mb-1">PER</div>
                  <div className="text-sm font-semibold text-white">
                    {stockInfo?.pe ? stockInfo.pe.toFixed(2) : "-"}
                  </div>
                </div>
              </div>
            </div>

            {/* AI Insight Card */}
            <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">
                AI 종합 인사이트
              </h2>
              <div className="space-y-4">
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-blue-400">✓</span>
                    <h3 className="text-sm font-medium text-white">
                      상승 요인 Top 3
                    </h3>
                  </div>
                  <ul className="space-y-1 text-sm text-gray-300 ml-6">
                    <li>• 20일 이동평균선 상향 돌파</li>
                    <li>• 기관 5일 연속 순매수</li>
                    <li>• 거래량 20일 평균 대비 +230%</li>
                  </ul>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-red-400">✗</span>
                    <h3 className="text-sm font-medium text-white">
                      하락 요인 Top 3
                    </h3>
                  </div>
                  <ul className="space-y-1 text-sm text-gray-300 ml-6">
                    <li>• RSI 과매수 구간 진입</li>
                    <li>• 단기 급등으로 조정 압력</li>
                    <li>• 외국인 3일 연속 순매도</li>
                  </ul>
                </div>
                <div className="p-4 bg-[#0f0f0f] rounded-lg border border-gray-800">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-yellow-400">⚠</span>
                    <h3 className="text-sm font-medium text-white">
                      리스크 요약
                    </h3>
                  </div>
                  <p className="text-sm text-gray-300 ml-6">
                    변동성 확대, 단기 급등으로 인한 조정 가능성 존재
                  </p>
                </div>
              </div>
            </div>

            {/* Main Chart + Tabs */}
            <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-6">
              <div className="mb-4">
                <div className="flex items-center gap-1 mb-2">
                  {(["1Y", "3Y", "5Y"] as const).map((r) => (
                    <button
                      key={r}
                      onClick={() => setChartRange(r)}
                      className={`px-2.5 py-1 text-xs rounded transition-colors ${
                        chartRange === r
                          ? "bg-gray-600 text-white"
                          : "text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {r}
                    </button>
                  ))}
                  <div className="mx-1 h-3 border-l border-gray-700" />
                  {(["day", "week", "month"] as const).map((p) => (
                    <button
                      key={p}
                      onClick={() => setChartPeriod(p)}
                      className={`px-2.5 py-1 text-xs rounded transition-colors ${
                        chartPeriod === p
                          ? "bg-gray-600 text-white"
                          : "text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {p === "day" ? "일" : p === "week" ? "주" : "월"}
                    </button>
                  ))}
                </div>
                <div className="h-[550px] bg-[#0f0f0f] rounded-lg border border-gray-800 mb-4">
                  <CandlestickChart data={candleData} />
                </div>

                {/* Chart Tabs */}
                <div className="flex items-center gap-2 border-b border-gray-800">
                  <button
                    onClick={() => setChartTab("technical")}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      chartTab === "technical"
                        ? "text-white bg-[#252525] border-b-2 border-transparent"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    기술
                  </button>
                  <button
                    onClick={() => setChartTab("flow")}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      chartTab === "flow"
                        ? "text-white bg-[#252525] border-b-2 border-transparent"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    수급
                  </button>
                  <button
                    onClick={() => setChartTab("financial")}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      chartTab === "financial"
                        ? "text-white bg-[#252525] border-b-2 border-transparent"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    재무
                  </button>
                  <button
                    onClick={() => setChartTab("news")}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      chartTab === "news"
                        ? "text-white bg-[#252525] border-b-2 border-transparent"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    뉴스
                  </button>
                </div>

                {/* Tab Content */}
                <div className="mt-4">
                  {chartTab === "technical" && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="p-3 bg-[#0f0f0f] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">
                          RSI (14일)
                        </div>
                        <div className="text-lg font-semibold text-white">
                          {currentPrice
                            ? (45 + Math.random() * 20).toFixed(1)
                            : "-"}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          중립 구간
                        </div>
                      </div>
                      <div className="p-3 bg-[#0f0f0f] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">MACD</div>
                        <div className="text-lg font-semibold text-white">
                          {currentPrice
                            ? (Math.random() * 1000 - 500).toFixed(2)
                            : "-"}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          신호선 대비
                        </div>
                      </div>
                      <div className="p-3 bg-[#0f0f0f] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">
                          볼린저 밴드
                        </div>
                        <div className="text-sm text-white">
                          상단:{" "}
                          {currentPrice
                            ? formatPrice(currentPrice * 1.05)
                            : "-"}
                          원
                        </div>
                        <div className="text-sm text-white">
                          하단:{" "}
                          {currentPrice
                            ? formatPrice(currentPrice * 0.95)
                            : "-"}
                          원
                        </div>
                      </div>
                      <div className="p-3 bg-[#0f0f0f] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-1">
                          이동평균선
                        </div>
                        <div className="text-sm text-white">
                          5일:{" "}
                          {currentPrice
                            ? formatPrice(currentPrice * 0.99)
                            : "-"}
                          원
                        </div>
                        <div className="text-sm text-white">
                          20일:{" "}
                          {currentPrice
                            ? formatPrice(currentPrice * 0.97)
                            : "-"}
                          원
                        </div>
                        <div className="text-sm text-white">
                          60일:{" "}
                          {currentPrice
                            ? formatPrice(currentPrice * 0.95)
                            : "-"}
                          원
                        </div>
                      </div>
                    </div>
                  )}

                  {chartTab === "flow" && (
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 mb-4">
                        {(["1D", "1W", "1M", "3M", "1Y"] as const).map(
                          (period) => (
                            <button
                              key={period}
                              onClick={() => setFlowPeriod(period)}
                              className={`px-3 py-1 text-xs rounded transition-colors ${
                                flowPeriod === period
                                  ? "bg-blue-600 text-white"
                                  : "bg-[#0f0f0f] text-gray-400 hover:text-white"
                              }`}
                            >
                              {period}
                            </button>
                          )
                        )}
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="p-4 bg-[#0f0f0f] rounded border border-gray-800">
                          <div className="text-xs text-gray-400 mb-2">
                            기관 순매수
                          </div>
                          <div className="text-lg font-semibold text-blue-400 mb-2">
                            +120억원
                          </div>
                          <div className="text-xs text-gray-500">5일 연속</div>
                        </div>
                        <div className="p-4 bg-[#0f0f0f] rounded border border-gray-800">
                          <div className="text-xs text-gray-400 mb-2">
                            외국인 순매수
                          </div>
                          <div className="text-lg font-semibold text-red-400 mb-2">
                            -50억원
                          </div>
                          <div className="text-xs text-gray-500">3일 연속</div>
                        </div>
                        <div className="p-4 bg-[#0f0f0f] rounded border border-gray-800">
                          <div className="text-xs text-gray-400 mb-2">
                            개인 순매수
                          </div>
                          <div className="text-lg font-semibold text-blue-400 mb-2">
                            -70억원
                          </div>
                          <div className="text-xs text-gray-500">2일 연속</div>
                        </div>
                      </div>
                      <div className="p-4 bg-[#0f0f0f] rounded border border-gray-800">
                        <div className="text-xs text-gray-400 mb-2">
                          수급 그래프
                        </div>
                        <div className="h-32 flex items-end gap-1">
                          {Array.from({ length: 20 }).map((_, i) => (
                            <div
                              key={i}
                              className="flex-1 bg-blue-600 rounded-t"
                              style={{
                                height: `${Math.random() * 100}%`,
                              }}
                            />
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {chartTab === "financial" && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <h4 className="text-sm font-medium text-gray-400 mb-3">
                          핵심 지표
                        </h4>
                        <div className="space-y-2">
                          <div className="flex justify-between p-2 bg-[#0f0f0f] rounded">
                            <span className="text-sm text-gray-400">PER</span>
                            <span className="text-sm text-white font-medium">
                              {stockInfo?.pe ? stockInfo.pe.toFixed(2) : "-"}
                            </span>
                          </div>
                          <div className="flex justify-between p-2 bg-[#0f0f0f] rounded">
                            <span className="text-sm text-gray-400">PBR</span>
                            <span className="text-sm text-white font-medium">
                              {stockInfo?.pbr ? stockInfo.pbr.toFixed(2) : "-"}
                            </span>
                          </div>
                          <div className="flex justify-between p-2 bg-[#0f0f0f] rounded">
                            <span className="text-sm text-gray-400">ROE</span>
                            <span className="text-sm text-white font-medium">
                              {stockInfo?.pe
                                ? (stockInfo.pe * 0.1).toFixed(2)
                                : "-"}
                              %
                            </span>
                          </div>
                        </div>
                      </div>
                      <div>
                        <h4 className="text-sm font-medium text-gray-400 mb-3">
                          실적 트렌드
                        </h4>
                        <div className="p-4 bg-[#0f0f0f] rounded border border-gray-800">
                          <div className="h-32 flex items-end gap-2">
                            {Array.from({ length: 5 }).map((_, i) => (
                              <div
                                key={i}
                                className="flex-1 bg-blue-600 rounded-t"
                                style={{
                                  height: `${60 + Math.random() * 40}%`,
                                }}
                              />
                            ))}
                          </div>
                          <div className="text-xs text-gray-400 mt-2 text-center">
                            최근 5년 매출 추이
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {chartTab === "news" && (
                    <div className="space-y-3">
                      {[1, 2, 3].map((i) => (
                        <div
                          key={i}
                          className="p-4 bg-[#0f0f0f] rounded border border-gray-800"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <h4 className="text-sm font-medium text-white">
                              {selectedStockName || symbol} 관련 주요 뉴스 {i}
                            </h4>
                            <span className="text-xs text-gray-500">
                              2024.01.{15 + i}
                            </span>
                          </div>
                          <p className="text-sm text-gray-300 mb-2">
                            {selectedStockName || symbol} 관련 뉴스 요약 내용...
                          </p>
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-1 text-xs bg-blue-600/20 text-blue-400 rounded">
                              #AI
                            </span>
                            <span className="px-2 py-1 text-xs bg-blue-600/20 text-blue-400 rounded">
                              긍정 +0.7
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 p-12 text-center">
              <ChartBar className="w-16 h-16 text-gray-600 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-white mb-2">
                종목 분석
              </h3>
              <p className="text-sm text-gray-400 mb-4">
                종목 분석 기능은 전략연구소에서 이용하실 수 있습니다
              </p>
              <button
                onClick={() => router.push("/analytics")}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-600"
              >
                전략연구소로 이동
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
