"use client";

import { useRouter } from "next/navigation";
import { VirtualAccount } from "@/types/portfolio";

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
            생성일: {new Date(account.createdAt).toLocaleDateString("ko-KR")}
          </p>
        </div>

        {/* 총 자산 */}
        <div className="mb-3">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">총 자산</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatPrice(account.totalValue)} 원
          </p>
        </div>

        {/* 초기 투자금액 */}
        <div className="mb-3">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">초기 투자금액</p>
          <p className="text-base font-medium text-gray-700 dark:text-gray-300">
            {formatPrice(account.initialAmount)} 원
          </p>
        </div>

        {/* 손익 */}
        <div className="mb-3">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">손익</p>
          <div className="flex items-center gap-2">
            <p
              className={`text-lg font-semibold ${
                profit >= 0
                  ? "text-red-600 dark:text-red-400"
                  : "text-blue-500 dark:text-blue-400"
              }`}
            >
              {profit >= 0 ? "+" : ""}
              {formatPrice(profit)} 원
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
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">현재 잔액</p>
          <p className="text-base font-medium text-gray-900 dark:text-white">
            {formatPrice(account.currentBalance)} 원
          </p>
        </div>
      </div>
    </div>
  );
}

