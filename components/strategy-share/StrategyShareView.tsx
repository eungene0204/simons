"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Spinner } from "phosphor-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { t } from "@/lib/i18n";
import { useRegionHref } from "@/lib/geo/useRegion";
import { buildStrategySummaryFromDsl, buildStrategySummaryGroups } from "@/lib/strategy-summary";
import type { StrategyDSL } from "@/types/strategy";
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
  // 전략 조건 — 계좌 상세 화면과 같은 라벨 규칙(유니버스·진입신호·청산신호·리스트·리스크 관리).
  const groups = buildStrategySummaryGroups(
    buildStrategySummaryFromDsl(strategy.settings as StrategyDSL | null)
  );
  // ETF 테마("반도체")는 유니버스 라벨이 "ETF"로만 나오므로 설정의 테마를 유니버스 칩에 덧붙인다.
  const etfTheme = typeof strategy.settings?.etf_theme === "string" ? strategy.settings.etf_theme : null;
  if (etfTheme) {
    const label = /[a-z]/i.test(etfTheme) ? etfTheme : t("{0} 테마", etfTheme);
    const universeGroup = groups.find((group) => group.chips.length > 0 && group.label === t("유니버스"));
    if (universeGroup && !universeGroup.chips.includes(label)) universeGroup.chips = [...universeGroup.chips, label];
    else if (!universeGroup) groups.unshift({ label: t("유니버스"), chips: [label] });
  }
  return (
    <article
      className="flex h-[32rem] flex-col rounded-2xl bg-[var(--card-bg)] p-5"
      data-testid="shared-strategy-card"
    >
      <h2 className="truncate text-sm font-black text-white">{strategy.name}</h2>
      {strategy.description && (
        <p className="mt-2 line-clamp-2 text-xs font-bold leading-relaxed text-gray-400">{strategy.description}</p>
      )}

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

      <div
        className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto pt-1"
        data-testid="shared-strategy-conditions"
      >
        {groups.length === 0 ? (
          <p className="text-xs font-bold text-gray-400">{t("표시할 전략 조건이 없습니다.")}</p>
        ) : (
          groups.map((group) => (
            <div key={group.label}>
              <p className="text-[11px] font-bold text-[var(--text-label)]">{group.label}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {group.chips.map((chip, index) => (
                  <span
                    key={`${chip}-${index}`}
                    className="inline-flex items-center rounded-md bg-white/[0.06] px-2 py-1 text-xs font-bold text-gray-300"
                  >
                    {chip}
                  </span>
                ))}
              </div>
            </div>
          ))
        )}
      </div>

      {strategy.accounts.length > 0 && (
        <ul className="mt-4 max-h-24 overflow-y-auto">
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
      <div className="w-full min-w-0">
        <div>
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
                {t("'내 전략' 메뉴에서 전략을 공개로 전환하면 여기에 표시됩니다.")}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">
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
