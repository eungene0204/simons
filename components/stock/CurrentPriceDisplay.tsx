"use client";

interface CurrentPriceDisplayProps {
  currentPrice?: number;
  previousClose?: number;
  change?: number;
  changePercent?: number;
  volume?: number;
  open?: number;
  high?: number;
  low?: number;
}

export default function CurrentPriceDisplay({
  currentPrice,
  previousClose,
  change,
  changePercent,
  volume,
  open,
  high,
  low,
}: CurrentPriceDisplayProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const formatVolume = (vol: number) => {
    if (vol >= 1000000) {
      return `${(vol / 1000000).toFixed(1)}M`;
    } else if (vol >= 1000) {
      return `${(vol / 1000).toFixed(1)}K`;
    }
    return vol.toString();
  };

  if (!currentPrice) {
    return (
      <div className="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center">
          종목을 선택하면 현재가가 표시됩니다
        </p>
      </div>
    );
  }

  const isUp = change && change > 0;
  const isDown = change && change < 0;

  return (
    <div className="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="flex items-baseline gap-3 mb-2">
            <span
              className={`text-3xl font-bold ${
                isUp
                  ? "text-red-600 dark:text-red-400"
                  : isDown
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-gray-900 dark:text-white"
              }`}
            >
              {formatPrice(currentPrice)}
            </span>
            {change !== undefined && changePercent !== undefined && (
              <div className="flex items-center gap-2">
                <span
                  className={`text-lg font-semibold ${
                    isUp
                      ? "text-red-600 dark:text-red-400"
                      : isDown
                      ? "text-blue-500 dark:text-blue-400"
                      : "text-gray-900 dark:text-white"
                  }`}
                >
                  {change >= 0 ? "+" : ""}
                  {formatPrice(change)}
                </span>
                <span
                  className={`text-lg font-semibold ${
                    isUp
                      ? "text-red-600 dark:text-red-400"
                      : isDown
                      ? "text-blue-500 dark:text-blue-400"
                      : "text-gray-900 dark:text-white"
                  }`}
                >
                  ({changePercent >= 0 ? "+" : ""}
                  {changePercent.toFixed(2)}%)
                </span>
              </div>
            )}
          </div>
          {volume && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              거래량: {formatVolume(volume)}
            </p>
          )}
        </div>
        <div className="text-right space-y-1">
          {open !== undefined && (
            <div className="flex gap-4 text-xs">
              <span className="text-gray-500 dark:text-gray-400 w-12">시가</span>
              <span className="text-gray-900 dark:text-white font-medium w-20 text-right">
                {formatPrice(open)}
              </span>
            </div>
          )}
          {high !== undefined && (
            <div className="flex gap-4 text-xs">
              <span className="text-gray-500 dark:text-gray-400 w-12">고가</span>
              <span className="text-red-600 dark:text-red-400 font-medium w-20 text-right">
                {formatPrice(high)}
              </span>
            </div>
          )}
          {low !== undefined && (
            <div className="flex gap-4 text-xs">
              <span className="text-gray-500 dark:text-gray-400 w-12">저가</span>
              <span className="text-blue-500 dark:text-blue-400 font-medium w-20 text-right">
                {formatPrice(low)}
              </span>
            </div>
          )}
          {previousClose !== undefined && (
            <div className="flex gap-4 text-xs">
              <span className="text-gray-500 dark:text-gray-400 w-12">기준</span>
              <span className="text-gray-900 dark:text-white font-medium w-20 text-right">
                {formatPrice(previousClose)}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

