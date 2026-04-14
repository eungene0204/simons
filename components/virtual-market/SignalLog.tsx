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
    <div className="divide-y divide-white/[0.04]">
      {logs.map((log) => (
        <div
          key={log.id}
          className="flex items-center justify-between px-2 py-2 hover:bg-white/[0.02] transition-colors"
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span
              className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold flex-shrink-0 ${
                log.signalType === "entry"
                  ? "bg-white/[0.06] text-gray-300"
                  : "bg-white/[0.06] text-gray-300"
              }`}
            >
              {log.signalType === "entry" ? "진입" : "청산"}
            </span>
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
            <span className="inline-flex items-center rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-bold text-gray-400">
              {log.action === "auto_executed" ? "체결" : log.action === "notified" ? "알림" : "스킵"}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
