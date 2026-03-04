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
import OrderBook from "@/components/order/OrderBook";
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
  refreshAccountValue,
  updateHolding,
  addTransaction,
  updateAccount,
  getHoldingsByAccount,
} from "@/lib/portfolio";
import type { VirtualAccount } from "@/types/portfolio";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
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
  const [isUnsettledTransaction, setIsUnsettledTransaction] = useState(false);
  const [availableAmount, setAvailableAmount] = useState(12); // 구매가능 금액
  const [chartPeriod, setChartPeriod] = useState<"day" | "week" | "month">(
    "day"
  );
  const [virtualAccounts, setVirtualAccounts] = useState<VirtualAccount[]>([]);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const accountDropdownRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<
    "chart" | "info" | "news" | "trading" | "community" | "analysis"
  >("chart");
  const [chartTab, setChartTab] = useState<
    "technical" | "flow" | "financial" | "news"
  >("technical");
  const [flowPeriod, setFlowPeriod] = useState<
    "1D" | "1W" | "1M" | "3M" | "1Y"
  >("1M");

  // 가상계좌 목록 로드 및 주기적 업데이트
  useEffect(() => {
    const loadAccounts = () => {
      const accounts = getAllAccounts();
      accounts.forEach((account) => {
        refreshAccountValue(account.id);
      });
      const updatedAccounts = getAllAccounts();

      // 이전 계좌 목록과 비교하여 실제로 변경된 경우에만 업데이트
      setVirtualAccounts((prevAccounts) => {
        // 계좌 개수가 다르면 업데이트
        if (prevAccounts.length !== updatedAccounts.length) {
          return updatedAccounts;
        }

        // ID 기반으로 계좌를 매핑하여 비교
        const prevMap = new Map(prevAccounts.map((acc) => [acc.id, acc]));
        const hasChanged = updatedAccounts.some((current) => {
          const prev = prevMap.get(current.id);
          if (!prev) return true; // 새 계좌가 추가됨

          // 잔액이나 총 자산이 변경되었는지 확인 (이름 변경은 무시)
          return (
            prev.currentBalance !== current.currentBalance ||
            prev.totalValue !== current.totalValue
          );
        });

        return hasChanged ? updatedAccounts : prevAccounts;
      });
    };

    // 초기 로드
    loadAccounts();

    // 주기적으로 업데이트 (3초마다)
    const interval = setInterval(loadAccounts, 3000);

    return () => clearInterval(interval);
  }, []); // 초기 로드 시 한 번만 실행

  // 초기 로드 시 기본 계좌 선택
  useEffect(() => {
    if (!selectedAccountId) {
      const accounts = getAllAccounts();
      if (accounts.length > 0) {
        setSelectedAccountId(accounts[0].id);
      }
    }
  }, []); // 초기 로드 시 한 번만 실행

  // 선택된 계좌 변경 시 잔액 업데이트
  useEffect(() => {
    if (selectedAccountId) {
      const account = getAccount(selectedAccountId);
      if (account) {
        // 잔액만 즉시 업데이트 (refreshAccountValue는 loadAccounts에서 처리)
        setAvailableAmount(account.currentBalance);
      } else {
        setAvailableAmount(0);
      }
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

  // 매수/매도 주문 처리
  const handleOrder = async () => {
    if (!selectedAccountId) {
      alert("가상계좌를 선택해주세요.");
      return;
    }

    if (!symbol) {
      alert("종목을 선택해주세요.");
      return;
    }

    if (!quantity || !price) {
      alert("수량과 가격을 입력해주세요.");
      return;
    }

    const account = getAccount(selectedAccountId);
    if (!account) {
      alert("계좌를 찾을 수 없습니다.");
      return;
    }

    const qty = parseInt(quantity);
    const prc = parseFloat(price);

    if (isNaN(qty) || qty <= 0 || isNaN(prc) || prc <= 0) {
      alert("올바른 수량과 가격을 입력해주세요.");
      return;
    }

    const totalAmount = qty * prc;

    if (transactionType === "buy") {
      if (account.currentBalance < totalAmount) {
        alert("잔액이 부족합니다.");
        return;
      }

      // 종목 이름 가져오기
      let stockName = selectedStockName || symbol;
      try {
        const response = await fetch(`/api/stock/${symbol}/detail`);
        if (response.ok) {
          const data = await response.json();
          stockName = data.name || selectedStockName || symbol;
        }
      } catch (error) {
        console.error("Failed to fetch stock name:", error);
      }

      // 매수 처리
      updateHolding(selectedAccountId, symbol, qty, prc, stockName);
      updateAccount({
        ...account,
        currentBalance: account.currentBalance - totalAmount,
      });

      addTransaction({
        accountId: selectedAccountId,
        type: "buy",
        symbol: symbol,
        name: stockName,
        quantity: qty,
        price: prc,
        totalAmount,
      });

      // 계좌 정보 업데이트
      refreshAccountValue(selectedAccountId);
      const updatedAccount = getAccount(selectedAccountId);
      if (updatedAccount) {
        setAvailableAmount(updatedAccount.currentBalance);
      }

      // 가상계좌 목록 업데이트
      const updatedAccounts = getAllAccounts();
      setVirtualAccounts(updatedAccounts);

      alert(
        `매수가 완료되었습니다.\n종목: ${stockName}\n수량: ${qty}주\n가격: ${formatPrice(
          prc
        )}원\n총액: ${formatPrice(totalAmount)}원`
      );

      // 폼 초기화
      setQuantity("");
    } else if (transactionType === "sell") {
      // 매도 처리
      const holdings = getHoldingsByAccount(selectedAccountId);
      const holding = holdings.find((h) => h.symbol === symbol);

      if (!holding || holding.quantity < qty) {
        alert("보유 수량이 부족합니다.");
        return;
      }

      // 종목 이름 가져오기
      let stockName = holding.name || selectedStockName || symbol;

      updateHolding(selectedAccountId, symbol, -qty, prc, stockName);
      updateAccount({
        ...account,
        currentBalance: account.currentBalance + totalAmount,
      });

      addTransaction({
        accountId: selectedAccountId,
        type: "sell",
        symbol: symbol,
        name: stockName,
        quantity: qty,
        price: prc,
        totalAmount,
      });

      // 계좌 정보 업데이트
      refreshAccountValue(selectedAccountId);
      const updatedAccount = getAccount(selectedAccountId);
      if (updatedAccount) {
        setAvailableAmount(updatedAccount.currentBalance);
      }

      // 가상계좌 목록 업데이트
      const updatedAccounts = getAllAccounts();
      setVirtualAccounts(updatedAccounts);

      alert(
        `매도가 완료되었습니다.\n종목: ${stockName}\n수량: ${qty}주\n가격: ${formatPrice(
          prc
        )}원\n총액: ${formatPrice(totalAmount)}원`
      );

      // 폼 초기화
      setQuantity("");
    } else {
      // 대기 주문 (아직 구현되지 않음)
      alert("대기 주문 기능은 아직 구현되지 않았습니다.");
    }
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
          if (data.currentPrice) {
            setPrice(data.currentPrice.toString());
            setCurrentPrice(data.currentPrice);
          } else {
            const basePrice = getBasePrice(symbol);
            if (basePrice) {
              setCurrentPrice(basePrice);
              setPrice(basePrice.toString());
            }
          }
        })
        .catch((error) => {
          console.error("Failed to fetch stock info:", error);
          const basePrice = getBasePrice(symbol);
          if (basePrice) {
            setCurrentPrice(basePrice);
            setPrice(basePrice.toString());
          }
        });
    }
  }, [symbol]);

  // 주기적으로 가격 업데이트
  useEffect(() => {
    if (!symbol) return;

    const interval = setInterval(() => {
      const priceData = generateStockPriceData(symbol);
      setCurrentPrice(priceData.currentPrice);
      // 지정가가 아니거나 가격이 선택되지 않았을 때만 자동 업데이트
      if (priceType === "market" && !selectedOrderPrice) {
        setPrice(priceData.currentPrice.toString());
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [symbol, priceType, selectedOrderPrice]);

  // 차트용 캔들 데이터 생성: 일=1년, 주/월=5년
  const candleData: OHLCV[] = useMemo(() => {
    const now = new Date();
    const base = Number(currentPrice || getBasePrice(symbol) || 100000);
    const data: OHLCV[] = [];

    const addPoint = (d: Date, prevClose: number) => {
      const drift = (Math.random() - 0.5) * (base * 0.01); // 변동폭 (기간에 상관없이 상대적)
      const open = prevClose;
      const close = Math.max(1, open + drift);
      const high = Math.max(open, close) + Math.abs(drift) * 0.6;
      const low = Math.min(open, close) - Math.abs(drift) * 0.6;
      const volume = Math.floor(100000 + Math.random() * 300000);
      const time = d.toISOString().slice(0, 10);
      data.push({ time, open, high, low, close, volume });
      return close;
    };

    // 시작 날짜 계산
    let start = new Date(now);
    if (chartPeriod === "day") {
      start.setFullYear(start.getFullYear() - 1); // 1년
    } else {
      start.setFullYear(start.getFullYear() - 5); // 5년
    }

    // 최초 종가 기준값
    let prevClose = base;

    // 일/주/월 간격으로 루프
    const cursor = new Date(start);
    while (cursor <= now) {
      // 주말은 건너뛰기 (일간일 때만)
      if (chartPeriod === "day") {
        const day = cursor.getDay();
        if (day === 0 || day === 6) {
          cursor.setDate(cursor.getDate() + 1);
          continue;
        }
        prevClose = addPoint(new Date(cursor), prevClose);
        cursor.setDate(cursor.getDate() + 1);
      } else if (chartPeriod === "week") {
        prevClose = addPoint(new Date(cursor), prevClose);
        cursor.setDate(cursor.getDate() + 7);
      } else {
        prevClose = addPoint(new Date(cursor), prevClose);
        cursor.setMonth(cursor.getMonth() + 1);
      }
    }

    return data;
  }, [symbol, currentPrice, chartPeriod]);

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
            {/* Stock Chart */}
            <div className="mb-6 bg-[#1a1a1a] rounded-lg border border-gray-800 p-3">
              <div className="h-72">
                <CandlestickChart data={candleData} />
              </div>
            </div>

            {/* Order Page */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-fade-in items-stretch">
              {/* Order Book - Left Side */}
              <div className="lg:col-span-1 flex animate-slide-in min-h-[440px]">
                <div className="flex-1 h-full">
                  <OrderBook
                    symbol={symbol}
                    currentPrice={currentPrice}
                    onPriceSelect={(selectedPrice) => {
                      setSelectedOrderPrice(selectedPrice);
                      setPriceType("limit");
                      setPrice(selectedPrice.toString());
                    }}
                  />
                </div>
              </div>
              {/* Order Form - Right Side */}
              <div className="lg:col-span-1 flex flex-col bg-[#1a1a1a] rounded-lg border border-gray-800 p-3 min-h-[440px]">
                {/* Header */}
                <div className="mb-3">
                  <h2 className="text-base font-semibold text-white">
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
                    onClick={() => setTransactionType("pending")}
                    className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                      transactionType === "pending"
                        ? "bg-red-600 text-white"
                        : "bg-gray-900 text-gray-300 hover:bg-gray-800"
                    }`}
                  >
                    대기
                  </button>
                </div>

                {/* Order Form */}
                <div className="space-y-4">
                  {/* 주문 유형 */}
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-gray-300">
                      주문 유형
                    </label>
                    <select
                      value={orderType === "limit" ? "general" : "market"}
                      onChange={(e) =>
                        setOrderType(
                          e.target.value === "general" ? "limit" : "market"
                        )
                      }
                      className="px-2 py-1.5 border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-white text-sm"
                    >
                      <option value="general">일반 주문</option>
                      <option value="market">시장가 주문</option>
                    </select>
                  </div>

                  {/* 매수 가격 */}
                  <div>
                    <label className="block text-xs font-medium text-gray-300 mb-2">
                      매수 가격
                    </label>
                    <div className="flex items-center gap-3 mb-2.5">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="priceType"
                          checked={priceType === "limit"}
                          onChange={() => setPriceType("limit")}
                          className="w-4 h-4 text-red-600 border-gray-300 focus:ring-red-500"
                        />
                        <span className="text-xs text-gray-300">지정가</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="priceType"
                          checked={priceType === "market"}
                          onChange={() => setPriceType("market")}
                          className="w-4 h-4 text-red-600 border-gray-300 focus:ring-red-500"
                        />
                        <span className="text-xs text-gray-300">시장가</span>
                      </label>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={price}
                        onChange={(e) => setPrice(e.target.value)}
                        className="flex-1 px-1 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-white text-sm [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                        placeholder="619,000"
                      />
                      <span className="text-base font-bold text-gray-300 px-3">
                        원
                      </span>
                      <button
                        onClick={() =>
                          setPrice((prev) => (Number(prev || 0) - 1).toString())
                        }
                        className="px-5 h-[38px] border border-gray-700 rounded-md bg-[#1a1a1a] border-gray-700 text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 text-base font-bold"
                      >
                        -
                      </button>
                      <button
                        onClick={() =>
                          setPrice((prev) => (Number(prev || 0) + 1).toString())
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
                        onChange={(e) => setQuantity(e.target.value)}
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
                          setQuantity((maxQty * 0.1).toString());
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
                          setQuantity((maxQty * 0.25).toString());
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
                          setQuantity((maxQty * 0.5).toString());
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

                  {/* 미수거래 */}
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-gray-300">
                      미수거래 (현금 50%)
                    </label>
                    <button
                      onClick={() =>
                        setIsUnsettledTransaction(!isUnsettledTransaction)
                      }
                      className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors ${
                        isUnsettledTransaction
                          ? "bg-red-600"
                          : "bg-gray-300 dark:bg-gray-600"
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          isUnsettledTransaction
                            ? "translate-x-5"
                            : "translate-x-1"
                        }`}
                      />
                    </button>
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

                  {/* 총 주문 금액 */}
                  <div className="flex items-center justify-between py-1.5 border-t border-gray-800">
                    <span className="text-xs font-medium text-gray-300">
                      총 주문 금액
                    </span>
                    <span className="text-sm font-semibold text-white">
                      {formatPrice(Number(price || 0) * Number(quantity || 0))}
                      원
                    </span>
                  </div>

                  {/* Submit Button */}
                  <button
                    onClick={handleOrder}
                    className={`w-full py-3 rounded-md font-semibold text-white text-sm transition-colors ${
                      transactionType === "buy"
                        ? "bg-red-600 hover:bg-red-700"
                        : transactionType === "sell"
                        ? "bg-blue-600 hover:bg-blue-600"
                        : "bg-gray-600 hover:bg-gray-700"
                    }`}
                  >
                    {transactionType === "buy"
                      ? "매수하기"
                      : transactionType === "sell"
                      ? "매도하기"
                      : "대기하기"}
                  </button>
                </div>
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
