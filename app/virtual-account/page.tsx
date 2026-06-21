"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";
import {
  readLastVirtualAccountDetail,
  shouldRestoreLastVirtualAccountDetail,
} from "@/components/virtual-account/virtualAccountDetailMemory";

export default function VirtualAccountPage() {
  const router = useRouter();
  const [isRestoringDetail, setIsRestoringDetail] = useState(true);

  useEffect(() => {
    if (!shouldRestoreLastVirtualAccountDetail()) {
      setIsRestoringDetail(false);
      return;
    }

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
        <div
          role="status"
          aria-label="가상계좌 불러오는 중"
          className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center"
        >
          <Spinner size={32} className="animate-spin text-gray-500" aria-hidden="true" />
        </div>
      ) : (
        <VirtualAccountOverview />
      )}
    </DashboardLayout>
  );
}
