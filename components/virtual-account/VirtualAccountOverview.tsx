"use client";

import { useEffect, useState, type MouseEvent } from "react";
import Link from "next/link";
import { Bell, Robot, Spinner, X } from "phosphor-react";
import { StrategyWaveBackground } from "@/components/strategy/StrategyWaveBackground";
import CreateAccountModal from "@/components/ui/CreateAccountModal";
import VirtualAccountSimulationNotice from "@/components/virtual-account/VirtualAccountSimulationNotice";
import { createAccount, deleteAccount, getAccount } from "@/lib/portfolio";
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
  const [loadError, setLoadError] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [openingAccountId, setOpeningAccountId] = useState<string | null>(null);
  const [accountPendingDeletion, setAccountPendingDeletion] = useState<VirtualAccount | null>(null);
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadAccounts = async (options?: { showLoading?: boolean; force?: boolean }) => {
    const shouldShowLoading = options?.showLoading ?? !getCachedVirtualAccounts();
    if (shouldShowLoading) setLoading(true);
    try {
      const nextAccounts = await refreshVirtualAccountOverviewCache({
        force: options?.force,
      });
      setAccounts(nextAccounts);
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
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
        setLoadError(false);
        setLoading(false);
      })
      .catch(() => {
        if (!isMounted) return;
        setLoadError(true);
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

  const handleAccountClick = async (
    event: MouseEvent<HTMLAnchorElement>,
    accountId: string
  ) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      openingAccountId
    ) {
      return;
    }

    event.preventDefault();
    setOpeningAccountId(accountId);

    try {
      const account = await getAccount(accountId);
      if (!account) {
        await loadAccounts({ showLoading: false, force: true });
        return;
      }

      window.location.assign(`/virtual-account/${accountId}`);
    } finally {
      setOpeningAccountId((current) => (current === accountId ? null : current));
    }
  };

  const handleDeleteClick = (
    event: MouseEvent<HTMLButtonElement>,
    account: VirtualAccount
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setDeleteError(null);
    setAccountPendingDeletion(account);
  };

  const handleConfirmDelete = async () => {
    if (!accountPendingDeletion || isDeletingAccount) return;

    setIsDeletingAccount(true);
    setDeleteError(null);

    try {
      await deleteAccount(accountPendingDeletion.id);
      setAccountPendingDeletion(null);
      await loadAccounts({ showLoading: false, force: true });
    } catch {
      setDeleteError("계좌 정산에 실패했습니다. 현재가 조회 또는 정산 상태를 확인해 주세요.");
    } finally {
      setIsDeletingAccount(false);
    }
  };

  if (loading) {
    return (
      <div
        role="status"
        aria-label="가상계좌 불러오는 중"
        className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center"
      >
        <Spinner size={32} className="animate-spin text-gray-500" aria-hidden="true" />
      </div>
    );
  }

  return (
    <>
      <div
        data-testid="virtual-account-overview-root"
        className="flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] flex-col px-2 pb-2 md:px-3 md:pb-3"
      >
        <div
          data-testid="virtual-account-overview-content"
          className="flex flex-1 flex-col"
        >
          {loadError ? (
            <div className="flex flex-1 flex-col border border-white/[0.08]">
              <div className="flex flex-1 flex-col items-center justify-center gap-4 px-5 text-center">
                <p className="text-3xl font-black tracking-tight text-white">
                  가상계좌를 불러오지 못했습니다
                </p>
                <p className="max-w-md text-sm font-bold leading-relaxed text-gray-500">
                  저장된 계좌가 없는 것이 아니라 계좌 조회 요청이 실패했습니다. 잠시 후 다시 시도해 주세요.
                </p>
                <button
                  type="button"
                  onClick={() => void loadAccounts({ showLoading: true, force: true })}
                  className="rounded-lg border border-white/[0.12] bg-[#111111] px-5 py-3 text-sm font-black text-white transition-colors hover:bg-[#181818]"
                >
                  다시 불러오기
                </button>
              </div>
            </div>
          ) : accounts.length === 0 ? (
            <div
              data-testid="virtual-account-empty-state"
              className="relative flex flex-1 flex-col items-center justify-center gap-6 overflow-hidden px-5 py-8 text-center"
            >
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
                  전략과 가상계좌를 연결해서
                  <br />
                  실제 시장에서 시뮬레이션 하세요
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

                const accountLinkClass =
                  openingAccountId === account.id ? "pointer-events-none opacity-70" : "";

                return (
                  <article
                    key={account.id}
                    className={`group max-w-lg rounded-lg border border-white/[0.08] bg-[#111111] p-4 text-left transition-colors hover:bg-[#151515] ${accountLinkClass}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <Link
                        href={`/virtual-account/${account.id}`}
                        onClick={(event) => void handleAccountClick(event, account.id)}
                        aria-disabled={openingAccountId === account.id}
                        className="min-w-0 flex-1"
                      >
                        <h2 className="truncate text-lg font-black tracking-tight text-white">
                          {account.name}
                        </h2>
                        <p className="mt-1 truncate text-xs font-bold text-gray-500">
                          {account.strategyName || "전략 미연결"}
                        </p>
                      </Link>
                      <button
                        type="button"
                        aria-label={`${account.name} 계좌 삭제`}
                        onClick={(event) => handleDeleteClick(event, account)}
                        className="inline-flex shrink-0 items-center justify-center rounded-md bg-white/[0.06] p-2 text-gray-500 transition-colors hover:bg-[var(--main-red)]/15 hover:text-[var(--main-red)]"
                      >
                        <X size={14} weight="bold" />
                      </button>
                    </div>

                    <Link
                      href={`/virtual-account/${account.id}`}
                      onClick={(event) => void handleAccountClick(event, account.id)}
                      aria-disabled={openingAccountId === account.id}
                      className="block"
                    >
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
                  </article>
                );
              })}
            </div>
          )}
        </div>
        <VirtualAccountSimulationNotice className="mt-auto" />
      </div>

      <CreateAccountModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onCreate={handleCreateAccount}
      />

      {accountPendingDeletion ? (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-account-modal-title"
        >
          <div className="flex min-h-[320px] w-full max-w-sm flex-col justify-between rounded-3xl border border-white/[0.08] bg-[#080808] px-6 py-10 shadow-2xl shadow-black/60">
            <div>
              <h2
                id="delete-account-modal-title"
                className="text-2xl font-black tracking-tight text-white"
              >
                계좌 삭제
              </h2>
              <p className="mt-5 text-sm font-bold leading-7 text-gray-400">
                계좌의 보유 종목은 현재가 기준으로 강제 매도됩니다. 매도 대금과 남은 현금은
                회원님 자산으로 반환됩니다.
              </p>
              {deleteError ? (
                <p className="mt-4 text-sm font-black text-[var(--main-red)]">{deleteError}</p>
              ) : null}
            </div>
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => {
                  if (isDeletingAccount) return;
                  setAccountPendingDeletion(null);
                  setDeleteError(null);
                }}
                disabled={isDeletingAccount}
                className="rounded-xl border border-white/[0.08] px-5 py-3 text-sm font-black text-gray-400 transition-colors hover:bg-white/[0.04] hover:text-white disabled:cursor-wait disabled:opacity-60"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => void handleConfirmDelete()}
                disabled={isDeletingAccount}
                className="rounded-xl border border-white/[0.08] px-5 py-3 text-sm font-black text-[var(--main-red)] transition-colors hover:bg-white/[0.04] disabled:cursor-wait disabled:opacity-60"
              >
                {isDeletingAccount ? "정산 중..." : "계좌 삭제"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
