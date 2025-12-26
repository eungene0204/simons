"use client";

import { memo } from "react";

function DashboardHeaderComponent() {
  return (
    <header className="bg-[#0f0f0f] px-4 py-2.5">
      {/* Empty header - Upgrade button moved to Sidebar */}
    </header>
  );
}

// memo로 감싸서 리렌더링 방지
export default memo(DashboardHeaderComponent);
