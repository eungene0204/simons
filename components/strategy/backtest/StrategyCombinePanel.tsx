"use client";

import { useEffect, useMemo, useState } from "react";
import { Spinner } from "phosphor-react";

import type { BacktestHistoryItem, BacktestResult } from "@/types/strategy";
import { t } from "@/lib/i18n";
import {
  combineStrategies,
  type CombineInput,
  type CombineRebalance,
  type CombineResult,
} from "@/lib/strategy-combine";

const MAX_COMPONENTS = 5;
const CURRENT_ID = "__current__";

interface Props {
  result: BacktestResult;
  strategyName?: string;
}

type Picked = { id: string; name: string; weight: number };

const REBALANCE_OPTIONS: Array<{ id: CombineRebalance; label: string }> = [
  { id: "none", label: "리밸런싱 없음(드리프트)" },
  { id: "monthly", label: "매월" },
  { id: "quarterly", label: "분기" },
  { id: "yearly", label: "매년" },
];

function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return `${v.toFixed(digits)}%`;
}

function num(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return v.toFixed(digits);
}

function CombinedChart({ result }: { result: CombineResult }) {
  const width = 640;
  const height = 220;
  const series = [
    { name: t("결합 포트폴리오"), curve: result.combined, stroke: "#38bdf8", strokeWidth: 2.5 },
    ...result.components.map((c, i) => ({
      name: c.name,
      curve: c.curve,
      stroke: ["#a3a3a3", "#c084fc", "#fbbf24", "#34d399", "#f87171"][i % 5],
      strokeWidth: 1.2,
    })),
  ];
  const all = series.flatMap((s) => s.curve);
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const n = result.dates.length;
  const path = (curve: number[]) =>
    curve
      .map((v, i) => {
        const x = (i / Math.max(1, n - 1)) * width;
        const y = height - ((v - min) / span) * (height - 10) - 5;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  return (
    <div className="mt-4">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full" role="img" aria-label={t("결합 자산곡선")}>
        {series.map((s) => (
          <path key={s.name} d={path(s.curve)} fill="none" stroke={s.stroke} strokeWidth={s.strokeWidth} />
        ))}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] font-bold text-gray-300">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-4" style={{ background: s.stroke }} />
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function StrategyCombinePanel({ result, strategyName }: Props) {
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [picked, setPicked] = useState<Picked[]>([
    { id: CURRENT_ID, name: strategyName || t("현재 결과"), weight: 50 },
  ]);
  const [rebalance, setRebalance] = useState<CombineRebalance>("monthly");
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [combined, setCombined] = useState<CombineResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/backtest/history")
      .then(async (res) => {
        if (!res.ok) throw new Error(t("저장된 백테스트 목록을 불러오지 못했습니다."));
        return (await res.json()) as BacktestHistoryItem[];
      })
      .then((items) => {
        if (!cancelled) setHistory(Array.isArray(items) ? items : []);
      })
      .catch((error) => {
        if (!cancelled) setHistoryError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const pickedIds = useMemo(() => new Set(picked.map((p) => p.id)), [picked]);

  const toggle = (item: BacktestHistoryItem) => {
    setCombined(null);
    setPicked((prev) => {
      if (prev.some((p) => p.id === item.id)) return prev.filter((p) => p.id !== item.id);
      if (prev.length >= MAX_COMPONENTS) return prev;
      return [...prev, { id: item.id, name: item.strategyName, weight: 50 }];
    });
  };

  const setWeight = (id: string, weight: number) => {
    setCombined(null);
    setPicked((prev) => prev.map((p) => (p.id === id ? { ...p, weight } : p)));
  };

  const run = async () => {
    setIsRunning(true);
    setRunError(null);
    try {
      const inputs: CombineInput[] = [];
      for (const p of picked) {
        if (p.id === CURRENT_ID) {
          inputs.push({ id: p.id, name: p.name, dates: result.dates, equity: result.equity, weight: p.weight });
          continue;
        }
        const res = await fetch(`/api/backtest/history/${p.id}`);
        if (!res.ok) throw new Error(t("'{0}' 기록을 불러오지 못했습니다.", p.name));
        const item = (await res.json()) as { result?: { dates?: string[]; equity?: number[] } };
        const dates = item.result?.dates ?? [];
        const equity = item.result?.equity ?? [];
        if (dates.length < 2 || equity.length !== dates.length) {
          throw new Error(t("'{0}' 기록에는 결합에 쓸 자산곡선이 없습니다.", p.name));
        }
        inputs.push({ id: p.id, name: p.name, dates, equity, weight: p.weight });
      }
      setCombined(combineStrategies(inputs, rebalance));
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsRunning(false);
    }
  };

  const canRun = picked.length >= 2 && picked.some((p) => p.weight > 0) && !isRunning;

  return (
    <div data-testid="backtest-combine-section" className="rounded-2xl border border-white/[0.08] bg-[#0f0f10] p-4 sm:p-5 lg:p-6">
      <div className="space-y-2">
        <h3 className="text-xl font-black text-white">{t("다중 전략 결합")}</h3>
        <p className="max-w-2xl text-sm font-bold leading-6 text-gray-300">
          {t("저장된 백테스트 결과의 자산곡선을 비중대로 섞어 결합 포트폴리오의 과거 성과와 전략 간 상관을 계산합니다. 각 전략의 거래 비용은 이미 자산곡선에 들어 있고, 결합 리밸런싱 비용은 더하지 않습니다.")}
        </p>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
          <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">
            {t("결합할 전략 (최대 {0}개)", MAX_COMPONENTS)}
          </div>
          {isLoadingHistory && (
            <div className="mt-3 flex items-center gap-2 text-xs font-bold text-gray-400">
              <Spinner className="h-4 w-4 animate-spin motion-reduce:animate-none" /> {t("저장된 백테스트를 불러오는 중입니다.")}
            </div>
          )}
          {historyError && (
            <p className="mt-3 text-xs font-bold text-red-300">{historyError}</p>
          )}
          <ul className="mt-3 max-h-64 space-y-1 overflow-y-auto">
            <li className="flex items-center justify-between rounded-lg bg-white/[0.04] px-3 py-2 text-xs font-bold text-gray-200">
              <span>{strategyName || t("현재 결과")}</span>
              <span className="text-[10px] text-sky-300">{t("현재 결과")}</span>
            </li>
            {history
              .filter((item) => item.id !== (result as { cacheKey?: string }).cacheKey)
              .map((item) => (
                <li key={item.id}>
                  <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 text-xs font-bold text-gray-300 hover:bg-white/[0.04]">
                    <span className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={pickedIds.has(item.id)}
                        onChange={() => toggle(item)}
                        disabled={!pickedIds.has(item.id) && picked.length >= MAX_COMPONENTS}
                      />
                      <span className="line-clamp-1">{item.strategyName}</span>
                    </span>
                    <span className="shrink-0 text-[10px] text-gray-500">
                      CAGR {pct(item.metrics?.cagr)} · MDD {pct(item.metrics?.mdd)}
                    </span>
                  </label>
                </li>
              ))}
          </ul>
          {!isLoadingHistory && !historyError && history.length === 0 && (
            <p className="mt-3 text-xs font-bold text-gray-500">{t("저장된 백테스트가 없습니다. 결과를 저장한 뒤 결합할 수 있습니다.")}</p>
          )}
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
          <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("비중과 리밸런싱")}</div>
          <ul className="mt-3 space-y-2">
            {picked.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 text-xs font-bold text-gray-200">
                <span className="line-clamp-1">{p.name}</span>
                <span className="flex items-center gap-1">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={5}
                    value={p.weight}
                    aria-label={t("{0} 비중(%)", p.name)}
                    onChange={(e) => setWeight(p.id, Number(e.target.value))}
                    className="w-16 rounded border border-white/15 bg-transparent px-2 py-1 text-right"
                  />
                  <span className="text-gray-500">%</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold text-gray-400">{t("결합 리밸런싱")}</span>
            <select
              value={rebalance}
              onChange={(e) => {
                setCombined(null);
                setRebalance(e.target.value as CombineRebalance);
              }}
              aria-label={t("결합 리밸런싱")}
              className="rounded border border-white/15 bg-[#171717] px-2 py-1 text-xs font-bold text-gray-200"
            >
              {REBALANCE_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>{t(o.label)}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={run}
            disabled={!canRun}
            className="mt-4 inline-flex items-center gap-2 rounded-lg border border-sky-400/40 px-4 py-2 text-xs font-black text-sky-200 transition-colors hover:bg-sky-400/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isRunning && <Spinner className="h-4 w-4 animate-spin motion-reduce:animate-none" />}
            {t("결합 계산")}
          </button>
          {picked.length < 2 && (
            <p className="mt-2 text-[11px] font-bold text-gray-500">{t("전략을 2개 이상 고르면 계산할 수 있습니다.")}</p>
          )}
          {runError && <p className="mt-2 text-xs font-bold text-red-300">{runError}</p>}
        </div>
      </div>

      {combined && (
        <div className="mt-6" data-testid="backtest-combine-result">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-xs font-bold text-gray-200">
              <thead className="text-[10px] uppercase tracking-widest text-gray-500">
                <tr>
                  <th className="px-2 py-1 text-left">{t("전략")}</th>
                  <th className="px-2 py-1 text-right">{t("비중")}</th>
                  <th className="px-2 py-1 text-right">{t("총수익률")}</th>
                  <th className="px-2 py-1 text-right">CAGR</th>
                  <th className="px-2 py-1 text-right">MDD</th>
                  <th className="px-2 py-1 text-right">{t("변동성")}</th>
                  <th className="px-2 py-1 text-right">{t("샤프")}</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-white/10 text-sky-200">
                  <td className="px-2 py-1.5">{t("결합 포트폴리오")}</td>
                  <td className="px-2 py-1.5 text-right">100%</td>
                  <td className="px-2 py-1.5 text-right">{pct(combined.stats.totalReturn)}</td>
                  <td className="px-2 py-1.5 text-right">{pct(combined.stats.cagr)}</td>
                  <td className="px-2 py-1.5 text-right">{pct(combined.stats.maxDrawdown)}</td>
                  <td className="px-2 py-1.5 text-right">{pct(combined.stats.volatility)}</td>
                  <td className="px-2 py-1.5 text-right">{num(combined.stats.sharpe)}</td>
                </tr>
                {combined.components.map((c) => (
                  <tr key={c.id} className="border-t border-white/5">
                    <td className="px-2 py-1.5">{c.name}</td>
                    <td className="px-2 py-1.5 text-right">{pct(c.weight, 0)}</td>
                    <td className="px-2 py-1.5 text-right">{pct(c.stats.totalReturn)}</td>
                    <td className="px-2 py-1.5 text-right">{pct(c.stats.cagr)}</td>
                    <td className="px-2 py-1.5 text-right">{pct(c.stats.maxDrawdown)}</td>
                    <td className="px-2 py-1.5 text-right">{pct(c.stats.volatility)}</td>
                    <td className="px-2 py-1.5 text-right">{num(c.stats.sharpe)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] font-bold text-gray-500">
            {t("공통 거래일 {0}일 · 결합 리밸런싱 {1}회 · 과거 데이터 기반 시뮬레이션 결과이며 미래 수익은 보장되지 않습니다.", combined.dates.length, combined.rebalanceCount)}
          </p>

          <div className="mt-5">
            <div className="text-[11px] font-black uppercase tracking-widest text-gray-500">{t("전략 간 일수익률 상관")}</div>
            <table className="mt-2 text-xs font-bold text-gray-200">
              <thead>
                <tr>
                  <th className="px-2 py-1" />
                  {combined.components.map((c) => (
                    <th key={c.id} className="max-w-[120px] truncate px-2 py-1 text-right text-[10px] text-gray-500">{c.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {combined.correlation.map((row, i) => (
                  <tr key={combined.components[i].id}>
                    <td className="max-w-[160px] truncate px-2 py-1 text-[10px] text-gray-500">{combined.components[i].name}</td>
                    {row.map((v, j) => (
                      <td key={j} className="px-2 py-1 text-right">{num(v)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <CombinedChart result={combined} />
        </div>
      )}
    </div>
  );
}
