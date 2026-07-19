"use client";

import { useEffect, useRef, useState } from "react";
import type { AccountMonthlyData } from "@/app/api/dashboard/account-monthly/route";

/*
 *  Stacked bar chart with ribbon connectors
 *  - 각 월 그룹: 같은 너비의 바가 세로로 쌓임 (큰 값 = 아래, 작은 값 = 위)
 *  - 값이 클수록 바 높이가 커짐
 *  - 인접 그룹 간 리본(사다리꼴)으로 같은 계좌의 바를 연결
 */

const ACCOUNT_COLORS = [
  { bar: "linear-gradient(180deg,#8fcf9e,#73B682)", rgb: "115,182,130" },
  { bar: "linear-gradient(180deg,#82c0e0,#62A8CB)", rgb: "98,168,203"  },
  { bar: "linear-gradient(180deg,#ffb366,#FF9933)", rgb: "255,153,51"  },
  { bar: "linear-gradient(180deg,#3d6e82,#2A4954)", rgb: "42,73,84"    },
  { bar: "linear-gradient(180deg,#484848,#272626)", rgb: "39,38,38"    },
  { bar: "linear-gradient(180deg,#73B682,#62A8CB)", rgb: "100,175,165" },
];

const CHART_H         = 180;  // 차트 영역 높이
const STACK_GAP       = 4;    // 스택 내 바 사이 간격
const LABEL_H         = 32;   // 월 라벨 높이
const VALUE_H         = 32;   // 하단 값 라벨 높이
const GROUP_GAP_RATIO = 0.30; // 리본 갭 비율
const ZERO_BAR_H      = 10;   // 0% 계좌도 화면에서 확인 가능하도록 표시
const MIN_BAR_H       = 6;

function fmtMonth(ym: string): string {
  const [y, m] = ym.split("/");
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString("ko-KR", { month: "short" });
}

function fmtPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function monthOrdinal(ym: string): number {
  const [year, month] = ym.split("/").map(Number);
  return year * 12 + month;
}

function createdMonthFromIso(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}/${String(date.getMonth() + 1).padStart(2, "0")}`;
}

export default function AccountProfitChart({ initialData }: { initialData: AccountMonthlyData | null }) {
  const [data, setData]                     = useState<AccountMonthlyData | null>(initialData);
  const [accountCreatedMonths, setAccountCreatedMonths] = useState<Record<string, string>>({});
  const [hasLoadedAccountCreatedMonths, setHasLoadedAccountCreatedMonths] = useState(false);
  const [hoveredMonth, setHoveredMonth]     = useState<number | null>(null);
  const containerRef                        = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    let isMounted = true;

    fetch("/api/dashboard/account-monthly", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((nextData: AccountMonthlyData | null) => {
        if (!isMounted || !nextData) return;
        setData(nextData);
      })
      .catch(() => {});

    fetch("/api/dashboard/virtual-account-list", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((nextData: { accounts?: Array<{ id: string; createdAt?: string | null }> } | null) => {
        if (!isMounted || !nextData?.accounts) return;
        const createdMonths: Record<string, string> = {};
        for (const account of nextData.accounts) {
          const createdMonth = createdMonthFromIso(account.createdAt);
          if (createdMonth) createdMonths[account.id] = createdMonth;
        }
        setAccountCreatedMonths(createdMonths);
        setHasLoadedAccountCreatedMonths(true);
      })
      .catch(() => {});

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const updateWidth = () => {
      const width = containerRef.current?.getBoundingClientRect().width ?? 0;
      if (width > 0) setContainerWidth(width);
    };
    const ro = new ResizeObserver((entries) => {
      const width = entries[0].contentRect.width;
      if (width > 0) setContainerWidth(width);
    });
    ro.observe(containerRef.current);
    updateWidth();
    const frame = requestAnimationFrame(updateWidth);
    window.addEventListener("resize", updateWidth);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", updateWidth);
      ro.disconnect();
    };
  }, []);

  const nAccounts = data?.accounts.length ?? 0;
  const totalH    = LABEL_H + CHART_H + VALUE_H;

  if (!data) {
    return (
      <div
        className="flat-card h-full p-3 sm:p-4 lg:p-5"
        data-testid="account-profit-card"
      >
        <div className="h-4 bg-white/5 rounded w-1/3 mb-5 animate-pulse" />
        <div className="flex items-end gap-8 mt-4" style={{ height: CHART_H }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex-1 bg-white/5 rounded-lg animate-pulse"
              style={{ height: 40 + i * 30 }} />
          ))}
        </div>
      </div>
    );
  }

  if (nAccounts === 0 || data.months.length === 0) {
    const emptyStateMessage =
      nAccounts === 0 ? "개설된 계좌가 없습니다." : "표시할 수익률 데이터가 없습니다.";
    const emptyStateDescription =
      nAccounts === 0
        ? "계좌를 개설하면 여기서 수익률을 확인할 수 있습니다"
        : "수익률 데이터가 쌓이면 여기서 확인할 수 있습니다";

    return (
      <div
        className="flat-card h-full p-3 sm:p-4 lg:p-5"
        data-testid="account-profit-card"
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-base font-black uppercase tracking-widest text-gray-400 font-outfit">
              계좌별 수익률
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">누적 실현 수익률 변화</p>
          </div>
        </div>

        <div className="flex items-start justify-center pt-6 text-center" style={{ height: totalH }}>
          <div data-testid="account-profit-empty-state">
            <p className="text-lg font-medium text-gray-500">{emptyStateMessage}</p>
            <p className="mt-3 text-base font-medium text-gray-600">{emptyStateDescription}</p>
          </div>
        </div>
      </div>
    );
  }

  const visibleMonthItems = data.months.map((ym, index) => ({ ym, index }));
  const nMonths = visibleMonthItems.length;
  const isAccountVisibleInMonth = (accountId: string, ym: string): boolean => {
    if (!hasLoadedAccountCreatedMonths) return false;
    const createdMonth = accountCreatedMonths[accountId];
    return createdMonth ? monthOrdinal(ym) >= monthOrdinal(createdMonth) : true;
  };

  /* ── Geometry ─────────────────────────────── */
  // 모든 값의 절대값 합계 중 최대 (스택 높이 기준)
  const monthSums = visibleMonthItems.map(({ ym, index }) =>
    data!.accounts.reduce(
      (sum, account) =>
        isAccountVisibleInMonth(account.id, ym)
          ? sum + Math.abs(account.monthlyProfitPct[index] ?? 0)
          : sum,
      0
    )
  );
  const maxSum = Math.max(...monthSums, 1);

  // 고정 순서: 마지막 달 기준 절대값 내림차순 (큰 값 = 아래)
  const lastVisibleMonth = visibleMonthItems[nMonths - 1];
  const fixedOrder = data.accounts
    .map((a, ai) => ({ ai, val: Math.abs(a.monthlyProfitPct[lastVisibleMonth.index] ?? 0) }))
    .sort((a, b) => b.val - a.val)  // 내림차순: 큰 값이 먼저 (아래)
    .map((x) => x.ai);

  // 그룹 레이아웃
  const totalGapW = containerWidth * GROUP_GAP_RATIO;
  const totalBarW = containerWidth - totalGapW;
  const groupW    = nMonths > 0 ? totalBarW / nMonths : 0;
  const gapW      = nMonths > 1 ? totalGapW / (nMonths - 1) : 0;
  const groupLX   = (mi: number) => mi * (groupW + gapW);
  const hasMeasuredWidth = containerWidth > 0;

  // 바 높이 계산 (개별 값 → 스택 내 높이)
  const getBarH = (val: number) => {
    if (Math.abs(val) < 0.05) return ZERO_BAR_H;
    const totalStackGap = (nAccounts - 1) * STACK_GAP;
    const availableH = CHART_H - totalStackGap;
    return Math.max((Math.abs(val) / maxSum) * availableH, MIN_BAR_H);
  };

  // 스택 위치 계산: barGeo[mi][ai] = { yTop, yBot, h }
  // 아래에서 위로 쌓음 (fixedOrder[0] = 가장 아래)
  const barGeo: Record<number, { yTop: number; yBot: number; h: number }>[] = [];

  for (let mi = 0; mi < nMonths; mi++) {
    const { ym, index } = visibleMonthItems[mi];
    const geo: Record<number, { yTop: number; yBot: number; h: number }> = {};
    let yOffset = LABEL_H + CHART_H; // 바 영역 하단 (SVG 좌표)

    for (const ai of fixedOrder) {
      const account = data.accounts[ai];
      if (!isAccountVisibleInMonth(account.id, ym)) continue;
      const val = account.monthlyProfitPct[index] ?? 0;
      const h   = getBarH(val);
      const yBot = yOffset;
      const yTop = yOffset - h;
      geo[ai] = { yTop, yBot, h };
      yOffset = yTop - STACK_GAP;
    }
    barGeo.push(geo);
  }

  const activeIdx =
    hoveredMonth !== null && hoveredMonth < nMonths ? hoveredMonth : nMonths - 1;
  const activeMonth = visibleMonthItems[activeIdx];

  // 계좌별 수익률(%)의 단순 합은 분모가 달라 의미가 없으므로,
  // 초기 투자금 가중 평균(= Σ누적손익 / Σ초기투자금)으로 포트폴리오 수익률을 계산한다.
  const weightedMonthReturn = (ym: string, index: number): number => {
    let pnlSum = 0;
    let cashSum = 0;
    for (const account of data!.accounts) {
      if (!isAccountVisibleInMonth(account.id, ym)) continue;
      pnlSum += ((account.monthlyProfitPct[index] ?? 0) / 100) * account.initialCash;
      cashSum += account.initialCash;
    }
    return cashSum > 0 ? (pnlSum / cashSum) * 100 : 0;
  };
  const activeTotal = weightedMonthReturn(activeMonth.ym, activeMonth.index);

  /* ── SVG ribbons ─────────────────────────── */
  const ribbons: JSX.Element[] = [];

  if (containerWidth > 0) {
    for (let mi = 0; mi < nMonths - 1; mi++) {
      for (const ai of fixedOrder) {
        const g1    = barGeo[mi][ai];
        const g2    = barGeo[mi + 1][ai];
        if (!g1 || !g2) continue;
        const color = ACCOUNT_COLORS[ai % ACCOUNT_COLORS.length];

        const x1r = groupLX(mi) + groupW;    // 그룹 mi 오른쪽 끝
        const x2l = groupLX(mi + 1);         // 그룹 mi+1 왼쪽 끝

        const d = [
          `M${x1r},${g1.yTop}`,
          `L${x2l},${g2.yTop}`,
          `L${x2l},${g2.yBot}`,
          `L${x1r},${g1.yBot}`,
          "Z",
        ].join(" ");

        ribbons.push(
          <path
            key={`ribbon-${mi}-${ai}`}
            d={d}
            fill={`rgba(${color.rgb},0.10)`}
          />
        );
      }
    }
  }

  /* ── Render ──────────────────────────────── */
  return (
    <div
      className="flat-card h-full p-3 sm:p-4 lg:p-5"
      data-testid="account-profit-card"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-base font-black uppercase tracking-widest text-gray-400 font-outfit">
            계좌별 수익률
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">누적 실현 수익률 변화</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-black font-outfit tabular-nums text-white">
            {fmtPct(activeTotal)}
          </p>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 font-bold">
            {fmtMonth(activeMonth.ym)} 투자금 가중
          </p>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 mb-4">
        {data.accounts.map((acc, i) => {
          const color = ACCOUNT_COLORS[i % ACCOUNT_COLORS.length];
          return (
            <div key={acc.id} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                style={{ background: color.bar }} />
              <span className="text-[10px] text-gray-400 font-bold">{acc.name}</span>
            </div>
          );
        })}
        {data.accounts.some((acc) => acc.monthlyProfitPct.some((v) => v < 0)) && (
          <div className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
              style={{
                background:
                  "repeating-linear-gradient(135deg, rgba(156,163,175,0.85) 0px, rgba(156,163,175,0.85) 2px, rgba(156,163,175,0.30) 2px, rgba(156,163,175,0.30) 4px)",
              }}
            />
            <span className="text-[10px] text-gray-400 font-bold">빗금 = 손실</span>
          </div>
        )}
      </div>

      {/* Chart */}
      <div ref={containerRef} className="relative w-full" style={{ height: totalH }}>
        <>
          {/* SVG: ribbons */}
          {hasMeasuredWidth && (
            <svg
              className="absolute inset-0 pointer-events-none"
              width={containerWidth}
              height={totalH}
            >
              {ribbons}
            </svg>
          )}

          <div
            aria-hidden="true"
            className="absolute left-0 right-0 border-t border-white/[0.08]"
            style={{ top: LABEL_H + CHART_H }}
          />

          {/* Month groups */}
          {visibleMonthItems.map(({ ym, index }, mi) => {
            const isActive   = mi === activeIdx;
            const monthTotal = weightedMonthReturn(ym, index);
            const groupStyle = hasMeasuredWidth
              ? { left: groupLX(mi), width: groupW, height: totalH }
              : { left: `${(mi / nMonths) * 100}%`, width: `${100 / nMonths}%`, height: totalH };

            return (
              <div
                key={ym}
                className="absolute top-0 cursor-pointer px-1"
                style={groupStyle}
                onMouseEnter={() => setHoveredMonth(mi)}
                onMouseLeave={() => setHoveredMonth(null)}
              >
                {/* 수익률 라벨 — 상단 */}
                <div className="absolute top-0 left-0 right-0 flex items-end justify-center pb-1"
                  style={{ height: LABEL_H }}>
                  <span className={`text-xs font-bold tabular-nums transition-colors ${
                    isActive ? "text-white font-black" : "text-gray-600"
                  }`}>
                    {fmtPct(monthTotal)}
                  </span>
                </div>

                {/* 스택 바들 */}
                {fixedOrder.map((ai) => {
                  const geo   = barGeo[mi][ai];
                  if (!geo) return null;
                  const color = ACCOUNT_COLORS[ai % ACCOUNT_COLORS.length];
                  // 바 높이는 절댓값 기준이므로 손실(음수) 계좌는 스트라이프로 구분한다.
                  const isNegative = (data!.accounts[ai].monthlyProfitPct[index] ?? 0) < 0;
                  return (
                    <div
                      key={data!.accounts[ai].id}
                      data-testid="account-profit-bar"
                      data-negative={isNegative ? "true" : undefined}
                      className="absolute left-1 right-1 rounded-lg transition-all duration-300"
                      style={{
                        top       : geo.yTop,
                        height    : geo.h,
                        background: isNegative
                          ? `repeating-linear-gradient(135deg, rgba(${color.rgb},0.85) 0px, rgba(${color.rgb},0.85) 4px, rgba(${color.rgb},0.30) 4px, rgba(${color.rgb},0.30) 8px)`
                          : color.bar,
                        boxShadow : isActive ? `0 4px 16px rgba(${color.rgb},0.40)` : "none",
                        opacity   : isActive ? 1 : 0.45,
                      }}
                    />
                  );
                })}

                {/* 월 라벨 — 하단 */}
                <div className="absolute left-0 right-0 bottom-0 flex items-center justify-center"
                  style={{ height: VALUE_H }}>
                  <span className={`text-xs font-black font-outfit transition-colors ${
                    isActive ? "text-white" : "text-gray-600"
                  }`}>
                    {fmtMonth(ym)}
                  </span>
                </div>
              </div>
            );
          })}
        </>
      </div>
    </div>
  );
}
