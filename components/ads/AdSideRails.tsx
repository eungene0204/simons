import { AdSlot } from "@/components/ads/AdSlot";
import { AD_SLOTS } from "@/lib/ads/adsense";

const SIDE_AD_SIZE = { width: 160, height: 600 };

// 본문(max-w-3xl) 양옆 여백의 160×600 세로 광고 — xl(1280px) 이상에서만 보이고 스크롤을 따라온다.
// 부모가 `relative`여야 한다(여백 위치를 부모 기준 absolute로 잡는다). 광고 칸은 pageKey를 key로 다시 마운트해
// 클라이언트 이동 때 새 광고를 받는다.
export function AdSideRails({ pageKey }: { pageKey: string }) {
  return (
    <>
      <div className="absolute inset-y-0 left-[calc(50%_-_26rem_-_160px)] hidden w-[160px] pt-28 xl:block">
        <AdSlot key={`${pageKey}-left`} slot={AD_SLOTS.sideLeft} size={SIDE_AD_SIZE} className="sticky top-24" />
      </div>
      <div className="absolute inset-y-0 right-[calc(50%_-_26rem_-_160px)] hidden w-[160px] pt-28 xl:block">
        <AdSlot key={`${pageKey}-right`} slot={AD_SLOTS.sideRight} size={SIDE_AD_SIZE} className="sticky top-24" />
      </div>
    </>
  );
}
