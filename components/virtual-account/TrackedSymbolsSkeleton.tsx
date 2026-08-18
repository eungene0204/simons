"use client";

import { t } from "@/lib/i18n";
interface TrackedSymbolsSkeletonProps {
  rows?: number;
}

export default function TrackedSymbolsSkeleton({
  rows = 5,
}: TrackedSymbolsSkeletonProps) {
  return (
    <div
      className="overflow-x-auto lg:overflow-x-visible"
      data-testid="tracked-symbols-skeleton-scroll"
    >
      <div className="min-w-[520px] lg:min-w-0">
      <div className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 px-2 py-2 bg-white/[0.06] rounded-lg text-xs font-bold text-gray-400 uppercase tracking-widest">
        <span>{t("종목")}</span>
        <span className="text-right">{t("현재가")}</span>
        <span className="text-right">{t("등락률")}</span>
        <span className="text-right">{t("거래량")}</span>
        <span className="text-right">{t("상태")}</span>
        <span />
      </div>
      <div className="max-h-64 overflow-y-auto scrollbar-hide divide-y divide-white/[0.03]">
        {Array.from({ length: rows }, (_, index) => (
          <div
            key={index}
            className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 items-center px-1 py-2.5"
            aria-hidden="true"
          >
            <div className="min-w-0 space-y-1.5">
              <div className="shimmer h-3.5 w-24 rounded bg-white/[0.04]" />
              <div className="shimmer h-2.5 w-14 rounded bg-white/[0.03]" />
            </div>
            <div className="shimmer ml-auto h-3.5 w-14 rounded bg-white/[0.04]" />
            <div className="shimmer ml-auto h-3.5 w-12 rounded bg-white/[0.04]" />
            <div className="shimmer ml-auto h-3.5 w-14 rounded bg-white/[0.04]" />
            <div className="shimmer ml-auto h-5 w-11 rounded-md bg-white/[0.04]" />
            <div className="shimmer ml-auto h-4 w-4 rounded bg-white/[0.04]" />
          </div>
        ))}
      </div>
      </div>
    </div>
  );
}
