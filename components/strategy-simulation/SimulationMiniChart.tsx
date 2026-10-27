import { t } from "@/lib/i18n";

// 카드용 누적 수익률 미니 그래프 — 저장된 곡선을 그대로 그린다(축·툴팁 없음, 0% 기준선만).
export type SimulationCurve = { dates: string[]; returnPct: number[] };

const W = 240;
const H = 64;
const PAD = 4;

export function SimulationMiniChart({ curve }: { curve: SimulationCurve }) {
  const values = curve.returnPct.filter((v) => Number.isFinite(v));
  if (values.length < 2) return null;
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const span = max - min || 1;
  const x = (i: number) => PAD + (i / (values.length - 1)) * (W - PAD * 2);
  const y = (v: number) => H - PAD - ((v - min) / span) * (H - PAD * 2);
  const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values[values.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("누적 수익률 추이")} className="h-16 w-full">
      <line x1={PAD} x2={W - PAD} y1={y(0)} y2={y(0)} stroke="#2a2926" strokeDasharray="3 3" />
      <polyline
        points={points}
        fill="none"
        stroke={last >= 0 ? "var(--main-red)" : "var(--main-blue)"}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
