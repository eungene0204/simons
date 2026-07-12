"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { VirtualAccountListData } from "@/app/api/dashboard/virtual-account-list/route";

function formatKRW(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(1)}억`;
  if (abs >= 10_000) return `${sign}${Math.round(abs / 10_000).toLocaleString()}만`;
  return `${sign}${abs.toLocaleString("ko-KR")}`;
}

function fmtPct(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function getValueColorClass(v: number): string {
  if (v > 0) return "text-[var(--main-red)]";
  if (v < 0) return "text-[var(--main-blue)]";
  return "text-white";
}

function StatusBadge({ status }: { status: "ACTIVE" | "CLOSED" }) {
  if (status === "ACTIVE") {
    return (
      <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
        운용중
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] font-bold text-gray-500">
      삭제됨
    </span>
  );
}

export default function VirtualAccountList({ initialData }: { initialData: VirtualAccountListData }) {
  const router = useRouter();
  const [data, setData] = useState<VirtualAccountListData>(initialData);
  const loading = false;

  useEffect(() => {
    let isMounted = true;

    fetch("/api/dashboard/virtual-account-list", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((nextData: VirtualAccountListData | null) => {
        if (!isMounted || !nextData) return;
        setData(nextData);
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, []);

  const accounts = data?.accounts ?? [];

  return (
    <div className="flat-card p-5 h-full">
      {/* 헤더 */}
      <div className="mb-5">
        <h2 className="text-base font-black uppercase tracking-widest text-gray-400 font-outfit">
          가상계좌 목록
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">운용중/삭제된 계좌별 수익 현황</p>
      </div>

      {/* 테이블 헤더 */}
      <div className="grid grid-cols-[minmax(0,1fr)_120px_110px] gap-2 px-2 mb-2">
        {["계좌명", "수익률", "총 수익금"].map((h) => (
          <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-500">
            {h}
          </span>
        ))}
      </div>

      {/* 구분선 */}
      <div className="border-t border-white/[0.05] mb-1" />

      {/* 로딩 */}
      {loading ? (
        <div className="space-y-1">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-11 bg-white/[0.03] rounded-xl animate-pulse"
            />
          ))}
        </div>
      ) : accounts.length === 0 ? (
        <div className="py-10 text-center">
          <p className="text-gray-500 text-sm">등록된 가상계좌가 없습니다</p>
          <p className="text-gray-600 text-xs mt-1">가상계좌를 생성하면 여기서 확인할 수 있습니다</p>
        </div>
      ) : (
        <div className="divide-y divide-white/[0.04] overflow-y-auto max-h-64 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
          {accounts.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => router.push(`/virtual-account/${a.id}`)}
              className="grid w-full grid-cols-[minmax(0,1fr)_120px_110px] gap-2 items-center px-2 py-3 text-left hover:bg-white/[0.02] rounded-xl transition-colors cursor-pointer"
            >
              {/* 계좌명 */}
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="text-base font-bold text-white truncate">{a.name}</p>
                  <StatusBadge status={a.status} />
                </div>
                <p className="text-xs text-gray-600 mt-0.5">{a.strategyName ?? "전략 미연결"}</p>
              </div>

              {/* 수익률 */}
              <span className={`text-sm font-bold tabular-nums font-outfit ${getValueColorClass(a.returnPct)}`}>
                {fmtPct(a.returnPct)}
              </span>

              {/* 총 수익금 */}
              <span
                className={`text-base font-bold tabular-nums font-outfit ${getValueColorClass(a.profit)}`}
              >
                {formatKRW(a.profit)}원
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
