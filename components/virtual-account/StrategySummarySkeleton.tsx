"use client";

export default function StrategySummarySkeleton() {
  return (
    <div className="py-3 space-y-2" aria-hidden="true" data-testid="strategy-summary-skeleton">
      <div className="flex justify-end mb-3">
        <div className="shimmer h-5 w-16 rounded-md bg-white/[0.04]" />
      </div>
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index} className="flex flex-wrap items-center gap-1.5">
          <div className="shimmer h-3.5 w-14 rounded bg-white/[0.03]" />
          <div className="shimmer h-6 w-20 rounded-md bg-white/[0.04]" />
          <div className="shimmer h-6 w-16 rounded-md bg-white/[0.04]" />
        </div>
      ))}
    </div>
  );
}
