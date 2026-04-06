"use client";

import { useState } from "react";
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
  Trash,
  Warning,
  X,
} from "phosphor-react";
import type { StrategyListItem } from "@/app/api/dashboard/strategy-list/route";

function formatDate(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

function DeleteConfirmModal({
  strategy,
  onConfirm,
  onCancel,
  isDeleting,
}: {
  strategy: StrategyListItem;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative w-full max-w-sm glass-card p-6 space-y-5">
        {/* 닫기 */}
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 rounded-lg text-gray-600 hover:text-gray-400 transition-colors duration-200"
        >
          <X size={16} weight="bold" />
        </button>

        {/* 아이콘 + 제목 */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white/[0.05] flex items-center justify-center shrink-0">
            <Trash size={18} className="text-gray-400" weight="fill" />
          </div>
          <div>
            <h3 className="text-base font-black text-white">전략 삭제</h3>
            <p className="text-xs font-bold text-gray-500 mt-0.5 line-clamp-1">{strategy.name}</p>
          </div>
        </div>

        {/* 본문 */}
        <p className="text-xs font-bold text-gray-500 leading-relaxed">
          이 전략을 영구적으로 삭제합니다. 백테스트 결과도 함께 삭제되며 복구할 수 없습니다.
        </p>

        {/* 자동매매 경고 */}
        {strategy.autoTradingCount > 0 && (
          <div className="flex items-start gap-3 rounded-xl border border-[var(--main-blue)]/30 px-4 py-3">
            <Warning size={14} className="text-gray-500 mt-0.5 shrink-0" weight="fill" />
            <p className="text-xs font-bold text-gray-300 leading-relaxed">
              이 전략을 사용하는{" "}
              <span className="font-black text-white">{strategy.autoTradingCount}개 계좌</span>의
              자동매매가 즉시 중지됩니다.
            </p>
          </div>
        )}

        {/* 버튼 */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={isDeleting}
            className="flex-1 py-2.5 rounded-xl border border-white/[0.08] text-xs font-bold text-gray-500 hover:text-gray-300 hover:border-white/[0.15] transition-all duration-200 disabled:opacity-50"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="flex-1 py-2.5 rounded-xl bg-white/[0.08] border border-white/[0.12] hover:bg-white/[0.12] text-xs font-black text-gray-300 hover:text-white transition-all duration-200 disabled:opacity-50"
          >
            {isDeleting ? "삭제 중..." : "삭제"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function StrategyLabClient({ strategies: initial }: { strategies: StrategyListItem[] }) {
  const router = useRouter();
  const [strategies, setStrategies] = useState(initial);
  const [deleteTarget, setDeleteTarget] = useState<StrategyListItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  function openDeleteModal(e: React.MouseEvent, strategy: StrategyListItem) {
    e.stopPropagation();
    setDeleteTarget(strategy);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      const res = await fetch(`/api/strategy/${deleteTarget.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Delete failed");
      setStrategies((prev) => prev.filter((s) => s.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch {
      setDeleteTarget(null);
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <DashboardLayout userName="">
      <div className="p-4 md:p-5 lg:p-6 space-y-5 w-full min-w-0">

        {/* 헤더 */}
        <div className="flex items-end">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <ChartLineUp size={20} className="text-sky-400" weight="fill" />
              <h1 className="text-xl font-black text-white">전략연구소</h1>
            </div>
            <p className="text-xs font-bold text-gray-500 ml-7">
              투자 전략을 설계하고 백테스트로 검증하세요
            </p>
          </div>
        </div>

        {/* 전략 목록 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">내 전략</span>
            <span className="text-xs font-bold text-gray-600 tabular-nums">{strategies.length}개</span>
          </div>

          {strategies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 glass-card">
              <ChartLineUp size={36} className="text-gray-700 mb-4" />
              <p className="text-sm font-bold text-gray-600">저장된 전략이 없습니다</p>
              <p className="text-xs font-bold text-gray-700 mt-1 mb-5">새 전략을 만들어 백테스트를 시작해보세요</p>
              <button
                onClick={() => router.push("/analytics/new")}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-sky-500/10 border border-sky-500/20 hover:bg-sky-500/15 text-sky-400 text-xs font-black transition-all duration-200"
              >
                <Plus size={13} weight="bold" />
                새 전략 만들기
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* 새 전략 만들기 카드 */}
              <button
                onClick={() => router.push("/analytics/new")}
                className="group relative overflow-hidden flex flex-col items-center justify-center gap-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] hover:border-white/[0.12] py-8 transition-all duration-300"
              >
                <span
                  aria-hidden
                  className="pointer-events-none absolute -top-8 -left-8 w-40 h-40 rounded-full opacity-0 group-hover:opacity-40 blur-3xl transition-opacity duration-700"
                  style={{ background: "radial-gradient(circle, #3b82f6 0%, #6366f1 60%, transparent 100%)" }}
                />
                <span
                  aria-hidden
                  className="pointer-events-none absolute -bottom-8 -right-8 w-36 h-36 rounded-full opacity-0 group-hover:opacity-30 blur-3xl transition-opacity duration-700 delay-75"
                  style={{ background: "radial-gradient(circle, #818cf8 0%, #38bdf8 60%, transparent 100%)" }}
                />
                <span
                  aria-hidden
                  className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-16 rounded-full opacity-0 group-hover:opacity-20 blur-2xl transition-opacity duration-700 delay-150"
                  style={{ background: "radial-gradient(ellipse, #60a5fa 0%, #a78bfa 100%)" }}
                />
                <div className="relative z-10 w-9 h-9 rounded-xl bg-white/[0.05] flex items-center justify-center">
                  <Plus size={16} className="text-white" weight="bold" />
                </div>
                <div className="relative z-10 text-center">
                  <p className="text-xs font-black text-white">새 전략 만들기</p>
                  <div className="flex items-center gap-0.5 justify-center mt-0.5">
                    <span className="text-[10px] font-bold text-gray-500">AI로 빠르게 설계</span>
                    <ArrowRight size={9} className="text-gray-500" />
                  </div>
                </div>
              </button>

              {strategies.map((s) => {
                const isPositive = s.avgReturnPct >= 0;
                return (
                  <div
                    key={s.id}
                    onClick={() => router.push(`/analytics/${s.id}`)}
                    className="group glass-card p-4 space-y-3 cursor-pointer"
                  >
                    {/* 이름 + 삭제 버튼 */}
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-black text-white group-hover:text-sky-300 transition-colors duration-200 leading-snug line-clamp-2 flex-1">
                        {s.name}
                      </p>
                      <button
                        onClick={(e) => openDeleteModal(e, s)}
                        className="shrink-0 p-1 rounded-lg text-gray-700 hover:text-[var(--main-blue)] hover:bg-[var(--main-blue)]/10 transition-all duration-200 opacity-0 group-hover:opacity-100"
                      >
                        <Trash size={13} weight="bold" />
                      </button>
                    </div>

                    {/* 설명 */}
                    {s.description && (
                      <p className="text-xs font-bold text-gray-500 leading-relaxed line-clamp-2">{s.description}</p>
                    )}

                    {/* 메트릭 */}
                    <div className="flex items-center justify-between pt-1 border-t border-white/[0.05]">
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-1">
                          {isPositive
                            ? <TrendUp size={12} className="text-[var(--main-red)]" weight="bold" />
                            : <TrendDown size={12} className="text-[var(--main-blue)]" weight="bold" />
                          }
                          <span className={`text-sm font-black tabular-nums ${isPositive ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
                            {isPositive ? "+" : ""}{s.avgReturnPct.toFixed(1)}%
                          </span>
                        </div>

                        {s.accountCount > 0 && (
                          <div className="flex items-center gap-1">
                            <Bank size={10} className="text-gray-600" />
                            <span className="text-[10px] font-bold text-gray-600 tabular-nums">{s.accountCount}개 계좌</span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-1">
                        <CalendarBlank size={10} className="text-gray-600" />
                        <span className="text-[10px] font-bold text-gray-600">{formatDate(s.createdAt)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* 삭제 확인 모달 */}
      {deleteTarget && (
        <DeleteConfirmModal
          strategy={deleteTarget}
          onConfirm={confirmDelete}
          onCancel={() => !isDeleting && setDeleteTarget(null)}
          isDeleting={isDeleting}
        />
      )}
    </DashboardLayout>
  );
}
