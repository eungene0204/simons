"use client";

import { useState, useRef } from "react";
import { X, ArrowsClockwise, ChartLine, CheckCircle, Warning } from "phosphor-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface WalkForwardSettings {
  n_splits: number;
  train_pct: number;
  anchor: boolean;
  target_metric: string;
  n_trials: number;
}

interface WindowResult {
  window: number;
  is_period: string;
  oos_period: string;
  best_params: Record<string, any>;
  is_metrics: Record<string, any>;
  oos_metrics: Record<string, any>;
  oos_equity: number[];
  oos_dates: string[];
  error?: string;
}

interface WalkForwardResult {
  status: string;
  message?: string;
  n_splits: number;
  anchor: boolean;
  target_metric: string;
  windows: WindowResult[];
  aggregate: Record<string, number>;
  combined_equity: number[];
  combined_dates: string[];
  walk_forward_efficiency: number;
}

interface WalkForwardModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRun: (settings: WalkForwardSettings) => Promise<WalkForwardResult>;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmt = (v: any, suffix = "%") => {
  if (v === null || v === undefined) return "-";
  const n = typeof v === "number" ? v : Number(v);
  if (isNaN(n)) return "-";
  return `${n.toFixed(2)}${suffix}`;
};

const fmtNum = (v: any, decimals = 2) => {
  if (v === null || v === undefined) return "-";
  const n = typeof v === "number" ? v : Number(v);
  if (isNaN(n)) return "-";
  return n.toFixed(decimals);
};

const WFE_LABEL = (wfe: number) => {
  if (wfe >= 0.7) return { text: "우수", color: "text-green-400", bg: "bg-green-400/10 border-green-400/30" };
  if (wfe >= 0.4) return { text: "보통", color: "text-yellow-400", bg: "bg-yellow-400/10 border-yellow-400/30" };
  return { text: "미흡", color: "text-red-400", bg: "bg-red-400/10 border-red-400/30" };
};

const TARGET_METRICS = [
  { id: "cagr", label: "CAGR" },
  { id: "sharpe", label: "샤프 지수" },
  { id: "totalReturn", label: "총 수익률" },
  { id: "profitFactor", label: "손익비" },
  { id: "winRate", label: "승률" },
];

// ─── Component ───────────────────────────────────────────────────────────────

export default function WalkForwardModal({ open, onOpenChange, onRun }: WalkForwardModalProps) {
  const [settings, setSettings] = useState<WalkForwardSettings>({
    n_splits: 5,
    train_pct: 0.7,
    anchor: false,
    target_metric: "cagr",
    n_trials: 30,
  });
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<WalkForwardResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  if (!open) return null;

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    setResult(null);

    try {
      const res = await onRun(settings);
      if (res.status === "error") {
        setError(res.message || "분석 중 오류가 발생했습니다.");
      } else {
        setResult(res);
      }
    } catch (e: any) {
      setError(e.message || "알 수 없는 오류가 발생했습니다.");
    } finally {
      setIsRunning(false);
      abortRef.current = null;
    }
  };

  const handleClose = () => {
    if (!isRunning) onOpenChange(false);
  };

  // Equity chart data
  const chartData = result?.combined_dates?.map((d, i) => ({
    date: d,
    equity: result.combined_equity[i] ?? null,
  })) ?? [];

  // Thin date labels for x-axis
  const xTickFormatter = (val: string) => val?.slice(0, 7) ?? "";

  const wfe = result?.walk_forward_efficiency ?? 0;
  const wfeLabel = WFE_LABEL(wfe);

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-start justify-center p-4 pt-20 bg-black/70 backdrop-blur-md"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-4xl bg-[#111] rounded-2xl shadow-2xl flex flex-col border border-white/10 overflow-hidden max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-white/[0.06] rounded-xl flex items-center justify-center border border-white/10">
              <ChartLine className="w-5 h-5 text-gray-200" weight="bold" />
            </div>
            <div>
              <h2 className="text-base font-black text-white">워크포워드 분석</h2>
              <p className="text-[11px] text-white/40 font-medium">훈련/검증 기간 분할로 전략 과적합을 검증합니다</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={isRunning}
            className="p-2 rounded-lg hover:bg-white/5 text-white/40 hover:text-white transition-colors disabled:opacity-40"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {/* Settings */}
          {!result && (
            <div className="p-6 space-y-6">
              <div className="grid grid-cols-2 gap-6">
                {/* n_splits */}
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-white/40 uppercase tracking-widest">
                    분할 수 (Windows)
                  </label>
                  <div className="flex gap-2 flex-wrap">
                    {[3, 4, 5, 6, 8].map((n) => (
                      <button
                        key={n}
                        onClick={() => setSettings((s) => ({ ...s, n_splits: n }))}
                        className={`px-3 py-1.5 rounded-lg text-sm font-bold border transition-all ${
                          settings.n_splits === n
                            ? "bg-white/10 border-white/15 text-white"
                            : "bg-white/5 border-white/10 text-white/50 hover:text-white"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>

                {/* train_pct */}
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-white/40 uppercase tracking-widest">
                    훈련 비율 (IS %)
                  </label>
                  <div className="flex gap-2 flex-wrap">
                    {[
                      { v: 0.6, label: "60%" },
                      { v: 0.7, label: "70%" },
                      { v: 0.75, label: "75%" },
                      { v: 0.8, label: "80%" },
                    ].map(({ v, label }) => (
                      <button
                        key={v}
                        onClick={() => setSettings((s) => ({ ...s, train_pct: v }))}
                        className={`px-3 py-1.5 rounded-lg text-sm font-bold border transition-all ${
                          settings.train_pct === v
                            ? "bg-white/10 border-white/15 text-white"
                            : "bg-white/5 border-white/10 text-white/50 hover:text-white"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* target_metric */}
                <div className="space-y-2">
                  <label className="text-[10px] font-black text-white/40 uppercase tracking-widest">
                    최적화 목표 지표
                  </label>
                  <div className="flex gap-2 flex-wrap">
                    {TARGET_METRICS.map(({ id, label }) => (
                      <button
                        key={id}
                        onClick={() => setSettings((s) => ({ ...s, target_metric: id }))}
                        className={`px-3 py-1.5 rounded-lg text-sm font-bold border transition-all ${
                          settings.target_metric === id
                            ? "bg-white/10 border-white/15 text-white"
                            : "bg-white/5 border-white/10 text-white/50 hover:text-white"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* n_trials & anchor */}
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-white/40 uppercase tracking-widest">
                      Optuna 시도 횟수
                    </label>
                    <div className="flex gap-2 flex-wrap">
                      {[20, 30, 50].map((n) => (
                        <button
                          key={n}
                          onClick={() => setSettings((s) => ({ ...s, n_trials: n }))}
                          className={`px-3 py-1.5 rounded-lg text-sm font-bold border transition-all ${
                            settings.n_trials === n
                              ? "bg-white/10 border-white/15 text-white"
                              : "bg-white/5 border-white/10 text-white/50 hover:text-white"
                          }`}
                        >
                          {n}회
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black text-white/40 uppercase tracking-widest">
                      IS 창 방식
                    </label>
                    <div className="flex gap-2">
                      {[
                        { v: false, label: "롤링 (Rolling)" },
                        { v: true, label: "확장 (Anchored)" },
                      ].map(({ v, label }) => (
                        <button
                          key={String(v)}
                          onClick={() => setSettings((s) => ({ ...s, anchor: v }))}
                          className={`px-3 py-1.5 rounded-lg text-sm font-bold border transition-all ${
                            settings.anchor === v
                              ? "bg-white/10 border-white/15 text-white"
                              : "bg-white/5 border-white/10 text-white/50 hover:text-white"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Info box */}
              <div className="bg-white/3 border border-white/8 rounded-xl p-4 text-xs text-white/40 leading-relaxed font-medium">
                <span className="text-white/60 font-black">워크포워드 분석이란? </span>
                데이터를 {settings.n_splits}개 구간으로 나눠 각 구간의 훈련 기간(IS)에서 최적 파라미터를 찾고,
                바로 다음 검증 기간(OOS)에서 성과를 측정합니다.
                {settings.anchor ? " IS 창은 항상 데이터 시작부터 확장됩니다." : " IS 창과 OOS 창이 함께 앞으로 이동합니다."}
                &nbsp;WFE (워크포워드 효율) 0.7 이상이면 전략 신뢰도가 높습니다.
                <br />
                <span className="text-yellow-400/70">⚠ 분할 수 × Optuna 시도 횟수만큼 백테스트가 실행됩니다. 시간이 오래 걸릴 수 있습니다.</span>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mx-6 mt-4 p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3">
              <Warning className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
              <p className="text-sm text-red-300 font-medium">{error}</p>
            </div>
          )}

          {/* Results */}
          {result && (
            <div className="p-6 space-y-6">
              {/* WFE + aggregate */}
              <div className="grid grid-cols-2 gap-4">
                {/* WFE */}
                <div className={`rounded-2xl border p-5 flex flex-col gap-2 ${wfeLabel.bg}`}>
                  <span className="text-[10px] font-black uppercase tracking-widest text-white/40">
                    Walk-Forward Efficiency
                  </span>
                  <div className="flex items-end gap-2">
                    <span className={`text-4xl font-black ${wfeLabel.color}`}>
                      {(wfe * 100).toFixed(1)}%
                    </span>
                    <span className={`text-sm font-black mb-1 ${wfeLabel.color}`}>
                      {wfeLabel.text}
                    </span>
                  </div>
                  <p className="text-[10px] text-white/30 font-medium leading-relaxed">
                    평균 OOS 수익률 / 평균 IS 수익률. 1.0에 가까울수록 IS 최적화 성과가 OOS에 잘 이전됩니다.
                  </p>
                </div>

                {/* Aggregate metrics */}
                <div className="rounded-2xl border border-white/8 bg-white/3 p-5">
                  <span className="text-[10px] font-black uppercase tracking-widest text-white/40 block mb-3">
                    OOS 평균 성과 ({result.n_splits}개 구간)
                  </span>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                    {[
                      { key: "avg_oos_cagr", label: "CAGR", suffix: "%" },
                      { key: "avg_oos_totalReturn", label: "총수익", suffix: "%" },
                      { key: "avg_oos_maxDrawdown", label: "MDD", suffix: "%" },
                      { key: "avg_oos_sharpe", label: "Sharpe", suffix: "" },
                      { key: "avg_oos_winRate", label: "승률", suffix: "%" },
                      { key: "avg_oos_profitFactor", label: "손익비", suffix: "" },
                    ].map(({ key, label, suffix }) => (
                      <div key={key} className="flex justify-between items-center">
                        <span className="text-[10px] text-white/40 font-medium">{label}</span>
                        <span className={`text-xs font-black ${
                          key.includes("Drawdown") || key.includes("mdd")
                            ? (result.aggregate[key] < -15 ? "text-red-400" : "text-yellow-400")
                            : (result.aggregate[key] > 0 ? "text-green-400" : "text-red-400")
                        }`}>
                          {suffix === "%" ? fmt(result.aggregate[key], "%") : fmtNum(result.aggregate[key])}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Combined OOS equity chart */}
              {chartData.length > 0 && (
                <div>
                  <span className="text-[10px] font-black uppercase tracking-widest text-white/40 block mb-3">
                    연속 OOS 에퀴티 커브
                  </span>
                  <div className="h-48 bg-white/3 border border-white/8 rounded-2xl p-4">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData}>
                        <XAxis
                          dataKey="date"
                          tickFormatter={xTickFormatter}
                          tick={{ fontSize: 9, fill: "#666" }}
                          tickLine={false}
                          axisLine={false}
                          interval={Math.floor(chartData.length / 6)}
                        />
                        <YAxis
                          tick={{ fontSize: 9, fill: "#666" }}
                          tickLine={false}
                          axisLine={false}
                          tickFormatter={(v) => `${v.toFixed(0)}`}
                          width={36}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "#1a1a1a",
                            border: "1px solid rgba(255,255,255,0.1)",
                            borderRadius: 8,
                            fontSize: 11,
                          }}
                          labelStyle={{ color: "#999" }}
                          formatter={(v: any) => [`${Number(v).toFixed(2)}`, "자산"]}
                        />
                        <ReferenceLine y={chartData[0]?.equity ?? 1} stroke="rgba(255,255,255,0.1)" strokeDasharray="3 3" />
                        <Line
                          type="monotone"
                          dataKey="equity"
                          stroke="#a855f7"
                          strokeWidth={2}
                          dot={false}
                          activeDot={{ r: 3, fill: "#a855f7" }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Per-window table */}
              <div>
                <span className="text-[10px] font-black uppercase tracking-widest text-white/40 block mb-3">
                  구간별 결과
                </span>
                <div className="rounded-2xl border border-white/8 overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-white/[0.06]">
                        <th className="text-left px-4 py-3 text-[10px] font-black text-white/40 uppercase tracking-wider">구간</th>
                        <th className="text-left px-4 py-3 text-[10px] font-black text-white/40 uppercase tracking-wider">IS 기간</th>
                        <th className="text-left px-4 py-3 text-[10px] font-black text-white/40 uppercase tracking-wider">OOS 기간</th>
                        <th className="text-right px-4 py-3 text-[10px] font-black text-white/40 uppercase tracking-wider">IS CAGR</th>
                        <th className="text-right px-4 py-3 text-[10px] font-black text-white/40 uppercase tracking-wider">OOS CAGR</th>
                        <th className="text-right px-4 py-3 text-[10px] font-black text-white/40 uppercase tracking-wider">OOS MDD</th>
                        <th className="text-right px-4 py-3 text-[10px] font-black text-white/40 uppercase tracking-wider">OOS 승률</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.windows.map((w) => {
                        const oosReturn = w.oos_metrics?.totalReturn;
                        const isPositive = typeof oosReturn === "number" && oosReturn > 0;
                        return (
                          <tr
                            key={w.window}
                            className="hover:bg-white/[0.02] transition-colors"
                          >
                            <td className="px-4 py-3 font-black text-white/60">
                              W{w.window}
                              {w.error && (
                                <span className="ml-2 text-red-400 text-[10px]">(오류)</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-white/40 font-mono text-[10px]">{w.is_period}</td>
                            <td className="px-4 py-3 text-white/40 font-mono text-[10px]">{w.oos_period}</td>
                            <td className="px-4 py-3 text-right font-bold text-white/60">
                              {fmt(w.is_metrics?.cagr, "%")}
                            </td>
                            <td className={`px-4 py-3 text-right font-black ${isPositive ? "text-green-400" : "text-red-400"}`}>
                              {fmt(w.oos_metrics?.cagr, "%")}
                            </td>
                            <td className="px-4 py-3 text-right font-bold text-red-400/80">
                              {fmt(w.oos_metrics?.maxDrawdown, "%")}
                            </td>
                            <td className="px-4 py-3 text-right font-bold text-white/60">
                              {fmt(w.oos_metrics?.winRate, "%")}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Best params summary for each window */}
              <div>
                <span className="text-[10px] font-black uppercase tracking-widest text-white/40 block mb-3">
                  구간별 최적 파라미터
                </span>
                <div className="space-y-2">
                  {result.windows.map((w) => {
                    const params = w.best_params;
                    const paramEntries = Object.entries(params);
                    if (paramEntries.length === 0) return null;
                    return (
                      <div key={w.window} className="bg-white/3 border border-white/8 rounded-xl px-4 py-3">
                        <div className="flex items-start gap-3 flex-wrap">
                          <span className="text-[10px] font-black text-gray-300 mt-0.5 shrink-0">W{w.window}</span>
                          <div className="flex flex-wrap gap-2">
                            {paramEntries.slice(0, 8).map(([k, v]) => {
                              // Show only the last segment of the key path
                              const shortKey = k.split(".").pop() ?? k;
                              return (
                                <span key={k} className="text-[10px] bg-white/5 border border-white/10 px-2 py-0.5 rounded font-mono text-white/50">
                                  {shortKey}: <span className="text-white/80">{String(v)}</span>
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-white/5 flex justify-between items-center">
          {result ? (
            <button
              onClick={() => { setResult(null); setError(null); }}
              className="text-sm font-bold text-white/40 hover:text-white transition-colors"
            >
              재설정
            </button>
          ) : (
            <div />
          )}
          <div className="flex gap-3">
            <button
              onClick={handleClose}
              disabled={isRunning}
              className="px-4 py-2 text-sm font-bold text-white/40 hover:text-white rounded-lg bg-white/5 border border-white/8 transition-all disabled:opacity-40"
            >
              닫기
            </button>
            {!result && (
              <button
                onClick={handleRun}
                disabled={isRunning}
                className="px-5 py-2 text-sm font-black text-black bg-white hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isRunning ? (
                  <>
                    <ArrowsClockwise className="w-4 h-4 animate-spin" />
                    분석 중... ({settings.n_splits}개 구간)
                  </>
                ) : (
                  <>
                    <ChartLine className="w-4 h-4" />
                    워크포워드 분석 시작
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
