"use client";

import { memo } from "react";

function DashboardHeaderComponent() {
  return (
    <header className="bg-black/20 backdrop-blur-xl px-4 h-1">
      {/* Empty header - Upgrade button moved to Sidebar */}
    </header>
  );
}

// memo로 감싸서 리렌더링 방지
export default memo(DashboardHeaderComponent);
