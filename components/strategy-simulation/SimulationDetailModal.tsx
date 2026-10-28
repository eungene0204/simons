"use client";

import { useEffect, useRef, useState } from "react";
import { Spinner } from "phosphor-react";
import { useDialogBehavior } from "@/lib/hooks/useDialogBehavior";
import { t } from "@/lib/i18n";
import { buildStrategySummaryFromDsl, buildStrategySummaryGroups } from "@/lib/strategy-summary";
import type { StrategyDSL } from "@/types/strategy";
import { signTone, won } from "./format";
import { SimulationComparison } from "./SimulationComparison";
import { Metric, SummaryMetrics } from "./SimulationMetrics";
import { SimulationParamForm } from "./SimulationParamForm";
import { SimulationReturnChart } from "./SimulationReturnChart";
import { useModifiedSimulation, type ParamDescriptor } from "./useModifiedSimulation";
import type { SimulationCurve } from "./SimulationMiniChart";

type Contributor = { symbol: string; name: string; profit: number };
type Original = {
  status: string;
  reason?: string;
  window?: { requestedStart?: string; requestedEnd?: string; actualStart?: string; actualEnd?: string; dataAsOf?: string; stale?: boolean; limited?: boolean };
  conditions?: Record<string, any>;
  summary?: Record<string, any>;
  curve?: SimulationCurve;
  contributors?: { top: Contributor[]; bottom: Contributor[]; hidden?: string };
  computedAt?: string;
  dataAsOf?: string;
  editableParams?: ParamDescriptor[];
};
type Assumption = { question: string; answer: string; random: boolean };
type Detail = { publicId: string; name: string; description: string | null; strategy: Record<string, unknown>; assumptions?: Assumption[]; baseSnapshotHash: string; original: Original };

const rate = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(3).replace(/\.?0+$/, "")}%` : "-");

function timingText(timing?: string, delay?: number): string {
  const base = timing === "current_close" ? t("신호 당일 종가") : timing === "next_avg" ? t("신호 다음 거래일 평균가") : t("신호 다음 거래일 시가");
  return delay && delay > 1 && (!timing || timing === "next_open") ? `${base} (${t("{0}거래일 지연", delay)})` : base;
}

type ContributorSet = { top: Contributor[]; bottom: Contributor[]; hidden?: string };

function ContributorList({ title, rows }: { title: string; rows: Contributor[] }) {
  return (
    <div>
      <h5 className="text-xs font-bold text-[var(--text-label)]">{title}</h5>
      {rows.length === 0 ? (
        <p className="mt-1 text-xs text-gray-400">{t("해당 종목이 없습니다.")}</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {rows.map((r) => (
            <li key={r.symbol} className="flex justify-between gap-2 text-sm">
              <span className="truncate text-gray-200">{r.name !== r.symbol ? `${r.name} (${r.symbol})` : r.symbol}</span>
              <span className={`shrink-0 font-black ${signTone(r.profit)}`}>{won(r.profit)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ContributorBlock({ heading, data }: { heading?: string; data: ContributorSet }) {
  return (
    <div>
      {heading && <h4 className="text-xs font-black text-white">{heading}</h4>}
      {data.hidden ? (
        <p className="mt-1 text-xs text-gray-400">{t("종목별 합계가 총 손익과 일치하지 않아 표시하지 않습니다.")}</p>
      ) : (
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          <ContributorList title={t("손익 기여 상위 종목")} rows={data.top} />
          <ContributorList title={t("손익 기여 하위 종목")} rows={data.bottom} />
        </div>
      )}
    </div>
  );
}

// sv-SE는 "YYYY-MM-DD HH:mm:ss" 형태라 언어 설정과 무관하게 같은 표기가 나온다.
const kst = (iso?: string) => (iso ? `${new Date(iso).toLocaleString("sv-SE", { timeZone: "Asia/Seoul" }).slice(0, 16)} KST` : "—");

function errorText(e: { code: string; reason?: string; retryAfterSeconds?: number }): string {
  switch (e.code) {
    case "BASELINE_CHANGED": return e.reason === "REFRESHING" ? t("원본 결과를 최신 데이터로 갱신하는 중이라 잠시 후 다시 시도해 주세요.") : t("원본 결과가 갱신되었습니다.");
    case "RATE_LIMITED": return t("요청이 많아 잠시 후 다시 시도해 주세요.");
    case "BUSY": return t("지금은 계산 요청이 몰려 있습니다. 잠시 후 다시 시도해 주세요.");
    case "TIMEOUT": return t("계산 시간이 초과되었습니다. 값을 바꿔 다시 시도해 주세요.");
    case "INVALID_PARAMETER": return t("입력값을 확인해 주세요.");
    case "STRATEGY_NOT_PUBLIC": case "NOT_FOUND": return t("존재하지 않는 예시 전략입니다.");
    default: return t("수정 결과를 계산하지 못했습니다.");
  }
}

function Result({ o, sim, onReload }: { o: Original; sim: ReturnType<typeof useModifiedSimulation>; onReload: () => void }) {
  const s = o.summary ?? {};
  const c = o.conditions ?? {};
  const w = o.window ?? {};
  const modified = sim.result && !sim.loading ? sim.result : null;
  return (
    <>
      <section>
        <h3 className="text-sm font-black text-white">{t("기간·계산 조건")}</h3>
        <dl className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Metric label={t("요청 기간")} value={`${w.requestedStart} ~ ${w.requestedEnd}`} />
          <Metric label={t("실제 계산 기간")} value={`${w.actualStart} ~ ${w.actualEnd}`} />
          <Metric label={t("데이터 기준일")} value={w.dataAsOf ?? "—"} />
          <Metric label={t("계산 완료 시각")} value={kst(o.computedAt)} />
          <Metric label={t("초기 자본")} value={won(c.initialCapital ?? 0)} />
          <Metric label={t("체결 시점")} value={timingText(c.executionTiming, c.executionDelayDays)} />
          <Metric label={t("매수 수수료")} value={rate(c.buyFeeRate)} />
          <Metric label={t("매도 수수료")} value={rate(c.sellFeeRate)} />
          <Metric label={t("슬리피지")} value={rate(c.slippageRate)} />
          <Metric
            label={t("매도 세금")}
            value={c.sellTaxRate != null ? rate(c.sellTaxRate) : Array.isArray(c.sellTaxRateRange) ? `${rate(c.sellTaxRateRange[0])} ~ ${rate(c.sellTaxRateRange[1])}` : "-"}
          />
        </dl>
        {w.limited && <p className="mt-2 text-xs text-gray-400">{t("데이터 부족으로 요청 기간보다 짧게 계산했습니다.")}</p>}
        {w.stale && <p className="mt-2 text-xs text-gray-400">{t("최신 거래일 데이터가 아직 반영되지 않았을 수 있습니다.")}</p>}
      </section>

      <section>
        <h3 className="text-sm font-black text-white">{t("요약 지표")}</h3>
        <SummaryMetrics summary={s} />
        <p className="mt-2 text-[11px] leading-relaxed text-gray-400">
          {t("총 손익은 최종 평가자산에서 초기 자본을 뺀 값으로, 미청산 포지션의 평가손익을 포함하고 수수료·세금·슬리피지를 반영합니다.")}
        </p>
        {o.status === "no_trades" && <p className="mt-2 text-xs font-bold text-gray-400">{t("이 기간에는 거래가 없었습니다.")}</p>}
      </section>

      {o.curve && (
        <section>
          <h3 className="text-sm font-black text-white">{t("누적 수익률")}</h3>
          <SimulationReturnChart curve={o.curve} modified={modified?.curve} />
        </section>
      )}

      {o.contributors && (
        <section>
          <h3 className="text-sm font-black text-white">{t("종목별 손익")}</h3>
          <div className="mt-2 space-y-4">
            <ContributorBlock heading={modified?.contributors ? t("원본") : undefined} data={o.contributors} />
            {modified?.contributors && <ContributorBlock heading={t("사용자 수정 시뮬레이션")} data={modified.contributors} />}
          </div>
        </section>
      )}

      <section>
        <h3 className="text-sm font-black text-white">{t("지표 값 바꿔 보기")}</h3>
        <p className="mt-1 text-xs text-gray-400">{t("값을 바꾸고 적용을 누르면 같은 기간·자본·비용 조건으로 다시 계산합니다. 원본 결과는 바뀌지 않습니다.")}</p>
        <div className="mt-3">
          <SimulationParamForm params={o.editableParams ?? []} inputs={sim.inputs} errors={sim.errors} onChange={sim.setInput} onApply={sim.apply} onReset={sim.reset} dirty={sim.dirty} changed={sim.changed} />
        </div>
        {sim.loading && <p className="mt-3 text-xs font-bold text-gray-400">{t("수정 결과를 계산하고 있습니다.")}</p>}
        {sim.error && (
          <p role="alert" className="mt-3 text-xs font-bold text-gray-300">
            {errorText(sim.error)}{" "}
            {sim.error.code === "BASELINE_CHANGED" && <button type="button" className="underline" onClick={onReload}>{t("다시 불러오기")}</button>}
          </p>
        )}
        {modified?.summary && (
          <div className="mt-3">
            <h4 className="mb-2 text-xs font-black text-white">{t("사용자 수정 시뮬레이션")}</h4>
            {modified.status === "no_trades" && <p className="mb-2 text-xs font-bold text-gray-400">{t("수정한 값으로는 이 기간에 거래가 없었습니다.")}</p>}
            <SimulationComparison original={s} modified={modified.summary} />
          </div>
        )}
      </section>
    </>
  );
}

export function SimulationDetailModal({ publicId, onClose }: { publicId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<"NOT_FOUND" | "FAILED" | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setError(null);
    fetch(`/api/strategy-simulation/${encodeURIComponent(publicId)}`, { cache: "no-store", signal: controller.signal })
      .then(async (res) => {
        if (res.status === 404) return setError("NOT_FOUND");
        const body = await res.json().catch(() => null);
        if (!res.ok || !body?.original) return setError("FAILED");
        setDetail(body);
      })
      .catch((e) => {
        if (e?.name !== "AbortError") setError("FAILED");
      });
    return () => controller.abort();
  }, [publicId, reloadKey]);

  // Esc·포커스 트랩·열기 전 요소로의 포커스 복귀·스크롤 잠금은 공용 훅이 맡는다.
  useDialogBehavior({ open: true, onClose, containerRef: dialogRef });

  const groups = detail ? buildStrategySummaryGroups(buildStrategySummaryFromDsl(detail.strategy as unknown as StrategyDSL)) : [];
  const o = detail?.original;
  const sim = useModifiedSimulation({
    publicId,
    baseSnapshotHash: detail?.baseSnapshotHash ?? "",
    dataAsOf: o?.dataAsOf ?? o?.window?.dataAsOf ?? "",
    params: o?.editableParams ?? [],
  });
  const reload = () => {
    sim.reset();
    setReloadKey((k) => k + 1);
  };
  const hasResult = o && ["ready", "no_trades", "refreshing"].includes(o.status) && o.summary;

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 sm:items-center sm:p-6" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={detail?.name ? t(detail.name) : t("전략 시뮬레이션")}
        className="h-[100dvh] w-full max-w-3xl space-y-6 overflow-y-auto bg-[var(--card-bg)] p-5 sm:h-auto sm:max-h-[92dvh] sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-black text-white">{detail?.name ? t(detail.name) : ""}</h2>
            {detail?.description && <p className="mt-1 text-xs text-gray-400">{t(detail.description)}</p>}
          </div>
          <button type="button" onClick={onClose} className="shrink-0 rounded-lg border border-white/[0.12] px-3 py-1.5 text-sm font-bold text-white">
            {t("닫기")}
          </button>
        </div>

        {!detail && !error && (
          <p role="status" className="flex items-center gap-2 text-sm font-bold text-gray-400">
            <Spinner size={16} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {t("불러오는 중")}
          </p>
        )}
        {error === "NOT_FOUND" && <p role="alert" className="text-sm font-bold text-gray-400">{t("존재하지 않는 예시 전략입니다.")}</p>}
        {error === "FAILED" && <p role="alert" className="text-sm font-bold text-gray-400">{t("상세 정보를 불러오지 못했습니다.")}</p>}

        {detail && (
          <>
            <section>
              <h3 className="text-sm font-black text-white">{t("전략 조건")}</h3>
              {groups.length === 0 ? (
                <p className="mt-1 text-xs text-gray-400">{t("표시할 전략 조건이 없습니다.")}</p>
              ) : (
                <div className="mt-2 space-y-3">
                  {groups.map((g) => (
                    <div key={g.label}>
                      <p className="text-[11px] font-bold text-[var(--text-label)]">{g.label}</p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {g.chips.map((chip, i) => (
                          <span key={`${chip}-${i}`} className="rounded-md bg-white/[0.06] px-2 py-1 text-xs font-bold text-gray-300">{chip}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
            {!!detail.assumptions?.length && (
              <section>
                <h3 className="text-sm font-black text-white">{t("예시 문장에 없어 정한 값")}</h3>
                <p className="mt-1 text-xs text-gray-400">
                  {detail.assumptions.some((a) => a.random)
                    ? t("예시 문장이 정하지 않은 값은 선택지 중 무작위로 골랐습니다. 아래 값이 이 결과에 쓰였습니다.")
                    : t("예시 문장이 정하지 않은 값은 아래처럼 정했습니다.")}
                </p>
                <ul className="mt-2 space-y-1.5">
                  {detail.assumptions.map((a, i) => (
                    <li key={`${a.question}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                      <span className="text-gray-400">{t(a.question)}</span>
                      <span className="rounded-md bg-white/[0.06] px-2 py-1 font-bold text-gray-200">{t(a.answer)}</span>
                      {a.random && <span className="text-[11px] font-bold text-[var(--text-label)]">{t("무작위 선택")}</span>}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {hasResult ? (
              <Result o={o} sim={sim} onReload={reload} />
            ) : (
              <p className="text-sm font-bold text-gray-400">
                {o?.status === "unavailable" ? t("이 전략은 시뮬레이션할 수 없는 조건을 포함합니다.") : t("원본 결과를 계산하고 있습니다.")}
              </p>
            )}
            <p className="text-[11px] font-bold leading-relaxed text-[var(--text-label)]">
              {t("과거 데이터 기반 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다.")}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
