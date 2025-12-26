"use client";

type HoldingData = {
  type: string;
  percentage: number;
  count: number;
  color: string;
};

export default function HoldingsCharacteristics() {
  const holdings: HoldingData[] = [
    { type: "High Growth", percentage: 22, count: 819, color: "bg-blue-600" },
    { type: "Stable", percentage: 58, count: 2150, color: "bg-yellow-500" },
    { type: "Volatile", percentage: 20, count: 742, color: "bg-orange-500" },
  ];

  const fakeHoldings = 5.3;
  const realHoldings = 94.7;

  return (
    <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800">
      <h3 className="text-base sm:text-lg font-semibold text-white mb-2">
        Holdings Characteristics
      </h3>
      <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mb-4 sm:mb-6">
        (This is a dummy preview)
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        {/* Left: Bar Chart */}
        <div className="space-y-3 sm:space-y-4">
          {holdings.map((holding) => (
            <div key={holding.type} className="space-y-1">
              <div className="flex justify-between text-xs sm:text-sm">
                <span className="text-gray-700 dark:text-gray-300">
                  {holding.type}
                </span>
                <span className="font-medium text-white">
                  {holding.percentage}%
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 sm:h-3">
                <div
                  className={`${holding.color} h-2 sm:h-3 rounded-full`}
                  style={{ width: `${holding.percentage}%` }}
                />
              </div>
            </div>
          ))}
          <div className="pt-2 border-t border-gray-800">
            <div className="flex justify-between text-xs sm:text-sm">
              <span className="text-blue-500 dark:text-blue-400 font-medium">
                Verified Holdings
              </span>
              <span className="font-medium text-white">
                819
              </span>
            </div>
          </div>
        </div>

        {/* Right: Fake/Real Ratio */}
        <div className="flex items-center justify-center">
          <div className="relative w-24 h-24 sm:w-32 sm:h-32">
            <svg viewBox="0 0 100 100" className="transform -rotate-90 w-full h-full">
              <circle
                cx="50"
                cy="50"
                r="45"
                fill="none"
                stroke="#ef4444"
                strokeWidth="10"
                strokeDasharray={`${fakeHoldings * 2.827} ${100 * 2.827}`}
              />
              <circle
                cx="50"
                cy="50"
                r="45"
                fill="none"
                stroke="#3b82f6"
                strokeWidth="10"
                strokeDasharray={`${realHoldings * 2.827} ${100 * 2.827}`}
                strokeDashoffset={`-${fakeHoldings * 2.827}`}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[10px] sm:text-xs font-medium text-red-600 dark:text-red-400">
                Fake: {fakeHoldings}%
              </span>
              <span className="text-xs sm:text-sm font-bold text-blue-500 dark:text-blue-400">
                Real: {realHoldings}%
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 sm:mt-6 flex flex-wrap gap-2">
        <button className="px-3 sm:px-4 py-1.5 sm:py-2 bg-blue-100 dark:bg-blue-800 text-blue-500 dark:text-blue-400 rounded-lg font-medium text-xs sm:text-sm">
          Holdings
        </button>
        <button className="px-3 sm:px-4 py-1.5 sm:py-2 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-lg font-medium text-xs sm:text-sm hover:bg-gray-200 dark:hover:bg-gray-600">
          Watchlist
        </button>
      </div>
    </div>
  );
}
