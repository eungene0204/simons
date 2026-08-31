"use client";

// 가격 페이지 조회(pricing_view) 이벤트 — 페이지 방문당 1회만 전송한다.
// (렌더마다 중복 전송 금지 — ref 가드로 StrictMode 이중 마운트도 막는다)

import { useEffect, useRef } from "react";
import { trackEvent } from "@/lib/analytics";

export default function PricingViewTracker({ source }: { source?: string }) {
  const sentRef = useRef(false);

  useEffect(() => {
    if (sentRef.current) return;
    sentRef.current = true;
    trackEvent("pricing_view", source ? { source } : {});
  }, [source]);

  return null;
}
