"use client";

import { VirtualMarketLog } from "@/lib/virtual-market";

interface SignalLogProps {
  logs: VirtualMarketLog[];
  symbolNameMap?: Record<string, string>;
}

export default function SignalLog({ logs, symbolNameMap = {} }: SignalLogProps) {
  const formatPrice = (price: number) =>
    new Intl.NumberFormat("ko-KR").format(price);

  if (logs.length === 0) {
    return (
      <div className="p-4 text-center text-sm text-gray-400">
        아직 시그널이 발생하지 않았습니다.
      </div>
    );
  }

  return (
    <div className="space-y-1.5 max-h-64 overflow-y-auto">
      {logs.map((log) => (
        <div
          key={log.id}
          className="flex items-center justify-between px-3 py-2 bg-[#111111] rounded-lg text-sm"
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {/* 시그널 타입 배지 */}
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0 ${
                log.signalType === "entry"
                  ? "bg-blue-900/40 text-blue-400"
                  : "bg-red-900/40 text-red-400"
              }`}
            >
              {log.signalType === "entry" ? "진입" : "청산"}
            </span>

            {/* 종목 + 날짜 */}
            <div className="min-w-0">
              <span className="font-medium text-white">
                {log.stockName ?? symbolNameMap[log.symbol] ?? log.symbol}
              </span>
              <span className="text-gray-500 ml-1.5 text-xs">
                {log.virtualDate}
              </span>
              {log.reason && (
                <p className="text-xs text-gray-400 truncate">
                  {log.reason}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0 ml-2">
            {/* 가격 */}
            <span className="text-gray-300 text-xs">
              {formatPrice(log.price)}원
            </span>

            {/* 실행 상태 배지 */}
            <span
              className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                log.action === "auto_executed"
                  ? "bg-green-900/40 text-green-400"
                  : log.action === "notified"
                  ? "bg-yellow-900/40 text-yellow-400"
                  : "bg-[#252525] text-gray-400"
              }`}
            >
              {log.action === "auto_executed"
                ? "체결"
                : log.action === "notified"
                ? "알림"
                : "스킵"}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
