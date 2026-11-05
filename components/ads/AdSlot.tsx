"use client";

import { useEffect } from "react";
import { ADSENSE_CLIENT } from "@/lib/ads/adsense";

// AdSense 디스플레이 광고 한 칸. 스크립트(adsbygoogle.js)는 app/layout.tsx가 KR 페이지에만 싣는다 —
// 스크립트가 없으면(/us) push는 빈 배열에 쌓일 뿐 아무것도 그리지 않는다.
// 클라이언트 이동 때 새 광고를 받으려면 호출 쪽이 글마다 다른 key를 줘서 다시 마운트시킨다.
// 채울 광고가 없으면(data-ad-status="unfilled") 칸 전체를 globals.css의 .ad-slot 규칙이 숨긴다.
// slot 번호는 lib/ads/adsense.ts — 이 파일은 "use client"라 컴포넌트 말고는 export하지 않는다(서버 컴포넌트가 값 대신 참조를 받는다).
// size를 주면 반응형 광고 단위를 그 크기로 고정한다(AdSense 안내: 너비·높이 지정 + data-ad-format 생략).

declare global {
  interface Window {
    adsbygoogle?: unknown[];
  }
}

export function AdSlot({
  slot,
  className = "",
  size,
}: {
  slot: string;
  className?: string;
  size?: { width: number; height: number };
}) {
  useEffect(() => {
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch {
      // 개발 모드 StrictMode의 이중 실행은 "이미 광고가 있는 칸"으로 던진다 — 광고 실패가 글을 깨면 안 된다.
    }
  }, []);

  return (
    <aside aria-label="광고" className={`ad-slot ${className}`}>
      <p className="text-xs font-bold text-[var(--text-label)]">광고</p>
      <ins
        className={`adsbygoogle mt-2 ${size ? "" : "min-h-[100px]"}`}
        style={
          size
            ? {
                display: "inline-block",
                width: size.width,
                height: size.height,
              }
            : { display: "block" }
        }
        data-ad-client={ADSENSE_CLIENT}
        data-ad-slot={slot}
        {...(size
          ? {}
          : { "data-ad-format": "auto", "data-full-width-responsive": "true" })}
        {...(process.env.NODE_ENV !== "production"
          ? { "data-adtest": "on" }
          : {})}
      />
    </aside>
  );
}
