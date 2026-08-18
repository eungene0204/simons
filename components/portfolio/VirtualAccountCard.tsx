"use client";

import { useRouter } from "next/navigation";
import { VirtualAccount } from "@/types/portfolio";
import { getLocale, t } from "@/lib/i18n";

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("ko-KR").format(price);
};

interface VirtualAccountCardProps {
  account: VirtualAccount;
}

export default function VirtualAccountCard({ account }: VirtualAccountCardProps) {
  const router = useRouter();

  const profit = account.totalValue - account.initialAmount;
  const profitPercent = (profit / account.initialAmount) * 100;

  return (
    <div
      onClick={() => router.push(`/virtual-account/${account.id}`)}
      className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 cursor-pointer hover:shadow-md transition-shadow hover:border-blue-500 dark:hover:border-blue-500"
    >
      <div className="flex flex-col h-full">
        {/* 계좌 이름 */}
        <div className="mb-3">
          <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">
            {account.name}
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t("생성일: {0}", new Date(account.createdAt).toLocaleDateString(getLocale()))}
          </p>
        </div>

        {/* 총 자산 */}
        <div className="mb-3">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t("총 자산")}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("{0} 원", formatPrice(account.totalValue))}
          </p>
        </div>

        {/* 초기 모의 투자금액 */}
        <div className="mb-3">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t("초기 모의 투자금액")}</p>
          <p className="text-base font-medium text-gray-700 dark:text-gray-300">
            {t("{0} 원", formatPrice(account.initialAmount))}
          </p>
        </div>

        {/* 손익 */}
        <div className="mb-3">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t("손익")}</p>
          <div className="flex items-center gap-2">
            <p
              className={`text-lg font-semibold ${
                profit >= 0
                  ? "text-red-600 dark:text-red-400"
                  : "text-blue-500 dark:text-blue-400"
              }`}
            >
              {t("{0}{1} 원", profit >= 0 ? "+" : "", formatPrice(profit))}
            </p>
            <p
              className={`text-sm font-medium ${
                profitPercent >= 0
                  ? "text-red-600 dark:text-red-400"
                  : "text-blue-500 dark:text-blue-400"
              }`}
            >
              ({profitPercent >= 0 ? "+" : ""}
              {profitPercent.toFixed(2)}%)
            </p>
          </div>
        </div>

        {/* 현재 잔액 */}
        <div className="mt-auto pt-3 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t("현재 잔액")}</p>
          <p className="text-base font-medium text-gray-900 dark:text-white">
            {t("{0} 원", formatPrice(account.currentBalance))}
          </p>
        </div>
      </div>
    </div>
  );
}

