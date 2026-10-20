"use client";

import { useEffect, useState } from "react";
import { Globe, Lock, Spinner, X } from "phosphor-react";
import { getLocale, t } from "@/lib/i18n";
import { useRegionHref } from "@/lib/geo/useRegion";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  getCachedMyStrategies,
  refreshMyStrategiesCache,
  setCachedMyStrategies,
  type SavedStrategy,
} from "@/lib/my-strategies-cache";

// 내 전략(2026-10-21) — 전략연구소 탭에서 상단 메뉴 화면으로 옮겼다.
export default function MyStrategiesView() {
  const regionHref = useRegionHref();
  // 캐시가 있으면 로딩 없이 바로 그리고, 뒤에서 최신 목록으로 교체한다.
  const cachedStrategies = getCachedMyStrategies();
  const [myStrategies, setMyStrategiesState] = useState<SavedStrategy[]>(cachedStrategies ?? []);
  const [isLoadingStrategies, setIsLoadingStrategies] = useState(!cachedStrategies);
  const [strategiesError, setStrategiesError] = useState<string | null>(null);
  const [deletingStrategyIds, setDeletingStrategyIds] = useState<Set<string>>(() => new Set());
  const [updatingVisibilityIds, setUpdatingVisibilityIds] = useState<Set<string>>(() => new Set());

  // 화면 상태와 캐시를 함께 바꾼다 — 삭제·공개 전환이 캐시에서 되살아나지 않게.
  const setMyStrategies = (updater: (prev: SavedStrategy[]) => SavedStrategy[]) => {
    setMyStrategiesState((prev) => {
      const next = updater(prev);
      setCachedMyStrategies(next);
      return next;
    });
  };

  useEffect(() => {
    let ignore = false;
    refreshMyStrategiesCache()
      .then((strategies) => {
        if (ignore) return;
        setMyStrategiesState(strategies);
        setStrategiesError(null);
      })
      .catch(() => {
        // 캐시로 이미 그린 목록은 그대로 둔다 — 새로고침 실패로 화면을 비우지 않는다.
        if (ignore || getCachedMyStrategies()) return;
        setStrategiesError(t("전략 목록을 불러오지 못했습니다."));
      })
      .finally(() => {
        if (!ignore) {
          setIsLoadingStrategies(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  const handleDeleteStrategy = async (strategyId: string) => {
    setDeletingStrategyIds((prev) => {
      const next = new Set(prev);
      next.add(strategyId);
      return next;
    });

    try {
      const response = await fetch(`/api/strategy/${strategyId}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Failed to delete strategy");
      }
      setMyStrategies((prev) => prev.filter((strategy) => strategy.id !== strategyId));
    } catch (error) {
      console.error("Failed to delete strategy:", error);
    } finally {
      setDeletingStrategyIds((prev) => {
        const next = new Set(prev);
        next.delete(strategyId);
        return next;
      });
    }
  };

  // 공개 전환(2026-10-20) — 공개 전략은 '전략공유' 화면에 카드로 실린다.
  const handleToggleStrategyVisibility = async (strategy: SavedStrategy) => {
    const nextPublic = !strategy.isPublic;
    setUpdatingVisibilityIds((prev) => new Set(prev).add(strategy.id));
    try {
      const response = await fetch(`/api/strategy/${strategy.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isPublic: nextPublic }),
      });
      if (!response.ok) {
        throw new Error("Failed to update strategy visibility");
      }
      setMyStrategies((prev) =>
        prev.map((item) => (item.id === strategy.id ? { ...item, isPublic: nextPublic } : item))
      );
    } catch (error) {
      console.error("Failed to update strategy visibility:", error);
    } finally {
      setUpdatingVisibilityIds((prev) => {
        const next = new Set(prev);
        next.delete(strategy.id);
        return next;
      });
    }
  };

  return (
    <DashboardLayout userName="">
      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">
          <header className="p-5">
            <h1 className="font-serif text-2xl text-white">{t("내 전략")}</h1>
          </header>
          <div className="p-5" data-testid="strategy-my-content">
              {isLoadingStrategies ? (
                <div
                  className="flex flex-col items-center justify-center gap-3 py-10"
                  role="status"
                  aria-live="polite"
                  data-testid="strategy-my-loading"
                >
                  <Spinner
                    size={24}
                    className="animate-spin text-gray-500 motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                  <p className="text-xs font-bold text-gray-500">{t("전략 목록을 불러오는 중입니다...")}</p>
                </div>
              ) : strategiesError ? (
                <div className="py-8 text-center">
                  <p className="text-sm font-black text-white">{t("전략 목록을 불러올 수 없습니다")}</p>
                  <p className="mt-1 text-xs font-bold text-gray-500">{strategiesError}</p>
                </div>
              ) : myStrategies.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-sm font-black text-white">{t("아직 저장된 전략이 없습니다")}</p>
                  <p className="mt-1 text-xs font-bold text-gray-500">{t("전략을 생성하고 저장하면 여기에서 확인할 수 있습니다.")}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  {myStrategies.map((strategy) => {
                    const isDeleting = deletingStrategyIds.has(strategy.id);
                    const isUpdatingVisibility = updatingVisibilityIds.has(strategy.id);
                    return (
                      <div key={strategy.id} className="relative group">
                        <a
                          href={regionHref(`/analytics/${strategy.id}`)}
                          className="flex h-36 flex-col rounded-2xl border border-white/[0.05] bg-[#121212] px-4 py-4 pr-14 transition-all duration-200 hover:border-white/[0.12] hover:bg-[#171717]"
                        >
                          <div className="flex items-start justify-between gap-3 pr-14">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-black text-white/85 group-hover:text-white">{strategy.name}</p>
                            </div>
                          </div>
                          <p className="mt-3 line-clamp-2 min-h-[2.5rem] text-xs font-bold leading-relaxed text-gray-400">
                            {strategy.description || t("저장된 전략 상세 결과로 이동합니다.")}
                          </p>
                          <div className="mt-auto flex items-center justify-between pt-3 text-[10px] font-black uppercase tracking-widest text-gray-600">
                            <span>{t("{0}개 계좌 연결", strategy.accountCount)}</span>
                            <span>{new Date(strategy.createdAt).toLocaleDateString(getLocale())}</span>
                          </div>
                        </a>
                        <button
                          type="button"
                          onClick={() => void handleDeleteStrategy(strategy.id)}
                          disabled={isDeleting}
                          aria-label={t("{0} 전략 삭제", strategy.name)}
                          className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-md bg-white/[0.06] text-gray-500 transition-colors hover:bg-white/[0.10] hover:text-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <X size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleToggleStrategyVisibility(strategy)}
                          disabled={isUpdatingVisibility}
                          aria-pressed={strategy.isPublic === true}
                          title={t("공개하면 전략공유 화면에 표시됩니다.")}
                          className={`absolute right-11 top-3 inline-flex h-6 items-center gap-1 rounded-md border px-2 text-[10px] font-black transition-colors duration-200 ${
                            strategy.isPublic
                              ? "border-sky-400/25 bg-sky-500/10 text-sky-300"
                              : "border-white/[0.08] bg-white/[0.03] text-gray-500 hover:border-white/[0.16] hover:text-gray-300"
                          } disabled:cursor-not-allowed disabled:opacity-60`}
                        >
                          {strategy.isPublic ? <Globe size={10} weight="bold" /> : <Lock size={10} weight="bold" />}
                          {strategy.isPublic ? t("공개") : t("비공개")}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
