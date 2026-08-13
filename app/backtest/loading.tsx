"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import BacktestHistoryLoading from "./BacktestHistoryLoading";

// 라우트 전환 중 페이지가 준비되기 전에 보여줄 화면.
export default function BacktestHistoryRouteLoading() {
  return (
    <DashboardLayout userName="">
      <BacktestHistoryLoading />
    </DashboardLayout>
  );
}
