import type { AdvisorResult } from "@/components/strategy/StrategyAdvisorPanel";
import { t } from "@/lib/i18n";

export function AdvisorResponseSections({ result }: { result: AdvisorResult }) {
  const sections = result.response_sections ?? [];

  if (sections.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-black uppercase tracking-widest text-indigo-200">{t("전략 리뷰")}</p>
        <span className="text-[10px] font-black text-gray-600">{t("{0}개 섹션", sections.length)}</span>
      </div>
      <div className="divide-y divide-white/[0.05] overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.02]">
        {sections.map((section, index) => (
          <div key={`${section.title}-${index}`} className="px-3 py-2.5">
            <div className="flex items-start gap-2.5">
              <span className="mt-0.5 text-[10px] font-black tabular-nums text-gray-600">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-black uppercase tracking-widest text-gray-400">
                  {section.title}
                </p>
                <p className="mt-1 text-xs font-bold leading-relaxed text-gray-400">
                  {section.body}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
