"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import VirtualAccountMainView from "@/components/portfolio/VirtualAccountMainView";

export default function VirtualAccountPage() {
  return (
    <DashboardLayout userName="사용자">
      <VirtualAccountMainView />
    </DashboardLayout>
  );
}

