"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChartBar,
  CreditCard,
  Crown,
  Lightning,
  MagnifyingGlass,
  Rocket,
  UserCircle,
  X,
} from "phosphor-react";
import {
  formatBacktestResetIn,
  formatUsageValue,
  getUsagePercent,
} from "./planUsageFormat";

type SubscriptionSummary = {
  planId: string;
  nextBillingAt: string | null;
  canceled: boolean;
} | null;

type SettingsPlanSummary = {
  plan: { planId: string; name: string; planEndDate?: string | null };
  subscription: SubscriptionSummary;
  accounts: { used: number; limit: number };
  strategies: { used: number; limit: number | null; unlimited: boolean };
  backtests: { used: number; limit: number };
};

type PaymentOrderSummary = {
  id: string;
  planId: string;
  amount: number;
  status: string;
  date: string;
};

type SettingsTab = "account" | "billing" | "usage";

const TABS: { id: SettingsTab; label: string; Icon: typeof UserCircle }[] = [
  { id: "account", label: "계정", Icon: UserCircle },
  { id: "billing", label: "결제", Icon: CreditCard },
  { id: "usage", label: "사용량", Icon: ChartBar },
];

const PLAN_ICONS: Record<string, typeof Lightning> = {
  FREE: Lightning,
  PRO: Rocket,
  PREMIUM: Crown,
};

const ORDER_STATUS_LABELS: Record<string, string> = {
  DONE: "Paid",
  FAILED: "Failed",
};

function formatBillingDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function formatOrderAmount(amount: number): string {
  return `₩${amount.toLocaleString("ko-KR")}`;
}

interface SettingsModalProps {
  userEmail?: string | null;
  onClose: () => void;
  /** 로그아웃 행에서 호출 — 부모(TopNavigation)의 로그아웃 흐름을 재사용한다 */
  onLogout: () => void;
  /** 계정 삭제 성공 후 호출 — 부모가 로그아웃/리다이렉트를 수행한다 */
  onAccountDeleted: () => void;
}

export default function SettingsModal({
  userEmail,
  onClose,
  onLogout,
  onAccountDeleted,
}: SettingsModalProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<SettingsTab>("account");
  const [searchQuery, setSearchQuery] = useState("");
  const [summary, setSummary] = useState<SettingsPlanSummary | null>(null);
  const [orders, setOrders] = useState<PaymentOrderSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isCanceling, setIsCanceling] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    (async () => {
      try {
        const [planRes, ordersRes] = await Promise.all([
          fetch("/api/user/plan", {
            cache: "no-store",
            credentials: "same-origin",
          }),
          fetch("/api/payment/orders", {
            cache: "no-store",
            credentials: "same-origin",
          }),
        ]);
        if (!planRes.ok) throw new Error("Failed to load plan");
        const planData = (await planRes.json()) as SettingsPlanSummary;
        // 청구서 목록은 부가 정보 — 실패해도 설정 모달 자체는 동작한다
        const ordersData = ordersRes.ok
          ? ((await ordersRes.json()) as { orders?: PaymentOrderSummary[] })
          : null;
        if (!disposed) {
          setSummary(planData);
          setOrders(
            Array.isArray(ordersData?.orders) ? ordersData.orders : []
          );
        }
      } catch {
        if (!disposed) setLoadError("설정 정보를 불러오지 못했습니다.");
      } finally {
        if (!disposed) setIsLoading(false);
      }
    })();
    return () => {
      disposed = true;
    };
  }, []);

  const visibleTabs = useMemo(() => {
    const query = searchQuery.trim();
    if (!query) return TABS;
    return TABS.filter((tab) => tab.label.includes(query));
  }, [searchQuery]);

  const subscription = summary?.subscription ?? null;
  const hasActiveRenewal = subscription != null && !subscription.canceled;

  const handleCancelSubscription = async () => {
    if (isCanceling) return;
    if (
      !window.confirm(
        "자동갱신을 해지할까요? 이미 결제된 기간에는 계속 이용할 수 있습니다."
      )
    ) {
      return;
    }
    setIsCanceling(true);
    setActionError(null);
    try {
      const res = await fetch("/api/payment/billing/cancel", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error("Failed to cancel");
      setSummary((prev) =>
        prev && prev.subscription
          ? { ...prev, subscription: { ...prev.subscription, canceled: true } }
          : prev
      );
    } catch {
      setActionError("구독 해지에 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setIsCanceling(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (isDeleting || hasActiveRenewal) return;
    if (
      !window.confirm(
        "계정을 삭제할까요? 삭제하면 다시 로그인할 수 없으며 되돌릴 수 없습니다."
      )
    ) {
      return;
    }
    setIsDeleting(true);
    setActionError(null);
    try {
      const res = await fetch("/api/user/account", {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as {
          error?: string;
        } | null;
        throw new Error(body?.error ?? "Failed to delete account");
      }
      onAccountDeleted();
    } catch (error) {
      setActionError(
        error instanceof Error && error.message !== "Failed to delete account"
          ? error.message
          : "계정 삭제에 실패했습니다. 잠시 후 다시 시도해주세요."
      );
      setIsDeleting(false);
    }
  };

  const PlanIcon = PLAN_ICONS[summary?.plan.planId ?? "FREE"] ?? Lightning;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-2 backdrop-blur-sm lg:px-4 lg:py-0"
      role="dialog"
      aria-modal="true"
      aria-label="설정"
    >
      <div
        data-testid="settings-modal-panel"
        className="flex h-[calc(100dvh-1rem)] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-white/[0.08] bg-[#0a0a0a] shadow-2xl shadow-black/60 lg:h-[min(720px,85vh)] lg:flex-row"
      >
        {/* 사이드바 */}
        <aside
          data-testid="settings-modal-sidebar"
          className="flex w-full flex-shrink-0 flex-col gap-3 border-b border-white/[0.06] bg-black/40 px-3 py-3 lg:w-56 lg:gap-5 lg:border-b-0 lg:border-r lg:py-5"
        >
          <label className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2.5">
            <MagnifyingGlass size={16} weight="bold" className="text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="검색"
              aria-label="설정 검색"
              className="w-full bg-transparent text-sm font-bold text-gray-200 outline-none placeholder:text-gray-600"
            />
          </label>
          <div>
            <p className="hidden px-3 pb-2 text-xs font-bold text-gray-600 lg:block">설정</p>
            <nav
              data-testid="settings-modal-tabs"
              className="flex gap-1 overflow-x-auto lg:block lg:space-y-1 lg:overflow-visible"
            >
              {visibleTabs.map(({ id, label, Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveTab(id)}
                  aria-current={activeTab === id ? "page" : undefined}
                  className={`flex w-auto flex-shrink-0 items-center gap-3 rounded-xl border px-3 py-2.5 text-left text-sm font-black transition-colors duration-200 lg:w-full ${
                    activeTab === id
                      ? "border-[var(--accent-blue)] bg-white/[0.08] text-white"
                      : "border-transparent text-gray-400 hover:bg-white/[0.04] hover:text-gray-200"
                  }`}
                >
                  <Icon size={18} weight="bold" />
                  <span>{label}</span>
                </button>
              ))}
            </nav>
          </div>
        </aside>

        {/* 콘텐츠 */}
        <div className="relative flex min-w-0 flex-1 flex-col">
          <button
            type="button"
            aria-label="설정 모달 닫기"
            onClick={onClose}
            className="absolute right-2 top-1 z-10 rounded-full p-2 text-gray-500 transition-colors hover:bg-white/[0.06] hover:text-white lg:right-5"
          >
            <X size={18} weight="bold" />
          </button>

          <div
            data-testid="settings-modal-content"
            className="flex-1 overflow-y-auto px-4 py-6 lg:px-10 lg:py-10"
          >
            {isLoading ? (
              <p className="text-sm font-bold text-gray-500">
                설정 정보를 불러오는 중입니다.
              </p>
            ) : loadError ? (
              <p className="text-sm font-black text-red-300">{loadError}</p>
            ) : summary ? (
              <>
                {actionError ? (
                  <p className="mb-5 text-sm font-black text-red-300">
                    {actionError}
                  </p>
                ) : null}

                {activeTab === "account" ? (
                  <section>
                    <h3 className="text-xl font-black tracking-tight text-gray-200">
                      계정
                    </h3>
                    <div className="mt-4">
                      <div className="flex items-center justify-between gap-5 border-b border-white/[0.06] py-4">
                        <p className="text-sm font-bold text-gray-300">
                          로그아웃
                        </p>
                        <button
                          type="button"
                          onClick={onLogout}
                          className="flex-shrink-0 rounded-xl bg-white/[0.08] px-4 py-2 text-xs font-black text-gray-200 transition-colors duration-200 hover:bg-white/[0.14]"
                        >
                          로그아웃
                        </button>
                      </div>
                      <div className="flex items-center justify-between gap-5 border-b border-white/[0.06] py-4">
                        <p className="min-w-0 text-sm font-bold text-gray-300">
                          {hasActiveRenewal
                            ? "계정을 삭제하려면 먼저 요금제 구독을 취소해 주세요."
                            : "계정을 삭제하면 다시 로그인할 수 없으며 되돌릴 수 없습니다."}
                        </p>
                        <button
                          type="button"
                          onClick={() => void handleDeleteAccount()}
                          disabled={hasActiveRenewal || isDeleting}
                          className="flex-shrink-0 rounded-xl bg-white/[0.08] px-4 py-2 text-xs font-black text-gray-200 transition-colors duration-200 hover:bg-white/[0.14] disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {isDeleting ? "삭제 중..." : "계정 삭제"}
                        </button>
                      </div>
                      {userEmail ? (
                        <div className="flex items-center justify-between gap-5 border-b border-white/[0.06] py-4">
                          <p className="text-sm font-bold text-gray-300">
                            이메일
                          </p>
                          <span className="truncate rounded-lg bg-white/[0.08] px-3 py-1.5 font-mono text-xs font-bold text-gray-300">
                            {userEmail}
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </section>
                ) : activeTab === "billing" ? (
                  <div className="space-y-10">
                    {/* 요금제 헤더 */}
                    <section
                      data-testid="settings-billing-header"
                      className="flex flex-col items-stretch gap-4 lg:flex-row lg:items-start lg:justify-between lg:gap-6"
                    >
                      <div className="flex items-start gap-4 lg:gap-5">
                        <span className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-2xl border border-white/[0.08] text-gray-300">
                          <PlanIcon size={30} weight="bold" />
                        </span>
                        <div>
                          <p className="text-lg font-black tracking-tight text-white">
                            {summary.plan.name} 요금제
                          </p>
                          {subscription ? (
                            <p className="mt-0.5 text-sm font-bold text-gray-500">
                              월간
                            </p>
                          ) : null}
                          <p className="mt-1.5 text-sm font-bold text-gray-400">
                            {subscription
                              ? subscription.canceled
                                ? `구독이 ${formatBillingDate(subscription.nextBillingAt)}에 만료됩니다.`
                                : `구독이 ${formatBillingDate(subscription.nextBillingAt)}에 자동으로 갱신됩니다.`
                              : summary.plan.planId === "FREE"
                                ? "무료 요금제를 사용 중입니다."
                                : "자동갱신 구독 없이 이용 중입니다."}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          onClose();
                          router.push("/pricing");
                        }}
                        className="w-full flex-shrink-0 rounded-xl bg-white/[0.08] px-4 py-2.5 text-xs font-black text-gray-200 transition-colors duration-200 hover:bg-white/[0.14] lg:mt-1 lg:w-auto"
                      >
                        요금제 조정
                      </button>
                    </section>

                    {/* 결제 수단 */}
                    {subscription ? (
                      <section>
                        <h3 className="text-lg font-black tracking-tight text-gray-200">
                          결제
                        </h3>
                        <div className="mt-4 flex items-center gap-3 border-b border-white/[0.06] pb-5">
                          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/[0.08] text-gray-300">
                            <CreditCard size={18} weight="bold" />
                          </span>
                          <p className="text-sm font-bold text-gray-300">
                            토스페이먼츠 자동결제
                          </p>
                        </div>
                      </section>
                    ) : null}

                    {/* 청구서 */}
                    <section>
                      <h3 className="text-lg font-black tracking-tight text-gray-200">
                        청구서
                      </h3>
                      {orders.length === 0 ? (
                        <p className="mt-4 text-sm font-bold text-gray-600">
                          결제 내역이 없습니다.
                        </p>
                      ) : (
                        <div className="mt-4">
                          <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-4 border-b border-white/[0.08] pb-3 text-xs font-bold text-gray-500">
                            <span>날짜</span>
                            <span>총계</span>
                            <span>상태</span>
                          </div>
                          {orders.map((order) => (
                            <div
                              key={order.id}
                              className="grid grid-cols-[1.4fr_1fr_1fr] gap-4 border-b border-white/[0.04] py-3.5 text-sm font-bold"
                            >
                              <span className="text-gray-200">
                                {formatBillingDate(order.date)}
                              </span>
                              <span className="tabular-nums text-gray-200">
                                {formatOrderAmount(order.amount)}
                              </span>
                              <span
                                className={
                                  order.status === "FAILED"
                                    ? "text-red-300"
                                    : "text-gray-400"
                                }
                              >
                                {ORDER_STATUS_LABELS[order.status] ??
                                  order.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </section>

                    {/* 취소 */}
                    {hasActiveRenewal ? (
                      <section>
                        <h3 className="text-lg font-black tracking-tight text-gray-200">
                          취소
                        </h3>
                        <div className="mt-4 flex items-center justify-between gap-5 py-1">
                          <p className="text-sm font-bold text-gray-300">
                            요금제 취소
                          </p>
                          <button
                            type="button"
                            onClick={() => void handleCancelSubscription()}
                            disabled={isCanceling}
                            className="flex-shrink-0 rounded-xl bg-red-500/90 px-5 py-2.5 text-xs font-black text-white transition-colors duration-200 hover:bg-red-500 disabled:cursor-wait disabled:opacity-60"
                          >
                            {isCanceling ? "해지 중..." : "취소"}
                          </button>
                        </div>
                        <p className="text-xs font-bold text-gray-600">
                          자동갱신을 해지해도 이미 결제된 기간에는 계속 이용할
                          수 있습니다.
                        </p>
                      </section>
                    ) : null}
                  </div>
                ) : (
                  <section>
                    <h3 className="text-xl font-black tracking-tight text-gray-200">
                      사용량
                    </h3>
                    <div className="mt-6 space-y-6">
                      {[
                        {
                          label: "사용 중인 계좌",
                          value: formatUsageValue(
                            summary.accounts.used,
                            summary.accounts.limit
                          ),
                          percent: getUsagePercent(
                            summary.accounts.used,
                            summary.accounts.limit
                          ),
                          sublabel: null as string | null,
                        },
                        {
                          label: "저장 가능 전략",
                          value: formatUsageValue(
                            summary.strategies.used,
                            summary.strategies.limit,
                            summary.strategies.unlimited
                          ),
                          percent: getUsagePercent(
                            summary.strategies.used,
                            summary.strategies.limit,
                            summary.strategies.unlimited
                          ),
                          sublabel: null as string | null,
                        },
                        {
                          label: "백테스트 횟수",
                          value: formatUsageValue(
                            summary.backtests.used,
                            summary.backtests.limit
                          ),
                          percent: getUsagePercent(
                            summary.backtests.used,
                            summary.backtests.limit
                          ),
                          sublabel: formatBacktestResetIn(
                            summary.plan.planEndDate
                          ),
                        },
                      ].map((item) => (
                        <div key={item.label} className="space-y-2">
                          <div className="flex items-center justify-between gap-4">
                            <span className="text-xs font-bold text-gray-500">
                              {item.label}
                            </span>
                            <span className="font-outfit text-sm font-bold tabular-nums text-gray-500">
                              {item.value}
                            </span>
                          </div>
                          <div
                            role="progressbar"
                            aria-label={item.label}
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={item.percent}
                            className="h-2 overflow-hidden rounded-full bg-white/[0.16]"
                          >
                            <div
                              className="h-full rounded-full bg-[var(--accent-blue)]"
                              style={{ width: `${item.percent}%` }}
                            />
                          </div>
                          {item.sublabel ? (
                            <p className="text-right font-outfit text-xs font-bold text-gray-600">
                              {item.sublabel}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
