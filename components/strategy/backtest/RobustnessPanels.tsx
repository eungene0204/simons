"use client";

import { useMemo, useState } from "react";
import { Spinner } from "phosphor-react";

import type { StrategyBacktestRequest } from "@/app/analytics/new/parsedStrategyMerge";
import {
  buildWalkForwardParameterDescriptors,
  buildWalkForwardParameterRanges,
  walkForwardRangeBoundsForPath,
} from "@/app/analytics/new/parsedStrategyMerge";
import { t } from "@/lib/i18n";

interface CommonProps {
  baseStrategy?: StrategyBacktestRequest;
  canRun: boolean;
  disabledReason?: string;
}

type Metrics = { totalReturn: number | null; cagr: number | null; maxDrawdown: number | null; sharpe: number | null; profitFactor: number | null; winRate: number | null; trades: number | null };

function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}%`;
}
function num(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}
function cls(v: number | null | undefined): string {
  if (v == null) return "text-gray-400";
  return v > 0 ? "text-main-red" : v < 0 ? "text-main-blue" : "text-gray-400";
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail || t("요청에 실패했습니다."));
  return data as T;
}

const card = "rounded-2xl border border-white/[0.08] bg-[#0f0f10] p-4 sm:p-5 lg:p-6";
const input = "w-20 rounded border border-white/15 bg-transparent px-2 py-1 text-right text-xs font-bold text-gray-200";
const runBtn = "mt-4 inline-flex items-center gap-2 rounded-lg border border-sky-400/40 px-4 py-2 text-xs font-black text-sky-200 transition-colors hover:bg-sky-400/10 disabled:cursor-not-allowed disabled:opacity-40";

function Gate({ canRun, disabledReason, baseStrategy }: CommonProps) {
  if (canRun && baseStrategy) return null;
  return (
    <p className="mt-3 text-xs font-bold text-gray-500">
      {!baseStrategy ? t("이 백테스트 결과에는 재실행에 필요한 전략 설정이 저장되어 있지 않습니다.") : disabledReason}
    </p>
  );
}

// ── 롤링 시작일 ───────────────────────────────────────────────────────────────

interface RollingRun { run: number; startDate: string; endDate: string; metrics: Metrics | null; error: string | null }
interface RollingResult {
  status: string; windowMonths: number; stepMonths: number; runs: RollingRun[];
  summary: Record<string, { mean: number; median: number; min: number; max: number; std: number; count: number } | null>;
  positiveShare: number | null;
}

export function RollingStartPanel({ baseStrategy, canRun, disabledReason }: CommonProps) {
  const [windowMonths, setWindowMonths] = useState(36);
  const [stepMonths, setStepMonths] = useState(3);
  const [runs, setRuns] = useState(8);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RollingResult | null>(null);

  const run = async () => {
    if (!baseStrategy) return;
    setIsRunning(true); setError(null);
    try {
      setResult(await postJson<RollingResult>("/api/backtest/rolling-start", {
        base_strategy: baseStrategy, window_months: windowMonths, step_months: stepMonths, runs,
      }));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setIsRunning(false); }
  };

  return (
    <div className={card} data-testid="backtest-rolling-start-section">
      <h3 className="text-xl font-black text-white">{t("롤링 시작일 백테스트")}</h3>
      <p className="mt-2 max-w-2xl text-sm font-bold leading-6 text-gray-300">
        {t("창 길이를 고정한 채 시작일을 조금씩 미루며 같은 전략을 여러 번 실행합니다. 결과가 시작 시점에 얼마나 좌우되는지 분포로 봅니다.")}
      </p>
      <Gate baseStrategy={baseStrategy} canRun={canRun} disabledReason={disabledReason} />
      <div className="mt-4 flex flex-wrap items-center gap-4 text-xs font-bold text-gray-300">
        <label className="flex items-center gap-2">{t("창 길이(개월)")}<input type="number" className={input} min={6} max={240} value={windowMonths} onChange={(e) => setWindowMonths(Number(e.target.value))} /></label>
        <label className="flex items-center gap-2">{t("이동 간격(개월)")}<input type="number" className={input} min={1} max={24} value={stepMonths} onChange={(e) => setStepMonths(Number(e.target.value))} /></label>
        <label className="flex items-center gap-2">{t("실행 횟수")}<input type="number" className={input} min={1} max={24} value={runs} onChange={(e) => setRuns(Number(e.target.value))} /></label>
      </div>
      <button type="button" className={runBtn} disabled={!canRun || !baseStrategy || isRunning} onClick={run}>
        {isRunning && <Spinner className="h-4 w-4 animate-spin motion-reduce:animate-none" />}{t("롤링 실행")}
      </button>
      {error && <p className="mt-2 text-xs font-bold text-red-300">{error}</p>}
      {result && (
        <div className="mt-5" data-testid="backtest-rolling-start-result">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-bold text-gray-200 sm:grid-cols-4">
            {(["cagr", "maxDrawdown", "sharpe", "totalReturn"] as const).map((k) => {
              const s = result.summary[k];
              const label = { cagr: "CAGR", maxDrawdown: "MDD", sharpe: t("샤프"), totalReturn: t("총수익률") }[k];
              return (
                <div key={k}>
                  <dt className="text-gray-500">{label}</dt>
                  <dd>{s ? (k === "sharpe" ? `${num(s.median)} (${num(s.min)}~${num(s.max)})` : `${pct(s.median)} (${pct(s.min)}~${pct(s.max)})`) : "—"}</dd>
                </div>
              );
            })}
          </dl>
          <p className="mt-2 text-[11px] font-bold text-gray-500">
            {t("중앙값 (최소~최대) · 수익 창 비율 {0} · 창 {1}개월, 간격 {2}개월", pct(result.positiveShare, 0), result.windowMonths, result.stepMonths)}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[520px] text-xs font-bold text-gray-200">
              <thead className="text-[10px] uppercase tracking-widest text-gray-500">
                <tr><th className="px-2 py-1 text-left">#</th><th className="px-2 py-1 text-left">{t("기간")}</th><th className="px-2 py-1 text-right">{t("총수익률")}</th><th className="px-2 py-1 text-right">CAGR</th><th className="px-2 py-1 text-right">MDD</th><th className="px-2 py-1 text-right">{t("샤프")}</th><th className="px-2 py-1 text-right">{t("거래")}</th></tr>
              </thead>
              <tbody>
                {result.runs.map((r) => (
                  <tr key={r.run} className="border-t border-white/5">
                    <td className="px-2 py-1">{r.run}</td>
                    <td className="px-2 py-1 font-mono text-gray-400">{r.startDate} ~ {r.endDate}</td>
                    {r.metrics ? (
                      <>
                        <td className={`px-2 py-1 text-right ${cls(r.metrics.totalReturn)}`}>{pct(r.metrics.totalReturn)}</td>
                        <td className={`px-2 py-1 text-right ${cls(r.metrics.cagr)}`}>{pct(r.metrics.cagr)}</td>
                        <td className="px-2 py-1 text-right text-main-blue">{pct(r.metrics.maxDrawdown)}</td>
                        <td className="px-2 py-1 text-right">{num(r.metrics.sharpe)}</td>
                        <td className="px-2 py-1 text-right text-gray-400">{r.metrics.trades ?? "—"}</td>
                      </>
                    ) : (
                      <td colSpan={5} className="px-2 py-1 text-red-300">{r.error}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 거래비용 민감도 ──────────────────────────────────────────────────────────

interface SweepCell { feePct: number; slippagePct: number; metrics: Metrics | null; error: string | null }
interface SweepResult { status: string; feeLevels: number[]; slippageLevels: number[]; cells: SweepCell[]; cagrDrop: number | null }

const FEE_DEFAULT = "0, 0.015, 0.05, 0.1, 0.2";
const SLIP_DEFAULT = "0, 0.05, 0.1, 0.3, 0.5";

function parseLevels(text: string): number[] {
  return text.split(/[,\s]+/).map((s) => Number(s)).filter((v) => Number.isFinite(v) && v >= 0).slice(0, 6);
}

export function CostSweepPanel({ baseStrategy, canRun, disabledReason }: CommonProps) {
  const [feeText, setFeeText] = useState(FEE_DEFAULT);
  const [slipText, setSlipText] = useState(SLIP_DEFAULT);
  const [metric, setMetric] = useState<"cagr" | "maxDrawdown" | "sharpe">("cagr");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SweepResult | null>(null);

  const run = async () => {
    if (!baseStrategy) return;
    setIsRunning(true); setError(null);
    try {
      setResult(await postJson<SweepResult>("/api/backtest/cost-sweep", {
        base_strategy: baseStrategy, fee_rates_pct: parseLevels(feeText), slippage_rates_pct: parseLevels(slipText),
      }));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setIsRunning(false); }
  };

  const grid = useMemo(() => {
    if (!result) return null;
    const map = new Map<string, SweepCell>();
    result.cells.forEach((c) => map.set(`${c.feePct}|${c.slippagePct}`, c));
    return map;
  }, [result]);

  return (
    <div className={card} data-testid="backtest-cost-sweep-section">
      <h3 className="text-xl font-black text-white">{t("거래비용 민감도")}</h3>
      <p className="mt-2 max-w-2xl text-sm font-bold leading-6 text-gray-300">
        {t("수수료와 슬리피지를 여러 단계로 바꿔 같은 전략을 반복 실행합니다. 비용이 커질수록 결과가 얼마나 무너지는지 봅니다.")}
      </p>
      <Gate baseStrategy={baseStrategy} canRun={canRun} disabledReason={disabledReason} />
      <div className="mt-4 grid gap-3 text-xs font-bold text-gray-300 sm:grid-cols-2">
        <label className="flex flex-col gap-1">{t("수수료 단계(%) — 쉼표 구분, 최대 6개")}<input className="rounded border border-white/15 bg-transparent px-2 py-1" value={feeText} onChange={(e) => setFeeText(e.target.value)} /></label>
        <label className="flex flex-col gap-1">{t("슬리피지 단계(%) — 쉼표 구분, 최대 6개")}<input className="rounded border border-white/15 bg-transparent px-2 py-1" value={slipText} onChange={(e) => setSlipText(e.target.value)} /></label>
      </div>
      <button type="button" className={runBtn} disabled={!canRun || !baseStrategy || isRunning} onClick={run}>
        {isRunning && <Spinner className="h-4 w-4 animate-spin motion-reduce:animate-none" />}{t("스윕 실행")}
      </button>
      {error && <p className="mt-2 text-xs font-bold text-red-300">{error}</p>}
      {result && grid && (
        <div className="mt-5" data-testid="backtest-cost-sweep-result">
          <div className="flex items-center gap-2 text-xs font-bold text-gray-400">
            <span>{t("표시 지표")}</span>
            <select value={metric} onChange={(e) => setMetric(e.target.value as typeof metric)} className="rounded border border-white/15 bg-[#171717] px-2 py-1 text-gray-200">
              <option value="cagr">CAGR</option><option value="maxDrawdown">MDD</option><option value="sharpe">{t("샤프")}</option>
            </select>
            {result.cagrDrop != null && <span className="ml-2 text-gray-500">{t("최저 비용 → 최고 비용 CAGR 차이 {0}%p", result.cagrDrop.toFixed(2))}</span>}
          </div>
          <table className="mt-2 text-xs font-bold text-gray-200">
            <thead className="text-[10px] uppercase tracking-widest text-gray-500">
              <tr><th className="px-2 py-1 text-left">{t("수수료 \\ 슬리피지")}</th>{result.slippageLevels.map((s) => <th key={s} className="px-2 py-1 text-right">{s}%</th>)}</tr>
            </thead>
            <tbody>
              {result.feeLevels.map((f) => (
                <tr key={f} className="border-t border-white/5">
                  <td className="px-2 py-1 text-gray-400">{f}%</td>
                  {result.slippageLevels.map((s) => {
                    const c = grid.get(`${f}|${s}`);
                    const v = c?.metrics?.[metric] ?? null;
                    return <td key={s} className={`px-2 py-1 text-right ${metric === "maxDrawdown" ? "text-main-blue" : cls(v)}`}>{metric === "sharpe" ? num(v) : pct(v)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── 파라미터 민감도 히트맵 ───────────────────────────────────────────────────

interface OptimizeItem { parameters: Record<string, number>; metrics: Record<string, number | null>; target_value?: number | null }
interface OptimizeResult { status: string; message?: string; top_results?: OptimizeItem[]; total_iterations?: number }

function levels(min: number, max: number, count: number): number[] {
  if (count <= 1 || max <= min) return [min];
  const step = (max - min) / (count - 1);
  const out = Array.from({ length: count }, (_, i) => Number((min + step * i).toFixed(4)));
  return Array.from(new Set(out));
}

export function ParameterHeatmapPanel({ baseStrategy, canRun, disabledReason }: CommonProps) {
  const ranges = useMemo(() => (baseStrategy ? buildWalkForwardParameterRanges(baseStrategy) : {}), [baseStrategy]);
  const descriptors = useMemo(
    () => (baseStrategy ? buildWalkForwardParameterDescriptors(baseStrategy, ranges).filter((d) => walkForwardRangeBoundsForPath(ranges, d.path) !== null) : []),
    [baseStrategy, ranges],
  );
  const [xPath, setXPath] = useState<string>("");
  const [yPath, setYPath] = useState<string>("");
  const [steps, setSteps] = useState(5);
  const [metric, setMetric] = useState<"cagr" | "maxDrawdown" | "sharpe">("cagr");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizeResult | null>(null);

  const x = xPath || descriptors[0]?.path || "";
  const y = yPath || descriptors.find((d) => d.path !== x)?.path || "";

  const run = async () => {
    if (!baseStrategy || !x || !y || x === y) return;
    const bx = walkForwardRangeBoundsForPath(ranges, x);
    const by = walkForwardRangeBoundsForPath(ranges, y);
    if (!bx || !by) return;
    setIsRunning(true); setError(null);
    try {
      const body = {
        base_strategy: baseStrategy, user_prompt: "parameter sensitivity", target_metric: metric,
        n_trials: steps * steps, ranges: { [x]: levels(bx.min, bx.max, steps), [y]: levels(by.min, by.max, steps) },
      };
      const data = await postJson<OptimizeResult>("/api/backtest/optimize", body);
      if (data.status !== "success" && data.status !== "ok" && !data.top_results?.length) throw new Error(data.message || t("실행에 실패했습니다."));
      setResult(data);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setIsRunning(false); }
  };

  const cells = useMemo(() => {
    if (!result?.top_results) return null;
    const xs = Array.from(new Set(result.top_results.map((r) => r.parameters[x]))).sort((a, b) => a - b);
    const ys = Array.from(new Set(result.top_results.map((r) => r.parameters[y]))).sort((a, b) => a - b);
    const map = new Map<string, number | null>();
    result.top_results.forEach((r) => map.set(`${r.parameters[x]}|${r.parameters[y]}`, r.metrics?.[metric] ?? null));
    const vals = Array.from(map.values()).filter((v): v is number => v != null);
    return { xs, ys, map, min: Math.min(...vals), max: Math.max(...vals) };
  }, [result, x, y, metric]);

  const label = (path: string) => descriptors.find((d) => d.path === path)?.label ?? path;

  return (
    <div className={card} data-testid="backtest-param-heatmap-section">
      <h3 className="text-xl font-black text-white">{t("파라미터 민감도 히트맵")}</h3>
      <p className="mt-2 max-w-2xl text-sm font-bold leading-6 text-gray-300">
        {t("전략 파라미터 두 개를 격자로 바꿔 가며 같은 전략을 실행하고 결과를 색으로 봅니다. 한 점만 좋은 조합인지, 주변까지 고르게 좋은지 확인합니다.")}
      </p>
      <Gate baseStrategy={baseStrategy} canRun={canRun} disabledReason={disabledReason} />
      {descriptors.length < 2 ? (
        <p className="mt-3 text-xs font-bold text-gray-500">{t("탐색할 수 있는 숫자 파라미터가 2개 미만입니다.")}</p>
      ) : (
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs font-bold text-gray-300">
          <label className="flex items-center gap-2">X<select value={x} onChange={(e) => setXPath(e.target.value)} className="rounded border border-white/15 bg-[#171717] px-2 py-1 text-gray-200">{descriptors.map((d) => <option key={d.path} value={d.path}>{d.label}</option>)}</select></label>
          <label className="flex items-center gap-2">Y<select value={y} onChange={(e) => setYPath(e.target.value)} className="rounded border border-white/15 bg-[#171717] px-2 py-1 text-gray-200">{descriptors.map((d) => <option key={d.path} value={d.path}>{d.label}</option>)}</select></label>
          <label className="flex items-center gap-2">{t("단계")}<input type="number" className={input} min={3} max={8} value={steps} onChange={(e) => setSteps(Math.max(3, Math.min(8, Number(e.target.value))))} /></label>
          <label className="flex items-center gap-2">{t("지표")}<select value={metric} onChange={(e) => setMetric(e.target.value as typeof metric)} className="rounded border border-white/15 bg-[#171717] px-2 py-1 text-gray-200"><option value="cagr">CAGR</option><option value="maxDrawdown">MDD</option><option value="sharpe">{t("샤프")}</option></select></label>
        </div>
      )}
      <button type="button" className={runBtn} disabled={!canRun || !baseStrategy || isRunning || descriptors.length < 2 || x === y} onClick={run}>
        {isRunning && <Spinner className="h-4 w-4 animate-spin motion-reduce:animate-none" />}{t("히트맵 실행 ({0}회)", steps * steps)}
      </button>
      {error && <p className="mt-2 text-xs font-bold text-red-300">{error}</p>}
      {cells && (
        <div className="mt-5 overflow-x-auto" data-testid="backtest-param-heatmap-result">
          <table className="text-xs font-bold text-gray-200">
            <thead className="text-[10px] uppercase tracking-widest text-gray-500">
              <tr><th className="px-2 py-1 text-left">{label(y)} \\ {label(x)}</th>{cells.xs.map((v) => <th key={v} className="px-2 py-1 text-right">{v}</th>)}</tr>
            </thead>
            <tbody>
              {cells.ys.map((yv) => (
                <tr key={yv} className="border-t border-white/5">
                  <td className="px-2 py-1 text-gray-400">{yv}</td>
                  {cells.xs.map((xv) => {
                    const v = cells.map.get(`${xv}|${yv}`) ?? null;
                    const span = cells.max - cells.min || 1;
                    const ratio = v == null ? 0 : (v - cells.min) / span;
                    const good = metric === "maxDrawdown" ? ratio : ratio;
                    const bg = v == null ? "transparent" : `rgba(56,189,248,${(0.12 + good * 0.6).toFixed(2)})`;
                    return <td key={xv} className="px-2 py-1 text-right" style={{ background: bg }}>{metric === "sharpe" ? num(v) : pct(v)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] font-bold text-gray-500">{t("진할수록 {0}이(가) 높은 조합입니다. 과거 데이터의 통계이며 미래 성과를 보장하지 않습니다.", metric === "cagr" ? "CAGR" : metric === "sharpe" ? t("샤프") : "MDD")}</p>
        </div>
      )}
    </div>
  );
}
