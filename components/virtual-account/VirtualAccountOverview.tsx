"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, Robot, X } from "phosphor-react";
import { StrategyWaveBackground } from "@/components/strategy/StrategyWaveBackground";
import CreateAccountModal from "@/components/ui/CreateAccountModal";
import { createAccount } from "@/lib/portfolio";
import type { VirtualAccount } from "@/types/portfolio";
import {
  getCachedVirtualAccounts,
  refreshVirtualAccountOverviewCache,
} from "./virtualAccountOverviewCache";

const formatPrice = (value: number) =>
  new Intl.NumberFormat("ko-KR").format(Math.round(value));

const formatSignedPercent = (value: number) =>
  `${value > 0 ? "+" : value < 0 ? "-" : ""}${Math.abs(value).toFixed(2)}%`;

export default function VirtualAccountOverview() {
  const initialAccounts = getCachedVirtualAccounts();
  const [accounts, setAccounts] = useState<VirtualAccount[]>(initialAccounts ?? []);
  const [loading, setLoading] = useState(!initialAccounts);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const loadAccounts = async (options?: { showLoading?: boolean; force?: boolean }) => {
    const shouldShowLoading = options?.showLoading ?? !getCachedVirtualAccounts();
    if (shouldShowLoading) setLoading(true);
    const nextAccounts = await refreshVirtualAccountOverviewCache({
      force: options?.force,
    });
    setAccounts(nextAccounts);
    setLoading(false);
  };

  useEffect(() => {
    let isMounted = true;
    const cachedAccounts = getCachedVirtualAccounts();

    if (cachedAccounts) {
      setAccounts(cachedAccounts);
      setLoading(false);
    }

    refreshVirtualAccountOverviewCache()
      .then((nextAccounts) => {
        if (!isMounted) return;
        setAccounts(nextAccounts);
        setLoading(false);
      })
      .catch(() => {
        if (!isMounted) return;
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
    // Initial fetch only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateAccount = async (
    name: string,
    amount: number,
    strategyId?: string,
    strategyName?: string,
    tradingMode?: "auto" | "manual"
  ) => {
    await createAccount(name, amount, strategyId, strategyName, tradingMode);
    await loadAccounts({ showLoading: false, force: true });
  };

  return (
    <>
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))] px-2 pb-2 md:px-3 md:pb-3">
        {loading ? (
          <div className="border border-white/[0.08]">
            <div className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center">
              <p className="text-sm font-bold text-gray-500">계좌를 불러오는 중입니다.</p>
            </div>
          </div>
        ) : accounts.length === 0 ? (
          <div className="relative flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] flex-col items-center justify-center gap-6 overflow-hidden px-5 py-8 text-center">
            <StrategyWaveBackground />
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(15,15,15,0.18)_0%,rgba(15,15,15,0.72)_72%)]" />
            <p className="relative z-10 max-w-4xl text-4xl font-black leading-tight text-white md:text-6xl">
              가상계좌를 만들고
              <br />
              전략을 시뮬레이션 해보세요
            </p>
            <div className="relative z-10 mt-4">
              <div className="pointer-events-none absolute -inset-x-8 -inset-y-4 bg-[radial-gradient(ellipse_at_center,rgba(55,122,244,0.28)_0%,rgba(34,197,94,0.12)_38%,rgba(15,15,15,0)_72%)] blur-2xl" />
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(true)}
                className="relative rounded-lg border border-white/[0.12] bg-[#111111] px-7 py-4 text-base font-black text-white transition-colors hover:bg-[#181818]"
              >
                가상계좌 만들기
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 p-3 sm:grid-cols-2 xl:grid-cols-3">
            <button
              type="button"
              onClick={() => setIsCreateModalOpen(true)}
              className="relative flex min-h-[252px] max-w-lg flex-col items-center justify-center overflow-hidden rounded-lg border border-white/[0.08] bg-[#111111] p-4 text-center transition-colors hover:bg-[#151515]"
            >
              <StrategyWaveBackground />
              <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(17,17,17,0.24)_0%,rgba(17,17,17,0.72)_76%)]" />
              <span className="relative text-xl font-black tracking-tight text-white">
                가상계좌 추가하기
              </span>
              <span className="relative mt-3 max-w-56 text-sm font-bold leading-relaxed text-gray-500">
                새 가상계좌를 추가해서
                <br />
                전략을 시뮬레이션 하세요
              </span>
            </button>
            {accounts.map((account) => {
              const profit = account.totalValue - account.initialAmount;
              const profitPercent =
                account.initialAmount > 0
                  ? (profit / account.initialAmount) * 100
                  : 0;
              const isPositive = profit > 0;
              const isNegative = profit < 0;

              return (
                <Link
                  key={account.id}
                  href={`/virtual-account/${account.id}`}
                  className="group max-w-lg rounded-lg border border-white/[0.08] bg-[#111111] p-4 transition-colors hover:bg-[#151515]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate text-lg font-black tracking-tight text-white">
                        {account.name}
                      </h2>
                      <p className="mt-1 truncate text-xs font-bold text-gray-500">
                        {account.strategyName || "전략 미연결"}
                      </p>
                    </div>
                    <span
                      aria-label="계좌 카드 닫기 배지"
                      className="inline-flex shrink-0 items-center justify-center rounded-md bg-white/[0.06] p-2 text-gray-500 transition-colors hover:bg-[var(--main-red)]/15 hover:text-[var(--main-red)]"
                    >
                      <X size={14} weight="bold" />
                    </span>
                  </div>

                  <div className="mt-5">
                    <p className="text-[10px] font-black uppercase tracking-widest text-gray-500">
                      총 자산 가치
                    </p>
                    <p className="mt-2 text-2xl font-black tabular-nums tracking-tight text-white">
                      {formatPrice(account.totalValue)}
                      <span className="ml-1 text-xs font-bold text-gray-500">
                        원
                      </span>
                    </p>
                    <p
                      className={`mt-2 text-sm font-black tabular-nums ${
                        isPositive
                          ? "text-[var(--main-red)]"
                          : isNegative
                            ? "text-[var(--main-blue)]"
                            : "text-gray-500"
                      }`}
                    >
                      {isPositive ? "+" : isNegative ? "-" : ""}
                      {formatPrice(Math.abs(profit))}원 (
                      {formatSignedPercent(profitPercent)})
                    </p>
                  </div>

                  <div className="mt-5 grid grid-cols-2 gap-2">
                    <div className="rounded-md border border-white/[0.06] bg-white/[0.02] p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.24em] text-gray-500">
                        현금 잔액
                      </p>
                      <p className="mt-2 text-sm font-black tabular-nums text-white">
                        {formatPrice(account.currentBalance)}원
                      </p>
                    </div>
                    <div className="relative rounded-md border border-white/[0.06] bg-white/[0.02] p-3">
                      {account.strategyName ? (
                        <span
                          className={`absolute -top-8 right-0 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-bold ${
                            account.tradingMode === "auto"
                              ? "bg-sky-500/15 text-sky-400"
                              : "bg-white/[0.06] text-gray-400"
                          }`}
                        >
                          {account.tradingMode === "auto" ? (
                            <Robot size={12} weight="bold" />
                          ) : (
                            <Bell size={12} weight="bold" />
                          )}
                          {account.tradingMode === "auto" ? "자동" : "알림"}
                        </span>
                      ) : null}
                      <p className="text-[10px] font-black uppercase tracking-[0.24em] text-gray-500">
                        초기 투자금
                      </p>
                      <p className="mt-2 text-sm font-black tabular-nums text-white">
                        {formatPrice(account.initialAmount)}원
                      </p>
                    </div>
                  </div>

                  <p className="mt-4 border-t border-white/[0.06] pt-3 text-right text-xs font-bold text-gray-500">
                    {new Date(account.createdAt).toLocaleDateString("ko-KR")}
                  </p>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      <CreateAccountModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreate={handleCreateAccount}
      />
    </>
  );
}
