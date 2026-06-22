"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";

export default function VirtualAccountPage() {
  return (
    <DashboardLayout userName="사용자">
      <VirtualAccountOverview />
    </DashboardLayout>
  );
}
