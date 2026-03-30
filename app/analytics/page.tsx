"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  ChartLineUp,
  Plus,
  TrendUp,
  TrendDown,
  Bank,
  CalendarBlank,
  ArrowRight,
} from "phosphor-react";
import type { StrategyListItem } from "@/app/api/dashboard/strategy-list/route";

const TYPE_STYLE: Record<string, { color: string; bg: string; border: string }> = {
  KOSPI: { color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  KOSDAQ: { color: "text-violet-400", bg: "bg-violet-500/10", border: "border-violet-500/20" },
  미국주식: { color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  기타: { color: "text-gray-400", bg: "bg-gray-500/10", border: "border-gray-500/20" },
};

function TypeBadge({ type }: { type: string }) {
  const style = TYPE_STYLE[type] ?? TYPE_STYLE["기타"];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-black ${style.bg} border ${style.border} ${style.color}`}>
      {type}
    </span>
  );
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

function StrategyLabContent() {
  const router = useRouter();
  const [strategies, setStrategies] = useState<StrategyListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/dashboard/strategy-list")
      .then((r) => r.json())
      .then((data) => setStrategies(data.strategies ?? []))
      .catch(() => setStrategies([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <DashboardLayout userName="">
      <div className="px-6 py-8 max-w-6xl mx-auto space-y-8">

        {/* 헤더 */}
        <div className="flex items-end justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <ChartLineUp size={22} className="text-blue-400" weight="fill" />
              <h1 className="text-xl font-black text-white tracking-tight">전략연구소</h1>
            </div>
            <p className="text-sm text-gray-500 ml-8">
              투자 전략을 설계하고 백테스트로 검증하세요
            </p>
          </div>

          <button
            onClick={() => router.push("/analytics/new")}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-sm font-black shadow-[0_0_16px_rgba(59,130,246,0.2)] hover:shadow-[0_0_24px_rgba(59,130,246,0.35)] transition-all"
          >
            <Plus size={16} weight="bold" />
            새 전략 만들기
          </button>
        </div>

        {/* 전략 목록 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-black text-white/70 tracking-tight">내 전략</h2>
            {!loading && (
              <span className="text-xs text-gray-600 font-bold">{strategies.length}개</span>
            )}
          </div>

          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-32 rounded-2xl bg-white/[0.03] border border-white/5 animate-pulse" />
              ))}
            </div>
          ) : strategies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 rounded-2xl border border-dashed border-white/10 bg-white/[0.02]">
              <ChartLineUp size={40} className="text-gray-700 mb-4" />
              <p className="text-sm font-bold text-gray-600">저장된 전략이 없습니다</p>
              <p className="text-xs text-gray-700 mt-1 mb-5">새 전략을 만들어 백테스트를 시작해보세요</p>
              <button
                onClick={() => router.push("/analytics/new")}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600/20 border border-blue-500/30 hover:bg-blue-600/30 text-blue-400 text-xs font-black transition-all"
              >
                <Plus size={13} weight="bold" />
                새 전략 만들기
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* 새 전략 만들기 카드 — 항상 첫 번째 */}
              <button
                onClick={() => router.push("/analytics/new")}
                className="group flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/10 hover:border-blue-500/40 bg-white/[0.01] hover:bg-blue-500/5 py-8 transition-all"
              >
                <div className="w-9 h-9 rounded-xl bg-white/5 group-hover:bg-blue-500/20 flex items-center justify-center transition-all">
                  <Plus size={18} className="text-gray-600 group-hover:text-blue-400 transition-colors" weight="bold" />
                </div>
                <div className="text-center">
                  <p className="text-xs font-black text-gray-600 group-hover:text-blue-400 transition-colors">새 전략 만들기</p>
                  <div className="flex items-center gap-0.5 justify-center mt-0.5">
                    <span className="text-[10px] text-gray-700 group-hover:text-blue-500/70 transition-colors">AI로 빠르게 설계</span>
                    <ArrowRight size={9} className="text-gray-700 group-hover:text-blue-500/70 transition-colors" />
                  </div>
                </div>
              </button>

              {strategies.map((s) => {
                const isPositive = s.avgReturnPct >= 0;
                return (
                  <button
                    key={s.id}
                    onClick={() => router.push(`/analytics/${s.id}`)}
                    className="group text-left rounded-2xl border border-white/5 hover:border-white/10 bg-white/[0.02] hover:bg-white/[0.04] p-4 transition-all space-y-3"
                  >
                    {/* 이름 + 타입 */}
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-black text-white group-hover:text-blue-300 transition-colors leading-snug line-clamp-2 flex-1">
                        {s.name}
                      </p>
                      <TypeBadge type={s.type} />
                    </div>

                    {/* 설명 */}
                    {s.description && (
                      <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">{s.description}</p>
                    )}

                    {/* 메트릭 */}
                    <div className="flex items-center justify-between pt-1 border-t border-white/5">
                      <div className="flex items-center gap-3">
                        {/* 수익률 */}
                        <div className="flex items-center gap-1">
                          {isPositive
                            ? <TrendUp size={13} className="text-emerald-400" weight="bold" />
                            : <TrendDown size={13} className="text-red-400" weight="bold" />
                          }
                          <span className={`text-xs font-black ${isPositive ? "text-emerald-400" : "text-red-400"}`}>
                            {isPositive ? "+" : ""}{s.avgReturnPct.toFixed(1)}%
                          </span>
                        </div>

                        {/* 계좌 수 */}
                        {s.accountCount > 0 && (
                          <div className="flex items-center gap-1">
                            <Bank size={11} className="text-gray-600" />
                            <span className="text-[11px] text-gray-600 font-bold">{s.accountCount}개 계좌</span>
                          </div>
                        )}
                      </div>

                      {/* 날짜 */}
                      <div className="flex items-center gap-1">
                        <CalendarBlank size={10} className="text-gray-700" />
                        <span className="text-[10px] text-gray-700 font-bold">{formatDate(s.createdAt)}</span>
                      </div>
                    </div>
                  </button>
                );
              })}

            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}

export default function StrategyLabPage() {
  return (
    <Suspense>
      <StrategyLabContent />
    </Suspense>
  );
}
