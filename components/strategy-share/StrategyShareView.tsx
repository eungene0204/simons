"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Spinner } from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getLocale, t } from "@/lib/i18n";
import { useRegionHref } from "@/lib/geo/useRegion";
import type { SharedStrategyCard } from "@/lib/server/sharedStrategies";

function formatReturn(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function ReturnBadge({ value }: { value: number }) {
  const isPositive = value >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-md px-2 py-0.5 text-xs font-bold ${
        isPositive
          ? "bg-[var(--main-red)]/10 text-[var(--main-red)]"
          : "bg-[var(--main-blue)]/10 text-[var(--main-blue)]"
      }`}
    >
      {formatReturn(value)}
      {isPositive ? <ArrowUpRight size={12} weight="bold" /> : <ArrowDownRight size={12} weight="bold" />}
    </span>
  );
}

function StrategyCard({ strategy }: { strategy: SharedStrategyCard }) {
  const regionHref = useRegionHref();
  return (
    <article className="flex flex-col border-r border-b border-white/[0.08] p-5" data-testid="shared-strategy-card">
      <h2 className="truncate text-sm font-black text-white">{strategy.name}</h2>
      <p className="mt-3 line-clamp-3 text-xs font-bold leading-relaxed text-gray-400">
        {strategy.description || t("전략 설명이 없습니다.")}
      </p>

      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-xs font-bold text-[var(--text-label)]">
          {strategy.accounts.length > 1 ? t("공개 계좌 평균 수익률") : t("공개 계좌 수익률")}
        </span>
        {strategy.avgReturnPct == null ? (
          <span className="text-xs font-bold text-gray-400">{t("공개된 운용 계좌가 없습니다")}</span>
        ) : (
          <ReturnBadge value={strategy.avgReturnPct} />
        )}
      </div>

      {strategy.accounts.length > 0 && (
        <ul className="mt-3 divide-y divide-white/[0.06] border-t border-white/[0.06]">
          {strategy.accounts.map((account) => (
            <li key={account.id}>
              <Link
                href={regionHref(`/shared/virtual-account/${account.id}`)}
                className="flex items-center justify-between gap-3 py-2 text-xs font-bold text-gray-300 transition-colors hover:text-white"
              >
                <span className="min-w-0 truncate">
                  {account.name}
                  {account.status === "CLOSED" && <span className="ml-1.5 text-gray-500">{t("(종료)")}</span>}
                </span>
                <span className={account.returnPct >= 0 ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}>
                  {formatReturn(account.returnPct)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-auto pt-4 text-[11px] font-bold text-gray-500">
        {t("최근 갱신 {0}", new Date(strategy.updatedAt).toLocaleDateString(getLocale()))}
      </p>
    </article>
  );
}

export default function StrategyShareView() {
  const [strategies, setStrategies] = useState<SharedStrategyCard[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    fetch("/api/shared/strategies", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load shared strategies");
        return response.json();
      })
      .then((data: { strategies?: SharedStrategyCard[] }) => {
        if (!ignore) setStrategies(Array.isArray(data.strategies) ? data.strategies : []);
      })
      .catch(() => {
        if (!ignore) setError(t("공유 전략을 불러오지 못했습니다."));
      })
      .finally(() => {
        if (!ignore) setIsLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <DashboardLayout userName="">
      <div className="w-full min-w-0 border border-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">
          <header className="p-5">
            <h1 className="font-serif text-2xl text-white">{t("전략공유")}</h1>
            <p className="mt-2 text-sm font-bold text-gray-400">
              {t("사용자가 공개한 전략과, 그 전략을 운용하는 공개 모의투자 계좌의 수익률입니다. 수익률 높은 순으로 정렬됩니다.")}
            </p>
            <p className="mt-1 text-xs font-bold text-[var(--text-label)]">
              {t("모의투자 시뮬레이션 결과이며 투자 권유가 아닙니다. 과거 수익률은 미래 수익을 보장하지 않습니다.")}
            </p>
          </header>

          {isLoading ? (
            <div className="flex flex-col items-center gap-3 py-16" data-testid="strategy-share-loading">
              <Spinner size={24} className="animate-spin text-gray-500 motion-reduce:animate-none" aria-hidden="true" />
              <p className="text-xs font-bold text-gray-400">{t("공유 전략을 불러오는 중입니다...")}</p>
            </div>
          ) : error ? (
            <div className="py-16 text-center">
              <p className="text-sm font-black text-white">{error}</p>
            </div>
          ) : strategies.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-sm font-black text-white">{t("아직 공개된 전략이 없습니다")}</p>
              <p className="mt-1 text-xs font-bold text-gray-400">
                {t("전략연구소의 '내 전략'에서 전략을 공개로 전환하면 여기에 표시됩니다.")}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
              {strategies.map((strategy) => (
                <StrategyCard key={strategy.key} strategy={strategy} />
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
