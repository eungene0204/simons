import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import ResearchTestConsole from "@/components/research/ResearchTestConsole";

export default async function ResearchPage() {
  const user = await getCurrentUser();
  const userName = user?.name || "게스트";

  return (
    <DashboardLayout userName={userName}>
      <ResearchTestConsole />
    </DashboardLayout>
  );
}
