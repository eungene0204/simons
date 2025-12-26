"use client";

type DistributionItem = {
  type: string;
  percentage: number;
  count: number;
  color: string;
  icon: string;
};

export default function HoldingsDistribution() {
  const distributions: DistributionItem[] = [
    {
      type: "Overactives",
      percentage: 21.79,
      count: 1222,
      color: "text-blue-500",
      icon: "⭐",
    },
    {
      type: "Inactives",
      percentage: 20.03,
      count: 1123,
      color: "text-gray-600",
      icon: "😐",
    },
    {
      type: "Fake/Spam",
      percentage: 5.3,
      count: 297,
      color: "text-red-600",
      icon: "❌",
    },
    {
      type: "Eggheads",
      percentage: 1.8,
      count: 101,
      color: "text-yellow-600",
      icon: "🥚",
    },
  ];

  // Calculate angles for pie chart
  let currentAngle = 0;
  const totalPercentage = distributions.reduce(
    (sum, item) => sum + item.percentage,
    0
  );

  return (
    <div className="bg-white dark:bg-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
      <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-white mb-3 sm:mb-4">
        Demo Holdings Stats
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        {/* Left: Pie Chart */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
          <div className="relative w-32 h-32 sm:w-40 sm:h-40">
            <svg viewBox="0 0 100 100" className="transform -rotate-90 w-full h-full">
              {distributions.map((item, index) => {
                const angle = (item.percentage / totalPercentage) * 360;
                const startAngle = currentAngle;
                currentAngle += angle;
                const endAngle = currentAngle;

                const x1 =
                  50 + 45 * Math.cos((startAngle * Math.PI) / 180);
                const y1 =
                  50 + 45 * Math.sin((startAngle * Math.PI) / 180);
                const x2 = 50 + 45 * Math.cos((endAngle * Math.PI) / 180);
                const y2 = 50 + 45 * Math.sin((endAngle * Math.PI) / 180);

                const largeArc = angle > 180 ? 1 : 0;

                const pathData = [
                  `M 50 50`,
                  `L ${x1} ${y1}`,
                  `A 45 45 0 ${largeArc} 1 ${x2} ${y2}`,
                  `Z`,
                ].join(" ");

                const colors = {
                  "Overactives": "#22c55e",
                  "Inactives": "#6b7280",
                  "Fake/Spam": "#ef4444",
                  "Eggheads": "#eab308",
                };

                return (
                  <path
                    key={index}
                    d={pathData}
                    fill={colors[item.type as keyof typeof colors]}
                    opacity={0.8}
                  />
                );
              })}
            </svg>
          </div>
          <div className="space-y-1.5 sm:space-y-2">
            {distributions.map((item) => (
              <div key={item.type} className="flex items-center gap-2">
                <span className="text-sm sm:text-base">{item.icon}</span>
                <span className={`text-xs sm:text-sm font-medium ${item.color}`}>
                  {item.type}: {item.percentage}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: List */}
        <div className="space-y-2 sm:space-y-3">
          {distributions.map((item) => (
            <div
              key={item.type}
              className="flex justify-between items-center p-2 sm:p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded"
            >
              <div>
                <p className="text-xs sm:text-sm font-medium text-gray-900 dark:text-white">
                  {item.count} {item.type}
                </p>
                <p className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">
                  {item.type === "Overactives"
                    ? "High Volatility"
                    : item.type === "Inactives"
                    ? "Low Engagement"
                    : item.type === "Fake/Spam"
                    ? "Suspicious"
                    : "New Accounts"}
                </p>
              </div>
              <a
                href="#"
                className="text-xs sm:text-sm text-blue-500 dark:text-blue-400 hover:underline"
              >
                List all &gt;
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
