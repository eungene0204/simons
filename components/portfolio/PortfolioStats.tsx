"use client";

type StatItem = {
  label: string;
  value: string;
};

export default function PortfolioStats() {
  const stats: StatItem[] = [
    { label: "Days Investing", value: "5,609" },
    { label: "Trade Frequency", value: "494 /mo" },
    { label: "Inactive Holdings", value: "1,123" },
    { label: "Fake Holdings", value: "297" },
    { label: "Overactive Holdings", value: "1,222" },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="bg-yellow-50 dark:bg-yellow-900/20 p-3 sm:p-4 rounded-lg border border-yellow-200 dark:border-yellow-800"
        >
          <p className="text-[10px] sm:text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {stat.label}
          </p>
          <p className="text-base sm:text-lg font-bold text-gray-900 dark:text-white">
            {stat.value}
          </p>
        </div>
      ))}
    </div>
  );
}
