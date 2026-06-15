"use client";

import { useState } from "react";
import { Flask } from "phosphor-react";
import type { DashboardBacktestRecord } from "@/types/dashboard";

function fmtPct(v: number): string {
  if (v === 0) return "0.0%";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function fmtDate(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

const UNIVERSE_COLOR: Record<string, string> = {
  KOSPI: "bg-sky-500/15 text-sky-400",
  KOSPI200: "bg-indigo-500/15 text-indigo-400",
  KOSDAQ: "bg-purple-500/15 text-purple-400",
};

const UNIVERSE_LABEL: Record<string, string> = {
  kospi: "KOSPI",
  KOSPI: "KOSPI",
  kospi200: "KOSPI200",
  KOSPI200: "KOSPI200",
  "KOSPI 200": "KOSPI200",
  kosdaq: "KOSDAQ",
  KOSDAQ: "KOSDAQ",
};

function normalizeUniverse(raw: string): string | null {
  return UNIVERSE_LABEL[raw] ?? null;
}

export default function RecentBacktestList({ initialRecords }: { initialRecords: DashboardBacktestRecord[] }) {
  const [records] = useState<DashboardBacktestRecord[]>(initialRecords.slice(0, 8));
  const loading = false;

  return (
    <div className="flat-card p-5 h-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-base font-black uppercase tracking-widest text-gray-400 font-outfit">
            최근 백테스트
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">최근 8개 실행 결과</p>
        </div>
        <Flask size={20} className="text-gray-600" />
      </div>

      {/* 테이블 헤더 */}
      <div className="grid grid-cols-[minmax(0,1fr)_64px_72px_56px] gap-2 px-2 mb-2">
        {["전략명", "유니버스", "수익률", "날짜"].map((h) => (
          <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-600">
            {h}
          </span>
        ))}
      </div>
      <div className="border-t border-white/[0.05] mb-1" />

      {loading ? (
        <div className="space-y-1">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-10 bg-white/[0.03] rounded-xl animate-pulse" />
          ))}
        </div>
      ) : records.length === 0 ? (
        <div className="py-8 text-center">
          <p className="text-gray-500 text-sm">백테스트 기록이 없습니다</p>
          <p className="text-gray-600 text-xs mt-1">전략을 실행하면 여기에 표시됩니다</p>
        </div>
      ) : (
        <div className="divide-y divide-white/[0.04]">
          {records.map((r) => {
            const ret = r.metrics.totalReturn ?? 0;
            const retColor = ret === 0 ? "text-white" : ret > 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]";
            const universeLabel = normalizeUniverse(r.universe);
            const universeColor = universeLabel ? UNIVERSE_COLOR[universeLabel] : "";
            return (
              <div
                key={r.id}
                className="grid grid-cols-[minmax(0,1fr)_64px_72px_56px] gap-2 items-center px-2 py-2.5 hover:bg-white/[0.02] rounded-xl transition-colors"
              >
                {/* 전략명 */}
                <p className="text-sm font-bold text-white truncate">{r.strategyName}</p>

                {/* 유니버스 */}
                {universeLabel ? (
                  <span className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded-md text-center ${universeColor}`}>
                    {universeLabel}
                  </span>
                ) : (
                  <span />
                )}

                {/* 수익률 */}
                <div className={`flex items-center gap-0.5 ${retColor}`}>
                  <span className="text-xs font-black tabular-nums font-outfit">
                    {fmtPct(ret)}
                  </span>
                </div>

                {/* 날짜 */}
                <span className="text-[10px] text-gray-600 font-bold">{fmtDate(r.timestamp)}</span>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
}
