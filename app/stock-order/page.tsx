"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "next/navigation";
import {
  CaretDown,
  CheckCircle,
  Warning,
  X,
} from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import OrderBook, { MarketStats } from "@/components/order/OrderBook";
import { formatMarketCap } from "@/lib/format-market-cap";
import CandlestickChart, { OHLCV } from "@/components/stock/CandlestickChart";
import NewsImpactPanel from "@/components/stock/NewsImpactPanel";
import InvestorTradingPanel from "@/components/order/InvestorTradingPanel";
import {
  mergeStockInfo,
  pickPositiveNumber,
  pickStockName,
  sanitizeMarketCap,
} from "@/app/stock-order/stock-info";
import { useStockPrices } from "@/lib/hooks/useStockPrices";
import type { StockPriceSnapshot as BatchQuoteItem } from "@/lib/stock-prices";
import {
  applyRealtimeToLatestCandle,
  resolveMarketPreviousClose,
} from "@/app/stock-order/market-candles";
import { useOrderAccount } from "@/contexts/OrderAccountContext";
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

const toFiniteNumber = (value: unknown): number | undefined => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : undefined;
  }
  if (typeof value === "string") {
    const parsed = Number(value.replace(/,/g, "").trim());
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const formatCompactDate = (value: unknown) => {
  if (!value) return "—";
  const digits = String(value).replace(/\D/g, "");
  if (digits.length === 8) {
    return `${digits.slice(0, 4)}.${digits.slice(4, 6)}.${digits.slice(6, 8)}`;
  }
  return String(value);
};

const formatCount = (value: unknown, unit: string) => {
  const number = toFiniteNumber(value);
  return number !== undefined ? `${formatPrice(number)}${unit}` : "—";
};

const formatWonMetric = (value: unknown) => {
  const number = toFiniteNumber(value);
  if (number === undefined) return "—";
  if (number === 0) return "0원";
  const sign = number < 0 ? "-" : "";
  return `${sign}${formatMarketCap(Math.abs(number))}`;
};

const translateBusinessPhrase = (value: string) => {
  return value
    .replace(/\bthe consumer electronics, information technology and mobile communications, and device solutions businesses\b/gi, "전자제품, 정보기술 및 모바일 커뮤니케이션, 디바이스 솔루션 사업")
    .replace(/\binformation technology and mobile communications\b/gi, "정보기술 및 모바일 커뮤니케이션")
    .replace(/\bdevice solutions businesses\b/gi, "디바이스 솔루션 사업")
    .replace(/\bconsumer electronics\b/gi, "전자제품")
    .replace(/\bsemiconductor businesses\b/gi, "반도체 사업")
    .replace(/\bsemiconductors\b/gi, "반도체")
    .replace(/\bdisplays\b/gi, "디스플레이")
    .replace(/\bmobile devices\b/gi, "모바일 기기")
    .replace(/\bnetwork systems\b/gi, "네트워크 시스템")
    .replace(/\baudio\b/gi, "오디오")
    .replace(/\bconnected-car businesses\b/gi, "커넥티드카 사업")
    .replace(/\bbusinesses\b/gi, "사업")
    .replace(/\bthe\b/gi, "")
    .replace(/\band\b/gi, "및")
    .replace(/\s+/g, " ")
    .replace(/,\s*/g, ", ");
};

const STOCK_DETAIL_RETRY_DELAYS_MS = [0, 400, 1200];

const getTickSize = (p: number): number => {
  if (p < 1000) return 1;
  if (p < 5000) return 5;
  if (p < 10000) return 10;
  if (p < 50000) return 50;
  if (p < 100000) return 100;
  if (p < 500000) return 500;
  return 1000;
};

const SHOW_ORDER_BOOK = false;
const SHOW_TRADE_PANEL = false;
const SHOW_COMMUNITY_TAB = false;
const SHOW_NEWS_TAB = process.env.NEXT_PUBLIC_NEWS_TAB_ENABLED === "true";

export default function OrderPage() {
  const searchParams = useSearchParams();
  const symbol = searchParams.get("symbol") || "";
  const name = searchParams.get("name") || "";
  const { selectedAccountId, setSelectedAccountId } = useOrderAccount();

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
  const [priceType, setPriceType] = useState<"limit" | "market">("limit");
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
    "chart" | "info" | "news" | "community"
  >("chart");
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
            const nextPrice = pickPositiveNumber(data.currentPrice);
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
    const year252 = candles.slice(-252);
    return {
      open: last.open,
      high: last.high,
      low: last.low,
      volume: last.volume,
      // 오늘 봉이 아직 OHLCV에 없는 라이브 상황에서 '이틀 전' 종가를 전일 종가로
      // 쓰지 않도록 한다(직전 거래일 종가/ KIS previousClose 사용).
      previousClose:
        resolveMarketPreviousClose(candles, liveQuote) ?? last.close,
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
  const companyBasic = stockInfo?.companyBasic ?? {};
  const summaryFinancials = stockInfo?.summaryFinancials ?? {};

  const PRICE_HISTORY_COLS = "grid-cols-[96px_90px_80px_110px_80px_80px_80px]";

  if (!symbol) {
    return (
      <DashboardLayout userName="사용자">
        <div className="w-full min-w-0 border border-white/[0.08]">
          <div className="py-16 text-center">
            <p className="text-sm font-bold text-gray-500">종목을 선택해주세요.</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout userName="사용자">
      {/* 주문 결과 모달 */}
      {orderModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setOrderModal(null)}
        >
          <div
            className="bg-[#161616] border border-white/[0.08] rounded-2xl w-full max-w-sm mx-4 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className={`flex flex-col items-center pt-8 pb-4 px-6 ${
              orderModal.type === "success" ? "bg-gradient-to-b from-[var(--main-red)]/10 to-transparent" :
              orderModal.type === "pending" ? "bg-gradient-to-b from-amber-500/10 to-transparent" :
              "bg-gradient-to-b from-white/[0.04] to-transparent"
            }`}>
              {orderModal.type === "success" && (
                <>
                  <CheckCircle size={56} className="text-[var(--main-red)] mb-3" weight="fill" />
                  <p className="text-lg font-black text-white">{orderModal.action} 체결 완료</p>
                  <p className="text-sm font-bold text-gray-400 mt-1">{orderModal.stockName}</p>
                </>
              )}
              {orderModal.type === "pending" && (
                <>
                  <Warning size={56} className="text-amber-400 mb-3" weight="fill" />
                  <p className="text-lg font-black text-white">지정가 대기 중</p>
                  <p className="text-sm font-bold text-gray-400 mt-1">{orderModal.stockName}</p>
                </>
              )}
              {orderModal.type === "error" && (
                <>
                  <X size={56} className="text-gray-500 mb-3" weight="bold" />
                  <p className="text-lg font-black text-white">주문 실패</p>
                  <p className="text-sm font-bold text-gray-400 mt-1">{orderModal.stockName}</p>
                </>
              )}
            </div>
            <div className="px-6 pb-6 space-y-3">
              {orderModal.type === "success" && (
                <div className="bg-white/[0.03] rounded-xl p-4 space-y-2 mt-2 border border-white/[0.05]">
                  <div className="flex justify-between text-xs font-bold">
                    <span className="text-gray-500">수량</span>
                    <span className="text-white tabular-nums">{formatPrice(orderModal.qty ?? 0)}주</span>
                  </div>
                  <div className="flex justify-between text-xs font-bold">
                    <span className="text-gray-500">체결가</span>
                    <span className="text-white tabular-nums">{formatPrice(orderModal.price ?? 0)}원</span>
                  </div>
                  <div className="flex justify-between text-xs font-bold">
                    <span className="text-gray-500">수수료</span>
                    <span className="text-gray-400 tabular-nums">{formatPrice(orderModal.fee ?? 0)}원</span>
                  </div>
                  <div className="border-t border-white/[0.06] pt-2 flex justify-between text-sm font-black">
                    <span className="text-gray-300">총액</span>
                    <span className="text-white tabular-nums font-outfit">{formatPrice(orderModal.total ?? 0)}원</span>
                  </div>
                </div>
              )}
              {orderModal.type === "pending" && (
                <div className="bg-white/[0.03] rounded-xl p-4 space-y-2 mt-2 border border-white/[0.05]">
                  <div className="flex justify-between text-xs font-bold">
                    <span className="text-gray-500">수량</span>
                    <span className="text-white tabular-nums">{formatPrice(orderModal.qty ?? 0)}주</span>
                  </div>
                  <div className="flex justify-between text-xs font-bold">
                    <span className="text-gray-500">지정가</span>
                    <span className="text-white tabular-nums">{formatPrice(orderModal.price ?? 0)}원</span>
                  </div>
                  <p className="text-xs font-bold text-amber-400/80 pt-1">가격 도달 시 자동으로 체결됩니다.</p>
                </div>
              )}
              {orderModal.type === "error" && (
                <div className="bg-white/[0.03] rounded-xl p-4 mt-2 border border-white/[0.05]">
                  <p className="text-sm font-bold text-gray-300 text-center">{orderModal.message}</p>
                </div>
              )}
              <button
                onClick={() => setOrderModal(null)}
                className="w-full py-3 rounded-xl text-sm font-bold text-white bg-white/[0.08] hover:bg-white/[0.12] transition-colors"
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">

        {/* ── 종목 헤더 ── */}
        <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
          {/* 좌: 종목명 + 현재가 */}
          <div className="lg:col-span-4 px-5 py-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-black text-white font-outfit leading-tight">
                  {displayStockName}
                </h1>
                <p className="text-xs font-bold uppercase tracking-widest text-gray-500 mt-1">{symbol}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <span className={`font-outfit text-3xl font-black tabular-nums leading-none ${priceTone}`}>
                {currentPrice ? `${formatPrice(currentPrice)}원` : "—"}
              </span>
              <div className={`pb-0.5 text-sm font-bold tabular-nums ${priceTone}`}>
                {priceChange !== undefined && priceChangePercent !== undefined
                  ? `${priceChange > 0 ? "+" : ""}${formatPrice(priceChange)}원 (${priceChangePercent > 0 ? "+" : ""}${priceChangePercent.toFixed(2)}%)`
                  : <span className="text-gray-600 text-xs">전일 대비 집계 중</span>}
              </div>
            </div>
          </div>
          {/* 우: 3개 KPI 타일 */}
          <div className="lg:col-span-6 grid grid-cols-2 sm:grid-cols-3 border-t border-l border-white/[0.08]">
            <div className="border-r border-b border-white/[0.08] px-4 py-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">전일 종가</p>
              <p className="mt-2 text-2xl font-black tabular-nums font-outfit text-white leading-none">
                {referenceClose ? `${formatPrice(referenceClose)}` : "—"}
              </p>
              <p className="mt-0.5 text-[10px] font-bold text-gray-600">원</p>
            </div>
            <div className="border-r border-b border-white/[0.08] px-4 py-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">시가총액</p>
              <p className="mt-2 text-2xl font-black tabular-nums font-outfit text-white leading-none">
                {stockInfo?.marketCap ? formatMarketCap(stockInfo.marketCap) : "—"}
              </p>
            </div>
            <div className="border-r border-b border-white/[0.08] px-4 py-4">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">거래량</p>
              <p className="mt-2 text-2xl font-black tabular-nums font-outfit text-white leading-none">
                {stockInfo?.volume ? formatPrice(stockInfo.volume) : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* ── 탭 네비게이션 ── */}
        <div className="px-4 py-2 overflow-x-auto scrollbar-hide">
          <div className="flex items-center gap-1">
            {([
              ["chart", "차트"],
              ["info", "종목정보"],
              ["news", "뉴스"],
              ["community", "커뮤니티"],
            ] as const)
              .filter(
                ([tab]) =>
                  (SHOW_NEWS_TAB || tab !== "news") &&
                  (SHOW_COMMUNITY_TAB || tab !== "community")
              )
              .map(([tab, label]) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`rounded-xl px-3 py-1.5 text-xs font-bold whitespace-nowrap transition-colors duration-150 ${
                  activeTab === tab
                    ? "bg-white/[0.08] text-white"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* ── 차트 탭 ── */}
        {(
          <div className={`border-t border-white/[0.08]${activeTab !== "chart" ? " hidden" : ""}`}>
            <div className="divide-y divide-white/[0.08]">
              {/* Row 1: 캔들차트 + 호가창 */}
              <div
                className="grid grid-cols-1 divide-y divide-white/[0.08] lg:grid-cols-10 lg:divide-x lg:divide-y-0"
              >
                {/* 캔들차트 */}
                <div
                  className={`flex flex-col overflow-hidden ${SHOW_ORDER_BOOK ? "lg:col-span-6" : "lg:col-span-10"}`}
                  style={{ height: 560 }}
                >
                  <div className="flex items-center justify-end gap-1 px-4 py-2 border-b border-white/[0.05] flex-wrap">
                    {(["1Y", "3Y", "5Y"] as const).map((range) => (
                      <button key={range} onClick={() => setChartRange(range)}
                        className={`rounded-xl px-3 py-1 text-xs font-bold transition-colors ${chartRange === range ? "bg-white/[0.08] text-white" : "text-gray-500 hover:text-gray-300"}`}>
                        {range}
                      </button>
                    ))}
                    <div className="w-px h-3 bg-white/[0.08]" />
                    {(["day", "week", "month"] as const).map((period) => (
                      <button key={period} onClick={() => setChartPeriod(period)}
                        className={`rounded-xl px-3 py-1 text-xs font-bold transition-colors ${chartPeriod === period ? "bg-white/[0.08] text-white" : "text-gray-500 hover:text-gray-300"}`}>
                        {period === "day" ? "일봉" : period === "week" ? "주봉" : "월봉"}
                      </button>
                    ))}
                  </div>
                  <div className="flex-1 min-h-0">
                    {isOhlcvLoading ? (
                      <div className="flex h-full items-center justify-center text-sm font-bold text-gray-500">차트 데이터를 불러오는 중...</div>
                    ) : (
                      <CandlestickChart data={candleData} />
                    )}
                  </div>
                </div>
                {/* 호가창 */}
                {SHOW_ORDER_BOOK && (
                  <div className="overflow-hidden lg:col-span-4" style={{ height: 560 }}>
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
                )}
              </div>

              {/* Row 2: 시세 테이블 + 투자자별 매매동향 + 주문 패널 */}
              <div className={`grid grid-cols-1 divide-y divide-white/[0.08] lg:divide-y-0 lg:divide-x ${SHOW_TRADE_PANEL ? "lg:grid-cols-3" : "lg:grid-cols-2"}`}>
                {/* 시세 테이블 */}
                <div className="flex flex-col overflow-hidden" style={{ height: 560 }}>
                <div className="px-4 py-3 border-b border-white/[0.05] shrink-0">
                  <h2 className="text-sm font-black uppercase tracking-widest text-white font-outfit">시세</h2>
                </div>
                <div className="flex flex-1 min-h-0 flex-col">
                  {/* 헤더 */}
                  <div className={`grid ${PRICE_HISTORY_COLS} gap-2 px-4 py-2 border-b border-white/[0.05] shrink-0`}>
                    {["일자", "종가", "등락률", "거래량", "시가", "고가", "저가"].map((h, i) => (
                      <span key={h} className={`text-xs font-bold uppercase tracking-widest text-gray-600 ${i > 0 ? "text-right" : ""}`}>{h}</span>
                    ))}
                  </div>
                  <div className="flex-1 min-h-0 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                    {isOhlcvLoading ? (
                      <div className="py-12 text-center">
                        <p className="text-sm font-bold text-gray-500">시세 데이터를 불러오는 중...</p>
                      </div>
                    ) : priceHistoryData.length === 0 ? (
                      <div className="py-12 text-center">
                        <p className="text-sm font-bold text-gray-500">시세 데이터가 없습니다.</p>
                      </div>
                    ) : (
                      <div className="divide-y divide-white/[0.04]">
                        {priceHistoryData.map((row, i) => {
                          const prevClose = priceHistoryData[i + 1]?.close;
                          const changeRate = prevClose ? ((row.close - prevClose) / prevClose) * 100 : 0;
                          const tone = changeRate > 0 ? "text-[var(--main-red)]" : changeRate < 0 ? "text-[var(--main-blue)]" : "text-white";
                          return (
                            <div key={row.time} className={`grid ${PRICE_HISTORY_COLS} gap-2 items-center px-4 py-3 hover:bg-white/[0.02] transition-colors duration-150`}>
                              <span className="text-xs font-bold tabular-nums text-gray-400">{row.time.slice(2).replace(/-/g, ".")}</span>
                              <span className={`text-xs font-black tabular-nums font-outfit text-right ${tone}`}>{formatPrice(row.close)}</span>
                              <span className={`text-xs font-bold tabular-nums text-right ${tone}`}>{prevClose ? `${changeRate > 0 ? "+" : ""}${changeRate.toFixed(2)}%` : "—"}</span>
                              <span className="text-xs font-bold tabular-nums text-right text-gray-400">{formatPrice(row.volume)}</span>
                              <span className="text-xs font-bold tabular-nums text-right text-gray-400">{formatPrice(row.open)}</span>
                              <span className="text-xs font-bold tabular-nums text-right text-[var(--main-red)]">{formatPrice(row.high)}</span>
                              <span className="text-xs font-bold tabular-nums text-right text-[var(--main-blue)]">{formatPrice(row.low)}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
                </div>

                {/* 투자자별 매매동향 패널 */}
                <div className="flex flex-col overflow-hidden" style={{ height: 560 }}>
                  <InvestorTradingPanel symbol={symbol} />
                </div>

                {/* 주문 패널 */}
                {SHOW_TRADE_PANEL && (
                  <div className="flex flex-col overflow-hidden" style={{ height: 560 }}>
                    {/* 매수/매도/미체결 탭 */}
                    <div className="grid grid-cols-3 border-b border-white/[0.08]">
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
                        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-y-auto rounded-xl border border-white/[0.08] bg-[#161616] p-1.5 shadow-2xl">
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
                              {priceType === "market" ? "시장가" : "지정가"}
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
                          <div className="relative flex rounded-xl bg-white/[0.06] p-1 overflow-hidden">
                            <div
                              className={`absolute top-1 bottom-1 w-[calc(50%-4px)] rounded-lg bg-white/20 ${
                                priceType === "limit" ? "left-1" : "left-[calc(50%+3px)]"
                              }`}
                              style={{ transition: "left 280ms cubic-bezier(0.25, 0.46, 0.45, 0.94)" }}
                            />
                            {(["limit", "market"] as const).map((type) => (
                              <button
                                key={type}
                                onClick={() => {
                                  setPriceType(type);
                                  if (type === "market" && currentPrice) setPrice(currentPrice.toString());
                                }}
                                className={`relative z-10 flex-1 py-1.5 text-xs font-bold transition-colors duration-200 ${
                                  priceType === type ? "text-white" : "text-gray-500 hover:text-gray-300"
                                }`}
                              >
                                {type === "limit" ? "지정가" : "시장가"}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* 가격 입력 */}
                        <div>
                          <div className="mb-1.5">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                              {transactionType === "buy" ? "매수가격" : "매도가격"}
                            </span>
                          </div>
                          <div className="flex gap-1.5">
                            <input
                              type="text"
                              value={priceType === "market" ? "" : (price ? Number(price).toLocaleString("ko-KR") : "")}
                              onChange={(e) => { const raw = e.target.value.replace(/,/g, ""); if (raw === "" || /^\d+$/.test(raw)) setPrice(raw); }}
                              disabled={priceType === "market"}
                              className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2.5 text-sm font-bold text-right tabular-nums text-white placeholder:text-gray-600 disabled:cursor-not-allowed disabled:opacity-40 outline-none focus:outline-none focus:ring-0"
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
                        </div>

                        {/* 수량 입력 */}
                        <div>
                          <div className="mb-1.5">
                            <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">수량</span>
                          </div>
                          <div className="flex gap-1.5">
                            <div className="relative min-w-0 flex-1">
                              <input
                                type="text"
                                value={quantity}
                                onChange={(e) => { const v = e.target.value.replace(/[^0-9]/g, ""); setQuantity(v); }}
                                className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] pl-3 pr-3 py-2.5 text-sm font-bold text-right tabular-nums text-white placeholder:text-gray-600 outline-none focus:outline-none focus:ring-0"
                                placeholder="0"
                              />
                              {!quantity && (
                                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">
                                  {transactionType === "sell" ? `최대 ${formatPrice(holdingQty)}주` : `최대 ${formatPrice(availableQty)}주`}
                                </span>
                              )}
                            </div>
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
                            ? priceType === "market" ? "시장가 매수" : "지정가 매수"
                            : priceType === "market" ? "시장가 매도" : "지정가 매도"}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
          </div>
        )}

        {/* ── 종목정보 탭 ── */}

        {(
          <div className={`divide-y divide-white/[0.08]${activeTab !== "info" ? " hidden" : ""}`}>
            {stockInfo ? (
              <>
                {/* 재무 핵심 지표 — border 그리드 패턴 */}
                <div className="grid grid-cols-2 sm:grid-cols-4 border-t border-l border-white/[0.08]">
                  {[
                    { label: "PER", sub: "", value: stockInfo.pe ? stockInfo.pe.toFixed(2) : "—" },
                    { label: "PBR", sub: "", value: stockInfo.pbr ? stockInfo.pbr.toFixed(2) : "—" },
                    {
                      label: "부채비율", sub: "Debt Ratio",
                      value: summaryFinancials.debtRatio !== undefined && summaryFinancials.debtRatio !== null
                        ? `${Number(summaryFinancials.debtRatio).toFixed(1)}%`
                        : stockInfo.debtRatio ? `${stockInfo.debtRatio.toFixed(1)}%` : "—",
                    },
                    { label: "매출액", sub: "Revenue", value: formatWonMetric(summaryFinancials.sales) },
                    { label: "영업이익", sub: "Op. Income", value: formatWonMetric(summaryFinancials.operatingProfit) },
                    { label: "당기순이익", sub: "Net Income", value: formatWonMetric(summaryFinancials.netIncome) },
                    { label: "총자산", sub: "Total Assets", value: formatWonMetric(summaryFinancials.totalAssets) },
                    { label: "총자본", sub: "Equity", value: formatWonMetric(summaryFinancials.totalEquity) },
                  ].map(({ label, sub, value }) => (
                    <div key={label} className="border-r border-b border-white/[0.08] p-4 flex flex-col gap-3">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-bold uppercase tracking-widest text-gray-500">{label}</span>
                      </div>
                      <div>
                        <p className="text-2xl font-black text-white tabular-nums font-outfit leading-none">{value}</p>
                        {sub && <p className="text-[10px] uppercase tracking-widest text-gray-600 font-bold mt-1">{sub}</p>}
                      </div>
                    </div>
                  ))}
                </div>

                {/* 기본 정보 + 기업 상세 */}
                <div className="grid grid-cols-1 lg:grid-cols-10">
                  <div className="lg:col-span-5 p-5">
                    <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit mb-4">기본 정보</h2>
                    <div>
                      {[
                        ["종목명", displayStockName],
                        ["종목코드", symbol],
                        ["상장일", formatCompactDate(stockInfo.listingDate)],
                        ["설립일", formatCompactDate(companyBasic.establishmentDate)],
                        ["대표자", companyBasic.representativeName || "—"],
                        ["섹터", stockInfo.sector || "—"],
                        ["종업원", formatCount(companyBasic.employeeCount, "명")],
                        [
                          "홈페이지",
                          companyBasic.homepageUrl ? (
                            <a href={companyBasic.homepageUrl} target="_blank" rel="noreferrer" className="text-sky-400 hover:text-sky-300 transition-colors">방문</a>
                          ) : "—",
                        ],
                      ].map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between py-3 hover:bg-white/[0.02] rounded-xl px-1 transition-colors">
                          <span className="text-xs font-bold uppercase tracking-widest text-gray-500">{label}</span>
                          <span className="max-w-[60%] truncate text-right text-sm font-bold text-white tabular-nums">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="lg:col-span-5 p-5">
                    <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit mb-4">기업 상세</h2>
                    <div>
                      {[
                        ["회계연도", summaryFinancials.businessYear || "—"],
                        ["결산월", companyBasic.settlementMonth ? `${companyBasic.settlementMonth}월` : "—"],
                        ["영문명", companyBasic.englishName || "—"],
                        ["사업자번호", companyBasic.businessRegistrationNumber || "—"],
                      ].map(([label, value]) => (
                        <div key={label} className="flex items-center justify-between py-3 hover:bg-white/[0.02] rounded-xl px-1 transition-colors">
                          <span className="text-xs font-bold uppercase tracking-widest text-gray-500">{label}</span>
                          <span className="max-w-[60%] truncate text-right text-sm font-bold text-white tabular-nums">{value}</span>
                        </div>
                      ))}
                    </div>
                    {companyBasic.address && (
                      <div className="mt-4 pt-4 border-t border-white/[0.04]">
                        <p className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-2">주소</p>
                        <p className="text-sm font-bold text-gray-400 leading-relaxed">{companyBasic.address}</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* 주요 사업 */}
                {companyBasic.mainBusiness && (
                  <div className="p-5">
                    <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit mb-3">주요 사업</h2>
                    <p className="text-sm font-bold leading-relaxed text-gray-400">{companyBasic.mainBusiness}</p>
                  </div>
                )}
              </>
            ) : (
              <div className="py-16 text-center">
                <p className="text-sm font-bold text-gray-500">종목 정보를 불러오는 중...</p>
              </div>
            )}
          </div>
        )}

        {/* ── 뉴스·공시 탭 ── */}
        {SHOW_NEWS_TAB && (
          <div className={`p-5${activeTab !== "news" ? " hidden" : ""}`}>
            <NewsImpactPanel symbol={symbol} />
          </div>
        )}


        {/* ── 커뮤니티 탭 ── */}
        {SHOW_COMMUNITY_TAB && (
          <div className={`divide-y divide-white/[0.08]${activeTab !== "community" ? " hidden" : ""}`}>
            <div className="px-5 py-4">
              <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">커뮤니티</h2>
              <p className="text-xs text-gray-500 mt-0.5">투자자 토론 및 의견</p>
            </div>
            <div className="p-5 divide-y divide-white/[0.04]">
              {[["인기 게시글", `${displayStockName} 관련 커뮤니티 게시글이 없습니다.`], ["토론", `${displayStockName} 관련 토론이 없습니다.`]].map(([title, msg]) => (
                <div key={title} className="py-5 first:pt-0 last:pb-0">
                  <h3 className="text-sm font-black text-white mb-2">{title}</h3>
                  <p className="text-sm font-bold text-gray-500">{msg}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        </div>
      </div>
    </DashboardLayout>
  );
}
