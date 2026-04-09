"use client";

interface TrackedSymbolsSkeletonProps {
  rows?: number;
}

export default function TrackedSymbolsSkeleton({
  rows = 5,
}: TrackedSymbolsSkeletonProps) {
  return (
    <div>
      <div className="grid grid-cols-[1fr_80px_72px_80px_52px_24px] gap-x-3 px-1 pb-2 border-b border-white/[0.05] text-xs font-bold text-gray-600 uppercase tracking-widest">
        <span>종목</span>
        <span className="text-right">현재가</span>
        <span className="text-right">등락률</span>
        <span className="text-right">거래량</span>
        <span className="text-right">상태</span>
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
  );
}
