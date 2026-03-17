"use client";

interface MarketSummaryProps {
  week52High: number;
  week52Low: number;
  upperLimit: number;
  lowerLimit: number;
  upVI: number;
  downVI: number;
  openPrice: number;
  highPrice: number;
  lowPrice: number;
  volumeTotal: number;
  yesterdayRatio: number;
  formatPrice: (price: number) => string;
  formatQuantity: (quantity: number) => string;
}

function StatItem({
  label,
  value,
  valueClass = "text-gray-900 dark:text-white",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex flex-col px-3 py-[3px]">
      <span className="text-gray-500 dark:text-gray-400 text-[10px] tracking-wider leading-tight">
        {label}
      </span>
      <span className={`${valueClass} text-[11px] tabular-nums tracking-wider leading-tight font-medium`}>
        {value}
      </span>
    </div>
  );
}

export default function MarketSummary({
  week52High,
  week52Low,
  upperLimit,
  lowerLimit,
  upVI,
  downVI,
  openPrice,
  highPrice,
  lowPrice,
  volumeTotal,
  yesterdayRatio,
  formatPrice,
  formatQuantity,
}: MarketSummaryProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex-1" />
      <div className="pb-1">
        <StatItem label="52주 최고" value={formatPrice(week52High)} />
        <StatItem label="52주 최저" value={formatPrice(week52Low)} />
        <StatItem label="상한가" value={formatPrice(upperLimit)} valueClass="text-red-400" />
        <StatItem label="하한가" value={formatPrice(lowerLimit)} valueClass="text-blue-400" />
        <StatItem label="상승VI" value={formatPrice(upVI)} valueClass="text-red-400" />
        <StatItem label="하강VI" value={formatPrice(downVI)} valueClass="text-blue-400" />
        <div className="h-2" />
        <StatItem label="시가" value={formatPrice(openPrice)} />
        <StatItem label="고가" value={formatPrice(highPrice)} valueClass="text-red-400" />
        <StatItem label="저가" value={formatPrice(lowPrice)} valueClass="text-blue-400" />
        <div className="h-2" />
        <StatItem label="거래량" value={formatQuantity(volumeTotal)} />
        <StatItem
          label="어제 대비"
          value={`${yesterdayRatio >= 0 ? "+" : ""}${yesterdayRatio.toFixed(2)}%`}
          valueClass={yesterdayRatio > 0 ? "text-red-400" : yesterdayRatio < 0 ? "text-blue-400" : "text-gray-900 dark:text-white"}
        />
      </div>
    </div>
  );
}
