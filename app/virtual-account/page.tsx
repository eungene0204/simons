"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";
import { readLastVirtualAccountDetail } from "@/components/virtual-account/virtualAccountDetailMemory";

export default function VirtualAccountPage() {
  const router = useRouter();
  const [isRestoringDetail, setIsRestoringDetail] = useState(true);

  useEffect(() => {
    const lastAccountId = readLastVirtualAccountDetail();

    if (lastAccountId) {
      router.replace(`/virtual-account/${lastAccountId}`);
      return;
    }

    setIsRestoringDetail(false);
  }, [router]);

  return (
    <DashboardLayout userName="사용자">
      {isRestoringDetail ? (
        <div className="min-h-screen bg-[#050505] px-6 py-10 text-sm font-bold text-gray-500">
          계좌 페이지로 이동 중입니다...
        </div>
      ) : (
        <VirtualAccountOverview />
      )}
    </DashboardLayout>
  );
}
