"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PlusCircle } from "phosphor-react";
import CreateAccountModal from "@/components/ui/CreateAccountModal";
import type { VirtualAccount } from "@/types/portfolio";

function formatKRW(v: number): string {
  if (Math.abs(v) >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억원`;
  if (Math.abs(v) >= 10_000) return `${(v / 10_000).toFixed(0)}만원`;
  return `${v.toLocaleString("ko-KR")}원`;
}

export default function VirtualAccountSummary() {
  const [accounts, setAccounts] = useState<VirtualAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  const fetchAccounts = () => {
    fetch("/api/virtual-account")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: VirtualAccount[]) => setAccounts(data))
      .catch(() => setAccounts([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  const handleCreate = async (
    name: string,
    amount: number,
    strategyId?: string,
    strategyName?: string,
    tradingMode?: "auto" | "manual"
  ) => {
    await fetch("/api/virtual-account", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, initialAmount: amount, strategyId, strategyName, tradingMode }),
    });
    setModalOpen(false);
    fetchAccounts();
  };

  return (
    <div className="glass-card p-5 h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
            가상계좌
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">모의투자 현황</p>
        </div>
        <Link
          href="/virtual-account"
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          전체보기 →
        </Link>
      </div>

      {loading ? (
        <div className="space-y-3 animate-pulse">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-16 bg-white/5 rounded-xl" />
          ))}
        </div>
      ) : accounts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <p className="text-gray-400 font-medium">가상계좌가 없습니다</p>
          <p className="text-gray-600 text-sm mt-1">전략을 검증할 계좌를 만들어보세요</p>
          <button
            onClick={() => setModalOpen(true)}
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-blue-600/80 text-white text-sm font-bold rounded-lg hover:bg-blue-600 transition-colors"
          >
            <PlusCircle size={16} />
            계좌 만들기
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {accounts.slice(0, 5).map((acc) => {
            const profit = acc.totalValue - acc.initialAmount;
            const profitPct = acc.initialAmount > 0 ? (profit / acc.initialAmount) * 100 : 0;
            const isPos = profit >= 0;
            return (
              <Link
                key={acc.id}
                href={`/virtual-account/${acc.id}`}
                className="block p-3 rounded-xl bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 hover:border-white/10 transition-all"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-bold text-white text-sm truncate">{acc.name}</p>
                    {acc.strategyName && (
                      <span className="text-[10px] text-blue-400 bg-blue-500/10 border border-blue-500/20 px-1.5 py-0.5 rounded font-medium">
                        {acc.strategyName}
                      </span>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-black text-white tabular-nums">
                      {formatKRW(acc.totalValue)}
                    </p>
                    <p
                      className={`text-xs font-bold tabular-nums ${
                        isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"
                      }`}
                    >
                      {isPos ? "+" : ""}
                      {profitPct.toFixed(2)}%
                    </p>
                  </div>
                </div>
              </Link>
            );
          })}
          <button
            onClick={() => setModalOpen(true)}
            className="w-full flex items-center justify-center gap-1.5 py-2.5 text-xs text-gray-500 hover:text-gray-300 border border-white/5 hover:border-white/10 rounded-xl transition-colors"
          >
            <PlusCircle size={14} />
            새 계좌 만들기
          </button>
        </div>
      )}

      <CreateAccountModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreate={handleCreate}
      />
    </div>
  );
}
