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
      <div className="pb-1 text-xs" style={{ letterSpacing: "0.05em" }}>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            52주 최고
          </span>
          <span className="text-gray-900 dark:text-white text-right tabular-nums tracking-wider">
            {formatPrice(week52High)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            52주 최저
          </span>
          <span className="text-gray-900 dark:text-white text-right tabular-nums tracking-wider">
            {formatPrice(week52Low)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            상한가
          </span>
          <span className="text-red-400 text-right tabular-nums tracking-wider">
            {formatPrice(upperLimit)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            하한가
          </span>
          <span className="text-blue-400 text-right tabular-nums tracking-wider">
            {formatPrice(lowerLimit)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            상승VI
          </span>
          <span className="text-red-400 text-right tabular-nums tracking-wider">
            {formatPrice(upVI)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            하강VI
          </span>
          <span className="text-blue-400 text-right tabular-nums tracking-wider">
            {formatPrice(downVI)}
          </span>
        </div>
        <div className="h-[16px]" />
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            시가
          </span>
          <span className="text-gray-900 dark:text-white text-right tabular-nums tracking-wider">
            {formatPrice(openPrice)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            고가
          </span>
          <span className="text-red-400 text-right tabular-nums tracking-wider">
            {formatPrice(highPrice)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            저가
          </span>
          <span className="text-blue-400 text-right tabular-nums tracking-wider">
            {formatPrice(lowPrice)}
          </span>
        </div>
        <div className="h-[16px]" />
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            거래량
          </span>
          <span className="text-gray-900 dark:text-white text-right tabular-nums tracking-wider">
            {formatQuantity(volumeTotal)}
          </span>
        </div>
        <div className="h-[16px] flex items-center justify-between px-3">
          <span className="text-gray-600 dark:text-gray-400 tracking-wider">
            어제 대비
          </span>
          <span className="text-gray-900 dark:text-white text-right tabular-nums tracking-wider">
            {yesterdayRatio.toFixed(2)}%
          </span>
        </div>
      </div>
    </div>
  );
}
