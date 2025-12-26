import { getCurrentUser } from "@/lib/get-user";
import DashboardLayout from "@/components/layout/DashboardLayout";
import Watchlist from "@/components/watchlist/Watchlist";

export default async function WatchlistPage() {
  const user = await getCurrentUser();

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">로그인이 필요합니다.</p>
      </div>
    );
  }

  return (
    <DashboardLayout userName={user.name}>
      <div className="p-3 sm:p-4 md:p-6 max-w-7xl mx-auto overflow-x-hidden w-full">
        <Watchlist />
      </div>
    </DashboardLayout>
  );
}

