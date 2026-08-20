"use client";

import { useState, useEffect, useMemo, useRef, useTransition } from "react";
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
} from "@/lib/portfolio";
import { getMarketLogs, type VirtualMarketLog } from "@/lib/virtual-market";
import { Plus, Robot, Spinner, TrendUp } from "phosphor-react";
import OrderBook from "@/components/order/OrderBook";
import PortfolioPerformanceChart from "@/components/portfolio/PortfolioPerformanceChart";
import StockSearchModal from "@/components/stock/StockSearchModal";
import StrategyReplaceModal from "@/components/ui/StrategyReplaceModal";
import AutoTradingStrategyMissingModal from "@/components/virtual-account/AutoTradingStrategyMissingModal";
import VirtualAccountSimulationNotice from "@/components/virtual-account/VirtualAccountSimulationNotice";
import {
  forgetVirtualAccountDetail,
  rememberVirtualAccountDetail,
} from "@/components/virtual-account/virtualAccountDetailMemory";
import { refreshVirtualAccountOverviewCache } from "@/components/virtual-account/virtualAccountOverviewCache";
import TrackedSymbolRow from "@/components/virtual-account/TrackedSymbolRow";
import TrackedSymbolsSkeleton from "@/components/virtual-account/TrackedSymbolsSkeleton";
import StrategySummarySkeleton from "@/components/virtual-account/StrategySummarySkeleton";
import SignalLogSkeleton from "@/components/virtual-account/SignalLogSkeleton";
import {
  resolveHoldingDisplayNames,
  resolveStockDisplayName,
  resolveTrackedDisplayNames,
  type StockMetadataMap,
} from "@/components/virtual-account/stockDisplayNames";
import SignalLog from "@/components/virtual-market/SignalLog";
import { useStockPrices } from "@/lib/hooks/useStockPrices";
import { useDelistingStatus, resolveListingStatus } from "@/lib/hooks/useDelistingStatus";
import DelistingRiskBanner from "@/components/virtual-account/DelistingRiskBanner";
import { getStatusBadgeClasses, getStatusBadge } from "@/lib/listing-status";
import {
  buildStrategySummaryGroups,
  buildStrategySummaryFromDsl,
} from "@/lib/strategy-summary";
import { colorTokens } from "@/components/strategy/colorTokens";
import { buildRealizedPerformanceSeries } from "@/app/virtual-account/performanceSeries";
import type { StockPriceSnapshot as BatchQuoteItem } from "@/lib/stock-prices";
import type { StrategyDSL } from "@/types/strategy";
import { getLocale, t } from "@/lib/i18n";

type AccountDetailCache = {
  account: VirtualAccount;
  holdings: PortfolioHolding[];
  transactions: Transaction[];
  trackedSymbols: { symbol: string; name: string }[];
};

const formatPrice = (price: number) =>
  new Intl.NumberFormat("ko-KR").format(Math.round(price));

const formatSignedPrice = (value: number) => {
  if (value === 0) return formatPrice(0);
  return `${value > 0 ? "+" : "-"}${formatPrice(Math.abs(value))}`;
};

const formatSignedPercent = (value: number) => {
  if (value === 0) return "0.00%";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
};

const formatCompact = (val: number) => {
  if (Math.abs(val) >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (Math.abs(val) >= 1_000) return `${(val / 1_000).toFixed(0)}k`;
  return String(val);
};

const getAccountDetailCacheKey = (accountId: string) =>
  `virtual-account-detail:${accountId}`;

function readAccountDetailCache(accountId: string): AccountDetailCache | null {
  if (typeof window === "undefined" || !accountId) return null;

  try {
    const raw = window.sessionStorage.getItem(getAccountDetailCacheKey(accountId));
    return raw ? (JSON.parse(raw) as AccountDetailCache) : null;
  } catch {
    return null;
  }
}

function writeAccountDetailCache(
  accountId: string,
  cache: AccountDetailCache
) {
  if (typeof window === "undefined" || !accountId) return;

  try {
    window.sessionStorage.setItem(
      getAccountDetailCacheKey(accountId),
      JSON.stringify(cache)
    );
  } catch {
    // Non-critical: the live API response remains the source of truth.
  }
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
  const [showOrderPage, setShowOrderPage] = useState(false);
  const [activeTab, setActiveTab] = useState<"holdings" | "transactions" | "performance">("holdings");
  const [dbStrategyDescription, setDbStrategyDescription] = useState<string | null>(null);
  const [dbStrategySettings, setDbStrategySettings] = useState<StrategyDSL | null>(null);
  const [dbStrategyHistorySummary, setDbStrategyHistorySummary] = useState<any>(null);
  const [trackedSymbols, setTrackedSymbols] = useState<{ symbol: string; name: string }[]>([]);
  const [stockMetadata, setStockMetadata] = useState<StockMetadataMap>({});
  const [trackedPrices, setTrackedPrices] = useState<Record<string, BatchQuoteItem>>({});
  const [isTrackedSymbolsLoading, setIsTrackedSymbolsLoading] = useState(true);
  const [isStrategyDetailLoading, setIsStrategyDetailLoading] = useState(true);
  const [isStockSearchOpen, setIsStockSearchOpen] = useState(false);
  const [isAddingTrackedSymbols, setIsAddingTrackedSymbols] = useState(false);
  const [signalLogs, setSignalLogs] = useState<VirtualMarketLog[]>([]);
  const [isSignalLogsLoading, setIsSignalLogsLoading] = useState(true);
  const [isStrategyReplaceOpen, setIsStrategyReplaceOpen] = useState(false);
  const [isMissingStrategyModalOpen, setIsMissingStrategyModalOpen] = useState(false);
  const [missingStrategyModalTitle, setMissingStrategyModalTitle] = useState(t("자동매매 설정"));
  const [missingStrategyModalDescription, setMissingStrategyModalDescription] = useState(
    t("자동매매를 시작하려면 저장된 전략이 필요합니다.")
  );
  const [isCheckingAutoTradingStrategy, setIsCheckingAutoTradingStrategy] = useState(false);
  const [isCreatingStrategy, startCreateStrategyTransition] = useTransition();
  const [isPromptVisible, setIsPromptVisible] = useState(false);
  const [promptPos, setPromptPos] = useState<{ top: number; right: number } | null>(null);
  const promptButtonRef = useRef<HTMLButtonElement>(null);

  const delistingStatus = useDelistingStatus();
  const trackedSymbolsList = trackedSymbols.map((s) => s.symbol);

  useEffect(() => {
    rememberVirtualAccountDetail(accountId);
  }, [accountId]);

  // 위험 종목 목록 (배너용): 추적 종목 + 보유 종목 중 비정상 상태
  // TRADING_SUSPENDED는 목록의 '거래정지' 배지로 충분해 배너에서 제외
  const riskItems = useMemo(() => {
    const symbolSet = new Set([
      ...trackedSymbols.map((s) => s.symbol),
      ...holdings.map((h) => h.symbol),
    ]);
    return Array.from(symbolSet)
      .map((sym) => {
        const ls = resolveListingStatus(sym, delistingStatus);
        if (ls === "NORMAL" || ls === "TRADING_SUSPENDED") return null;
        const name =
          holdings.find((h) => h.symbol === sym)?.name ||
          trackedSymbols.find((tv) => tv.symbol === sym)?.name ||
          delistingStatus.names[sym] ||
          sym;
        return {
          symbol: sym,
          name,
          listingStatus: ls,
          detail: delistingStatus.details[sym] ?? null,
        };
      })
      .filter(Boolean) as { symbol: string; name: string; listingStatus: string; detail: any }[];
  }, [trackedSymbols, holdings, delistingStatus]);

  const handleForceLiquidate = async (symbol: string) => {
    if (!confirm(t("{0} 포지션을 강제청산하시겠습니까?", symbol))) return;
    try {
      const res = await fetch(`/api/virtual-account/${accountId}/liquidate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      const data = await res.json();
      if (!res.ok) { alert(data.error ?? t("강제청산에 실패했습니다.")); return; }
      await loadAccountData();
    } catch {
      alert(t("강제청산 중 오류가 발생했습니다."));
    }
  };
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
    const cached = readAccountDetailCache(accountId);
    if (!cached) return;

    setAccount(cached.account);
    setHoldings(cached.holdings);
    setTransactions(cached.transactions);
    // trackedSymbols는 실시간 시세 폴링(useStockPrices)이 바로 시작되도록 캐시값을 채워두되,
    // isTrackedSymbolsLoading은 내리지 않는다 — 캐시가 오래돼 실제로는 종목이 있는데 비어
    // 있을 수 있어, 로딩이 끝나기 전까지는 "추적 중인 종목이 없습니다"를 절대 보여주지 않고
    // shimmer만 보여준다. 실제 로딩 종료는 loadAccountData의 신선한 응답에서만 확정한다.
    setTrackedSymbols(cached.trackedSymbols);
  }, [accountId]);

  useEffect(() => {
    if (accountId) loadAccountData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId]);

  useEffect(() => {
    let isMounted = true;

    fetch("/api/stocks/names")
      .then((res) => (res.ok ? res.json() : {}))
      .then((metadata: StockMetadataMap) => {
        if (!isMounted) return;
        setStockMetadata(metadata);
      })
      .catch(() => {
        if (!isMounted) return;
        setStockMetadata({});
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (Object.keys(stockMetadata).length === 0) return;
    setHoldings((prev) => resolveHoldingDisplayNames(prev, stockMetadata));
    setTrackedSymbols((prev) => resolveTrackedDisplayNames(prev, stockMetadata));
  }, [stockMetadata]);

  useEffect(() => {
    if (!isPromptVisible) return;
    const close = () => setIsPromptVisible(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [isPromptVisible]);

  useEffect(() => {
    if (!accountId) return;
    const interval = setInterval(async () => {
      // 백그라운드 탭에서는 폴링을 쉬게 한다.
      if (document.hidden) return;
      const result = await refreshAccountValue(accountId);
      if (!result) return;
      setAccount(result.account);
      setHoldings(resolveHoldingDisplayNames(result.holdings, stockMetadata));
    }, 3000);
    return () => clearInterval(interval);
  }, [accountId, stockMetadata]);

  useEffect(() => {
    if (!accountId) return;
    loadSignalLogs();
    const interval = setInterval(() => {
      if (document.hidden) return;
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

  // 운용 전략은 고정 데이터이므로 loadAccountData가 반복 호출돼도 다시 읽지 않고,
  // 연결된 전략(strategyId)이 실제로 바뀔 때만 한 번 조회한다.
  useEffect(() => {
    const strategyId = account?.strategyId;
    if (!strategyId) {
      setDbStrategyDescription(null);
      setDbStrategySettings(null);
      setDbStrategyHistorySummary(null);
      setIsStrategyDetailLoading(false);
      return;
    }

    let isMounted = true;
    setIsStrategyDetailLoading(true);
    fetch(`/api/strategy/${strategyId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => {
        if (!isMounted) return;
        setDbStrategyDescription(s?.description ?? null);
        setDbStrategySettings((s?.settings as StrategyDSL | null) ?? null);
        setDbStrategyHistorySummary(s?.historySummary ?? null);
      })
      .catch(() => {
        if (!isMounted) return;
        setDbStrategyDescription(null);
        setDbStrategySettings(null);
        setDbStrategyHistorySummary(null);
      })
      .finally(() => {
        if (isMounted) setIsStrategyDetailLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [account?.strategyId]);

  useEffect(() => {
    if (!isMissingStrategyModalOpen) return;
    router.prefetch("/analytics/new");
    void refreshVirtualAccountOverviewCache();
  }, [isMissingStrategyModalOpen, router]);

  const loadAccountData = async () => {
    // 계정 정보(account/holdings/transactions)와 모니터링 종목(trackedSymbols)을 같은
    // Promise.all로 묶으면 두 상태가 항상 같은 렌더에서 함께 확정되어, 전체 페이지 스피너가
    // 걷힌 시점엔 이미 isTrackedSymbolsLoading도 false라 shimmer가 보일 틈이 없다.
    // 계정 조회와 별개로 진행시켜 계정이 먼저 뜬 뒤에도 shimmer가 실제로 보이게 한다.
    const marketPromise = fetch(`/api/virtual-market/${accountId}`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);

    const [acc, tv] = await Promise.all([
      getAccount(accountId),
      getTransactionsByAccount(accountId),
    ]);
    if (!acc) {
      setIsTrackedSymbolsLoading(false);
      return;
    }
    setAccount(acc);
    const nextHoldings = resolveHoldingDisplayNames((acc as any).holdings ?? [], stockMetadata);
    const nextTransactions = tv.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    setHoldings(nextHoldings);
    setTransactions(nextTransactions);

    const marketState = await marketPromise;
    const nextTrackedSymbols = marketState?.symbols?.length
      ? marketState.symbols.map((sym: string) => ({
          symbol: sym,
          name: resolveStockDisplayName(sym, marketState.symbolNames?.[sym], stockMetadata),
        }))
      : [];
    setTrackedSymbols(nextTrackedSymbols);
    setIsTrackedSymbolsLoading(false);
    writeAccountDetailCache(accountId, {
      account: acc,
      holdings: nextHoldings,
      transactions: nextTransactions,
      trackedSymbols: nextTrackedSymbols,
    });
  };

  const loadSignalLogs = async () => {
    // 첫 응답이 확정되기 전에는 "신호가 없다"는 안내를 보여주지 않고 shimmer만 보여준다.
    // 5초 폴링에서는 이미 false라 shimmer가 다시 뜨지 않는다.
    try {
      const logs = await getMarketLogs(accountId, 30);
      setSignalLogs(
        [...logs].sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        )
      );
    } finally {
      setIsSignalLogsLoading(false);
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

  const handleAddTrackedSymbols = async (
    selected: { symbol: string; name: string }[]
  ) => {
    if (!account) return;

    const existingSymbols = new Set(trackedSymbols.map(({ symbol }) => symbol));
    const additions = selected.filter(({ symbol }) => {
      if (existingSymbols.has(symbol)) return false;
      existingSymbols.add(symbol);
      return true;
    });
    if (additions.length === 0) return;

    const merged = [...trackedSymbols, ...additions];
    setIsAddingTrackedSymbols(true);
    try {
      const response = await fetch(`/api/virtual-market/${accountId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: merged.map(({ symbol }) => symbol) }),
      });

      if (!response.ok) {
        throw new Error("Failed to add tracked symbols");
      }

      const marketState = await response.json();
      const selectedNameMap: Record<string, string> = Object.fromEntries(
        merged.map(({ symbol, name }) => [symbol, name])
      );
      const savedSymbols =
        Array.isArray(marketState?.symbols) && marketState.symbols.length > 0
          ? marketState.symbols.map((sym: string) => ({
              symbol: sym,
              name: resolveStockDisplayName(
                sym,
                marketState.symbolNames?.[sym] ?? selectedNameMap[sym],
                stockMetadata
              ),
            }))
          : [];

      setTrackedSymbols(savedSymbols);
      writeAccountDetailCache(accountId, {
        account,
        holdings,
        transactions,
        trackedSymbols: savedSymbols,
      });
    } catch (error) {
      console.error("Failed to add tracked symbols:", error);
    } finally {
      setIsAddingTrackedSymbols(false);
    }
  };

  const handleStockSelect = (symbol: string, name: string) => {
    router.push(`/stock-order?symbol=${symbol}&name=${encodeURIComponent(name)}`);
  };

  const handleAutoTradingClick = async () => {
    setIsCheckingAutoTradingStrategy(true);
    try {
      if (account?.tradingMode === "auto") {
        const updated = await updateTradingMode(accountId, "manual");
        const nextAccount = { ...account, ...updated, tradingMode: updated.tradingMode };
        setAccount(nextAccount);
        writeAccountDetailCache(accountId, {
          account: nextAccount,
          holdings,
          transactions,
          trackedSymbols,
        });
        void refreshVirtualAccountOverviewCache({ force: true });
        return;
      }

      const response = await fetch("/api/strategy");
      const strategies = response.ok ? await response.json() : [];

      if (!Array.isArray(strategies) || strategies.length === 0) {
        setMissingStrategyModalTitle(t("자동매매 설정"));
        setMissingStrategyModalDescription(t("자동매매를 시작하려면 저장된 전략이 필요합니다."));
        setIsMissingStrategyModalOpen(true);
        return;
      }

      const updated = await updateTradingMode(accountId, "auto");
      const nextAccount = account
        ? { ...account, ...updated, tradingMode: updated.tradingMode }
        : updated;
      setAccount(nextAccount);
      writeAccountDetailCache(accountId, {
        account: nextAccount,
        holdings,
        transactions,
        trackedSymbols,
      });
      void refreshVirtualAccountOverviewCache({ force: true });
    } catch {
      alert(t("저장된 전략을 확인하지 못했습니다."));
    } finally {
      setIsCheckingAutoTradingStrategy(false);
    }
  };

  const handleStrategyReplaceClick = async () => {
    try {
      const response = await fetch("/api/strategy");
      const strategies = response.ok ? await response.json() : [];

      if (!Array.isArray(strategies) || strategies.length === 0) {
        setMissingStrategyModalTitle(t("전략 만들기"));
        setMissingStrategyModalDescription(t("계좌에 연결하려면 저장된 전략이 필요합니다."));
        setIsMissingStrategyModalOpen(true);
        return;
      }

      setIsStrategyReplaceOpen(true);
    } catch {
      alert(t("저장된 전략을 확인하지 못했습니다."));
    }
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
    if (!result.success) { alert(result.error ?? t("거래에 실패했습니다.")); return; }
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
      .filter((tv) => tv.type === "sell" && tv.status === "FILLED" && tv.filledAt?.startsWith(todayStr))
      .reduce((sum, tv) => sum + (tv.realizedPnl ?? 0), 0);
    const todayPnlPct = account.initialAmount > 0 ? (todayPnl / account.initialAmount) * 100 : 0;
    const startDate = new Date(account.createdAt);
    const days = Math.max(1, Math.round((Date.now() - startDate.getTime()) / 86400000));
    const performanceData = buildRealizedPerformanceSeries(
      account.createdAt,
      transactions,
      account.initialAmount,
      todayStr
    );
    const investedValue = Math.max(0, account.totalValue - account.currentBalance);
    const cashRatio = account.totalValue > 0 ? (account.currentBalance / account.totalValue) * 100 : 0;
    const filledTradeCount = transactions.filter((tv) => tv.status === "FILLED").length;
    return { profit: p, profitPercent: pp, todayPnl, todayPnlPct, performanceData, activeDays: days, investedValue, cashRatio, filledTradeCount };
  }, [account, transactions]);

  if (!account) {
    return (
      <DashboardLayout userName={t("사용자")}>
        <div
          role="status"
          aria-label={t("가상계좌 상세 불러오는 중")}
          className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center"
        >
          <Spinner size={32} className="animate-spin text-gray-500" aria-hidden="true" />
        </div>
      </DashboardLayout>
    );
  }

  const shouldShowOrderPage = showOrderPage || selectedSymbol;
  const strategySettingsSummary = buildStrategySummaryFromDsl(dbStrategySettings);
  const strategySettingsGroups = buildStrategySummaryGroups(strategySettingsSummary);
  const strategyHistoryGroups = buildStrategySummaryGroups(dbStrategyHistorySummary);
  const strategySummaryGroups =
    strategyHistoryGroups.length > 0 ? strategyHistoryGroups : strategySettingsGroups;
  const stockSearchUniverseId =
    dbStrategySettings?.universe?.id ?? dbStrategyHistorySummary?.universeName ?? null;

  const strategies = account.strategyName
    ? [{ name: account.strategyName, status: "active" as const }]
    : [];

  const isClosedAccount = account.status === "CLOSED";

  const HOLDINGS_COLS = "grid-cols-[minmax(0,1fr)_100px_100px_56px_88px_110px]";
  const TXN_COLS = "grid-cols-[minmax(0,1fr)_56px_100px_56px_110px_88px_100px_130px]";

  return (
    <DashboardLayout userName={t("사용자")}>
      <div className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] w-full min-w-0 flex-col">
        <div className="flex-1">

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
                    className="text-xs font-bold text-blue-500 hover:text-blue-400 transition-colors duration-200"
                  >
                    {t("← 돌아가기")}
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
                        {tab === "buy" ? t("매수") : tab === "sell" ? t("매도") : tab === "amend" ? t("정정/취소") : tab === "unfilled" ? t("미체결") : t("잔고")}
                      </button>
                    ))}
                  </div>
                  <div className="p-5 space-y-4 flex-1 flex flex-col">
                    {/* 현금/신용 */}
                    <div className="flex gap-2">
                      {(["cash", "credit"] as const).map((tv) => (
                        <button
                          key={tv}
                          onClick={() => setPaymentType(tv)}
                          className={`flex-1 px-3 py-1.5 text-xs font-bold rounded-xl transition-all duration-200 ${
                            paymentType === tv
                              ? "bg-white/10 text-white"
                              : "bg-white/[0.03] text-gray-400 hover:text-gray-300"
                          }`}
                        >
                          {tv === "cash" ? t("현금") : t("신용")}
                        </button>
                      ))}
                    </div>
                    {/* 주문 유형 */}
                    <select
                      value={orderType}
                      onChange={(e) => setOrderType(e.target.value as any)}
                      className="w-full px-3 py-1.5 text-xs font-bold rounded-xl bg-white/[0.05] text-white border border-white/[0.05] focus:outline-none"
                    >
                      <option value="limit">{t("보통(지정가)")}</option>
                      <option value="market">{t("시장가")}</option>
                    </select>
                    {/* 수량 */}
                    <div>
                      <label className="block text-xs font-bold text-gray-500 uppercase tracking-widest mb-1.5">{t("수량")}</label>
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
                      <label className="block text-xs font-bold text-gray-500 uppercase tracking-widest mb-1.5">{t("가격")}</label>
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
                        <span className="text-xs font-bold text-gray-500">{t("원")}</span>
                        <button
                          onClick={() => { const p = parseFloat(price || "0"); const np = p + p * 0.01; setPrice(np.toFixed(0)); setSelectedOrderPrice(np); }}
                          className="px-2.5 py-1.5 text-xs font-bold bg-white/[0.05] text-gray-300 rounded-lg hover:bg-white/10 transition-all duration-200"
                        >+</button>
                      </div>
                    </div>
                    {/* 총 거래금액 */}
                    <div className="bg-white/[0.03] rounded-xl p-4 border border-white/[0.05]">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">{t("총 거래금액")}</span>
                        <span className="text-lg font-black text-white tabular-nums font-outfit">
                          {t("{0}원", quantity && price ? formatPrice(parseFloat(quantity) * parseFloat(price)) : "0")}
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
                        {paymentType === "cash" ? t("현금") : t("신용")}{transactionType === "buy" ? t("매수") : t("매도")}
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

              {/* 리스크 배너 */}
              {riskItems.length > 0 && (
                <DelistingRiskBanner
                  items={riskItems}
                  onForceLiquidate={handleForceLiquidate}
                />
              )}

              {/* 헤더 */}
              <div className="flex items-center justify-between px-5 py-4">
                <div className="flex items-center gap-4">
                  <h1 className="text-2xl font-black text-white font-outfit">{account.name}</h1>
                  {isClosedAccount ? (
                    <span className="inline-flex items-center rounded-lg border border-white/[0.08] px-2.5 py-1 text-[11px] font-bold text-gray-500">
                      {t("삭제된 계좌")}
                    </span>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={handleAutoTradingClick}
                        disabled={isCheckingAutoTradingStrategy}
                        aria-pressed={account.tradingMode === "auto"}
                        style={
                          account.tradingMode === "auto"
                            ? { textShadow: "0 0 6px rgba(251, 146, 60, 0.65), 0 0 14px rgba(251, 146, 60, 0.35)" }
                            : undefined
                        }
                        className={`inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[10px] font-black transition-colors duration-200 ${
                          account.tradingMode === "auto"
                            ? "border-amber-400/25 bg-[#1a1208]/90 text-amber-300 shadow-[0_0_18px_rgba(245,158,11,0.22)]"
                            : "border-white/[0.08] bg-white/[0.03] text-gray-500 hover:border-white/[0.16] hover:text-gray-300"
                        } disabled:cursor-not-allowed disabled:opacity-60`}
                      >
                        <Robot size={10} weight="bold" />
                        {account.tradingMode === "auto" ? t("시뮬레이션 ON") : t("시뮬레이션 OFF")}
                      </button>
                      <span
                        className="group relative flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-white/[0.14] text-[10px] font-black text-gray-500 transition-colors duration-200 hover:border-white/[0.28] hover:text-white focus:outline-none focus:ring-2 focus:ring-white/20"
                        role="button"
                        tabIndex={0}
                        aria-label={t("시뮬레이션 토글 설명")}
                      >
                        <span aria-hidden="true">?</span>
                        <span
                          className="pointer-events-none fixed inset-x-4 bottom-4 z-50 w-auto rounded-lg border border-white/[0.08] bg-[#1c1c1c] px-3 py-2 text-left text-xs font-bold leading-5 text-gray-300 opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 lg:absolute lg:inset-x-auto lg:bottom-auto lg:left-1/2 lg:top-full lg:z-30 lg:mt-2 lg:w-56 lg:-translate-x-1/2"
                          data-testid="auto-trading-help-tooltip"
                        >
                          {t("ON이면 전략 조건을 만족할 때 가상 거래가 실행됩니다.")}
                          <span className="absolute -top-[5px] left-1/2 hidden h-2.5 w-2.5 -translate-x-1/2 rotate-45 border-l border-t border-white/[0.08] bg-[#1c1c1c] lg:block" />
                        </span>
                      </span>
                    </div>
                  )}
                  <span className="text-[11px] font-bold text-gray-600">
                    {t("개설 {0}", new Date(account.createdAt).toLocaleDateString(getLocale(), { year: "numeric", month: "2-digit", day: "2-digit" }))}
                  </span>
                  {isClosedAccount && account.closedAt && (
                    <span className="text-[11px] font-bold text-gray-600">
                      {t("해지 {0}", new Date(account.closedAt).toLocaleDateString(getLocale(), { year: "numeric", month: "2-digit", day: "2-digit" }))}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      forgetVirtualAccountDetail(accountId);
                      router.push("/virtual-account");
                    }}
                    className="flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-[var(--main-blue)] transition-all duration-200 hover:text-[var(--main-blue)]/80"
                  >
                    {t("계좌닫기")}
                  </button>
                </div>
              </div>

              {/* KPI 4개 */}
              <div className="grid grid-cols-2 lg:grid-cols-4 border-t border-l border-white/[0.08]">
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">{t("총 자산")}</span>
                  <p
                    className="mt-2 text-2xl font-black tabular-nums font-outfit leading-none"
                    style={{ color: colorTokens.main_white }}
                  >
                    {formatPrice(account.totalValue)}
                  </p>
                  <p className="mt-1 text-[10px] font-bold text-gray-500">{t("원")}</p>
                </div>
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">{t("주문 가능")}</span>
                  <p
                    className="mt-2 text-2xl font-black tabular-nums font-outfit leading-none"
                    style={{ color: colorTokens.main_white }}
                  >
                    {formatPrice(account.currentBalance)}
                  </p>
                  <p className="mt-1 text-[10px] font-bold text-gray-500">{t("원")}</p>
                </div>
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">{t("당일 실현손익")}</span>
                  <p
                    className={`mt-2 text-2xl font-black tabular-nums font-outfit leading-none ${todayPnl === 0 ? "" : todayPnl > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}
                    style={todayPnl === 0 ? { color: colorTokens.main_white } : undefined}
                  >
                    {formatSignedPrice(todayPnl)}
                  </p>
                  <p
                    className={`mt-1 text-[10px] font-bold tabular-nums ${todayPnl === 0 ? "text-gray-500" : todayPnl > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}
                  >
                    {formatSignedPercent(todayPnlPct)}
                    <span className="ml-1 font-bold text-gray-500">{t("초기 자본 대비")}</span>
                  </p>
                </div>
                <div className="border-r border-b border-white/[0.08] px-5 py-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">{t("누적 수익률")}</span>
                  <p
                    className={`mt-2 text-2xl font-black tabular-nums font-outfit leading-none ${profitPercent === 0 ? "" : profitPercent > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}
                    style={profitPercent === 0 ? { color: colorTokens.main_white } : undefined}
                  >
                    {formatSignedPercent(profitPercent)}
                  </p>
                  <p className="mt-1 text-[10px] font-bold text-gray-500">{t("초기 자본 대비")}</p>
                </div>
              </div>

              {/* 추적 종목 + 운용 전략 + 매매 신호 */}
              <div className="grid grid-cols-1 lg:h-[400px] lg:grid-cols-[minmax(0,1.3fr)_280px_minmax(0,0.7fr)] divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">

                {/* 추적 종목 */}
                <div className="p-3 sm:p-4 lg:p-5 flex flex-col min-h-0">
                  <div className="mb-4 flex flex-col items-start gap-3 lg:flex-row lg:items-center lg:justify-between lg:gap-0 shrink-0">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <h2
                          className="text-base font-black uppercase tracking-widest font-outfit"
                          style={{ color: colorTokens.title_main }}
                        >
                          {t("모니터링 종목")}
                        </h2>
                        <span
                          className="group relative flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-white/[0.14] text-[10px] font-black text-gray-500 transition-colors duration-200 hover:border-white/[0.28] hover:text-white focus:outline-none focus:ring-2 focus:ring-white/20"
                          role="button"
                          tabIndex={0}
                          aria-label={t("모니터링 종목 설명")}
                        >
                          <span aria-hidden="true">?</span>
                          <span
                            className="pointer-events-none fixed inset-x-4 bottom-4 z-50 w-auto rounded-lg border border-white/[0.08] bg-[#1c1c1c] px-3 py-2 text-left text-xs font-bold leading-5 text-gray-300 opacity-0 shadow-xl transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 lg:absolute lg:inset-x-auto lg:bottom-auto lg:left-full lg:top-full lg:z-30 lg:ml-2 lg:mt-2 lg:w-64"
                            data-testid="tracked-symbols-help-tooltip"
                          >
                            {t("연결된 전략의 백테스트에서 성과가 높았던 종목들 입니다.")}
                            <span className="absolute -left-[5px] top-2 hidden h-2.5 w-2.5 rotate-45 border-b border-l border-white/[0.08] bg-[#1c1c1c] lg:block" />
                          </span>
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                        {t("{0}개", trackedSymbols.length)}
                      </span>
                      <button
                        type="button"
                        onClick={() => setIsStockSearchOpen(true)}
                        disabled={isAddingTrackedSymbols}
                        className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] px-2.5 py-1 text-xs font-bold text-gray-400 transition-colors duration-200 hover:border-white/[0.16] hover:bg-white/[0.04] hover:text-white disabled:cursor-wait disabled:opacity-50"
                      >
                        <Plus size={13} weight="bold" />
                        {t("종목 추가")}
                      </button>
                    </div>
                  </div>
                  {isTrackedSymbolsLoading ? (
                    <TrackedSymbolsSkeleton />
                  ) : trackedSymbols.length === 0 ? (
                    <div className="flex flex-1 min-h-[12rem] flex-col items-center justify-center gap-3">
                      <TrendUp size={32} className="text-gray-700" weight="thin" />
                      <p className="text-sm font-bold text-gray-600">{t("추적 중인 종목이 없습니다")}</p>
                    </div>
                  ) : (
                    <div
                      className="flex-1 min-h-0 flex flex-col overflow-x-auto lg:overflow-x-visible"
                      data-testid="tracked-symbols-table-scroll"
                    >
                      <div className="min-w-[520px] lg:min-w-0 flex-1 min-h-0 flex flex-col">
                      {/* 테이블 헤더 */}
                      <div className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 px-1 mb-1 shrink-0">
                        {["종목", "현재가", "등락률", "거래량", "상태", ""].map((h) => (
                          <span key={h} className={`text-xs font-bold uppercase tracking-widest text-gray-600 ${h === "현재가" || h === "등락률" || h === "거래량" ? "text-right" : h === "상태" ? "text-center" : ""}`}>
                            {t(h)}
                          </span>
                        ))}
                      </div>
                      <div className="border-t border-white/[0.05] mb-1 shrink-0" />
                      {/* 테이블 행 */}
                      <div className="flex-1 min-h-0 max-h-64 lg:max-h-none overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                        <div className="divide-y divide-white/[0.04]">
                          {trackedSymbols.map(({ symbol, name }) => {
                            const q = trackedPrices[symbol];
                            const holding = holdings.find((h) => h.symbol === symbol);
                            const ls = resolveListingStatus(symbol, delistingStatus);
                            return (
                              <TrackedSymbolRow
                                key={symbol}
                                symbol={symbol}
                                name={name}
                                quote={q}
                                hasHolding={!!holding}
                                listingStatus={ls}
                                onSelect={handleStockSelect}
                                onRemove={handleRemoveTrackedSymbol}
                                formatPrice={formatPrice}
                              />
                            );
                          })}
                        </div>
                      </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* 운용 전략 */}
                <div className="p-5 flex flex-col min-h-0">
                  <div className="flex items-center justify-between mb-5 shrink-0">
                    <div>
                      <h2
                        className="text-base font-black uppercase tracking-widest font-outfit"
                        style={{ color: colorTokens.title_main }}
                      >
                        {t("운용 전략")}
                      </h2>
                      <p className="text-xs text-gray-500 mt-0.5">{t("현재 계좌에 적용된 매매 전략")}</p>
                    </div>
                    <button
                      onClick={handleStrategyReplaceClick}
                      className="inline-flex items-center rounded-xl px-3 py-1.5 text-xs font-bold text-[var(--main-blue)] transition-colors duration-200 hover:text-[var(--main-blue)]/80"
                    >
                      {t("전략 교체")}
                    </button>
                  </div>
                  <div className="flex-1 min-h-0 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent space-y-3">
                    {strategies.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full gap-2">
                        <p className="text-sm font-bold text-gray-600">{t("연결된 전략이 없습니다")}</p>
                        <button
                          onClick={handleStrategyReplaceClick}
                          className="text-xs font-bold text-[var(--main-green)] hover:text-[var(--main-green)]/80 transition-colors"
                        >
                          {t("전략 연결하기")}
                        </button>
                      </div>
                    ) : isStrategyDetailLoading ? (
                      <StrategySummarySkeleton />
                    ) : (
                      strategies.map((strategy, idx) => {
                        const isAccountStrategy = strategy.name === account.strategyName;
                        const description = isAccountStrategy ? dbStrategyDescription : null;
                        return (
                          <div key={idx} className="py-3">
                            {description && (
                              <div className="flex justify-end mb-3">
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
                                    className="inline-flex items-center rounded-md bg-white/[0.06] hover:bg-white/[0.1] px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-[var(--main-green)] transition-colors duration-200"
                                  >
                                    {t("프롬프트")}
                                  </button>
                                </div>
                              </div>
                            )}
                            {strategySummaryGroups.length > 0 && (
                              <div className="space-y-2">
                                {strategySummaryGroups.map((group) => (
                                  <div key={group.label} className="flex items-start justify-between gap-3">
                                    <span className="text-xs font-bold uppercase tracking-widest text-gray-500 shrink-0 py-1">
                                      {group.label}
                                    </span>
                                    <div className="flex flex-col items-end gap-1 min-w-0">
                                      {group.chips.map((chip) => (
                                        <span
                                          key={chip}
                                          className="inline-flex items-center rounded-md bg-white/[0.06] px-2.5 py-1 text-xs font-bold text-yellow-500 text-right"
                                        >
                                          {chip}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
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
                <div className="p-5 flex flex-col min-h-0 max-h-[400px]">
                  <div className="flex items-center justify-between mb-4 shrink-0">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2
                          className="text-base font-black uppercase tracking-widest font-outfit"
                          style={{ color: colorTokens.title_main }}
                        >
                          {t("매매 신호")}
                        </h2>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">{t("최근 발생한 전략 신호")}</p>
                    </div>
                    {isSignalLogsLoading ? (
                      <div className="shimmer h-5 w-11 rounded-md bg-white/[0.05]" aria-hidden="true" />
                    ) : (
                      <span className="text-xs font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                        {t("{0}건", signalLogs.length)}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-h-0 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                    {isSignalLogsLoading ? (
                      <SignalLogSkeleton />
                    ) : (
                      <SignalLog
                        logs={signalLogs}
                        accountCreatedAt={account.createdAt}
                        onStrategyReplace={handleStrategyReplaceClick}
                      />
                    )}
                  </div>
                </div>
              </div>

              {/* 보유 종목 / 거래 내역 / 성과 분석 탭 */}
              <div className={activeTab === "performance" ? "" : "p-5"}>
                <div className={`flex items-center justify-between mb-5 ${activeTab === "performance" ? "px-5 pt-5" : ""}`}>
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      {(["holdings", "transactions", "performance"] as const).map((tab) => (
                        <button
                          key={tab}
                          onClick={() => setActiveTab(tab)}
                          className={`px-3 py-1.5 text-sm font-bold rounded-lg transition-all duration-200 ${
                            activeTab === tab
                              ? "bg-white/[0.08] text-white"
                              : "text-gray-500 hover:text-gray-300"
                          }`}
                        >
                          {tab === "holdings" ? t("보유 종목") : tab === "transactions" ? t("거래 내역") : t("성과 분석")}
                        </button>
                      ))}
                    </div>
                    {activeTab === "holdings" && (
                      <span className="text-[10px] font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                        {t("{0}개 포지션", holdings.length)}
                      </span>
                    )}
                    {activeTab === "transactions" && (
                      <span className="text-[10px] font-bold text-gray-500 bg-white/[0.05] px-2.5 py-0.5 rounded-md">
                        {t("{0}건", transactions.length)}
                      </span>
                    )}
                  </div>
                </div>

                {/* 보유 종목 */}
                {activeTab === "holdings" && (
                  holdings.length === 0 ? (
                    <div className="py-12 text-center">
                      <p className="text-sm font-bold text-gray-600">{t("보유 중인 종목이 없습니다.")}</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      {/* 헤더 */}
                      <div className={`grid ${HOLDINGS_COLS} gap-2 px-2 mb-1`}>
                        {["종목", "평균 단가", "현재가", "수량", "수익률", "평가 손익"].map((h, i) => (
                          <span key={h} className={`text-xs font-bold uppercase tracking-widest text-gray-600 ${i > 0 ? "text-right" : ""}`}>
                            {t(h)}
                          </span>
                        ))}
                      </div>
                      <div className="border-t border-white/[0.05] mb-1" />
                      {/* 행 */}
                      <div className="max-h-[360px] overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                        <div className="divide-y divide-white/[0.04]">
                          {holdings.map((h) => {
                            const ls = resolveListingStatus(h.symbol, delistingStatus);
                            const isDelisted = ls === "DELISTED";
                            const isZero = isDelisted;
                            const displayPrice = isZero ? 0 : h.currentPrice;
                            const displayProfit = isZero ? -(h.averagePrice * h.quantity) : h.profit;
                            const displayProfitPct = isZero
                              ? -100
                              : h.profitPercent;
                            const pnlColor = displayProfitPct === 0 ? "text-white" : displayProfitPct > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]";
                            const badge = getStatusBadge(ls);
                            return (
                              <div
                                key={h.symbol}
                                onClick={() => handleStockSelect(h.symbol, h.name || h.symbol)}
                                className={`grid ${HOLDINGS_COLS} gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors duration-150 cursor-pointer ${isDelisted ? "opacity-60" : ""}`}
                              >
                                <div className="min-w-0">
                                  <div className="flex items-center gap-1.5 min-w-0">
                                    <p className="text-sm font-bold text-white truncate">{h.name || h.symbol}</p>
                                    {badge && (
                                      <span className={`shrink-0 text-[9px] font-black tracking-wide px-1 py-0.5 rounded ${getStatusBadgeClasses(badge.variant)}`}>
                                        {badge.label}
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-[10px] font-bold text-gray-500">{h.symbol}</p>
                                </div>
                                <p className="text-sm font-bold text-gray-400 tabular-nums text-right">{formatPrice(h.averagePrice)}</p>
                                <p className={`text-sm font-black tabular-nums text-right ${isZero ? "text-gray-600 line-through" : "text-white"}`}>
                                  {isZero ? "0" : formatPrice(displayPrice)}
                                </p>
                                <p className="text-sm font-bold text-gray-400 tabular-nums text-right">{h.quantity.toLocaleString()}</p>
                                <div className={`flex items-center justify-end gap-0.5 ${pnlColor}`}>
                                  <span className="text-xs font-black tabular-nums font-outfit">{formatSignedPercent(displayProfitPct)}</span>
                                </div>
                                <p className={`text-sm font-black tabular-nums text-right ${pnlColor}`}>
                                  {formatSignedPrice(Math.round(displayProfit))}
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
                      <p className="text-sm font-bold text-gray-600">{t("거래 내역이 없습니다.")}</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      {/* 헤더 */}
                      <div className={`grid ${TXN_COLS} gap-2 px-2 mb-1`}>
                        {["종목", "구분", "체결가", "수량", "거래금액", "수수료", "실현손익", "체결시간"].map((h, i) => (
                          <span key={h} className={`text-xs font-bold uppercase tracking-widest text-gray-600 ${i > 0 ? "text-right" : ""}`}>
                            {t(h)}
                          </span>
                        ))}
                      </div>
                      <div className="border-t border-white/[0.05] mb-1" />
                      {/* 행 */}
                      <div className="max-h-[360px] overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
                        <div className="divide-y divide-white/[0.04]">
                          {transactions.map((tv) => (
                            <div
                              key={tv.id}
                              className={`grid ${TXN_COLS} gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors duration-150`}
                            >
                              <div className="min-w-0">
                                <p className="text-sm font-bold text-white truncate">{tv.name}</p>
                                <p className="text-[10px] font-bold text-gray-500">{tv.symbol}</p>
                              </div>
                              <div className="text-right">
                                <span className={`text-xs font-black px-1.5 py-0.5 rounded-md ${
                                  tv.type === "buy"
                                    ? "bg-[var(--main-red)]/15 text-[var(--main-red)]"
                                    : "bg-[var(--main-blue)]/15 text-[var(--main-blue)]"
                                }`}>
                                  {tv.type === "buy" ? t("매수") : t("매도")}
                                </span>
                              </div>
                              <p className="text-sm font-bold text-white tabular-nums text-right">{formatPrice(tv.filledPrice ?? tv.price)}</p>
                              <p className="text-sm font-bold text-gray-400 tabular-nums text-right">{tv.quantity}</p>
                              <p className="text-sm font-bold text-white tabular-nums text-right">{formatPrice(tv.totalAmount)}</p>
                              <p className="text-sm font-bold text-gray-500 tabular-nums text-right">{tv.fee != null ? t("{0}원", formatPrice(tv.fee)) : "—"}</p>
                              <div className="text-right">
                                {tv.realizedPnl != null ? (
                                  <span className={`text-sm font-black tabular-nums ${tv.realizedPnl === 0 ? "text-white" : tv.realizedPnl > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                                    {formatSignedPrice(Math.round(tv.realizedPnl))}
                                  </span>
                                ) : (
                                  <span className="text-sm font-bold text-gray-600">—</span>
                                )}
                              </div>
                              <div className="text-right">
                                <p className="text-[10px] font-bold text-gray-500 tabular-nums">
                                  {new Date(tv.filledAt ?? tv.timestamp).toLocaleDateString(getLocale())}
                                </p>
                                <p className="text-[10px] font-bold text-gray-500 tabular-nums">
                                  {new Date(tv.filledAt ?? tv.timestamp).toLocaleTimeString(getLocale())}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )
                )}

                {/* 성과 분석 */}
                {activeTab === "performance" && (
                  <div className="divide-y divide-white/[0.08]">
                      {/* 성과 KPI 6개 */}
                      <div className="grid grid-cols-2 xl:grid-cols-6 border-l border-t border-white/[0.08]">
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{t("누적 손익")}</p>
                          <p className={`mt-2 text-2xl font-black font-outfit tabular-nums leading-none ${profit === 0 ? "text-white" : profit > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {formatSignedPrice(profit)}
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">{t("초기 자본 대비")}</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{t("누적 수익률")}</p>
                          <p className={`mt-2 text-2xl font-black font-outfit tabular-nums leading-none ${profitPercent === 0 ? "text-white" : profitPercent > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {formatSignedPercent(profitPercent)}
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">{t("초기 자본 대비")}</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{t("당일 실현손익")}</p>
                          <p className={`mt-2 text-2xl font-black font-outfit tabular-nums leading-none ${todayPnl === 0 ? "text-white" : todayPnl > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {formatSignedPrice(todayPnl)}
                          </p>
                          <p className={`mt-1 text-[10px] font-bold tabular-nums ${todayPnl === 0 ? "text-gray-500" : todayPnl > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {formatSignedPercent(todayPnlPct)}
                            <span className="ml-1 font-bold text-gray-500">{t("초기 자본 대비")}</span>
                          </p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{t("운용 기간")}</p>
                          <p className="mt-2 text-2xl font-black font-outfit tabular-nums leading-none text-white">
                            {formatCompact(activeDays)}
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">{t("일 기준")}</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{t("체결 거래")}</p>
                          <p className="mt-2 text-2xl font-black font-outfit tabular-nums leading-none text-white">
                            {formatCompact(filledTradeCount)}
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">{t("누적 체결 건수")}</p>
                        </div>
                        <div className="border-r border-b border-white/[0.08] p-5">
                          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{t("현금 비중")}</p>
                          <p className="mt-2 text-2xl font-black font-outfit tabular-nums leading-none text-white">
                            {cashRatio.toFixed(1)}%
                          </p>
                          <p className="mt-1 text-[10px] font-bold text-gray-500">{t("주문 가능 금액")}</p>
                        </div>
                      </div>

                    {/* 성과 차트 + 분석 요약 */}
                    <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
                      <div className="lg:col-span-7 p-5">
                        <div className="flex items-start justify-between gap-4 mb-5">
                          <div>
                            <h2 className="text-base font-black uppercase tracking-widest font-outfit text-white">{t("실현손익 추이")}</h2>
                            <p className="mt-0.5 text-xs font-bold text-gray-500">{t("계좌 개설 이후 누적 실현손익 (초기 자본 대비)")}</p>
                          </div>
                        </div>
                        <div className="h-72">
                          <PortfolioPerformanceChart data={performanceData} />
                        </div>
                      </div>
                      <div className="lg:col-span-3 p-5">
                        <div className="mb-5">
                          <h2 className="text-base font-black uppercase tracking-widest font-outfit text-white">{t("분석 요약")}</h2>
                          <p className="mt-0.5 text-xs font-bold text-gray-500">{t("성과 해석에 필요한 현재 상태")}</p>
                        </div>
                        <div className="divide-y divide-white/[0.08] border-y border-white/[0.08]">
                          <div className="py-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-gray-600">{t("계좌 개설일")}</p>
                            <p className="mt-1 text-sm font-black text-white">{new Date(account.createdAt).toLocaleDateString(getLocale())}</p>
                          </div>
                          <div className="py-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-gray-600">{t("초기 모의 투자금")}</p>
                            <p className="mt-1 text-sm font-black font-outfit tabular-nums text-white">{t("{0}원", formatPrice(account.initialAmount))}</p>
                          </div>
                          <div className="py-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-gray-600">{t("주식 평가 금액")}</p>
                            <p className="mt-1 text-sm font-black font-outfit tabular-nums text-white">{t("{0}원", formatPrice(investedValue))}</p>
                          </div>
                          <div className="py-3">
                            <p className="text-xs font-bold uppercase tracking-widest text-gray-600">{t("보유 종목 수")}</p>
                            <p className="mt-1 text-sm font-black font-outfit tabular-nums text-white">{t("{0}개", holdings.length)}</p>
                          </div>
                        </div>
                        <div className="mt-5 space-y-2">
                          <p className="text-xs font-bold leading-5 text-gray-500">
                            {t("추이 차트는 매도 체결로 확정된 실현손익만 누적합니다. 보유 중인 종목의 평가손익은 포함되지 않아 위의 누적 수익률과 다를 수 있습니다.")}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* 세부 성과 리포트 */}
                    <div className="p-5">
                      <div className="flex items-start justify-between gap-4 mb-4">
                        <div>
                          <h2 className="text-base font-black uppercase tracking-widest font-outfit text-white">{t("세부 성과 리포트")}</h2>
                          <p className="mt-0.5 text-xs font-bold text-gray-500">{t("실현 손익, 승률, 일별 PnL, 종목별 성과")}</p>
                        </div>
                        <span className="inline-flex items-center rounded-md bg-white/[0.06] px-2.5 py-1 text-xs font-bold text-gray-400">
                          DETAIL
                        </span>
                      </div>
                      <VirtualTradingDashboard accountId={accountId} initialAmount={account.initialAmount} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        </div>

        {isPromptVisible && promptPos && dbStrategyDescription && (
          <div
            className="fixed z-[100] w-64 rounded-xl border border-white/[0.08] bg-[#1c1c1c] p-3 shadow-2xl"
            style={{ top: promptPos.top, right: promptPos.right }}
          >
            <p className="text-xs font-bold leading-5 text-gray-400 whitespace-pre-wrap">{dbStrategyDescription}</p>
            <div className="absolute -top-[5px] right-3.5 w-2.5 h-2.5 rotate-45 bg-[#1c1c1c] border-l border-t border-white/[0.08]" />
          </div>
        )}
        <StockSearchModal
          isOpen={isStockSearchOpen}
          onClose={() => setIsStockSearchOpen(false)}
          onSelect={handleAddTrackedSymbols}
          universeId={stockSearchUniverseId}
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
                ? { ...prev, strategyId: updated.strategyId, strategyName: updated.strategyName }
                : prev
            );
            setDbStrategyDescription(strategy.description ?? null);
            setDbStrategySettings(strategy as unknown as StrategyDSL);
            setDbStrategyHistorySummary(null);
            setIsPromptVisible(false);
            await loadAccountData();
          }}
        />
        <AutoTradingStrategyMissingModal
          isOpen={isMissingStrategyModalOpen}
          title={missingStrategyModalTitle}
          description={missingStrategyModalDescription}
          isCreatingStrategy={isCreatingStrategy}
          onClose={() => setIsMissingStrategyModalOpen(false)}
          onCreateStrategy={() => {
            startCreateStrategyTransition(() => {
              router.push("/analytics/new");
            });
          }}
        />
        <VirtualAccountSimulationNotice className="mt-auto" />
      </div>
    </DashboardLayout>
  );
}
