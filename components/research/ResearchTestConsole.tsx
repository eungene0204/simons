"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Play,
  StopCircle,
  ArrowClockwise,
  Flask,
  Spinner,
  Trophy,
  Warning,
} from "phosphor-react";
import { getLocale, t } from "@/lib/i18n";

// ─── types ───────────────────────────────────────────────────────────────────

interface RunSummary {
  id: string;
  status: string;
  goal: string | null;
  startedAt: string;
  finishedAt: string | null;
  totalCandidates: number;
  promotedCount: number;
  errorMessage: string | null;
}

interface RunDetail {
  run: RunSummary & { config: string; holdoutStart: string; seed: number };
  stageSummary: Record<string, number>;
}

interface TechnicalSignal {
  indicator: string;
  signal_type?: string;
  short_period?: number;
  long_period?: number;
  period?: number;
  threshold?: number;
  [key: string]: unknown;
}

interface ParsedDsl {
  description?: string;
  entry_signals?: TechnicalSignal[];
  exit_signals?: TechnicalSignal[];
  stop_loss_pct?: number;
  take_profit_pct?: number;
  trailing_stop_pct?: number;
  max_positions?: number;
  hold_period_days?: number | null;
}

interface Candidate {
  id: string;
  dslHash: string;
  template: string;
  stage: string;
  compositeScore: number | null;
  robustnessScore: number | null;
  deflatedSharpe: number | null;
  holdoutMetrics: string | null;
  prescreenMetrics: string | null;
  rejectionReason: string | null;
  dslJson: string | null;
}

// ─── constants ───────────────────────────────────────────────────────────────

const TEMPLATES = ["momentum", "mean_reversion", "value", "volume_breakout", "ai_signal"];

const TEMPLATE_LABELS: Record<string, string> = {
  momentum:        "모멘텀",
  mean_reversion:  "평균회귀",
  value:           "가치",
  volume_breakout: "거래량 돌파",
  ai_signal:       "AI 시그널",
};

const PIPELINE_STAGES = [
  "GENERATING",
  "PRESCREEN",
  "ROBUSTNESS",
  "OPTIMIZING",
  "HOLDOUT_VAL",
  "COMPLETED",
];

const STATUS_COLORS: Record<string, string> = {
  PENDING:    "text-gray-400 bg-white/[0.05]",
  GENERATING: "text-sky-400 bg-sky-500/10",
  PRESCREEN:  "text-indigo-400 bg-indigo-500/10",
  ROBUSTNESS: "text-purple-400 bg-purple-500/10",
  OPTIMIZING: "text-amber-400 bg-amber-500/10",
  HOLDOUT_VAL:"text-orange-400 bg-orange-500/10",
  COMPLETED:  "text-emerald-400 bg-emerald-500/10",
  FAILED:     "text-red-400 bg-red-500/10",
  CANCELLED:  "text-gray-500 bg-white/[0.03]",
};

const STAGE_LABELS: Record<string, string> = {
  GENERATED:         "생성됨",
  PRESCREEN_PASSED:  "사전통과",
  ROBUSTNESS_PASSED: "강건성통과",
  OPTIMIZED:         "최적화완료",
  APPROVED:          "승인",
  REJECTED:          "탈락",
  PROMOTED:          "승격됨",
};

function localizeRejectionReason(reason: string | null): string {
  if (!reason) return "—";

  // holdout
  if (reason.startsWith("holdout_failed")) {
    const dsr = reason.match(/dsr=([-\d.]+)/)?.[1];
    return dsr
      ? t("홀드아웃 실패 (편향보정 샤프 {0})", parseFloat(dsr).toFixed(2))
      : t("홀드아웃 검증 실패");
  }
  if (reason.startsWith("holdout_error:")) {
    return t("홀드아웃 오류: {0}", reason.replace("holdout_error:", "").trim());
  }

  // prescreen gates
  const tradeMin = reason.match(/^trades (\d+) < min (\d+)$/);
  if (tradeMin) return t("거래 횟수 부족 ({0}회 < 최소 {1}회)", tradeMin[1], tradeMin[2]);

  const tradeDensity = reason.match(/^trade density ([\d.]+)\/y < ([\d.]+)$/);
  if (tradeDensity) return t("연간 거래 빈도 부족 ({0}회/년)", tradeDensity[1]);

  const cagr = reason.match(/^cagr ([-\d.]+) < ([\d.]+)×benchmark$/);
  if (cagr) return t("수익률 미달 (CAGR {0}%)", (parseFloat(cagr[1]) * 100).toFixed(1));

  const pf = reason.match(/^profitFactor ([\d.]+) < ([\d.]+)$/);
  if (pf) return t("수익비 미달 ({0} < {1})", pf[1], pf[2]);

  const mdd = reason.match(/^maxDrawdown ([\d.]+) > ([\d.]+)$/);
  if (mdd) return t("최대낙폭 초과 ({0}% > {1}%)", (parseFloat(mdd[1]) * 100).toFixed(1), (parseFloat(mdd[2]) * 100).toFixed(0));

  // robustness gates
  const wfe = reason.match(/^wfe ([\d.]+) < ([\d.]+)$/);
  if (wfe) return t("워크포워드 효율 부족 ({0} < {1})", parseFloat(wfe[1]).toFixed(2), wfe[2]);

  const mcCagr = reason.match(/^mc_cagr_p05 ([-\d.]+) < ([-\d.]+)$/);
  if (mcCagr) return t("몬테카를로 CAGR 5%값 미달 ({0}%)", (parseFloat(mcCagr[1]) * 100).toFixed(1));

  const mcMdd = reason.match(/^mc_mdd_p95 ([\d.]+) > ([\d.]+)$/);
  if (mcMdd) return t("몬테카를로 MDD 95%값 초과 ({0}%)", (parseFloat(mcMdd[1]) * 100).toFixed(1));

  // errors
  if (reason.startsWith("backtest_error:")) return t("백테스트 오류: {0}", reason.replace("backtest_error:", "").trim());
  if (reason.startsWith("base_backtest_error:")) return t("백테스트 오류: {0}", reason.replace("base_backtest_error:", "").trim());
  if (reason.startsWith("ai_guard:")) return t("AI 데이터 누수 감지: {0}", reason.replace("ai_guard:", "").trim());
  if (reason.startsWith("circuit_breaker:")) return t("연속 실패 중단 (서킷브레이커)");

  return reason;
}

function formatSignal(s: TechnicalSignal): string {
  const ind = s.indicator ?? "";
  switch (ind) {
    case "ma_crossover":
      return t("MA 골든/데드크로스 ({0}일 / {1}일)", s.short_period, s.long_period);
    case "ema":
      return t("EMA {0}일 {1}", s.period, s.signal_type === "buy" ? t("상향돌파") : t("하향이탈"));
    case "rsi":
      return t("RSI {0}일 {1}", s.period, s.signal_type === "buy" ? `≤ ${s.threshold}` : `≥ ${s.threshold}`);
    case "macd":
      return t("MACD 시그널 {0}", s.signal_type === "buy" ? t("상향교차") : t("하향교차"));
    case "bollinger_bands":
      return t("볼린저밴드 {0}", s.signal_type === "buy" ? t("하단 터치") : t("상단 터치"));
    case "stochastic":
      return t("스토캐스틱 {0}", s.signal_type === "buy" ? `≤ ${s.threshold}` : `≥ ${s.threshold}`);
    case "cci":
      return t("CCI {0}일 {1}", s.period, s.signal_type === "buy" ? `≤ ${s.threshold}` : `≥ ${s.threshold}`);
    case "adx":
      return t("ADX {0}일 ≥ {1} (추세 강도)", s.period, s.threshold);
    case "volume_spike":
      return t("거래량 급증 (OBV {0}일 평균 상향 돌파)", s.period ?? 20);
    case "breakout":
      return t("가격 돌파 ({0}일 고점)", s.period);
    case "ai_model":
      return t("AI 매수 신호");
    case "ai_drop_model":
      return t("AI 하락 예측 신호");
    default:
      return ind;
  }
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-gray-500";
  if (score >= 0.8) return "text-emerald-400";
  if (score >= 0.6) return "text-blue-400";
  if (score >= 0.4) return "text-amber-400";
  return "text-red-400";
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(getLocale(), { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// ─── component ───────────────────────────────────────────────────────────────

export default function ResearchTestConsole() {
  // form state
  const [goal, setGoal] = useState(t("테스트 연구 런"));
  const [templates, setTemplates] = useState<string[]>(["momentum", "mean_reversion"]);
  const [universe, setUniverse] = useState("KOSPI200");
  const [maxCandidates, setMaxCandidates] = useState(20);
  const [optunaTrials, setOptunaTrials] = useState(20);
  const [wfaSplits, setWfaSplits] = useState(3);
  const [holdoutStart, setHoldoutStart] = useState("");

  // runtime state
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [eventLog, setEventLog] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedCandId, setExpandedCandId] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // ── fetch helpers ────────────────────────────────────────────────────────

  const fetchRuns = useCallback(async () => {
    const res = await fetch("/api/research/proxy/runs");
    if (res.ok) {
      const data = await res.json();
      setRuns(data.runs ?? []);
    }
  }, []);

  const fetchRunDetail = useCallback(async (runId: string) => {
    const [detailRes, candRes] = await Promise.all([
      fetch(`/api/research/proxy/runs/${runId}`),
      fetch(`/api/research/proxy/runs/${runId}/candidates?limit=100`),
    ]);
    if (detailRes.ok) setRunDetail(await detailRes.json());
    if (candRes.ok) {
      const data = await candRes.json();
      setCandidates(data.candidates ?? []);
    }
  }, []);

  // ── poll runs list ───────────────────────────────────────────────────────

  useEffect(() => {
    fetchRuns();
    const id = setInterval(fetchRuns, 6000);
    return () => clearInterval(id);
  }, [fetchRuns]);

  // ── fetch detail when selection changes ─────────────────────────────────

  useEffect(() => {
    if (!selectedRunId) return;
    setRunDetail(null);
    setCandidates([]);
    fetchRunDetail(selectedRunId);
  }, [selectedRunId, fetchRunDetail]);

  // ── SSE stream ──────────────────────────────────────────────────────────

  function startStream(runId: string) {
    esRef.current?.close();
    setEventLog([]);
    setIsStreaming(true);

    const es = new EventSource(`/api/research/proxy/runs/${runId}/stream`);
    esRef.current = es;

    const appendLog = (label: string, data: string) => {
      try {
        const parsed = JSON.parse(data);
        const msg = `[${new Date().toLocaleTimeString(getLocale())}] ${label}: ${JSON.stringify(parsed)}`;
        setEventLog((prev) => [...prev.slice(-300), msg]);
        setTimeout(() => {
          logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
        }, 30);
      } catch {
        setEventLog((prev) => [...prev.slice(-300), `[${label}] ${data}`]);
      }
    };

    const allEvents = [
      "ready", "stage_start", "generated", "prescreen", "robustness",
      "optimized", "optimize_skipped", "optimize_error",
      "holdout_passed", "holdout_rejected", "holdout_error",
      "finalized", "run_completed", "run_failed",
    ];

    allEvents.forEach((evt) => {
      es.addEventListener(evt, (e: MessageEvent) => {
        appendLog(evt, e.data);
        if (evt === "run_completed" || evt === "run_failed") {
          es.close();
          setIsStreaming(false);
          fetchRuns();
          fetchRunDetail(runId);
        }
      });
    });

    es.onerror = () => {
      setIsStreaming(false);
      es.close();
    };
  }

  function stopStream() {
    esRef.current?.close();
    setIsStreaming(false);
  }

  useEffect(() => () => esRef.current?.close(), []);

  // ── create run ──────────────────────────────────────────────────────────

  async function createRun() {
    if (templates.length === 0) {
      setError(t("최소 1개 이상의 템플릿을 선택하세요"));
      return;
    }
    setIsCreating(true);
    setError(null);

    const body = {
      goal: goal || undefined,
      templates,
      universes: [[universe]],
      max_candidates: maxCandidates,
      optuna_trials: optunaTrials,
      wfa_splits: wfaSplits,
      holdout_start: holdoutStart || undefined,
    };

    const res = await fetch("/api/research/proxy/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    setIsCreating(false);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: t("알 수 없는 오류") }));
      const msg = err.detail || err.error || t("Run 생성 실패");
      setError(
        res.status === 402
          ? t("PREMIUM 플랜 유저만 사용 가능합니다 (DB에서 planTier를 PREMIUM으로 변경해주세요)")
          : msg
      );
      return;
    }

    const data = await res.json();
    await fetchRuns();
    setSelectedRunId(data.runId);
    startStream(data.runId);
  }

  // ── toggle template ──────────────────────────────────────────────────────

  function toggleTemplate(tv: string) {
    setTemplates((prev) =>
      prev.includes(tv) ? prev.filter((x) => x !== tv) : [...prev, tv]
    );
  }

  // ── helpers ──────────────────────────────────────────────────────────────

  const activeRun = runs.find((r) => r.id === selectedRunId);
  const stageIdx = activeRun ? PIPELINE_STAGES.indexOf(activeRun.status) : -1;

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="p-4 space-y-4 min-h-screen" style={{ background: "var(--background)", color: "var(--foreground)" }}>

      {/* Header */}
      <div className="flex items-center gap-3 pb-2 border-b border-white/[0.08]">
        <Flask size={22} weight="bold" className="text-indigo-400" />
        <div>
          <h1 className="text-base font-black uppercase tracking-widest font-outfit text-white">
            Strategy Research Agent
          </h1>
          <p className="text-xs text-gray-500">{t("테스트 콘솔 — 전략 자동 탐색 파이프라인")}</p>
        </div>
        <button
          onClick={fetchRuns}
          className="ml-auto p-1.5 rounded hover:bg-white/[0.06] text-gray-500 hover:text-gray-300 transition-colors"
          title={t("새로고침")}
        >
          <ArrowClockwise size={16} />
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[340px_1fr] gap-4">

        {/* ── LEFT: Config form ─────────────────────────────────────────── */}
        <div className="space-y-3">
          <div
            className="rounded-lg p-4 space-y-4"
            style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)" }}
          >
            <p className="text-xs font-black uppercase tracking-widest text-gray-400 font-outfit">
              {t("Run 설정")}
            </p>

            {/* Goal */}
            <div className="space-y-1">
              <label className="text-xs font-bold text-gray-500">{t("목표")}</label>
              <input
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder={t("예: 고Sharpe 모멘텀 전략 탐색")}
                className="w-full text-sm bg-white/[0.04] border border-white/[0.08] rounded px-3 py-1.5 text-white placeholder-gray-600 focus:outline-none focus:border-white/20"
              />
            </div>

            {/* Templates */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-gray-500">{t("템플릿")}</label>
              <div className="flex flex-wrap gap-1.5">
                {TEMPLATES.map((tv) => (
                  <button
                    key={tv}
                    onClick={() => toggleTemplate(tv)}
                    className={`text-xs font-bold px-2.5 py-1 rounded transition-colors ${
                      templates.includes(tv)
                        ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                        : "bg-white/[0.04] text-gray-500 border border-white/[0.06] hover:text-gray-300"
                    }`}
                  >
                    {t(TEMPLATE_LABELS[tv])}
                  </button>
                ))}
              </div>
            </div>

            {/* Universe */}
            <div className="space-y-1">
              <label className="text-xs font-bold text-gray-500">{t("유니버스")}</label>
              <div className="flex gap-1.5">
                {["KOSPI200", "KOSPI", "KOSDAQ"].map((u) => (
                  <button
                    key={u}
                    onClick={() => setUniverse(u)}
                    className={`text-xs font-bold px-2.5 py-1 rounded transition-colors ${
                      universe === u
                        ? "bg-sky-500/20 text-sky-300 border border-sky-500/30"
                        : "bg-white/[0.04] text-gray-500 border border-white/[0.06] hover:text-gray-300"
                    }`}
                  >
                    {u}
                  </button>
                ))}
              </div>
            </div>

            {/* Numeric params */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: t("후보 수"), value: maxCandidates, set: setMaxCandidates, min: 10, max: 500 },
                { label: t("Optuna 시도"), value: optunaTrials, set: setOptunaTrials, min: 10, max: 200 },
                { label: t("WFA 분할"), value: wfaSplits, set: setWfaSplits, min: 3, max: 10 },
              ].map(({ label, value, set, min, max }) => (
                <div key={label} className="space-y-1">
                  <label className="text-xs font-bold text-gray-500">{label}</label>
                  <input
                    type="number"
                    value={value}
                    min={min}
                    max={max}
                    onChange={(e) => set(Number(e.target.value))}
                    className="w-full text-sm bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1.5 text-white focus:outline-none focus:border-white/20 tabular-nums"
                  />
                </div>
              ))}
            </div>

            {/* Holdout start */}
            <div className="space-y-1">
              <label className="text-xs font-bold text-gray-500">{t("홀드아웃 시작 (빈칸 = 자동)")}</label>
              <input
                type="date"
                value={holdoutStart}
                onChange={(e) => setHoldoutStart(e.target.value)}
                className="w-full text-sm bg-white/[0.04] border border-white/[0.08] rounded px-3 py-1.5 text-white focus:outline-none focus:border-white/20"
              />
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-start gap-2 p-3 rounded bg-red-500/10 border border-red-500/20">
                <Warning size={14} className="text-red-400 mt-0.5 shrink-0" />
                <p className="text-xs text-red-300">{error}</p>
              </div>
            )}

            {/* Start button */}
            <button
              onClick={createRun}
              disabled={isCreating}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded font-bold text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors"
            >
              {isCreating ? (
                <Spinner size={16} className="animate-spin" />
              ) : (
                <Play size={16} weight="fill" />
              )}
              {isCreating ? t("생성 중...") : t("Run 시작")}
            </button>
          </div>

          {/* Quick tip */}
          <div
            className="rounded-lg p-3"
            style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}
          >
            <p className="text-xs text-gray-600 leading-relaxed">
              <span className="text-gray-500 font-bold">TIP</span>{t(" — PREMIUM 플랜이 필요합니다. 개발 테스트 시 SQLite에서")}{" "}
              <code className="bg-white/[0.06] px-1 rounded text-gray-400">UPDATE User SET planTier=&apos;PREMIUM&apos;</code>
              {t("으로 변경 후 사용하세요.")}
            </p>
          </div>
        </div>

        {/* ── RIGHT: Runs + Detail ───────────────────────────────────────── */}
        <div className="space-y-3 min-w-0">

          {/* Runs table */}
          <div
            className="rounded-lg overflow-hidden"
            style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)" }}
          >
            <div className="px-4 py-3 border-b border-white/[0.06] flex items-center gap-2">
              <p className="text-xs font-black uppercase tracking-widest text-gray-400 font-outfit flex-1">
                Research Runs
              </p>
              <span className="text-xs text-gray-600">{t("{0}개", runs.length)}</span>
            </div>
            {runs.length === 0 ? (
              <div className="py-8 text-center text-sm text-gray-600">
                {t("아직 실행된 Run이 없습니다")}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/[0.04]">
                      {["Run ID", "상태", "목표", "후보", "시작"].map((h) => (
                        <th key={h} className="px-4 py-2 text-left font-bold text-gray-600 uppercase tracking-wider">
                          {t(h)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr
                        key={r.id}
                        onClick={() => setSelectedRunId(r.id)}
                        className={`border-b border-white/[0.03] cursor-pointer transition-colors ${
                          r.id === selectedRunId
                            ? "bg-indigo-500/10"
                            : "hover:bg-white/[0.03]"
                        }`}
                      >
                        <td className="px-4 py-2.5 font-mono text-gray-500">{r.id.slice(0, 12)}…</td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-flex items-center gap-1 font-bold px-2 py-0.5 rounded text-[10px] uppercase ${STATUS_COLORS[r.status] ?? "text-gray-400 bg-white/[0.05]"}`}>
                            {r.status}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-gray-300 max-w-[160px] truncate">{r.goal || "—"}</td>
                        <td className="px-4 py-2.5 text-gray-400 tabular-nums">{r.totalCandidates}</td>
                        <td className="px-4 py-2.5 text-gray-500 tabular-nums">{fmtDate(r.startedAt)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Run detail */}
          {selectedRunId && (
            <div className="space-y-3">

              {/* Pipeline progress */}
              <div
                className="rounded-lg p-4"
                style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)" }}
              >
                <div className="flex items-center gap-2 mb-3">
                  <p className="text-xs font-black uppercase tracking-widest text-gray-400 font-outfit flex-1">
                    {t("파이프라인 진행")}
                  </p>
                  {isStreaming && (
                    <button
                      onClick={stopStream}
                      className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300"
                    >
                      <StopCircle size={14} />
                      {t("스트림 중지")}
                    </button>
                  )}
                  {!isStreaming && activeRun && !["COMPLETED", "FAILED", "CANCELLED"].includes(activeRun.status) && (
                    <button
                      onClick={() => startStream(selectedRunId)}
                      className="flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300"
                    >
                      <ArrowClockwise size={14} />
                      {t("스트림 재연결")}
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {PIPELINE_STAGES.map((stage, i) => {
                    const done = stageIdx > i;
                    const active = stageIdx === i;
                    return (
                      <div key={stage} className="flex items-center gap-1 flex-1">
                        <div className={`flex flex-col items-center gap-1 flex-1 ${i > 0 ? "" : ""}`}>
                          <div className="w-full flex items-center gap-1">
                            {i > 0 && (
                              <div className={`h-px flex-1 ${done || active ? "bg-indigo-500/60" : "bg-white/[0.06]"}`} />
                            )}
                            <div className={`w-2 h-2 rounded-full shrink-0 ${
                              done ? "bg-emerald-400" : active ? "bg-indigo-400" : "bg-white/[0.1]"
                            }`} />
                            {i < PIPELINE_STAGES.length - 1 && (
                              <div className={`h-px flex-1 ${done ? "bg-indigo-500/60" : "bg-white/[0.06]"}`} />
                            )}
                          </div>
                          <span className={`text-[10px] font-bold whitespace-nowrap ${
                            done ? "text-emerald-400" : active ? "text-indigo-300" : "text-gray-600"
                          }`}>
                            {stage}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Stage summary counts */}
                {runDetail && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {Object.entries(runDetail.stageSummary).map(([stage, count]) => (
                      <span
                        key={stage}
                        className="text-[10px] font-bold px-2 py-0.5 rounded bg-white/[0.04] text-gray-500"
                      >
                        {stage}: <span className="text-gray-300 tabular-nums">{count}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Event log */}
              <div
                className="rounded-lg overflow-hidden"
                style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)" }}
              >
                <div className="px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-2">
                  <p className="text-xs font-black uppercase tracking-widest text-gray-400 font-outfit flex-1">
                    {t("이벤트 로그")}
                  </p>
                  {isStreaming && (
                    <span className="flex items-center gap-1 text-[10px] text-sky-400 font-bold">
                      <Spinner size={10} className="animate-spin" />
                      LIVE
                    </span>
                  )}
                  <button
                    onClick={() => setEventLog([])}
                    className="text-[10px] text-gray-600 hover:text-gray-400"
                  >
                    {t("지우기")}
                  </button>
                </div>
                <div
                  ref={logRef}
                  className="h-48 overflow-y-auto p-3 font-mono"
                  style={{ background: "rgba(0,0,0,0.3)" }}
                >
                  {eventLog.length === 0 ? (
                    <p className="text-xs text-gray-700">{t("이벤트가 없습니다. Run을 시작하면 실시간 이벤트가 표시됩니다.")}</p>
                  ) : (
                    eventLog.map((line, i) => (
                      <p key={i} className="text-[11px] text-gray-400 leading-relaxed">
                        {line}
                      </p>
                    ))
                  )}
                </div>
              </div>

              {/* Candidates */}
              {candidates.length > 0 && (
                <div
                  className="rounded-lg overflow-hidden"
                  style={{ background: "var(--card-bg)", border: "1px solid var(--card-border)" }}
                >
                  <div className="px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-2">
                    <Trophy size={14} className="text-amber-400" />
                    <p className="text-xs font-black uppercase tracking-widest text-gray-400 font-outfit flex-1">
                      {t("후보 결과")}
                    </p>
                    <span className="text-xs text-gray-600">{t("{0}개", candidates.length)}</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-white/[0.04]">
                          {["전략 설명", "단계", "종합점수", "강건성", "홀드아웃 CAGR", "탈락 사유"].map((h) => (
                            <th key={h} className="px-3 py-2 text-left font-bold text-gray-600 uppercase tracking-wider whitespace-nowrap">
                              {t(h)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {candidates.map((c) => {
                          const dsl: ParsedDsl | null = (() => {
                            try { return c.dslJson ? JSON.parse(c.dslJson) : null; } catch { return null; }
                          })();
                          const holdoutCagr = (() => {
                            try {
                              const m = c.holdoutMetrics ? JSON.parse(c.holdoutMetrics) : null;
                              return m?.cagr != null ? `${(m.cagr * 100).toFixed(1)}%` : null;
                            } catch { return null; }
                          })();
                          const isExpanded = expandedCandId === c.id;

                          return (
                            <>
                              <tr
                                key={c.id}
                                onClick={() => setExpandedCandId(isExpanded ? null : c.id)}
                                className={`border-b border-white/[0.03] cursor-pointer transition-colors ${isExpanded ? "bg-white/[0.04]" : "hover:bg-white/[0.02]"}`}
                              >
                                {/* 전략 설명 */}
                                <td className="px-3 py-2.5 max-w-[260px]">
                                  <p className="font-bold text-gray-200 truncate">{dsl?.description ?? c.template}</p>
                                  <p className="text-[10px] text-gray-600 mt-0.5">{t(TEMPLATE_LABELS[c.template] ?? c.template)}</p>
                                </td>
                                {/* 단계 */}
                                <td className="px-3 py-2.5">
                                  <span className={`inline-flex font-bold px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[c.stage] ?? "text-gray-400 bg-white/[0.05]"}`}>
                                    {t(STAGE_LABELS[c.stage] ?? c.stage)}
                                  </span>
                                </td>
                                {/* 종합점수 */}
                                <td className={`px-3 py-2.5 font-bold tabular-nums ${scoreColor(c.compositeScore)}`}>
                                  {c.compositeScore != null ? c.compositeScore.toFixed(3) : "—"}
                                </td>
                                {/* 강건성 */}
                                <td className={`px-3 py-2.5 tabular-nums ${scoreColor(c.robustnessScore)}`}>
                                  {c.robustnessScore != null ? c.robustnessScore.toFixed(3) : "—"}
                                </td>
                                {/* 홀드아웃 */}
                                <td className="px-3 py-2.5 text-gray-400 tabular-nums">{holdoutCagr ?? "—"}</td>
                                {/* 탈락 사유 */}
                                <td className="px-3 py-2.5 text-gray-500 max-w-[220px] truncate">
                                  {c.stage === "REJECTED"
                                    ? <span className="text-red-400">{localizeRejectionReason(c.rejectionReason)}</span>
                                    : "—"
                                  }
                                </td>
                              </tr>

                              {/* 확장 행: 전략 상세 */}
                              {isExpanded && dsl && (
                                <tr key={`${c.id}-detail`} className="border-b border-white/[0.03] bg-white/[0.02]">
                                  <td colSpan={6} className="px-4 py-3">
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[11px]">

                                      {/* 진입 조건 */}
                                      <div className="space-y-1">
                                        <p className="font-bold text-gray-500 uppercase tracking-wider">{t("진입 조건")}</p>
                                        {dsl.entry_signals?.length ? dsl.entry_signals.map((s, i) => (
                                          <p key={i} className="text-gray-300">{formatSignal(s)}</p>
                                        )) : <p className="text-gray-600">—</p>}
                                      </div>

                                      {/* 청산 조건 */}
                                      <div className="space-y-1">
                                        <p className="font-bold text-gray-500 uppercase tracking-wider">{t("청산 조건")}</p>
                                        {dsl.exit_signals?.length ? dsl.exit_signals.map((s, i) => (
                                          <p key={i} className="text-gray-300">{formatSignal(s)}</p>
                                        )) : <p className="text-gray-600">—</p>}
                                      </div>

                                      {/* 리스크 파라미터 */}
                                      <div className="space-y-1">
                                        <p className="font-bold text-gray-500 uppercase tracking-wider">{t("리스크 설정")}</p>
                                        {dsl.stop_loss_pct != null && <p className="text-gray-300">{t("손절: ")}<span className="text-red-400 font-bold">{dsl.stop_loss_pct}%</span></p>}
                                        {dsl.take_profit_pct != null && <p className="text-gray-300">{t("익절: ")}<span className="text-emerald-400 font-bold">{dsl.take_profit_pct}%</span></p>}
                                        {dsl.trailing_stop_pct != null && <p className="text-gray-300">{t("트레일링스탑: ")}<span className="text-amber-400 font-bold">{dsl.trailing_stop_pct}%</span></p>}
                                        {dsl.max_positions != null && <p className="text-gray-300">{t("최대 보유 종목: ")}<span className="text-gray-200 font-bold">{t("{0}개", dsl.max_positions)}</span></p>}
                                        {dsl.hold_period_days != null && <p className="text-gray-300">{t("최대 보유일: ")}<span className="text-gray-200 font-bold">{t("{0}일", dsl.hold_period_days)}</span></p>}
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
