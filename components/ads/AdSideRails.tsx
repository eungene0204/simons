import { AdSlot } from "@/components/ads/AdSlot";
import { AD_SLOTS } from "@/lib/ads/adsense";

const SIDE_AD_SIZE = { width: 160, height: 600 };

// 본문(max-w-3xl) 양옆 여백의 160×600 세로 광고 — xl(1280px) 이상에서만 보이고 스크롤을 따라온다.
// 본문에 붙이지 않고 화면 양쪽 끝(16px 안쪽)에 둔다 — 화면이 넓을수록 본문과 멀어지고, 1280px에서도 본문(768px)과 겹치지 않는다.
// 부모가 `relative`여야 한다(위치를 부모 기준 absolute로 잡는다). 광고 칸은 pageKey를 key로 다시 마운트해
// 클라이언트 이동 때 새 광고를 받는다.
export function AdSideRails({ pageKey }: { pageKey: string }) {
  return (
    <>
      <div className="absolute inset-y-0 left-4 hidden w-[160px] pt-28 xl:block">
        <AdSlot key={`${pageKey}-left`} slot={AD_SLOTS.sideLeft} size={SIDE_AD_SIZE} className="sticky top-24" />
      </div>
      <div className="absolute inset-y-0 right-4 hidden w-[160px] pt-28 xl:block">
        <AdSlot key={`${pageKey}-right`} slot={AD_SLOTS.sideRight} size={SIDE_AD_SIZE} className="sticky top-24" />
      </div>
    </>
  );
}
