"use client";

interface PriceRowProps {
  price: number;
  changePct?: number;
  side: "ask" | "bid";
  isCurrent?: boolean;
  isPulsing?: boolean;
  onPriceSelect?: (price: number) => void;
  formatPrice: (price: number) => string;
}

export function PriceRow({
  price,
  changePct,
  side,
  isCurrent,
  isPulsing,
  onPriceSelect,
  formatPrice,
}: PriceRowProps) {
  const tone = side === "ask"
    ? { text: "text-blue-400", bar: "bg-blue-600/30", border: "border-blue-500" }
    : { text: "text-red-400", bar: "bg-red-500/30", border: "border-red-400" };

  // 현재가 색상 결정 (상승: 빨강, 하락: 파랑, 보합: 회색)
  const getCurrentPriceStyle = () => {
    if (!isCurrent || changePct === undefined) return "";

    return `border-2 border-white bg-transparent rounded-lg ${isPulsing ? "animate-pulse" : ""}`;
  };

  const currentPriceColor = isCurrent && changePct !== undefined
    ? changePct > 0
      ? "text-red-400"
      : changePct < 0
      ? "text-blue-400"
      : "text-gray-400"
    : tone.text;

  return (
    <button
      onClick={() => onPriceSelect?.(price)}
      role="row"
      aria-current={isCurrent ? "true" : undefined}
      className={[
        "w-full grid grid-cols-[1fr_auto] items-center gap-3 px-3 py-2 rounded-md",
        "transition-all duration-200 tabular-nums tracking-tighter",
        "hover:bg-gray-50 dark:hover:bg-gray-700",
        isCurrent ? getCurrentPriceStyle() : "",
      ].join(" ")}
      style={isPulsing ? { animationDuration: "200ms" } : undefined}
    >
      <span className={`${currentPriceColor} text-sm tracking-tighter tabular-nums`}>
        {formatPrice(price)}
      </span>
      {typeof changePct === "number" && (
        <span className={`text-sm tabular-nums tracking-tighter ${
          changePct >= 0 ? "text-red-400" : "text-blue-400"
        }`}>
          {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
        </span>
      )}
    </button>
  );
}
