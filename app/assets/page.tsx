import Link from "next/link";
import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { calculateAccountValue, moneyToNumber } from "@/lib/server/assetService";
import { getUserUsage } from "@/lib/server/planLimits";

function formatWon(value: number) {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatLimit(limit: number, unlimited: boolean) {
  return unlimited ? "무제한" : limit.toLocaleString("ko-KR");
}

export default async function AssetsPage() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/");
  }

  const [usage, accountRecords] = await prisma.$transaction(async (tx) => {
    const planUsage = await getUserUsage(tx, user.id);
    const accounts = await tx.virtualAccount.findMany({
      where: { userId: user.id, status: "ACTIVE" },
      include: { VirtualPosition: true },
      orderBy: { createdAt: "desc" },
    });
    return [planUsage, accounts] as const;
  });

  const accounts = accountRecords.map((account) => ({
    id: account.id,
    name: account.name,
    initialAmount: moneyToNumber(account.initialCash),
    value: moneyToNumber(calculateAccountValue(account)),
    tradingMode: account.tradingMode ?? "manual",
  }));

  const usageCards: Array<{ label: string; used: number; limitText: string }> = [
    {
      label: "사용 중인 계좌",
      used: usage.accounts.used,
      limitText: usage.accounts.limit.toLocaleString("ko-KR"),
    },
    {
      label: "저장 가능 전략",
      used: usage.strategies.used,
      limitText: formatLimit(usage.strategies.limit, usage.strategies.unlimited),
    },
    {
      label: "이번 달 백테스트",
      used: usage.backtests.used,
      limitText: usage.backtests.limit.toLocaleString("ko-KR"),
    },
  ];

  return (
    <DashboardLayout userName={user.name || "게스트"}>
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))] bg-[#050505] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
          <section className="overflow-hidden border border-white/[0.08] bg-[#080808]">
            <div className="border-b border-white/[0.08] px-6 py-5">
              <p className="text-xs font-black uppercase tracking-[0.28em] text-blue-300/70">
                My Plan
              </p>
              <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <h1 className="text-3xl font-black tracking-[-0.04em] text-white md:text-5xl">
                    {usage.plan.name}
                  </h1>
                  <p className="mt-2 text-sm font-bold text-gray-500">
                    계좌당 초기 모의 투자금 {formatWon(usage.plan.initialInvestmentAmount)}
                  </p>
                </div>
                <Link
                  href="/pricing"
                  className="self-start rounded-xl border border-white/[0.1] px-4 py-2 text-xs font-black text-white transition-colors hover:bg-white/[0.06] md:self-auto"
                >
                  요금제 보기
                </Link>
              </div>
            </div>

            <div className="grid grid-cols-1 divide-y divide-white/[0.08] md:grid-cols-3 md:divide-x md:divide-y-0">
              {usageCards.map((card) => (
                <div key={card.label} className="p-6">
                  <p className="text-xs font-black tracking-[0.06em] text-gray-500">
                    {card.label}
                  </p>
                  <p className="mt-3 text-2xl font-black text-white">
                    {card.used.toLocaleString("ko-KR")}
                    <span className="ml-1 text-base font-black text-gray-500">
                      / {card.limitText}
                    </span>
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="border border-white/[0.08] bg-[#080808]">
            <div className="border-b border-white/[0.08] px-6 py-4">
              <h2 className="text-lg font-black text-white">가상계좌</h2>
              <p className="mt-1 text-xs font-bold text-gray-600">
                각 계좌의 초기 모의 투자금과 현재 평가금액입니다.
              </p>
            </div>
            <div className="divide-y divide-white/[0.08]">
              {accounts.length === 0 ? (
                <div className="px-6 py-10 text-sm font-bold text-gray-500">
                  아직 운용 중인 가상계좌가 없습니다.
                </div>
              ) : (
                accounts.map((account) => (
                  <div
                    key={account.id}
                    className="grid grid-cols-1 gap-4 px-6 py-5 md:grid-cols-[1fr_auto_auto]"
                  >
                    <div>
                      <p className="text-base font-black text-white">{account.name}</p>
                      <p className="mt-1 text-xs font-bold uppercase tracking-[0.16em] text-gray-600">
                        {account.tradingMode}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-black tracking-[0.06em] text-gray-600">
                        초기 모의 투자금
                      </p>
                      <p className="mt-1 text-sm font-black text-gray-200">
                        {formatWon(account.initialAmount)}
                      </p>
                    </div>
                    <div className="md:text-right">
                      <p className="text-xs font-black tracking-[0.06em] text-gray-600">
                        평가금액
                      </p>
                      <p className="mt-1 text-lg font-black text-blue-200">
                        {formatWon(account.value)}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </DashboardLayout>
  );
}
