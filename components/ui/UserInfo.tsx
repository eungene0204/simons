"use client";

import { useEffect, useState } from "react";
import {
  Star,
  Briefcase,
  ChartLineUp,
  Trophy,
  IconProps,
} from "phosphor-react";

interface UserInfoData {
  watchlistCount: number;
  accountCount: number;
  currentReturnRate: number;
  returnRateRank: number;
  totalUsers?: number;
}

export default function UserInfo() {
  const [userInfo, setUserInfo] = useState<UserInfoData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUserInfo();
  }, []);

  const fetchUserInfo = async () => {
    try {
      const response = await fetch("/api/user/info");
      if (response.ok) {
        const data = await response.json();
        setUserInfo(data);
      }
    } catch (error) {
      console.error("Failed to fetch user info:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3"></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-24 bg-gray-200 dark:bg-gray-700 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!userInfo) {
    return (
      <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden">
        <p className="text-gray-500 dark:text-gray-400">
          사용자 정보를 불러올 수 없습니다.
        </p>
      </div>
    );
  }

  const isPositiveReturn = userInfo.currentReturnRate >= 0;
  const returnColorClass = isPositiveReturn
    ? "text-red-600 dark:text-red-400"
    : "text-blue-500 dark:text-blue-400";

  const InfoCard = ({
    icon: Icon,
    label,
    value,
    valueColor = "text-white",
    suffix = "",
  }: {
    icon: React.ComponentType<IconProps>;
    label: string;
    value: string | number;
    valueColor?: string;
    suffix?: string;
  }) => {
    return (
      <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
        <div className="flex items-center gap-2 mb-2">
          <Icon size={20} className="text-gray-500 dark:text-gray-400" />
          <span className="text-xs sm:text-sm font-medium text-gray-600 dark:text-gray-400">
            {label}
          </span>
        </div>
        <p className={`text-xl sm:text-2xl font-bold ${valueColor}`}>
          {typeof value === "number" ? value.toLocaleString("ko-KR") : value}
          {suffix && <span className="text-base sm:text-lg ml-1">{suffix}</span>}
        </p>
      </div>
    );
  };

  return (
    <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base sm:text-lg font-semibold text-white">
          내 정보
        </h3>
        <button
          onClick={fetchUserInfo}
          className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
        >
          새로고침
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <InfoCard
          icon={Star}
          label="관심종목"
          value={userInfo.watchlistCount}
          suffix="개"
        />
        <InfoCard
          icon={Briefcase}
          label="보유계좌"
          value={userInfo.accountCount}
          suffix="개"
        />
        <InfoCard
          icon={ChartLineUp}
          label="현재 수익률"
          value={userInfo.currentReturnRate}
          valueColor={returnColorClass}
          suffix="%"
        />
        <InfoCard
          icon={Trophy}
          label="수익률 순위"
          value={userInfo.returnRateRank}
          suffix={
            userInfo.totalUsers ? ` / ${userInfo.totalUsers.toLocaleString("ko-KR")}` : ""
          }
        />
      </div>
    </div>
  );
}

