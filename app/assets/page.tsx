import { redirect } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import {
  calculateAccountValue,
  getUserAssetSummary,
  moneyToNumber,
} from "@/lib/server/assetService";

const ledgerLabels: Record<string, string> = {
  INITIAL_GRANT: "최초 지급",
  ACCOUNT_ALLOCATION: "계좌 배정",
  ACCOUNT_LIQUIDATION_RETURN: "계좌 정산 반환",
  BUY: "매수",
  SELL: "매도",
  FORCE_SELL: "강제 매도",
};

function formatWon(value: number) {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatSignedWon(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatWon(value)}`;
}

function formatDate(value: Date) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

export default async function AssetsPage() {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/");
  }

  const [summary, ledgerEntries] = await prisma.$transaction(async (tx) => {
    const assetSummary = await getUserAssetSummary(tx, user.id);
    const entries = await tx.assetLedger.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: "desc" },
      take: 20,
    });

    return [assetSummary, entries] as const;
  });

  const accounts = summary.accounts.map((account) => ({
    id: account.id,
    name: account.name,
    cash: moneyToNumber(account.currentCash),
    value: moneyToNumber(calculateAccountValue(account)),
    initialAmount: moneyToNumber(account.initialCash),
    tradingMode: account.tradingMode ?? "manual",
  }));

  const userName = user.name || "게스트";
  const availableCash = moneyToNumber(summary.availableCash);
  const activeAccountValue = moneyToNumber(summary.activeAccountValue);
  const totalAssets = moneyToNumber(summary.totalAssets);

  return (
    <DashboardLayout userName={userName}>
      <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))] bg-[#050505] px-5 py-6 text-white sm:px-8 lg:px-10">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
          <section className="overflow-hidden border border-white/[0.08] bg-[#080808]">
            <div className="border-b border-white/[0.08] px-6 py-5">
              <p className="text-xs font-black uppercase tracking-[0.28em] text-blue-300/70">
                Asset Wallet
              </p>
              <div className="mt-3 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                <div>
                  <h1 className="text-3xl font-black tracking-[-0.04em] text-white md:text-5xl">
                    내 자산
                  </h1>
                  <p className="mt-2 text-sm font-bold text-gray-500">
                    사용 가능 자산과 활성 가상계좌 평가금액을 합산해 총 자산을 계산합니다.
                  </p>
                </div>
                <div className="text-left md:text-right">
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-gray-500">
                    Total Assets
                  </p>
                  <p className="mt-1 text-3xl font-black text-white md:text-4xl">
                    {formatWon(totalAssets)}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 divide-y divide-white/[0.08] md:grid-cols-3 md:divide-x md:divide-y-0">
              <div className="p-6">
                <p className="text-xs font-black uppercase tracking-[0.22em] text-gray-500">
                  Available Cash
                </p>
                <p className="mt-3 text-2xl font-black text-emerald-300">
                  {formatWon(availableCash)}
                </p>
                <p className="mt-2 text-xs font-bold text-gray-600">
                  새 가상계좌에 배정 가능한 금액
                </p>
              </div>
              <div className="p-6">
                <p className="text-xs font-black uppercase tracking-[0.22em] text-gray-500">
                  Account Value
                </p>
                <p className="mt-3 text-2xl font-black text-blue-200">
                  {formatWon(activeAccountValue)}
                </p>
                <p className="mt-2 text-xs font-bold text-gray-600">
                  ACTIVE 계좌 현금과 보유 종목 평가금액 합계
                </p>
              </div>
              <div className="p-6">
                <p className="text-xs font-black uppercase tracking-[0.22em] text-gray-500">
                  Active Accounts
                </p>
                <p className="mt-3 text-2xl font-black text-white">
                  {accounts.length.toLocaleString("ko-KR")}개
                </p>
                <p className="mt-2 text-xs font-bold text-gray-600">
                  정산 전 운용 중인 가상계좌
                </p>
              </div>
            </div>
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <section className="border border-white/[0.08] bg-[#080808]">
              <div className="border-b border-white/[0.08] px-6 py-4">
                <h2 className="text-lg font-black text-white">활성 가상계좌</h2>
                <p className="mt-1 text-xs font-bold text-gray-600">
                  계좌 가치는 계좌 현금과 보유 포지션 평가금액으로 계산됩니다.
                </p>
              </div>
              <div className="divide-y divide-white/[0.08]">
                {accounts.length === 0 ? (
                  <div className="px-6 py-10 text-sm font-bold text-gray-500">
                    아직 활성 가상계좌가 없습니다.
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
                          {account.tradingMode} · initial {formatWon(account.initialAmount)}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs font-black uppercase tracking-[0.18em] text-gray-600">
                          Cash
                        </p>
                        <p className="mt-1 text-sm font-black text-gray-200">
                          {formatWon(account.cash)}
                        </p>
                      </div>
                      <div className="md:text-right">
                        <p className="text-xs font-black uppercase tracking-[0.18em] text-gray-600">
                          Value
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

            <section className="border border-white/[0.08] bg-[#080808]">
              <div className="border-b border-white/[0.08] px-6 py-4">
                <h2 className="text-lg font-black text-white">자산 이동 내역</h2>
                <p className="mt-1 text-xs font-bold text-gray-600">
                  최근 20건의 지급, 배정, 강제청산, 정산 반환 원장입니다.
                </p>
              </div>
              <div className="divide-y divide-white/[0.08]">
                {ledgerEntries.length === 0 ? (
                  <div className="px-6 py-10 text-sm font-bold text-gray-500">
                    아직 자산 이동 내역이 없습니다.
                  </div>
                ) : (
                  ledgerEntries.map((entry) => {
                    const amount = moneyToNumber(entry.amount);
                    return (
                      <div key={entry.id} className="px-6 py-4">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-sm font-black text-white">
                              {ledgerLabels[entry.type] ?? entry.type}
                            </p>
                            <p className="mt-1 text-xs font-bold text-gray-600">
                              {formatDate(entry.createdAt)}
                            </p>
                          </div>
                          <p
                            className={`text-sm font-black ${
                              amount < 0 ? "text-red-300" : "text-emerald-300"
                            }`}
                          >
                            {formatSignedWon(amount)}
                          </p>
                        </div>
                        <p className="mt-2 text-xs font-bold text-gray-600">
                          잔액 {formatWon(moneyToNumber(entry.balanceAfter))}
                        </p>
                      </div>
                    );
                  })
                )}
              </div>
            </section>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
