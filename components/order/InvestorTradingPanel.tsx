"use client";

import { useEffect, useState } from "react";
import { ArrowUp, ArrowDown, Minus } from "phosphor-react";

interface InvestorRow {
  date: string;
  individual_net: number;
  foreign_net: number;
  institutional_net: number;
  close_price?: number;
  volume?: number;
  foreign_hold_ratio?: string;
}

interface Props {
  symbol: string;
}

const fmtQty = (n: number) => {
  if (n === 0) return "—";
  const sign = n > 0 ? "+" : "-";
  return `${sign}${new Intl.NumberFormat("ko-KR").format(Math.abs(n))}`;
};

const fmtPrice = (n: number) =>
  n ? new Intl.NumberFormat("ko-KR").format(n) : "—";

function NetCell({ value }: { value: number }) {
  const tone =
    value > 0
      ? "text-[var(--main-red)]"
      : value < 0
      ? "text-[var(--main-blue)]"
      : "text-gray-600";
  const Icon = value > 0 ? ArrowUp : value < 0 ? ArrowDown : Minus;

  return (
    <div className={`flex items-center justify-end gap-0.5 text-xs font-black tabular-nums ${tone}`}>
      <Icon size={9} weight="bold" className="shrink-0" />
      <span>{fmtQty(value)}</span>
    </div>
  );
}

export default function InvestorTradingPanel({ symbol }: Props) {
  const [rows, setRows] = useState<InvestorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setRows([]);

    fetch(`/api/stock/${symbol}/investor-trading`, { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.error || `HTTP ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setRows(data.data ?? []);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "데이터 조회 실패");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol]);

  return (
    <div className="flex flex-col h-full">
      {/* 헤더 */}
      <div className="px-4 py-3 border-b border-white/[0.05] shrink-0">
        <h2 className="text-sm font-black uppercase tracking-widest text-white font-outfit">
          투자자별 매매동향
        </h2>
      </div>

      {/* 컬럼 헤더 */}
      <div className="grid grid-cols-[60px_1fr_1fr_1fr] gap-1 px-3 py-2 border-b border-white/[0.05] shrink-0">
        <span className="text-xs font-bold uppercase tracking-widest text-gray-600">일자</span>
        <span className="text-xs font-bold uppercase tracking-widest text-gray-600 text-right">개인</span>
        <span className="text-xs font-bold uppercase tracking-widest text-gray-600 text-right">외국인</span>
        <span className="text-xs font-bold uppercase tracking-widest text-gray-600 text-right">기관</span>
      </div>

      {/* 데이터 행 */}
      <div className="flex-1 min-h-0 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-xs font-bold text-gray-500">불러오는 중...</p>
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center px-4 text-center">
            <p className="text-xs font-bold text-gray-500">{error}</p>
          </div>
        ) : rows.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-xs font-bold text-gray-500">데이터 없음</p>
          </div>
        ) : (
          <div className="divide-y divide-white/[0.04]">
            {rows.map((row, i) => (
              <div
                key={row.date}
                className={`grid grid-cols-[60px_1fr_1fr_1fr] gap-1 items-center px-3 py-3 hover:bg-white/[0.02] transition-colors ${i === 0 ? "bg-white/[0.02]" : ""}`}
              >
                <span className="text-[11px] font-bold tabular-nums text-gray-400">
                  {row.date.slice(2).replace(/-/g, ".")}
                </span>
                <NetCell value={row.individual_net} />
                <NetCell value={row.foreign_net} />
                <NetCell value={row.institutional_net} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 외국인 보유비율 + 범례 */}
      {!loading && !error && rows.length > 0 && (
        <div className="px-3 py-2 border-t border-white/[0.05] shrink-0">
          {rows[0].foreign_hold_ratio && (
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-bold text-gray-600">외국인 보유비율</span>
              <span className="text-[10px] font-black tabular-nums text-gray-300">
                {rows[0].foreign_hold_ratio}
              </span>
            </div>
          )}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <ArrowUp size={8} weight="bold" className="text-[var(--main-red)]" />
              <span className="text-[10px] font-bold text-gray-600">순매수</span>
            </div>
            <div className="flex items-center gap-1">
              <ArrowDown size={8} weight="bold" className="text-[var(--main-blue)]" />
              <span className="text-[10px] font-bold text-gray-600">순매도</span>
            </div>
            <span className="text-[10px] text-gray-600 ml-auto">최근 5영업일</span>
          </div>
        </div>
      )}
    </div>
  );
}
