"use client";

import { useEffect, useState } from "react";
import { VirtualAccount, PortfolioHolding } from "@/types/portfolio";
import {
  getAccount,
  getHoldingsByAccount,
  refreshAccountValue,
} from "@/lib/portfolio";
import { useDrawer } from "@/contexts/DrawerContext";
import CandlestickChart from "@/components/stock/CandlestickChart";
import { generateStockPriceData } from "@/lib/mock-stock-data";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

export default function VirtualAccountMainView() {
  const { selectedAccountId } = useDrawer();
  const [account, setAccount] = useState<VirtualAccount | null>(null);
  const [holdings, setHoldings] = useState<PortfolioHolding[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (selectedAccountId) {
      loadAccountData();
      // 주기적으로 계좌 정보 업데이트
      const interval = setInterval(() => {
        loadAccountData();
      }, 3000);
      return () => clearInterval(interval);
    } else {
      setAccount(null);
      setHoldings([]);
      setLoading(false);
    }
  }, [selectedAccountId]);

  const loadAccountData = () => {
    if (!selectedAccountId) return;
    
    setLoading(true);
    const acc = getAccount(selectedAccountId);
    if (!acc) {
      setLoading(false);
      return;
    }

    refreshAccountValue(selectedAccountId);
    const updatedAccount = getAccount(selectedAccountId);
    if (updatedAccount) {
      setAccount(updatedAccount);
    }

    const h = getHoldingsByAccount(selectedAccountId);
    setHoldings(h);
    setLoading(false);
  };

  if (!selectedAccountId) {
    return (
      <div className="p-6 text-center">
        <p className="text-gray-500 dark:text-gray-400">
          가상계좌를 선택해주세요.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded"></div>
          <div className="h-64 bg-gray-200 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  if (!account) {
    return (
      <div className="p-6 text-center">
        <p className="text-red-500">계좌를 찾을 수 없습니다.</p>
      </div>
    );
  }

  const profit = account.totalValue - account.initialAmount;
  const profitPercent = ((profit / account.initialAmount) * 100);
  const isPositive = profit >= 0;

  // 차트 데이터 생성 (보유 종목들의 가치 변화)
  const chartData = holdings.length > 0 
    ? generateStockPriceData(holdings[0].symbol, 30)
    : generateStockPriceData("AAPL", 30);

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* 계좌 정보 카드 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            {account.name}
          </h2>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            생성일: {new Date(account.createdAt).toLocaleDateString("ko-KR")}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
              초기 투자금액
            </div>
            <div className="text-xl font-semibold text-gray-900 dark:text-white">
              {formatPrice(account.initialAmount)}원
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
              현재 잔액
            </div>
            <div className="text-xl font-semibold text-gray-900 dark:text-white">
              {formatPrice(account.currentBalance)}원
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
              총 자산 가치
            </div>
            <div className="text-xl font-semibold text-gray-900 dark:text-white">
              {formatPrice(account.totalValue)}원
            </div>
            <div
              className={`text-sm mt-1 ${
                isPositive
                  ? "text-orange-500 dark:text-orange-400"
                  : "text-red-600 dark:text-red-400"
              }`}
            >
              {isPositive ? "+" : ""}
              {formatPrice(Math.abs(profit))}원 (
              {isPositive ? "+" : ""}
              {profitPercent.toFixed(2)}%)
            </div>
          </div>
        </div>
      </div>

      {/* 차트 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {holdings.length > 0 
            ? `${holdings[0].name || holdings[0].symbol} 차트`
            : "차트"}
        </h3>
        <div className="h-96">
          <CandlestickChart data={chartData} />
        </div>
      </div>

      {/* 보유 종목 */}
      {holdings.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            보유 종목
          </h3>
          <div className="space-y-2">
            {holdings.map((holding) => {
              const holdingValue = holding.quantity * holding.currentPrice;
              const profit = holdingValue - (holding.quantity * holding.averagePrice);
              const profitPercent = ((profit / (holding.quantity * holding.averagePrice)) * 100);
              const isPositive = profit >= 0;

              return (
                <div
                  key={holding.symbol}
                  className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg"
                >
                  <div className="flex-1">
                    <div className="font-medium text-gray-900 dark:text-white">
                      {holding.name || holding.symbol}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      {holding.quantity}주 × {formatPrice(holding.currentPrice)}원
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-gray-900 dark:text-white">
                      {formatPrice(holdingValue)}원
                    </div>
                    <div
                      className={`text-sm ${
                        isPositive
                          ? "text-orange-500 dark:text-orange-400"
                          : "text-red-600 dark:text-red-400"
                      }`}
                    >
                      {isPositive ? "+" : ""}
                      {formatPrice(Math.abs(profit))}원 (
                      {isPositive ? "+" : ""}
                      {profitPercent.toFixed(2)}%)
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

