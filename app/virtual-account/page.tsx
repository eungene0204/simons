"use client";

import DashboardLayout from "@/components/layout/DashboardLayout";
import VirtualAccountOverview from "@/components/virtual-account/VirtualAccountOverview";
import { t } from "@/lib/i18n";

export default function VirtualAccountPage() {
  return (
    <DashboardLayout userName={t("사용자")}>
      <VirtualAccountOverview />
    </DashboardLayout>
  );
}
