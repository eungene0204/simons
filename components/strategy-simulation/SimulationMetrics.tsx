import { t } from "@/lib/i18n";
import { pct, signTone, won } from "./format";

// 요약 지표 정의 한 곳 — 원본 요약 표와 원본·수정 비교표가 같은 목록·표기를 쓴다.
export type Summary = Record<string, any>;
export const DASH = "—";

type MetricDef = {
  key: string; label: string; tip: string; tone?: (v: number) => string;
  format: (v: number) => string; diff: (d: number) => string;
};
const pp = (d: number) => `${d > 0 ? "+" : ""}${d.toFixed(2)}%p`;
const signed = (d: number, f: (n: number) => string) => (d > 0 ? "+" : "") + f(d);

export function summaryMetrics(): MetricDef[] {
  return [
    { key: "initialCapital", label: t("초기 자본"), tip: t("시뮬레이션에 적용된 초기 투자금입니다. 총 손익은 이 금액에 따라 달라집니다."), format: won, diff: (d) => signed(d, won) },
    { key: "finalEquity", label: t("최종 평가자산"), tip: t("기간 마지막 날의 현금과 보유 종목 평가금액의 합입니다."), format: won, diff: (d) => signed(d, won) },
    { key: "totalProfit", label: t("총 손익"), tip: t("최종 평가자산에서 초기 자본을 뺀 값입니다. 미청산 포지션의 평가손익을 포함하고 수수료·세금·슬리피지를 반영합니다."), tone: signTone, format: won, diff: (d) => signed(d, won) },
    { key: "totalReturnPct", label: t("누적 수익률"), tip: t("초기 자본 대비 최종 평가자산의 변화율입니다."), tone: signTone, format: pct, diff: pp },
    { key: "maxDrawdownPct", label: t("최대 낙폭"), tip: t("기간 중 직전 고점 대비 가장 크게 하락한 비율입니다(음수로 표시)."), format: pct, diff: pp },
    { key: "cagrPct", label: "CAGR", tip: t("누적 수익률을 1년 단위로 환산한 값입니다. 기간이 1년 미만이면 계산하지 않습니다."), format: pct, diff: pp },
    { key: "sharpe", label: t("샤프 비율"), tip: t("수익률 변동 한 단위당 평균 수익입니다. 수익률 변동이 없으면 계산하지 않습니다."), format: (v) => v.toFixed(2), diff: (d) => signed(d, (n) => n.toFixed(2)) },
    { key: "winRatePct", label: t("승률(미청산 포함)"), tip: t("수익으로 끝난 거래의 비율입니다. 아직 청산하지 않은 포지션을 포함합니다."), format: (v) => `${v.toFixed(1)}%`, diff: pp },
    { key: "trades", label: t("거래 수(미청산 포함)"), tip: t("기간 중 발생한 거래 수입니다. 아직 청산하지 않은 포지션을 포함합니다."), format: String, diff: (d) => signed(d, String) },
  ];
}

export const numeric = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** 설명 툴팁 — 마우스를 올리거나 키보드로 포커스하면 뜻과 읽는 법을 보인다. */
export function Tip({ text }: { text: string }) {
  return (
    <span className="group relative ml-1 inline-block align-middle">
      <span tabIndex={0} role="img" aria-label={text} className="cursor-help rounded-full border border-white/20 px-1 text-[10px] text-[var(--text-label)]">?</span>
      <span role="tooltip" className="pointer-events-none absolute left-0 top-full z-10 mt-1 hidden w-52 rounded-md border border-white/[0.12] bg-[var(--card-bg)] p-2 text-[11px] font-medium leading-relaxed text-gray-200 group-focus-within:block group-hover:block">
        {text}
      </span>
    </span>
  );
}

export function Metric({ label, value, tone = "text-white", tip, note }: { label: string; value: string; tone?: string; tip?: string; note?: string }) {
  return (
    <div>
      <dt className="text-[11px] text-[var(--text-label)]">{label}{tip && <Tip text={tip} />}</dt>
      <dd className={`mt-0.5 text-sm font-black ${tone}`}>{value}</dd>
      {note && <dd className="mt-0.5 text-[11px] text-gray-400">{note}</dd>}
    </div>
  );
}

// 서버가 사유를 한국어 문장으로 내리므로 지표 키로 화면 문구를 고른다(문장을 해석하지 않는다).
function unavailableNote(key: string, serverReason?: string): string | undefined {
  if (!serverReason) return undefined;
  if (key === "cagrPct") return t("기간이 1년 미만이라 연환산하지 않습니다.");
  if (key === "sharpe") return t("수익률 변동이 없어 계산할 수 없습니다.");
  if (key === "winRatePct") return t("거래가 없습니다.");
  return t("계산할 수 없습니다.");
}

/** 요약 지표 — 계산할 수 없는 값은 '—'와 사유를 보인다(숨기지 않는다). */
export function SummaryMetrics({ summary }: { summary: Summary }) {
  const reasons: Record<string, string> = summary.unavailableReasons ?? {};
  return (
    <dl className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
      {summaryMetrics().map((m) => {
        const v = summary[m.key];
        return numeric(v)
          ? <Metric key={m.key} label={m.label} tip={m.tip} value={m.format(v)} tone={m.tone?.(v)} />
          : <Metric key={m.key} label={m.label} tip={m.tip} value={DASH} note={unavailableNote(m.key, reasons[m.key])} />;
      })}
    </dl>
  );
}
