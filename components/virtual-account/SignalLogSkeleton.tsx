"use client";

interface SignalLogSkeletonProps {
  rows?: number;
}

export default function SignalLogSkeleton({ rows = 4 }: SignalLogSkeletonProps) {
  return (
    <div
      className="divide-y divide-white/[0.04]"
      aria-hidden="true"
      data-testid="signal-log-skeleton"
    >
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center justify-between px-2 py-2">
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="shimmer h-3 w-24 rounded bg-white/[0.04]" />
            <div className="shimmer h-2.5 w-32 rounded bg-white/[0.03]" />
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
            <div className="shimmer h-3 w-14 rounded bg-white/[0.04]" />
            <div className="shimmer h-4 w-9 rounded-md bg-white/[0.04]" />
          </div>
        </div>
      ))}
    </div>
  );
}
