"use client";

import { useState } from "react";
import type { StrategyListData, StrategyListItem } from "@/app/api/dashboard/strategy-list/route";

function formatKRW(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(1)}억`;
  if (abs >= 10_000) return `${sign}${Math.round(abs / 10_000).toLocaleString()}만`;
  return `${sign}${abs.toLocaleString("ko-KR")}`;
}

function fmtPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return <span className="text-xs text-gray-600">-</span>;
  const color =
    score >= 80 ? "text-emerald-400" :
    score >= 60 ? "text-blue-400" :
    score >= 40 ? "text-amber-400" :
    "text-red-400";
  return (
    <span className={`text-sm font-black tabular-nums font-outfit ${color}`}>
      {score.toFixed(0)}
    </span>
  );
}

export default function StrategyList({ initialData }: { initialData: StrategyListData }) {
  const [data] = useState<StrategyListData>(initialData);
  const loading = false;

  const strategies = data?.strategies ?? [];

  return (
    <div className="glass-card p-5 h-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
            전략 목록
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">계좌 연결 전략별 수익 현황</p>
        </div>
        <button className="text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors">
          전체 보기
        </button>
      </div>

      {/* 테이블 헤더 */}
      <div className="grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-2 px-2 mb-2">
        {["전략명", "점수", "평균 수익률", "총 수익금"].map((h) => (
          <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-600">
            {h}
          </span>
        ))}
      </div>

      {/* 구분선 */}
      <div className="border-t border-white/[0.05] mb-1" />

      {/* 로딩 */}
      {loading ? (
        <div className="space-y-1">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-11 bg-white/[0.03] rounded-xl animate-pulse"
            />
          ))}
        </div>
      ) : strategies.length === 0 ? (
        <div className="py-10 text-center">
          <p className="text-gray-500 text-sm">등록된 전략이 없습니다</p>
          <p className="text-gray-600 text-xs mt-1">전략을 생성하고 계좌에 연결하면 여기서 확인할 수 있습니다</p>
        </div>
      ) : (
        <div className="divide-y divide-white/[0.04] overflow-y-auto max-h-64 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
          {strategies.map((s) => (
            <div
              key={s.id}
              className="grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors cursor-pointer"
            >
              {/* 전략명 */}
              <div className="min-w-0">
                <p className="text-base font-bold text-white truncate">{s.name}</p>
                <p className="text-xs text-gray-600 mt-0.5">{s.accountCount}개 계좌</p>
              </div>

              {/* 점수 */}
              <div>
                <ScoreBadge score={s.aiScore} />
              </div>

              {/* 평균 수익률 */}
              <span className={`text-sm font-bold tabular-nums font-outfit ${s.avgReturnPct >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                {fmtPct(s.avgReturnPct)}
              </span>

              {/* 총 수익금 */}
              <span
                className={`text-base font-bold tabular-nums font-outfit ${
                  s.totalProfit >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"
                }`}
              >
                {formatKRW(s.totalProfit)}원
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
