// AdSense 게시자 ID와 광고 단위 slot 번호(애드센스 '광고 단위 기준'에서 만든 것).
// "use client" 파일(components/ads/AdSlot.tsx)에 두면 서버 컴포넌트가 값 대신 클라이언트 참조를 받으므로 여기 둔다.

export const ADSENSE_CLIENT = "ca-pub-8335444243080631";

export const AD_SLOTS = {
  articleMid: "3990598232",
  articleEnd: "4234352841",
  sideLeft: "4042781159",
  sideRight: "6017995779",
} as const;
