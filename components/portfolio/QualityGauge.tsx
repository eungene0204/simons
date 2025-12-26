"use client";

type QualityGaugeProps = {
  score: number;
  title: string;
  subtitle: string;
};

export default function QualityGauge({
  score,
  title,
  subtitle,
}: QualityGaugeProps) {
  const getScoreColor = (score: number) => {
    if (score >= 60) return "text-blue-500";
    if (score >= 40) return "text-yellow-500";
    return "text-blue-400";
  };

  const getScoreLabel = (score: number) => {
    if (score >= 60) return "OUTSTANDING";
    if (score >= 40) return "SOLID";
    return "MODEST";
  };

  const getGaugeColor = (score: number) => {
    if (score >= 60) return "stroke-blue-60000";
    if (score >= 40) return "stroke-yellow-500";
    return "stroke-blue-60000";
  };

  // Calculate stroke-dasharray for the gauge
  const circumference = 2 * Math.PI * 90; // radius = 90
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="bg-white dark:bg-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
      <div className="text-center mb-4 sm:mb-6">
        <h2 className="text-lg sm:text-xl md:text-2xl font-bold text-gray-900 dark:text-white mb-1 sm:mb-2">
          {title}
        </h2>
        <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400">{subtitle}</p>
      </div>

      <div className="flex justify-center mb-4 sm:mb-6">
        <div className="relative w-[150px] h-[150px] sm:w-[180px] sm:h-[180px] md:w-[200px] md:h-[200px]">
          <svg
            width="100%"
            height="100%"
            viewBox="0 0 200 200"
            className="transform -rotate-90"
            preserveAspectRatio="xMidYMid meet"
          >
            {/* Background circle */}
            <circle
              cx="100"
              cy="100"
              r="90"
              fill="none"
              stroke="#e5e7eb"
              strokeWidth="12"
              className="dark:stroke-gray-600"
            />
            {/* Colored segments */}
            <circle
              cx="100"
              cy="100"
              r="90"
              fill="none"
              stroke="#3b82f6"
              strokeWidth="12"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * 0.4}
              className="stroke-blue-60000"
            />
            <circle
              cx="100"
              cy="100"
              r="90"
              fill="none"
              stroke="#eab308"
              strokeWidth="12"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * 0.2}
              className="stroke-yellow-500"
            />
            {/* Score circle */}
            <circle
              cx="100"
              cy="100"
              r="90"
              fill="none"
              stroke={score >= 60 ? "#2563eb" : score >= 40 ? "#eab308" : "#3b82f6"}
              strokeWidth="12"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              className={getGaugeColor(score)}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-3xl sm:text-4xl md:text-5xl font-bold ${getScoreColor(score)}`}>
              {score}
            </span>
            <span
              className={`text-xs sm:text-sm font-medium mt-1 ${getScoreColor(score)}`}
            >
              {getScoreLabel(score)}
            </span>
          </div>
        </div>
      </div>

      <div className="text-center">
        <p className="text-xs sm:text-sm font-medium text-gray-700 dark:text-gray-300">
          Portfolio Quality Score
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          Analyzed by 널스탁
        </p>
      </div>
    </div>
  );
}
