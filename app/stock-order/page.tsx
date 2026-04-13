"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CaretDown,
  CheckCircle,
  Warning,
  X,
  ChartBar,
} from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import OrderBook, { MarketStats } from "@/components/order/OrderBook";
import { getBasePrice } from "@/lib/mock-stock-data";
import { formatMarketCap } from "@/lib/format-market-cap";
import CandlestickChart, { OHLCV } from "@/components/stock/CandlestickChart";
import {
  mergeStockInfo,
  pickPositiveNumber,
  pickStockName,
  sanitizeMarketCap,
} from "@/app/stock-order/stock-info";
import { useStockPrices } from "@/lib/hooks/useStockPrices";
import type { StockPriceSnapshot as BatchQuoteItem } from "@/lib/stock-prices";
import { useDrawer } from "@/contexts/DrawerContext";
import {
  getAllAccounts,
  getAccount,
  executeTrade,
  getPendingOrders,
  cancelOrder,
  fillPendingOrders,
  getHoldingsByAccount,
} from "@/lib/portfolio";
import type { VirtualAccount, PendingOrder } from "@/types/portfolio";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

const STOCK_DETAIL_RETRY_DELAYS_MS = [0, 400, 1200];

function applyRealtimeToLatestCandle(
  candles: OHLCV[] | null,
  quote?: BatchQuoteItem | null
): OHLCV[] {
  if (!candles || candles.length === 0) return [];
  if (!quote?.price || quote.price <= 0) return candles;

  const next = [...candles];
  const last = next[next.length - 1];
  const today = quote.date || new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
  }).format(new Date());
  const realtimeOpen = quote.open && quote.open > 0 ? quote.open : last.close;
  const realtimeHigh = quote.high && quote.high > 0 ? quote.high : Math.max(realtimeOpen, quote.price);
  const realtimeLow = quote.low && quote.low > 0 ? quote.low : Math.min(realtimeOpen, quote.price);
  const realtimeVolume = quote.volume ?? 0;

  if (last.time < today) {
    next.push({
      time: today,
      open: realtimeOpen,
      high: realtimeHigh,
      low: realtimeLow,
      close: quote.price,
      volume: realtimeVolume,
    });
    return next;
  }

  next[next.length - 1] = {
    ...last,
    open: realtimeOpen,
    close: quote.price,
    high: Math.max(last.high, realtimeHigh),
    low: Math.min(last.low, realtimeLow),
    volume: Math.max(last.volume, realtimeVolume),
  };
  return next;
}

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

  const [selectedStockName, setSelectedStockName] = useState(
    pickStockName(symbol, name) ?? ""
  );
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
  const [priceType, setPriceType] = useState<"limit" | "market" | "best_limit" | "conditional">("limit");
  const [availableAmount, setAvailableAmount] = useState(0); // 구매가능 금액
  const [holdingQty, setHoldingQty] = useState(0); // 보유수량
  const [avgBuyPrice, setAvgBuyPrice] = useState(0); // 평균매수가
  const [orderConfirmStep, setOrderConfirmStep] = useState(false); // 주문확인 단계
  const [pendingOrders, setPendingOrders] = useState<PendingOrder[]>([]);
  const [chartPeriod, setChartPeriod] = useState<"day" | "week" | "month">(
    "day"
  );
  const [chartRange, setChartRange] = useState<"1Y" | "3Y" | "5Y">("1Y");
  const [virtualAccounts, setVirtualAccounts] = useState<VirtualAccount[]>([]);
  const [isAccountDropdownOpen, setIsAccountDropdownOpen] = useState(false);
  const [isStockInfoLoading, setIsStockInfoLoading] = useState(false);
  const [isOhlcvLoading, setIsOhlcvLoading] = useState(false);
  const [liveQuote, setLiveQuote] = useState<BatchQuoteItem | null>(null);
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
  const { data: priceSnapshots } = useStockPrices(symbol ? [symbol] : [], {
    enabled: !!symbol,
    refetchInterval: 2000,
  });
  const realtimeQuote = symbol ? priceSnapshots?.[symbol] : undefined;

  // 가상계좌 목록 로드 및 주기적 업데이트
  useEffect(() => {
    let isMounted = true;

    const loadAccounts = async () => {
      const updatedAccounts = await getAllAccounts();
      if (!isMounted) return;
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

      if (!selectedAccountId && updatedAccounts.length > 0) {
        setSelectedAccountId(updatedAccounts[0].id);
      }
    };

    loadAccounts();
    const interval = setInterval(loadAccounts, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [selectedAccountId, setSelectedAccountId]);

  // 선택된 계좌 정보
  const selectedAccount = useMemo(() => {
    if (!selectedAccountId) return null;
    return virtualAccounts.find((acc) => acc.id === selectedAccountId);
  }, [selectedAccountId, virtualAccounts]);

  useEffect(() => {
    if (!selectedAccountId) {
      setAvailableAmount(0);
      return;
    }

    if (selectedAccount) {
      setAvailableAmount(selectedAccount.currentBalance);
      return;
    }

    getAccount(selectedAccountId).then((account) => {
      setAvailableAmount(account ? account.currentBalance : 0);
    });
  }, [selectedAccountId, selectedAccount]);

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

  // 보유수량/평균매수가 로드
  useEffect(() => {
    if (!selectedAccountId || !symbol) {
      setHoldingQty(0);
      setAvgBuyPrice(0);
      return;
    }
    getHoldingsByAccount(selectedAccountId).then((holdings) => {
      const h = holdings.find((h) => h.symbol === symbol);
      setHoldingQty(h?.quantity ?? 0);
      setAvgBuyPrice(h?.averagePrice ?? 0);
    });
  }, [selectedAccountId, symbol]);

  // 주문 확인 단계
  const handleOrderConfirm = () => {
    if (!selectedAccountId) { alert("가상계좌를 선택해주세요."); return; }
    if (!symbol) { alert("종목을 선택해주세요."); return; }
    if (transactionType !== "buy" && transactionType !== "sell") return;
    const qty = parseInt(quantity);
    const prc = priceType === "market" ? (currentPrice ?? 0) : parseFloat(price);
    if (!quantity || isNaN(qty) || qty <= 0) { alert("수량을 입력해주세요."); return; }
    if (priceType !== "market" && (!price || isNaN(prc) || prc <= 0)) { alert("가격을 입력해주세요."); return; }
    if (transactionType === "sell" && qty > holdingQty) { alert(`보유수량(${holdingQty}주)을 초과할 수 없습니다.`); return; }
    setOrderConfirmStep(true);
  };

  // 매수/매도 주문 처리
  const handleOrder = async () => {
    if (!selectedAccountId) { alert("가상계좌를 선택해주세요."); return; }
    if (!symbol) { alert("종목을 선택해주세요."); return; }
    if (transactionType !== "buy" && transactionType !== "sell") return;
    const qty = parseInt(quantity);
    const prc = priceType === "market" ? (currentPrice ?? parseFloat(price || "0")) : parseFloat(price);
    if (isNaN(qty) || qty <= 0) { alert("수량을 올바르게 입력해주세요."); return; }
    if (priceType !== "market" && (isNaN(prc) || prc <= 0)) { alert("가격을 올바르게 입력해주세요."); return; }

    setOrderConfirmStep(false);
    const orderTypeMapped: "MARKET" | "LIMIT" = priceType === "market" ? "MARKET" : "LIMIT";

    // 종목 이름 확정
    let stockName = pickStockName(symbol, selectedStockName, stockInfo?.name) || symbol;
    try {
      const res = await fetch(`/api/stock/${symbol}/detail`);
      if (res.ok) {
        const data = await res.json();
        stockName = pickStockName(symbol, data.name, stockName) || symbol;
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
    // 보유수량 갱신
    getHoldingsByAccount(selectedAccountId).then((holdings) => {
      const h = holdings.find((h) => h.symbol === symbol);
      setHoldingQty(h?.quantity ?? 0);
      setAvgBuyPrice(h?.averagePrice ?? 0);
    });
  };

  // URL 파라미터에서 name이 변경될 때 selectedStockName 업데이트
  useEffect(() => {
    const routeName = pickStockName(symbol, name);
    if (routeName) {
      setSelectedStockName(routeName);
    }
  }, [name, symbol]);

  useEffect(() => {
    const routeName = pickStockName(symbol, name);
    const resolvedName = pickStockName(symbol, routeName, stockInfo?.name, selectedStockName);
    if (!symbol || resolvedName) return;

    let isMounted = true;

    fetch("/api/stocks/names")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!isMounted || !data || typeof data !== "object") return;
        const metadataName = pickStockName(
          symbol,
          data[symbol]?.name,
        );
        if (metadataName) {
          setSelectedStockName(metadataName);
        }
      })
      .catch(() => {
        // Keep the current fallback when metadata lookup fails.
      });

    return () => {
      isMounted = false;
    };
  }, [symbol, name, stockInfo?.name, selectedStockName]);

  useEffect(() => {
    if (symbol) {
      let cancelled = false;

      setIsStockInfoLoading(true);
      setStockInfo(null);
      setCurrentPrice(undefined);
      setPrice("");
      setSelectedOrderPrice(undefined);
      setSelectedStockName(pickStockName(symbol, name) ?? "");
      // 시가총액은 장중에 거의 변하지 않으므로 누락 시 짧게 재시도해 일시적인 상세 시세 실패를 흡수한다.
      const loadStockInfo = async () => {
        let hadSuccessfulResponse = false;

        for (const delayMs of STOCK_DETAIL_RETRY_DELAYS_MS) {
          if (delayMs > 0) {
            await new Promise((resolve) => setTimeout(resolve, delayMs));
          }
          if (cancelled) {
            return;
          }

          try {
            const res = await fetch(`/api/stock/${symbol}/detail`, { cache: "no-store" });
            const rawData = await res.json();
            const data = {
              ...rawData,
              marketCap: sanitizeMarketCap(
                symbol,
                rawData?.marketCap,
                rawData?.currentPrice
              ),
            };
            hadSuccessfulResponse = true;

            if (cancelled) {
              return;
            }

            setStockInfo((prev: any) => mergeStockInfo(prev, data));
            const resolvedName = pickStockName(symbol, data.name, name);
            if (resolvedName) {
              setSelectedStockName(resolvedName);
            }
            // 백엔드에서 실제 lastClose를 받았으면 즉시 설정 (interval이 undefined로 덮어쓰는 것 방지)
            if (data.realLastClose) {
              setRealLastClose(data.realLastClose);
            }
            // 실제 ohlcv 데이터가 이미 로드됐으면 mock 가격으로 덮어쓰지 않음
            const nextPrice = pickPositiveNumber(data.currentPrice, getBasePrice(symbol));
            if (!hasRealPriceRef.current && nextPrice) {
              setCurrentPrice((prev) => prev ?? nextPrice);
              setPrice((prev) => prev || nextPrice.toString());
            }

            if (pickPositiveNumber(data.marketCap)) {
              break;
            }
          } catch (error) {
            if (delayMs === STOCK_DETAIL_RETRY_DELAYS_MS[STOCK_DETAIL_RETRY_DELAYS_MS.length - 1]) {
              console.error("Failed to fetch stock info:", error);
            }
          }
        }

        if (!hadSuccessfulResponse && !hasRealPriceRef.current) {
          const basePrice = getBasePrice(symbol);
          if (basePrice) {
            setCurrentPrice((prev) => prev ?? basePrice);
            setPrice((prev) => prev || basePrice.toString());
          }
        }

        if (!cancelled) {
          setIsStockInfoLoading(false);
        }
      };

      loadStockInfo();

      return () => {
        cancelled = true;
      };
    }
  }, [symbol, name]);

  // 공용 시세 소스로부터 현재가/거래량 갱신 + 미체결 주문 체결 트리거
  useEffect(() => {
    if (!symbol || !realtimeQuote || realtimeQuote.price <= 0) return;

    let cancelled = false;

    const applyRealtimeQuote = async () => {
      setLiveQuote(realtimeQuote);
      setCurrentPrice(realtimeQuote.price);
      setStockInfo((prev: any) =>
        prev
          ? {
              ...prev,
              currentPrice: realtimeQuote.price,
              changePercent: realtimeQuote.changePercent,
              volume:
                realtimeQuote.source?.startsWith("kis") && realtimeQuote.volume > 0
                  ? realtimeQuote.volume
                  : prev.volume,
              open: realtimeQuote.open ?? prev.open,
              high: realtimeQuote.high ?? prev.high,
              low: realtimeQuote.low ?? prev.low,
              previousClose: realtimeQuote.previousClose ?? prev.previousClose,
            }
          : prev
      );

      if (priceType === "market" && !selectedOrderPrice) {
        setPrice(realtimeQuote.price.toString());
      }

      if (selectedAccountId) {
        const fillResult = await fillPendingOrders(
          selectedAccountId,
          symbol,
          realtimeQuote.price
        );
        if (!cancelled && fillResult.count > 0) {
          getAccount(selectedAccountId).then((acc) => {
            if (acc) setAvailableAmount(acc.currentBalance);
          });
          getAllAccounts().then(setVirtualAccounts);
          loadPendingOrders();
        }
      }
    };

    applyRealtimeQuote();

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, realtimeQuote, priceType, selectedOrderPrice, selectedAccountId]);

  // 파케이 실제 OHLCV 데이터 fetch (백엔드 가용 시)
  useEffect(() => {
    if (!symbol) return;
    hasRealPriceRef.current = false;  // symbol 변경 시 리셋
    setRealDailyCandles(null);
    setRealLastClose(undefined);
    setLiveQuote(null);
    setIsOhlcvLoading(true);
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
      .catch(() => {/* 백엔드 미실행 시 GBM fallback */})
      .finally(() => setIsOhlcvLoading(false));
  }, [symbol]);

  // 실제 파케이 데이터 기반 시세 요약 (OrderBook MarketSummary용)
  const realMarketStats = useMemo<MarketStats | undefined>(() => {
    if (!realDailyCandles || realDailyCandles.length < 2) return undefined;
    const candles = applyRealtimeToLatestCandle(realDailyCandles, liveQuote);
    const last = candles[candles.length - 1];
    const prev = candles[candles.length - 2];
    const year252 = candles.slice(-252);
    return {
      open: last.open,
      high: last.high,
      low: last.low,
      volume: last.volume,
      previousClose: prev.close,
      week52High: Math.max(...year252.map((c) => c.high)),
      week52Low: Math.min(...year252.map((c) => c.low)),
    };
  }, [realDailyCandles, liveQuote]);

  // 시세 패널용 2년치 일봉 데이터 (최신순)
  const priceHistoryData = useMemo(() => {
    if (!symbol) return [];
    if (!realDailyCandles) return [];
    const daily = applyRealtimeToLatestCandle(realDailyCandles, liveQuote);
    return daily.slice(-504).reverse();
  }, [symbol, realDailyCandles, liveQuote]);

  // 차트용 캔들 데이터: 실제 파케이 데이터 우선, 없으면 GBM fallback
  const candleData: OHLCV[] = useMemo(() => {
    if (!symbol) return [];
    if (!realDailyCandles) return [];

    const dailySource = applyRealtimeToLatestCandle(realDailyCandles, liveQuote);

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
  }, [symbol, chartPeriod, chartRange, realDailyCandles, liveQuote]);

  const referenceClose = realMarketStats?.previousClose ?? stockInfo?.previousClose ?? realLastClose;
  const priceChange =
    currentPrice !== undefined && referenceClose !== undefined
      ? currentPrice - referenceClose
      : undefined;
  const priceChangePercent =
    priceChange !== undefined && referenceClose
      ? (priceChange / referenceClose) * 100
      : undefined;
  const priceTone =
    priceChange === undefined
      ? "text-white"
      : priceChange > 0
      ? "text-[var(--main-red)]"
      : priceChange < 0
      ? "text-[var(--main-blue)]"
      : "text-white";
  // 한국 주식 가격 제한 (±30%)
  const upperLimitPrice = referenceClose
    ? Math.floor((referenceClose * 1.3) / getTickSize(referenceClose * 1.3)) * getTickSize(referenceClose * 1.3)
    : undefined;
  const lowerLimitPrice = referenceClose
    ? Math.ceil((referenceClose * 0.7) / getTickSize(referenceClose * 0.7)) * getTickSize(referenceClose * 0.7)
    : undefined;

  // 주문 가능 수량: 매수=현금기준, 매도=보유수량기준
  const orderPrice = Number(price || 0);
  const availableQty = transactionType === "sell"
    ? holdingQty
    : Math.floor(availableAmount / Math.max(orderPrice, 1));

  const qty = Number(quantity || 0);
  const orderAmount = orderPrice * qty;
  // 수수료 0.015% (키움증권 기준), 매도 시 증권거래세 0.20% (코스피), 농어촌특별세 생략
  const commission = Math.floor(orderAmount * 0.00015);
  const securityTax = transactionType === "sell" ? Math.floor(orderAmount * 0.002) : 0;
  const settlementAmount =
    transactionType === "buy" ? orderAmount + commission : orderAmount - commission - securityTax;

  // 예상 손익 (매도 시)
  const estimatedPnl = transactionType === "sell" && avgBuyPrice > 0 && orderPrice > 0
    ? (orderPrice - avgBuyPrice) * qty - commission - securityTax
    : undefined;
  const estimatedPnlRate = estimatedPnl !== undefined && avgBuyPrice > 0
    ? ((orderPrice - avgBuyPrice) / avgBuyPrice) * 100
    : undefined;

  const displayStockName =
    pickStockName(symbol, selectedStockName, stockInfo?.name) ?? symbol;

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

      <div className="p-4 md:p-5 lg:p-6 space-y-5 w-full min-w-0 pb-24">
        <div className="flat-card p-5">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-2">
              <div>
                <h1 className="text-3xl font-black leading-none text-white">
                  {displayStockName}
                </h1>
                <p className="mt-2 text-sm font-bold uppercase tracking-[0.24em] text-gray-400">
                  {symbol}
                </p>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <span className={`font-outfit text-3xl font-black tabular-nums ${priceTone}`}>
                  {currentPrice ? `${formatPrice(currentPrice)}원` : "-"}
                </span>
                <div className={`pb-0.5 text-sm font-bold tabular-nums ${priceTone}`}>
                  {priceChange !== undefined && priceChangePercent !== undefined
                    ? `${priceChange > 0 ? "+" : ""}${formatPrice(priceChange)}원 (${priceChangePercent > 0 ? "+" : ""}${priceChangePercent.toFixed(2)}%)`
                    : "전일 대비 데이터 없음"}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[460px]">
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400">전일종가</div>
                <div className="mt-2 font-outfit text-lg font-black tabular-nums text-white">
                  {referenceClose ? `${formatPrice(referenceClose)}원` : "-"}
                </div>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400">시가총액</div>
                <div className="mt-2 font-outfit text-lg font-black tabular-nums text-white">
                  {stockInfo?.marketCap ? formatMarketCap(stockInfo.marketCap) : "-"}
                </div>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400">거래량</div>
                <div className="mt-2 font-outfit text-lg font-black tabular-nums text-white">
                  {stockInfo?.volume ? formatPrice(stockInfo.volume) : "-"}
                </div>
              </div>
              <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-[10px] font-bold uppercase tracking-widest text-gray-400">PER / PBR</div>
                <div className="mt-2 text-lg font-black tabular-nums text-white">
                  {stockInfo?.pe ? stockInfo.pe.toFixed(2) : "-"} / {stockInfo?.pbr ? stockInfo.pbr.toFixed(2) : "-"}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="flat-card p-2">
          <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide">
            {[
              ["analysis", "종목 분석"],
              ["chart", "차트 · 호가"],
              ["info", "종목정보"],
              ["news", "뉴스 · 공시"],
              ["trading", "거래현황"],
              ["community", "커뮤니티"],
            ].map(([tab, label]) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab as typeof activeTab)}
                className={`rounded-xl px-4 py-2 text-sm font-bold whitespace-nowrap transition-colors ${
                  activeTab === tab
                    ? "bg-white/[0.08] text-white"
                    : "text-gray-400 hover:bg-white/[0.04] hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === "chart" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-10 gap-6 items-stretch">
              <div className="lg:col-span-6">
                <div className="flat-card flex h-[620px] flex-col overflow-hidden p-0">
                  <div className="flex flex-col gap-3 border-b border-white/[0.05] px-5 py-4 md:flex-row md:items-center md:justify-end">
                    <div className="flex flex-wrap items-center gap-2">
                      {(["1Y", "3Y", "5Y"] as const).map((range) => (
                        <button
                          key={range}
                          onClick={() => setChartRange(range)}
                          className={`rounded-xl px-3 py-1.5 text-xs font-bold transition-colors ${
                            chartRange === range
                              ? "bg-white/[0.08] text-white"
                              : "bg-white/[0.03] text-gray-400 hover:text-white"
                          }`}
                        >
                          {range}
                        </button>
                      ))}
                      <div className="mx-1 hidden h-4 border-l border-white/[0.08] md:block" />
                      {(["day", "week", "month"] as const).map((period) => (
                        <button
                          key={period}
                          onClick={() => setChartPeriod(period)}
                          className={`rounded-xl px-3 py-1.5 text-xs font-bold transition-colors ${
                            chartPeriod === period
                              ? "bg-white/[0.08] text-white"
                              : "bg-white/[0.03] text-gray-400 hover:text-white"
                          }`}
                        >
                          {period === "day" ? "일봉" : period === "week" ? "주봉" : "월봉"}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="min-h-0 flex-1 overflow-hidden bg-black/20">
                    {isOhlcvLoading ? (
                      <div className="flex h-full items-center justify-center text-sm font-bold text-gray-500">
                        차트 데이터를 불러오는 중...
                      </div>
                    ) : (
                      <CandlestickChart data={candleData} />
                    )}
                  </div>
                </div>
              </div>

              <div className="lg:col-span-4">
                <div className="h-[620px]">
                  <OrderBook
                    symbol={symbol}
                    currentPrice={currentPrice}
                    marketStats={realMarketStats}
                    previousClose={referenceClose}
                    onPriceSelect={(selectedPrice) => {
                      setSelectedOrderPrice(selectedPrice);
                      setPriceType("limit");
                      setPrice(selectedPrice.toString());
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-10 gap-6 items-stretch">
              <div className="lg:col-span-6">
                <div className="flat-card h-[600px] overflow-hidden border-0">
                  <div className="flex items-center justify-between px-5 py-4">
                    <div className="text-lg font-semibold text-gray-900 dark:text-white">시세</div>
                  </div>
                  <div className="custom-scrollbar h-[calc(100%-73px)] overflow-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 z-10 bg-white/[0.06]">
                        <tr>
                          <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-widest text-gray-400 rounded-l-lg">일자</th>
                          <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-400">종가</th>
                          <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-400">등락률</th>
                          <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-400">거래량</th>
                          <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-400">시가</th>
                          <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-400">고가</th>
                          <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-widest text-gray-400 rounded-r-lg">저가</th>
                        </tr>
                      </thead>
                      <tbody>
                        {priceHistoryData.map((row, i) => {
                          const prevClose = priceHistoryData[i + 1]?.close;
                          const changeRate = prevClose ? ((row.close - prevClose) / prevClose) * 100 : 0;
                          const priceColor =
                            changeRate > 0
                              ? "text-[var(--main-red)]"
                              : changeRate < 0
                              ? "text-[var(--main-blue)]"
                              : "text-white";
                          return (
                            <tr key={row.time} className="hover:bg-white/[0.02]">
                              <td className="px-4 py-3 text-xs font-bold tabular-nums text-gray-400">{row.time.slice(2).replace(/-/g, ".")}</td>
                              <td className={`px-4 py-3 text-right font-bold tabular-nums ${priceColor}`}>{formatPrice(row.close)}</td>
                              <td className={`px-4 py-3 text-right font-bold tabular-nums ${priceColor}`}>
                                {prevClose ? `${changeRate > 0 ? "+" : ""}${changeRate.toFixed(2)}%` : "-"}
                              </td>
                              <td className="px-4 py-3 text-right font-bold tabular-nums text-gray-300">{formatPrice(row.volume)}</td>
                              <td className="px-4 py-3 text-right font-bold tabular-nums text-gray-300">{formatPrice(row.open)}</td>
                              <td className="px-4 py-3 text-right font-bold tabular-nums text-[var(--main-red)]">{formatPrice(row.high)}</td>
                              <td className="px-4 py-3 text-right font-bold tabular-nums text-[var(--main-blue)]">{formatPrice(row.low)}</td>
                            </tr>
                          );
                        })}
                        {!isOhlcvLoading && priceHistoryData.length === 0 && (
                          <tr>
                            <td colSpan={7} className="px-4 py-12 text-center text-sm font-bold text-gray-500">
                              시세 데이터를 불러오지 못했습니다.
                            </td>
                          </tr>
                        )}
                        {isOhlcvLoading && (
                          <tr>
                            <td colSpan={7} className="px-4 py-12 text-center text-sm font-bold text-gray-500">
                              시세 데이터를 불러오는 중...
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-4">
                <div className="flat-card flex flex-col overflow-hidden" style={{ height: "600px" }}>
                  {/* 매수/매도/미체결 탭 */}
                  <div className="grid grid-cols-3 border-b border-white/[0.06]">
                    {(["buy", "sell", "pending"] as const).map((type) => {
                      const label = type === "buy" ? "매수" : type === "sell" ? "매도" : `미체결${pendingOrders.length > 0 ? ` ${pendingOrders.length}` : ""}`;
                      const activeColor = type === "buy"
                        ? "border-b-2 border-[var(--main-red)] text-[var(--main-red)]"
                        : type === "sell"
                        ? "border-b-2 border-[var(--main-blue)] text-[var(--main-blue)]"
                        : "border-b-2 border-amber-400 text-amber-300";
                      return (
                        <button
                          key={type}
                          onClick={() => {
                            setTransactionType(type);
                            setOrderConfirmStep(false);
                            if (type === "pending") loadPendingOrders();
                          }}
                          className={`py-3 text-sm font-black transition-colors ${
                            transactionType === type ? activeColor : "text-gray-500 hover:text-gray-300"
                          }`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>

                  <div className="flex flex-1 flex-col overflow-y-auto px-4 py-3 space-y-3">
                    {/* 계좌 선택 */}
                    <div className="relative" ref={accountDropdownRef}>
                      <button
                        onClick={() => setIsAccountDropdownOpen(!isAccountDropdownOpen)}
                        className="flex w-full items-center justify-between rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2.5 text-left text-xs font-bold text-white transition-colors hover:bg-white/[0.05]"
                      >
                        <span className="truncate text-xs">
                          {selectedAccount
                            ? `${selectedAccount.name}  |  잔고 ${formatPrice(selectedAccount.currentBalance)}원`
                            : virtualAccounts.length === 0 ? "가상계좌 없음" : "계좌 선택"}
                        </span>
                        <CaretDown className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                      </button>
                      {isAccountDropdownOpen && (
                        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-y-auto rounded-xl border border-white/[0.08] bg-[rgb(20,20,20)] p-1.5 shadow-2xl">
                          {virtualAccounts.length === 0 ? (
                            <div className="px-3 py-2 text-xs text-gray-500">가상계좌가 없습니다</div>
                          ) : (
                            virtualAccounts.map((account) => (
                              <button
                                key={account.id}
                                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setSelectedAccountId(account.id); setIsAccountDropdownOpen(false); }}
                                className={`w-full rounded-lg px-3 py-2 text-left text-xs font-bold transition-colors ${selectedAccountId === account.id ? "bg-white/[0.08] text-white" : "text-gray-300 hover:bg-white/[0.04]"}`}
                              >
                                {account.name} ({formatPrice(account.currentBalance)}원)
                              </button>
                            ))
                          )}
                        </div>
                      )}
                    </div>

                    {transactionType === "pending" ? (
                      /* ── 미체결 패널 ── */
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-gray-400">미체결 주문</span>
                          <button onClick={loadPendingOrders} className="text-xs text-gray-500 hover:text-white">새로고침</button>
                        </div>
                        {pendingOrders.length === 0 ? (
                          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-8 text-center text-xs font-bold text-gray-500">
                            미체결 주문이 없습니다.
                          </div>
                        ) : (
                          pendingOrders.map((order) => (
                            <div key={order.id} className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                  <span className={`text-xs font-black ${order.type === "buy" ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                    {order.type === "buy" ? "매수" : "매도"}
                                  </span>
                                  <span className="truncate text-xs font-bold text-white">{order.name}</span>
                                </div>
                                <div className="mt-0.5 text-xs text-gray-400">{formatPrice(order.price)}원 × {order.quantity}주</div>
                                <div className="mt-0.5 text-[10px] text-gray-500">
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
                                  } else { alert(res.error ?? "취소 실패"); }
                                }}
                                className="ml-2 rounded-lg border border-white/[0.08] px-2.5 py-1.5 text-xs font-bold text-gray-400 hover:text-white"
                              >취소</button>
                            </div>
                          ))
                        )}
                      </div>
                    ) : orderConfirmStep ? (
                      /* ── 주문 확인 단계 ── */
                      <div className="flex flex-1 flex-col space-y-3">
                        <div className={`rounded-xl p-3 text-center text-xs font-black ${transactionType === "buy" ? "bg-[var(--main-red)]/10 text-[var(--main-red)]" : "bg-[var(--main-blue)]/10 text-[var(--main-blue)]"}`}>
                          {transactionType === "buy" ? "매수" : "매도"} 주문을 확인합니다
                        </div>
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-2">
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-400">종목</span>
                            <span className="font-bold text-white">{displayStockName} ({symbol})</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-400">주문유형</span>
                            <span className="font-bold text-white">
                              {priceType === "market" ? "시장가" : priceType === "best_limit" ? "최유리지정가" : priceType === "conditional" ? "조건부지정가" : "지정가"}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-400">주문가</span>
                            <span className="font-bold text-white">
                              {priceType === "market" ? "시장가" : `${formatPrice(Number(price))}원`}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-400">주문수량</span>
                            <span className="font-bold text-white">{formatPrice(Number(quantity))}주</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-400">주문금액</span>
                            <span className="font-bold text-white">{formatPrice(orderAmount)}원</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-400">수수료 (0.015%)</span>
                            <span className="text-gray-300">{formatPrice(commission)}원</span>
                          </div>
                          {transactionType === "sell" && (
                            <div className="flex justify-between text-xs">
                              <span className="text-gray-400">증권거래세 (0.20%)</span>
                              <span className="text-gray-300">{formatPrice(securityTax)}원</span>
                            </div>
                          )}
                          <div className="border-t border-white/[0.06] pt-2 flex justify-between text-xs font-bold">
                            <span className="text-gray-300">{transactionType === "buy" ? "총 결제금액" : "예상 수령금액"}</span>
                            <span className="text-white">{formatPrice(settlementAmount)}원</span>
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-2 mt-auto">
                          <button
                            onClick={() => setOrderConfirmStep(false)}
                            className="rounded-xl border border-white/[0.08] py-3 text-sm font-bold text-gray-300 hover:text-white"
                          >취소</button>
                          <button
                            onClick={handleOrder}
                            className={`rounded-xl py-3 text-sm font-black text-white ${transactionType === "buy" ? "bg-[var(--main-red)] hover:bg-red-500" : "bg-[var(--main-blue)] hover:bg-blue-500"}`}
                          >주문 확정</button>
                        </div>
                      </div>
                    ) : (
                      /* ── 주문 입력 ── */
                      <div className="flex flex-1 flex-col space-y-3">
                        {/* 매도 시 보유정보 */}
                        {transactionType === "sell" && (
                          <div className="grid grid-cols-2 gap-2">
                            <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                              <div className="text-[10px] text-gray-500">보유수량</div>
                              <div className="text-sm font-black tabular-nums text-white">{formatPrice(holdingQty)}주</div>
                            </div>
                            <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                              <div className="text-[10px] text-gray-500">평균단가</div>
                              <div className="text-sm font-black tabular-nums text-white">{avgBuyPrice > 0 ? `${formatPrice(avgBuyPrice)}원` : "-"}</div>
                            </div>
                          </div>
                        )}

                        {/* 주문유형 */}
                        <div>
                          <div className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-500">주문유형</div>
                          <div className="grid grid-cols-2 gap-1.5">
                            {([
                              ["limit", "지정가"],
                              ["market", "시장가"],
                              ["best_limit", "최유리지정가"],
                              ["conditional", "조건부지정가"],
                            ] as const).map(([type, label]) => (
                              <button
                                key={type}
                                onClick={() => {
                                  setPriceType(type);
                                  if (type === "market" && currentPrice) setPrice(currentPrice.toString());
                                }}
                                className={`rounded-lg py-1.5 text-xs font-bold transition-colors ${
                                  priceType === type
                                    ? transactionType === "buy"
                                      ? "bg-[var(--main-red)]/15 text-[var(--main-red)]"
                                      : "bg-[var(--main-blue)]/15 text-[var(--main-blue)]"
                                    : "border border-white/[0.06] bg-white/[0.02] text-gray-400 hover:text-gray-200"
                                }`}
                              >{label}</button>
                            ))}
                          </div>
                        </div>

                        {/* 가격 입력 */}
                        <div>
                          <div className="mb-1.5 flex items-center justify-between">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                              {transactionType === "buy" ? "매수가격" : "매도가격"}
                            </span>
                            {referenceClose && (
                              <div className="flex items-center gap-1 text-[10px]">
                                <span className="text-[var(--main-red)] font-bold">상:{upperLimitPrice ? formatPrice(upperLimitPrice) : "-"}</span>
                                <span className="text-gray-600">|</span>
                                <span className="text-[var(--main-blue)] font-bold">하:{lowerLimitPrice ? formatPrice(lowerLimitPrice) : "-"}</span>
                              </div>
                            )}
                          </div>
                          {/* 빠른 가격 버튼 */}
                          <div className="mb-1.5 flex gap-1">
                            {upperLimitPrice && (
                              <button
                                onClick={() => { setPriceType("limit"); setPrice(upperLimitPrice.toString()); }}
                                className="flex-1 rounded-md border border-[var(--main-red)]/30 bg-[var(--main-red)]/5 py-1 text-[10px] font-bold text-[var(--main-red)] hover:bg-[var(--main-red)]/10"
                              >상한가</button>
                            )}
                            {currentPrice && (
                              <button
                                onClick={() => { setPriceType("limit"); setPrice(currentPrice.toString()); }}
                                className="flex-1 rounded-md border border-white/[0.08] bg-white/[0.03] py-1 text-[10px] font-bold text-gray-300 hover:text-white"
                              >현재가</button>
                            )}
                            {lowerLimitPrice && (
                              <button
                                onClick={() => { setPriceType("limit"); setPrice(lowerLimitPrice.toString()); }}
                                className="flex-1 rounded-md border border-[var(--main-blue)]/30 bg-[var(--main-blue)]/5 py-1 text-[10px] font-bold text-[var(--main-blue)] hover:bg-[var(--main-blue)]/10"
                              >하한가</button>
                            )}
                          </div>
                          <div className="flex gap-1.5">
                            <input
                              type="text"
                              value={priceType === "market" ? "" : (price ? Number(price).toLocaleString("ko-KR") : "")}
                              onChange={(e) => { const raw = e.target.value.replace(/,/g, ""); if (raw === "" || /^\d+$/.test(raw)) setPrice(raw); }}
                              disabled={priceType === "market"}
                              className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2.5 text-sm font-bold text-right tabular-nums text-white placeholder:text-gray-600 disabled:cursor-not-allowed disabled:opacity-40"
                              placeholder={priceType === "market" ? "시장가" : "0"}
                            />
                            <button
                              disabled={priceType === "market"}
                              onClick={() => setPrice((prev) => { const cur = Number(prev || 0); return Math.max(0, cur - getTickSize(cur)).toString(); })}
                              className="w-9 rounded-lg border border-white/[0.08] bg-white/[0.03] text-base font-black text-gray-300 hover:text-white disabled:opacity-30"
                            >−</button>
                            <button
                              disabled={priceType === "market"}
                              onClick={() => setPrice((prev) => { const cur = Number(prev || 0); return (cur + getTickSize(cur)).toString(); })}
                              className="w-9 rounded-lg border border-white/[0.08] bg-white/[0.03] text-base font-black text-gray-300 hover:text-white disabled:opacity-30"
                            >+</button>
                          </div>
                          {priceType === "limit" && price && referenceClose && Number(price) > 0 && (
                            <div className={`mt-1 text-right text-[10px] font-bold ${Number(price) > referenceClose ? "text-[var(--main-red)]" : Number(price) < referenceClose ? "text-[var(--main-blue)]" : "text-gray-500"}`}>
                              전일비 {Number(price) > referenceClose ? "+" : ""}{(((Number(price) - referenceClose) / referenceClose) * 100).toFixed(2)}%
                            </div>
                          )}
                        </div>

                        {/* 수량 입력 */}
                        <div>
                          <div className="mb-1.5 flex items-center justify-between">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">수량</span>
                            <span className="text-[10px] text-gray-500">
                              {transactionType === "sell" ? `보유 ${formatPrice(holdingQty)}주` : `가능 ${formatPrice(availableQty)}주`}
                            </span>
                          </div>
                          <div className="flex gap-1.5">
                            <input
                              type="text"
                              value={quantity}
                              onChange={(e) => { const v = e.target.value.replace(/[^0-9]/g, ""); setQuantity(v); }}
                              className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2.5 text-sm font-bold text-right tabular-nums text-white placeholder:text-gray-600"
                              placeholder="0"
                            />
                            <button
                              onClick={() => setQuantity((prev) => Math.max(0, Number(prev || 0) - 1).toString())}
                              className="w-9 rounded-lg border border-white/[0.08] bg-white/[0.03] text-base font-black text-gray-300 hover:text-white"
                            >−</button>
                            <button
                              onClick={() => setQuantity((prev) => (Number(prev || 0) + 1).toString())}
                              className="w-9 rounded-lg border border-white/[0.08] bg-white/[0.03] text-base font-black text-gray-300 hover:text-white"
                            >+</button>
                          </div>
                          <div className="mt-1.5 grid grid-cols-4 gap-1">
                            {([0.1, 0.25, 0.5, 1] as const).map((ratio, i) => (
                              <button
                                key={ratio}
                                onClick={() => setQuantity(Math.floor(availableQty * ratio).toString())}
                                className="rounded-md border border-white/[0.06] bg-white/[0.02] py-1.5 text-[10px] font-bold text-gray-400 hover:text-white"
                              >{i === 3 ? "전체" : `${ratio * 100}%`}</button>
                            ))}
                          </div>
                        </div>

                        {/* 주문 요약 */}
                        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2.5 space-y-1.5">
                          {transactionType === "sell" && avgBuyPrice > 0 && Number(quantity) > 0 && orderPrice > 0 && (
                            <>
                              <div className="flex justify-between text-xs">
                                <span className="text-gray-500">예상손익</span>
                                <span className={`font-bold tabular-nums ${estimatedPnl !== undefined && estimatedPnl > 0 ? "text-[var(--main-red)]" : estimatedPnl !== undefined && estimatedPnl < 0 ? "text-[var(--main-blue)]" : "text-white"}`}>
                                  {estimatedPnl !== undefined ? `${estimatedPnl > 0 ? "+" : ""}${formatPrice(estimatedPnl)}원` : "-"}
                                  {estimatedPnlRate !== undefined ? ` (${estimatedPnlRate > 0 ? "+" : ""}${estimatedPnlRate.toFixed(2)}%)` : ""}
                                </span>
                              </div>
                              <div className="border-t border-white/[0.04]" />
                            </>
                          )}
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">{transactionType === "buy" ? "구매가능" : "보유수량"}</span>
                            <span className="font-bold tabular-nums text-gray-300">
                              {transactionType === "buy" ? `${formatPrice(availableAmount)}원` : `${formatPrice(holdingQty)}주`}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">주문금액</span>
                            <span className="font-bold tabular-nums text-white">{formatPrice(orderAmount)}원</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-gray-500">수수료 (0.015%)</span>
                            <span className="tabular-nums text-gray-400">{formatPrice(commission)}원</span>
                          </div>
                          {transactionType === "sell" && (
                            <div className="flex justify-between text-xs">
                              <span className="text-gray-500">증권거래세 (0.20%)</span>
                              <span className="tabular-nums text-gray-400">{formatPrice(securityTax)}원</span>
                            </div>
                          )}
                          <div className="border-t border-white/[0.06] pt-1.5 flex justify-between text-sm font-black">
                            <span className="text-gray-300">{transactionType === "buy" ? "총 결제금액" : "예상 수령금액"}</span>
                            <span className="tabular-nums text-white">{formatPrice(settlementAmount)}원</span>
                          </div>
                        </div>

                        {/* 주문 버튼 */}
                        <button
                          onClick={handleOrderConfirm}
                          disabled={!selectedAccountId || !quantity || (priceType !== "market" && !price)}
                          className={`w-full rounded-xl py-3.5 text-sm font-black transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                            transactionType === "buy"
                              ? "bg-[var(--main-red)] text-white hover:bg-red-500"
                              : "bg-[var(--main-blue)] text-white hover:bg-blue-400"
                          }`}
                        >
                          {transactionType === "buy"
                            ? priceType === "market" ? "시장가 매수" : priceType === "best_limit" ? "최유리 매수" : priceType === "conditional" ? "조건부 매수" : "지정가 매수"
                            : priceType === "market" ? "시장가 매도" : priceType === "best_limit" ? "최유리 매도" : priceType === "conditional" ? "조건부 매도" : "지정가 매도"}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "info" && (
          <div className="flat-card p-5">
            <div className="mb-5 border-b border-white/[0.05] pb-4">
              <p className="mt-1 text-sm text-gray-500">기본 정보와 재무 지표를 한눈에 확인합니다.</p>
            </div>
            {stockInfo ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 className="text-sm font-black uppercase tracking-widest text-gray-400 mb-3">
                    기본 정보
                  </h3>
                  <div className="space-y-2 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">종목명</span>
                      <span className="font-bold text-white">
                        {displayStockName}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">종목코드</span>
                      <span className="font-bold text-white">{symbol}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">섹터</span>
                      <span className="font-bold text-white">
                        {stockInfo.sector || "-"}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">업종</span>
                      <span className="font-bold text-white">
                        {stockInfo.industry || "-"}
                      </span>
                    </div>
                  </div>
                </div>
                <div>
                  <h3 className="text-sm font-black uppercase tracking-widest text-gray-400 mb-3">
                    재무 정보
                  </h3>
                  <div className="space-y-2 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">시가총액</span>
                      <span className="font-bold text-white">
                        {stockInfo.marketCap
                          ? formatMarketCap(stockInfo.marketCap)
                          : "-"}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">PER</span>
                      <span className="font-bold text-white">
                        {stockInfo.pe ? stockInfo.pe.toFixed(2) : "-"}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">PBR</span>
                      <span className="font-bold text-white">
                        {stockInfo.pbr ? stockInfo.pbr.toFixed(2) : "-"}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-sm text-gray-400">현재가</span>
                      <span className="font-bold text-white">
                        {currentPrice ? formatPrice(currentPrice) : "-"}원
                      </span>
                    </div>
                  </div>
                </div>
                {stockInfo.description && (
                  <div className="md:col-span-2">
                    <h3 className="text-sm font-black uppercase tracking-widest text-gray-400 mb-3">
                      기업 개요
                    </h3>
                    <p className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4 text-sm leading-relaxed text-gray-300">
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
          <div className="flat-card p-5">
            <div className="mb-5 border-b border-white/[0.05] pb-4">
              <p className="mt-1 text-sm text-gray-500">뉴스와 공시 피드를 같은 톤으로 정리합니다.</p>
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-bold text-white">주요 공시</h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {displayStockName} 관련 주요 공시사항이 없습니다.
                </p>
              </div>
              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-bold text-white">최신 뉴스</h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {displayStockName} 관련 최신 뉴스가 없습니다.
                </p>
              </div>
            </div>
          </div>
        )}

        {activeTab === "trading" && (
          <div className="flat-card p-5">
            <div className="mb-5 border-b border-white/[0.05] pb-4">
              <p className="mt-1 text-sm text-gray-500">당일 거래 지표와 가격 범위를 확인합니다.</p>
            </div>
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                  <div className="text-xs text-gray-400 mb-1">일일 거래량</div>
                  <div className="text-lg font-black tabular-nums text-white">
                    {stockInfo?.volume ? formatPrice(stockInfo.volume) : "-"}
                  </div>
                </div>
                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                  <div className="text-xs text-gray-400 mb-1">거래대금</div>
                  <div className="text-lg font-black tabular-nums text-white">
                    {currentPrice && stockInfo?.volume
                      ? formatPrice(currentPrice * stockInfo.volume)
                      : "-"}
                    원
                  </div>
                </div>
                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                  <div className="text-xs text-gray-400 mb-1">고가</div>
                  <div className="text-lg font-black tabular-nums text-[var(--main-red)]">
                    {stockInfo?.high ? formatPrice(stockInfo.high) : "-"}원
                  </div>
                </div>
                <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                  <div className="text-xs text-gray-400 mb-1">저가</div>
                  <div className="text-lg font-black tabular-nums text-[var(--main-blue)]">
                    {stockInfo?.low ? formatPrice(stockInfo.low) : "-"}원
                  </div>
                </div>
              </div>
              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <h3 className="mb-3 text-sm font-bold uppercase tracking-widest text-gray-400">
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
          <div className="flat-card p-5">
            <div className="mb-5 border-b border-white/[0.05] pb-4">
              <p className="mt-1 text-sm text-gray-500">커뮤니티 영역도 동일한 카드 톤을 유지합니다.</p>
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-bold text-white">
                    인기 게시글
                  </h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {displayStockName} 관련 커뮤니티 게시글이 없습니다.
                </p>
              </div>
              <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-bold text-white">토론</h3>
                  <span className="text-xs text-gray-500">2024.01.15</span>
                </div>
                <p className="text-sm text-gray-300">
                  {displayStockName} 관련 토론이 없습니다.
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
                    {displayStockName}
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
                      ? formatMarketCap(stockInfo.marketCap)
                      : "-"}
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
                              {displayStockName} 관련 주요 뉴스 {i}
                            </h4>
                            <span className="text-xs text-gray-500">
                              2024.01.{15 + i}
                            </span>
                          </div>
                          <p className="text-sm text-gray-300 mb-2">
                            {displayStockName} 관련 뉴스 요약 내용...
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
