"use client";

import { useState } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from "recharts";

interface MonteCarloResult {
  n_simulations: number;
  n_days: number;
  percentile_paths: Record<string, number[]>; // "5","25","50","75","95"
  final_return_pct: Record<string, number>;   // "1".."99"
  final_return_distribution: number[];
  mdd_distribution: number[];
  mdd_percentiles: Record<string, number>;
  sharpe_percentiles: Record<string, number>;
  prob_profit: number;
}

interface MonteCarloRequest {
  equity: number[];
  initial_capital: number;
  n_simulations: number;
  block_size: number;
}

interface MonteCarloProps {
  equity: number[];
  dates: string[];
  initialCapital: number;
}

function buildHistogramBuckets(data: number[], nBins = 40) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const binWidth = range / nBins;
  const bins: { x: number; count: number }[] = [];
  for (let i = 0; i < nBins; i++) {
    bins.push({ x: parseFloat((min + i * binWidth).toFixed(1)), count: 0 });
  }
  for (const v of data) {
    const idx = Math.min(Math.floor((v - min) / binWidth), nBins - 1);
    bins[idx].count++;
  }
  return bins;
}

function MetricCard({
  label,
  value,
  sub,
  color = "white",
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-[#0a0a0a] rounded-xl px-4 py-3 flex flex-col gap-0.5">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-xl font-black`} style={{ color }}>
        {value}
      </span>
      {sub && <span className="text-xs text-gray-600">{sub}</span>}
    </div>
  );
}

export default function MonteCarloPanel({
  equity,
  dates,
  initialCapital,
}: MonteCarloProps) {
  const [result, setResult] = useState<MonteCarloResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [nSims, setNSims] = useState(1000);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const payload: MonteCarloRequest = {
        equity,
        initial_capital: initialCapital,
        n_simulations: nSims,
        block_size: 20,
      };
      const res = await fetch("/api/backtest/monte-carlo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Unknown error");
      }
      const data: MonteCarloResult = await res.json();
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsRunning(false);
    }
  };

  // ── Percentile path chart data ──────────────────────────────────────────
  const pathChartData =
    result &&
    dates.map((d, i) => ({
      date: d,
      p5: result.percentile_paths["5"][i],
      p25: result.percentile_paths["25"][i],
      p50: result.percentile_paths["50"][i],
      p75: result.percentile_paths["75"][i],
      p95: result.percentile_paths["95"][i],
    }));

  // Downsample for performance (max 300 points)
  const downsample = <T,>(arr: T[], maxPoints = 300): T[] => {
    if (arr.length <= maxPoints) return arr;
    const step = Math.ceil(arr.length / maxPoints);
    return arr.filter((_, i) => i % step === 0 || i === arr.length - 1);
  };

  const sampledPath = pathChartData ? downsample(pathChartData) : [];

  const returnHistData = result
    ? buildHistogramBuckets(result.final_return_distribution)
    : [];

  const mddHistData = result
    ? buildHistogramBuckets(result.mdd_distribution)
    : [];

  const formatPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  const formatEquity = (v: number) =>
    v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)}M`
      : v >= 1_000
      ? `${(v / 1_000).toFixed(0)}K`
      : String(v);

  return (
    <div className="flex flex-col gap-5 px-4 py-4">
      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">시뮬레이션 횟수</span>
          {[500, 1000, 3000].map((n) => (
            <button
              key={n}
              onClick={() => setNSims(n)}
              className={`px-3 py-1 rounded-md text-sm font-bold transition-colors ${
                nSims === n
                  ? "bg-blue-600 text-white"
                  : "bg-[#0a0a0a] text-gray-400 hover:text-white"
              }`}
            >
              {n.toLocaleString()}
            </button>
          ))}
        </div>
        <button
          onClick={run}
          disabled={isRunning}
          className="ml-auto px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-bold rounded-lg transition-all active:scale-95"
        >
          {isRunning ? "시뮬레이션 중..." : "몬테카를로 실행"}
        </button>
      </div>

      {error && (
        <div className="text-red-400 text-sm bg-red-900/20 border border-red-500/30 rounded-lg px-4 py-3">
          오류: {error}
        </div>
      )}

      {!result && !isRunning && (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-gray-600">
          <span className="text-4xl">🎲</span>
          <p className="text-sm text-center">
            백테스트 수익률을 무작위로 재조합해 다양한 시나리오를 생성하고, 전략의 강건성을 통계적으로 검증합니다.
          </p>
        </div>
      )}

      {isRunning && (
        <div className="flex items-center justify-center py-16 gap-3 text-gray-400">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">
            {nSims.toLocaleString()}회 시뮬레이션 실행 중...
          </span>
        </div>
      )}

      {result && (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <MetricCard
              label="수익 확률"
              value={`${(result.prob_profit * 100).toFixed(1)}%`}
              sub="P(최종수익 > 0)"
              color={result.prob_profit >= 0.6 ? "#4ade80" : result.prob_profit >= 0.4 ? "#facc15" : "#f87171"}
            />
            <MetricCard
              label="중앙값 최종수익"
              value={formatPct(result.final_return_pct["50"])}
              sub="50번째 백분위"
              color={result.final_return_pct["50"] >= 0 ? "#4ade80" : "#f87171"}
            />
            <MetricCard
              label="95% 신뢰구간"
              value={`${formatPct(result.final_return_pct["5"])} ~ ${formatPct(result.final_return_pct["95"])}`}
              sub="하위 5% ~ 상위 5%"
            />
            <MetricCard
              label="중앙값 MDD"
              value={formatPct(result.mdd_percentiles["50"])}
              sub="50번째 백분위"
              color={Math.abs(result.mdd_percentiles["50"]) <= 10 ? "#4ade80" : Math.abs(result.mdd_percentiles["50"]) <= 20 ? "#facc15" : "#f87171"}
            />
          </div>

          {/* Percentile Paths */}
          <div className="bg-[#0a0a0a] rounded-xl p-4">
            <p className="text-sm font-bold text-white mb-3">
              수익률 시나리오 분포{" "}
              <span className="text-xs font-normal text-gray-500">
                ({result.n_simulations.toLocaleString()}개 경로)
              </span>
            </p>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={sampledPath} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: "#555" }}
                  tickFormatter={(v) => v?.slice(0, 7)}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tickFormatter={formatEquity}
                  tick={{ fontSize: 10, fill: "#555" }}
                  width={50}
                />
                <Tooltip
                  formatter={(v: number, name: string) => [formatEquity(v), name]}
                  labelFormatter={(l) => l}
                  contentStyle={{ background: "#111", border: "1px solid #333", fontSize: 12 }}
                />
                {/* 5-95 band */}
                <Area dataKey="p95" stroke="none" fill="#3b82f6" fillOpacity={0.08} name="상위 5%" />
                <Area dataKey="p75" stroke="none" fill="#3b82f6" fillOpacity={0.12} name="상위 25%" />
                {/* median */}
                <Area dataKey="p50" stroke="#3b82f6" strokeWidth={2} fill="none" name="중앙값" />
                <Area dataKey="p25" stroke="none" fill="#3b82f6" fillOpacity={0.06} name="하위 25%" />
                <Area dataKey="p5" stroke="none" fill="none" name="하위 5%" />
                <ReferenceLine y={initialCapital} stroke="#444" strokeDasharray="4 4" />
              </AreaChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-2 justify-center flex-wrap">
              {[
                { label: "상위 5% (낙관)", color: "#93c5fd" },
                { label: "상위 25%", color: "#60a5fa" },
                { label: "중앙값", color: "#3b82f6" },
                { label: "하위 25%", color: "#1d4ed8" },
                { label: "하위 5% (비관)", color: "#1e3a8a" },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded-sm" style={{ background: item.color }} />
                  <span className="text-xs text-gray-500">{item.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Histograms */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Final Return Distribution */}
            <div className="bg-[#0a0a0a] rounded-xl p-4">
              <p className="text-sm font-bold text-white mb-1">최종 수익률 분포</p>
              <p className="text-xs text-gray-600 mb-3">
                하위 5%: {formatPct(result.final_return_pct["5"])} / 상위 95%:{" "}
                {formatPct(result.final_return_pct["95"])}
              </p>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={returnHistData} barCategoryGap={1}>
                  <XAxis
                    dataKey="x"
                    tick={{ fontSize: 9, fill: "#555" }}
                    tickFormatter={(v) => `${v.toFixed(0)}%`}
                    interval={Math.floor(returnHistData.length / 5)}
                  />
                  <YAxis hide />
                  <Tooltip
                    formatter={(v: number) => [v, "빈도"]}
                    labelFormatter={(l) => `${Number(l).toFixed(1)}%`}
                    contentStyle={{ background: "#111", border: "1px solid #333", fontSize: 11 }}
                  />
                  <ReferenceLine x={0} stroke="#555" strokeDasharray="3 3" />
                  <Bar
                    dataKey="count"
                    fill="#3b82f6"
                    radius={[2, 2, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* MDD Distribution */}
            <div className="bg-[#0a0a0a] rounded-xl p-4">
              <p className="text-sm font-bold text-white mb-1">최대 낙폭(MDD) 분포</p>
              <p className="text-xs text-gray-600 mb-3">
                중앙값: {formatPct(result.mdd_percentiles["50"])} / 최악 5%:{" "}
                {formatPct(result.mdd_percentiles["5"])}
              </p>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={mddHistData} barCategoryGap={1}>
                  <XAxis
                    dataKey="x"
                    tick={{ fontSize: 9, fill: "#555" }}
                    tickFormatter={(v) => `${v.toFixed(0)}%`}
                    interval={Math.floor(mddHistData.length / 5)}
                  />
                  <YAxis hide />
                  <Tooltip
                    formatter={(v: number) => [v, "빈도"]}
                    labelFormatter={(l) => `${Number(l).toFixed(1)}%`}
                    contentStyle={{ background: "#111", border: "1px solid #333", fontSize: 11 }}
                  />
                  <Bar dataKey="count" fill="#f87171" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Percentile Table */}
          <div className="bg-[#0a0a0a] rounded-xl p-4">
            <p className="text-sm font-bold text-white mb-3">백분위 상세</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-white/5">
                    <th className="text-left py-2 pr-4 font-medium">백분위</th>
                    <th className="text-right py-2 pr-4 font-medium">최종 수익률</th>
                    <th className="text-right py-2 pr-4 font-medium">MDD</th>
                    <th className="text-right py-2 font-medium">Sharpe</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { pct: "1", label: "최악 1%" },
                    { pct: "5", label: "하위 5%" },
                    { pct: "25", label: "하위 25%" },
                    { pct: "50", label: "중앙값" },
                    { pct: "75", label: "상위 25%" },
                    { pct: "95", label: "상위 5%" },
                    { pct: "99", label: "최상 1%" },
                  ].map(({ pct, label }) => {
                    const ret = result.final_return_pct[pct] ?? 0;
                    const mdd = result.mdd_percentiles[pct] ?? 0;
                    const sharpe = result.sharpe_percentiles[pct] ?? 0;
                    return (
                      <tr key={pct} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                        <td className="py-2 pr-4 text-gray-400">{label}</td>
                        <td className={`py-2 pr-4 text-right font-mono font-bold ${ret >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {formatPct(ret)}
                        </td>
                        <td className={`py-2 pr-4 text-right font-mono font-bold ${Math.abs(mdd) <= 10 ? "text-green-400" : Math.abs(mdd) <= 20 ? "text-yellow-400" : "text-red-400"}`}>
                          {formatPct(mdd)}
                        </td>
                        <td className={`py-2 text-right font-mono font-bold ${sharpe >= 1.5 ? "text-green-400" : sharpe >= 1.0 ? "text-yellow-400" : "text-red-400"}`}>
                          {sharpe.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
