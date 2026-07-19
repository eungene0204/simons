"use client";

import { useEffect, useState } from "react";
import { VirtualAccount, PortfolioHolding } from "@/types/portfolio";
import { refreshAccountValue } from "@/lib/portfolio";
import { useOrderAccount } from "@/contexts/OrderAccountContext";
import CandlestickChart, { OHLCV } from "@/components/stock/CandlestickChart";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

export default function VirtualAccountMainView() {
  const { selectedAccountId } = useOrderAccount();
  const [account, setAccount] = useState<VirtualAccount | null>(null);
  const [holdings, setHoldings] = useState<PortfolioHolding[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartData, setChartData] = useState<OHLCV[]>([]);

  useEffect(() => {
    if (selectedAccountId) {
      loadAccountData(true);
      const interval = setInterval(() => loadAccountData(false), 30000);
      return () => clearInterval(interval);
    } else {
      setAccount(null);
      setHoldings([]);
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAccountId]);

  const loadAccountData = async (showLoading = false) => {
    if (!selectedAccountId) return;
    if (showLoading) setLoading(true);
    const result = await refreshAccountValue(selectedAccountId);
    if (!result) {
      if (showLoading) setLoading(false);
      return;
    }
    setAccount(result.account);
    setHoldings(result.holdings);
    setLoading(false);
  };

  useEffect(() => {
    const symbol = holdings[0]?.symbol;
    if (!symbol) {
      setChartData([]);
      return;
    }

    let cancelled = false;

    fetch(`/api/stock/${symbol}/ohlcv`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data?.candles) {
          return;
        }
        setChartData(
          data.candles.map(
            (c: {
              date: string;
              open: number;
              high: number;
              low: number;
              close: number;
              volume: number;
            }) => ({
              time: c.date,
              open: c.open,
              high: c.high,
              low: c.low,
              close: c.close,
              volume: c.volume,
            })
          )
        );
      })
      .catch(() => {
        if (!cancelled) {
          setChartData([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [holdings]);

  if (!selectedAccountId) {
    return (
      <div className="p-4 md:p-5 lg:p-6 flex flex-col items-center justify-center min-h-48 gap-3">
        <p className="text-sm font-bold text-gray-500">가상계좌를 선택해주세요.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-4 md:p-5 lg:p-6 space-y-5">
        <div className="animate-pulse space-y-5">
          <div className="h-32 bg-white/[0.04] rounded-2xl" />
          <div className="h-64 bg-white/[0.04] rounded-2xl" />
        </div>
      </div>
    );
  }

  if (!account) {
    return (
      <div className="p-4 md:p-5 lg:p-6 flex flex-col items-center justify-center min-h-48 gap-3">
        <p className="text-sm font-bold text-[var(--main-blue)]">계좌를 찾을 수 없습니다.</p>
      </div>
    );
  }

  const profit = account.totalValue - account.initialAmount;
  const profitPercent = ((profit / account.initialAmount) * 100);
  const isPositive = profit >= 0;

  return (
    <div className="p-4 md:p-5 lg:p-6 space-y-5">
      {/* 계좌 요약 */}
      <div className="flat-card p-3 sm:p-4 lg:p-5" data-testid="account-summary-card">
        <div
          className="mb-4 flex flex-col items-start gap-1 lg:flex-row lg:items-center lg:justify-between lg:gap-0"
          data-testid="account-summary-header"
        >
          <span className="text-base font-black uppercase tracking-widest text-white">{account.name}</span>
          <span className="text-xs font-bold text-gray-500">
            생성일: {new Date(account.createdAt).toLocaleDateString("ko-KR")}
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-1">초기 모의 투자금액</div>
            <div className="text-xl font-black text-white tabular-nums leading-none">
              {formatPrice(account.initialAmount)}<span className="text-xs font-bold text-gray-500 ml-1">원</span>
            </div>
          </div>
          <div>
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-1">현재 잔액</div>
            <div className="text-xl font-black text-white tabular-nums leading-none">
              {formatPrice(account.currentBalance)}<span className="text-xs font-bold text-gray-500 ml-1">원</span>
            </div>
          </div>
          <div>
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-1">총 자산 가치</div>
            <div className="text-xl font-black text-white tabular-nums leading-none">
              {formatPrice(account.totalValue)}<span className="text-xs font-bold text-gray-500 ml-1">원</span>
            </div>
            <div className={`text-xs font-bold mt-1 tabular-nums ${isPositive ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
              {isPositive ? "+" : ""}{formatPrice(Math.abs(profit))}원 ({isPositive ? "+" : ""}{profitPercent.toFixed(2)}%)
            </div>
          </div>
        </div>
      </div>

      {/* 차트 */}
      <div className="flat-card p-3 sm:p-4 lg:p-5">
        <span className="text-base font-black uppercase tracking-widest text-white block mb-4">
          {holdings.length > 0 ? `${holdings[0].name || holdings[0].symbol} 차트` : "차트"}
        </span>
        <div className="h-72 sm:h-80 lg:h-96" data-testid="account-chart-container">
          <CandlestickChart data={chartData} />
        </div>
      </div>

      {/* 보유 종목 */}
      {holdings.length > 0 && (
        <div className="flat-card p-3 sm:p-4 lg:p-5">
          <span className="text-base font-black uppercase tracking-widest text-white block mb-4">보유 종목</span>
          <div className="space-y-2">
            {holdings.map((holding) => {
              const holdingValue = holding.quantity * holding.currentPrice;
              const profit = holdingValue - (holding.quantity * holding.averagePrice);
              const profitPercent = ((profit / (holding.quantity * holding.averagePrice)) * 100);
              const isPositive = profit >= 0;
              return (
                <div
                  key={holding.symbol}
                  className="flex flex-col items-stretch gap-2 rounded-xl border border-white/[0.05] bg-white/[0.03] p-3 transition-all duration-200 hover:bg-white/[0.05] lg:flex-row lg:items-center lg:justify-between lg:gap-0"
                  data-testid="account-holding-row"
                >
                  <div className="w-full min-w-0 lg:flex-1">
                    <div className="text-sm font-bold text-white truncate">{holding.name || holding.symbol}</div>
                    <div className="text-xs font-bold text-gray-500 tabular-nums">
                      {holding.quantity}주 × {formatPrice(holding.currentPrice)}원
                    </div>
                  </div>
                  <div className="w-full text-left lg:w-auto lg:text-right" data-testid="account-holding-value">
                    <div className="text-sm font-black text-white tabular-nums leading-none">
                      {formatPrice(holdingValue)}원
                    </div>
                    <div className={`text-xs font-bold tabular-nums mt-0.5 ${isPositive ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                      {isPositive ? "+" : ""}{formatPrice(Math.abs(profit))}원 ({isPositive ? "+" : ""}{profitPercent.toFixed(2)}%)
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
