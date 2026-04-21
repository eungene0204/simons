"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  ArrowLeft,
  ArrowsClockwise,
  Bank,
  ChartLineUp,
  CheckCircle,
  ClockCounterClockwise,
  Warning,
} from "phosphor-react";

interface ResearchRunPayload {
  run: {
    id: string;
    status: string;
    goal?: string | null;
    startedAt?: string | null;
    finishedAt?: string | null;
    totalCandidates?: number;
    promotedCount?: number;
    errorMessage?: string | null;
  };
  stageSummary: Record<string, number>;
}

interface ResearchCandidate {
  id: string;
  template: string;
  stage: string;
  rejectionReason?: string | null;
  compositeScore?: number | null;
  robustnessScore?: number | null;
  deflatedSharpe?: number | null;
  holdoutMetrics?: string | null;
  prescreenMetrics?: string | null;
  promotedAccountId?: string | null;
  createdAt?: string;
}

interface ResearchEvent {
  id: string;
  level: string;
  event: string;
  payload?: string | null;
  createdAt: string;
}

function getResearchBaseUrl() {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

function metricLabel(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function formatTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString("ko-KR");
}

function parseMetricSummary(raw?: string | null) {
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export default function ResearchRunPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.runId as string;

  const [userId, setUserId] = useState<number | null>(null);
  const [accessState, setAccessState] = useState<"loading" | "ready" | "locked" | "unauthorized" | "offline">("loading");
  const [runData, setRunData] = useState<ResearchRunPayload | null>(null);
  const [candidates, setCandidates] = useState<ResearchCandidate[]>([]);
  const [events, setEvents] = useState<ResearchEvent[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPromoting, setIsPromoting] = useState(false);
  const [promotionMessage, setPromotionMessage] = useState<string | null>(null);

  const loadRun = useCallback(async (resolvedUserId: number, silent = false) => {
    if (!silent) {
      setIsRefreshing(true);
    }

    try {
      const headers = { "X-User-Id": String(resolvedUserId) };
      const [runResponse, candidateResponse, eventResponse] = await Promise.all([
        fetch(`${getResearchBaseUrl()}/research/runs/${runId}`, { headers }),
        fetch(`${getResearchBaseUrl()}/research/runs/${runId}/candidates?limit=20`, { headers }),
        fetch(`${getResearchBaseUrl()}/research/runs/${runId}/audit?limit=30`, { headers }),
      ]);

      if (runResponse.status === 402) {
        setAccessState("locked");
        return;
      }
      if (runResponse.status === 401) {
        setAccessState("unauthorized");
        return;
      }
      if (!runResponse.ok) {
        const body = await runResponse.json().catch(() => ({}));
        throw new Error(body?.detail ?? "연구 런을 불러오지 못했습니다.");
      }
      if (!candidateResponse.ok || !eventResponse.ok) {
        throw new Error("연구 세부 정보를 불러오지 못했습니다.");
      }

      const [runPayload, candidatePayload, eventPayload] = await Promise.all([
        runResponse.json() as Promise<ResearchRunPayload>,
        candidateResponse.json() as Promise<{ candidates: ResearchCandidate[] }>,
        eventResponse.json() as Promise<{ events: ResearchEvent[] }>,
      ]);

      setAccessState("ready");
      setRunData(runPayload);
      setCandidates(candidatePayload.candidates ?? []);
      setEvents(eventPayload.events ?? []);
      setSelectedCandidateId((current) => current ?? candidatePayload.candidates?.[0]?.id ?? null);
      setError(null);
    } catch (loadError: any) {
      setAccessState("offline");
      setError(loadError?.message ?? "연구 런을 불러오지 못했습니다.");
    } finally {
      if (!silent) {
        setIsRefreshing(false);
      }
    }
  }, [runId]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const userResponse = await fetch("/api/user", { cache: "no-store" });
        const userPayload = await userResponse.json();
        const nextUserId = userPayload?.user?.id ?? null;
        if (!nextUserId) {
          if (!cancelled) {
            setAccessState("unauthorized");
          }
          return;
        }
        if (!cancelled) {
          setUserId(nextUserId);
        }
        await loadRun(nextUserId);
      } catch {
        if (!cancelled) {
          setAccessState("offline");
          setError("사용자 정보를 확인하지 못했습니다.");
        }
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [loadRun]);

  useEffect(() => {
    if (!userId || !runData || !["PENDING", "RUNNING"].includes(runData.run.status)) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadRun(userId, true);
    }, 5000);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadRun, runData, userId]);

  const selectedCandidate = useMemo(
    () => candidates.find((candidate) => candidate.id === selectedCandidateId) ?? candidates[0] ?? null,
    [candidates, selectedCandidateId]
  );

  const selectedHoldout = parseMetricSummary(selectedCandidate?.holdoutMetrics);
  const selectedPrescreen = parseMetricSummary(selectedCandidate?.prescreenMetrics);

  async function handlePromote() {
    if (!selectedCandidate || !userId) {
      return;
    }

    setIsPromoting(true);
    setPromotionMessage(null);
    try {
      const response = await fetch(`${getResearchBaseUrl()}/research/candidates/${selectedCandidate.id}/promote`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": String(userId),
        },
        body: JSON.stringify({ initial_cash: 10000000 }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail ?? "승격에 실패했습니다.");
      }
      setPromotionMessage("가상계좌로 승격했습니다. 상세 페이지로 이동합니다.");
      router.push(`/virtual-account/${payload.accountId}`);
    } catch (promotionError: any) {
      setPromotionMessage(promotionError?.message ?? "승격에 실패했습니다.");
    } finally {
      setIsPromoting(false);
    }
  }

  async function handleCancelRun() {
    if (!userId || !runData || !["PENDING", "RUNNING"].includes(runData.run.status)) {
      return;
    }

    try {
      const response = await fetch(`${getResearchBaseUrl()}/research/runs/${runId}`, {
        method: "DELETE",
        headers: { "X-User-Id": String(userId) },
      });
      if (!response.ok) {
        throw new Error("연구 중단에 실패했습니다.");
      }
      await loadRun(userId);
    } catch (cancelError: any) {
      setError(cancelError?.message ?? "연구 중단에 실패했습니다.");
    }
  }

  if (accessState === "loading") {
    return (
      <DashboardLayout userName="">
        <div className="flex h-full items-center justify-center gap-2 text-gray-500">
          <ArrowsClockwise size={16} className="animate-spin" />
          <span className="text-sm font-bold">연구 런을 불러오는 중...</span>
        </div>
      </DashboardLayout>
    );
  }

  if (accessState !== "ready" || !runData) {
    return (
      <DashboardLayout userName="">
        <div className="flex h-full flex-col items-center justify-center gap-4 px-4 text-center">
          <Warning size={32} className="text-[var(--main-blue)]" weight="fill" />
          <p className="text-sm font-bold text-white">
            {error ??
              (accessState === "locked"
                ? "Premium 플랜에서만 연구 런을 볼 수 있습니다."
                : accessState === "unauthorized"
                  ? "로그인 후 연구 런을 확인할 수 있습니다."
                  : "연구 런에 연결할 수 없습니다.")}
          </p>
          <button
            onClick={() => router.push("/analytics/new?mode=research")}
            className="rounded-2xl border border-white/[0.08] px-4 py-2 text-xs font-black text-gray-300 transition-colors duration-200 hover:text-white"
          >
            연구 화면으로 돌아가기
          </button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout userName="">
      <div className="min-h-full px-4 py-6 md:px-6">
        <div className="mx-auto max-w-7xl space-y-5">
          <div className="flex flex-col gap-4 rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => router.push("/analytics")}
                  className="rounded-xl border border-white/[0.08] p-2 text-gray-500 transition-colors duration-200 hover:text-white"
                >
                  <ArrowLeft size={14} />
                </button>
                <div>
                  <div className="flex items-center gap-2">
                    <ChartLineUp size={16} className="text-emerald-300" weight="fill" />
                    <span className="text-sm font-black text-white">연구 런 {runData.run.id}</span>
                  </div>
                  <p className="mt-1 text-xs font-bold text-gray-500">{runData.run.goal || "연구 목표 설명 없음"}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-[11px] font-black uppercase tracking-[0.18em] text-emerald-200">
                  {runData.run.status}
                </span>
                <button
                  onClick={() => userId && loadRun(userId)}
                  className="inline-flex items-center gap-2 rounded-2xl border border-white/[0.08] px-4 py-2 text-xs font-black text-gray-300 transition-colors duration-200 hover:text-white"
                >
                  <ArrowsClockwise size={13} className={isRefreshing ? "animate-spin" : ""} />
                  새로고침
                </button>
                {["PENDING", "RUNNING"].includes(runData.run.status) && (
                  <button
                    onClick={handleCancelRun}
                    className="rounded-2xl border border-[var(--error-red)]/20 bg-[var(--error-red)]/10 px-4 py-2 text-xs font-black text-[var(--error-red)]"
                  >
                    연구 중단
                  </button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-4">
                <p className="text-[11px] font-black uppercase tracking-[0.18em] text-gray-600">Started</p>
                <p className="mt-2 text-sm font-black text-white">{formatTime(runData.run.startedAt)}</p>
              </div>
              <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-4">
                <p className="text-[11px] font-black uppercase tracking-[0.18em] text-gray-600">Candidates</p>
                <p className="mt-2 text-sm font-black text-white">{runData.run.totalCandidates ?? 0}</p>
              </div>
              <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-4">
                <p className="text-[11px] font-black uppercase tracking-[0.18em] text-gray-600">Approved</p>
                <p className="mt-2 text-sm font-black text-white">{runData.stageSummary.APPROVED ?? 0}</p>
              </div>
              <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-4">
                <p className="text-[11px] font-black uppercase tracking-[0.18em] text-gray-600">Promoted</p>
                <p className="mt-2 text-sm font-black text-white">{runData.run.promotedCount ?? 0}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.9fr_1.1fr_0.8fr]">
            <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5">
              <div className="mb-4 flex items-center gap-2">
                <ClockCounterClockwise size={14} className="text-gray-500" />
                <h2 className="text-sm font-black text-white">단계 요약</h2>
              </div>
              <div className="space-y-2">
                {["GENERATED", "PRESCREENED", "ROBUST", "OPTIMIZED", "APPROVED", "PROMOTED"].map((stage) => (
                  <div key={stage} className="flex items-center justify-between rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3">
                    <span className="text-xs font-black text-gray-300">{stage}</span>
                    <span className="text-xs font-black text-white">{runData.stageSummary[stage] ?? 0}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-sm font-black text-white">후보 전략</h2>
                <span className="text-[11px] font-black uppercase tracking-[0.18em] text-gray-600">{candidates.length} Loaded</span>
              </div>
              <div className="space-y-3">
                {candidates.length === 0 ? (
                  <div className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-6 text-center text-xs font-bold text-gray-500">
                    아직 표시할 후보가 없습니다. 실행 중이면 잠시 후 새로고침하세요.
                  </div>
                ) : (
                  candidates.map((candidate) => (
                    <button
                      key={candidate.id}
                      onClick={() => setSelectedCandidateId(candidate.id)}
                      className={`w-full rounded-2xl border p-4 text-left transition-colors duration-200 ${
                        selectedCandidate?.id === candidate.id
                          ? "border-emerald-400/30 bg-emerald-400/10"
                          : "border-white/[0.06] bg-black/20 hover:border-white/[0.12]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-black text-white">{candidate.template}</p>
                          <p className="mt-1 text-[11px] font-black uppercase tracking-[0.18em] text-gray-600">{candidate.stage}</p>
                        </div>
                        {candidate.stage === "APPROVED" && <CheckCircle size={16} className="text-emerald-300" weight="fill" />}
                      </div>
                      <div className="mt-4 grid grid-cols-3 gap-2">
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Score</p>
                          <p className="mt-1 text-xs font-black text-white">{metricLabel(candidate.compositeScore)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Robust</p>
                          <p className="mt-1 text-xs font-black text-white">{metricLabel(candidate.robustnessScore)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">DSR</p>
                          <p className="mt-1 text-xs font-black text-white">{metricLabel(candidate.deflatedSharpe)}</p>
                        </div>
                      </div>
                      {candidate.rejectionReason && (
                        <p className="mt-3 text-xs font-bold text-[var(--error-red)]">{candidate.rejectionReason}</p>
                      )}
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-sm font-black text-white">선택 후보 상세</h2>
                  {selectedCandidate && (
                    <span className="rounded-full border border-white/[0.08] px-3 py-1 text-[11px] font-black uppercase tracking-[0.15em] text-gray-400">
                      {selectedCandidate.stage}
                    </span>
                  )}
                </div>
                {!selectedCandidate ? (
                  <p className="text-xs font-bold text-gray-500">후보를 선택하면 상세 지표와 승격 액션을 볼 수 있습니다.</p>
                ) : (
                  <div className="space-y-4">
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-4">
                      <p className="text-sm font-black text-white">{selectedCandidate.template}</p>
                      <p className="mt-2 text-xs font-bold text-gray-400">
                        생성 시각 {formatTime(selectedCandidate.createdAt)}
                      </p>
                      {selectedCandidate.rejectionReason && (
                        <p className="mt-3 text-xs font-bold text-[var(--error-red)]">{selectedCandidate.rejectionReason}</p>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                        <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Holdout CAGR</p>
                        <p className="mt-1 text-xs font-black text-white">{metricLabel(selectedHoldout?.cagr)}</p>
                      </div>
                      <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                        <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Holdout MDD</p>
                        <p className="mt-1 text-xs font-black text-white">{metricLabel(selectedHoldout?.max_drawdown)}</p>
                      </div>
                      <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                        <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Prescreen Sharpe</p>
                        <p className="mt-1 text-xs font-black text-white">{metricLabel(selectedPrescreen?.sharpe)}</p>
                      </div>
                      <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                        <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Trades</p>
                        <p className="mt-1 text-xs font-black text-white">{metricLabel(selectedPrescreen?.trades, 0)}</p>
                      </div>
                    </div>

                    {promotionMessage && (
                      <div className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3 text-xs font-bold text-gray-300">
                        {promotionMessage}
                      </div>
                    )}

                    <button
                      onClick={handlePromote}
                      disabled={selectedCandidate.stage !== "APPROVED" || isPromoting}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-emerald-500 to-sky-500 px-4 py-3 text-sm font-black text-white transition-opacity duration-200 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {isPromoting ? <ArrowsClockwise size={14} className="animate-spin" /> : <Bank size={14} weight="fill" />}
                      가상계좌로 승격
                    </button>
                  </div>
                )}
              </div>

              <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-sm font-black text-white">이벤트 로그</h2>
                  <span className="text-[11px] font-black uppercase tracking-[0.18em] text-gray-600">{events.length} Events</span>
                </div>
                <div className="space-y-2">
                  {events.length === 0 ? (
                    <p className="text-xs font-bold text-gray-500">감사 로그가 아직 없습니다.</p>
                  ) : (
                    events.map((event) => (
                      <div key={event.id} className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-black text-white">{event.event}</p>
                          <span className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">{event.level}</span>
                        </div>
                        <p className="mt-1 text-[11px] font-bold text-gray-500">{formatTime(event.createdAt)}</p>
                        {event.payload && (
                          <p className="mt-2 line-clamp-3 text-xs font-bold leading-relaxed text-gray-400">{event.payload}</p>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>

          {runData.run.errorMessage && (
            <div className="rounded-2xl border border-[var(--error-red)]/20 bg-[var(--error-red)]/10 px-4 py-3 text-xs font-bold text-[var(--error-red)]">
              {runData.run.errorMessage}
            </div>
          )}
          {error && (
            <div className="rounded-2xl border border-[var(--error-red)]/20 bg-[var(--error-red)]/10 px-4 py-3 text-xs font-bold text-[var(--error-red)]">
              {error}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
