import { t } from "@/lib/i18n";
import { DASH, numeric, summaryMetrics, type Summary } from "./SimulationMetrics";

// 원본 대비 사용자 수정 시뮬레이션 — 값과 차이만 보인다. 차이에는 좋고 나쁨의 색을 주지 않는다(우열 판단 아님).
export function SimulationComparison({ original, modified }: { original: Summary; modified: Summary }) {
  return (
    <table className="w-full text-left text-xs">
      <thead>
        <tr className="text-[var(--text-label)]">
          <th className="py-1 font-bold" />
          <th className="py-1 font-bold">{t("원본")}</th>
          <th className="py-1 font-bold">{t("사용자 수정")}</th>
          <th className="py-1 font-bold">{t("차이")}</th>
        </tr>
      </thead>
      <tbody>
        {summaryMetrics().map((m) => {
          const a = original[m.key];
          const b = modified[m.key];
          return (
            <tr key={m.key} className="border-t border-white/[0.06]">
              <th className="py-1.5 font-bold text-[var(--text-label)]">{m.label}</th>
              <td className="py-1.5 font-black text-white">{numeric(a) ? m.format(a) : DASH}</td>
              <td className={`py-1.5 font-black ${numeric(b) && m.tone ? m.tone(b) : "text-white"}`}>{numeric(b) ? m.format(b) : DASH}</td>
              <td className="py-1.5 font-black text-gray-200">{numeric(a) && numeric(b) ? m.diff(b - a) : DASH}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
