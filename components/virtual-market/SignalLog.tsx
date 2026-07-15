"use client";

import { VirtualMarketLog } from "@/lib/virtual-market";

const SIGNAL_STALE_DAYS = 3;

interface SignalLogProps {
  logs: VirtualMarketLog[];
  symbolNameMap?: Record<string, string>;
  accountCreatedAt?: string;
  onStrategyReplace?: () => void;
}

export default function SignalLog({
  logs,
  symbolNameMap = {},
  accountCreatedAt,
  onStrategyReplace,
}: SignalLogProps) {
  const formatPrice = (price: number) =>
    new Intl.NumberFormat("ko-KR").format(price);

  if (logs.length === 0) {
    const daysSinceStart = accountCreatedAt
      ? Math.floor((Date.now() - new Date(accountCreatedAt).getTime()) / 86_400_000)
      : 0;
    const isStale = daysSinceStart >= SIGNAL_STALE_DAYS;

    if (isStale) {
      return (
        <div className="py-8 text-center">
          <p className="text-sm font-bold text-gray-500">
            최근 {daysSinceStart}일간 이 전략의 매매 신호가 발생하지 않았습니다.
          </p>
          <p className="text-xs font-bold text-gray-600 mt-1">
            설정한 조건에 해당하는 종목이 나타나지 않았습니다.
          </p>
          {onStrategyReplace && (
            <button
              onClick={onStrategyReplace}
              className="mt-3 text-xs font-bold text-[var(--main-green)] hover:text-[var(--main-green)]/80 transition-colors"
            >
              다른 전략으로 교체하기
            </button>
          )}
        </div>
      );
    }

    return (
      <div className="py-8 text-center">
        <p className="text-sm font-bold text-gray-500">아직 시그널이 발생하지 않았습니다.</p>
        <p className="text-xs font-bold text-gray-600 mt-1">전략 시그널이 감지되면 여기에 표시됩니다.</p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-white/[0.04]">
      {logs.map((log) => (
        <div
          key={log.id}
          className="flex items-center justify-between px-2 py-2 hover:bg-white/[0.02] transition-colors"
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div className="min-w-0">
              <p className="text-xs font-bold text-white truncate leading-tight">
                {log.stockName ?? symbolNameMap[log.symbol] ?? log.symbol}
              </p>
              <p className="text-[10px] text-gray-500 leading-tight">
                {log.date}{log.reason ? ` · ${log.reason}` : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
            <span className="text-[10px] font-bold text-gray-400 tabular-nums">
              {formatPrice(log.price)}원
            </span>
            {log.action === "skipped" ? (
              <span className="inline-flex items-center rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-bold text-gray-500">
                스킵
              </span>
            ) : (
              <span className={`inline-flex items-center rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-bold ${
                log.signalType === "entry" ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"
              }`}>
                {log.signalType === "entry" ? "매수" : "매도"}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
