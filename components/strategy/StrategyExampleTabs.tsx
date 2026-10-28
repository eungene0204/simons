"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Sparkle } from "phosphor-react";
import { t } from "@/lib/i18n";
import { EXAMPLES, type Example, type ExampleCategory, type ExampleLevel } from "./strategyExamples";

export { EXAMPLES };
export type { Example, ExampleCategory, ExampleLevel };

export function shuffleExamples(examples: Example[]): Example[] {
  const shuffled = [...examples];
  for (let i = shuffled.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

// 카테고리 배지는 중립 정보 배지(§11)다 — 종류마다 색을 주면 한 화면에 장식 강조색이 여섯이 되고
// 색이 의미(상승·하락·오류)를 잃는다(§2 강조색 단일화, 2026-09-08). 구분은 글자로 한다.
const NEUTRAL_BADGE = { color: "text-gray-300", bg: "bg-white/[0.06]", border: "" } as const;
export const CATEGORY_STYLE: Record<ExampleCategory, { label: string; color: string; bg: string; border: string }> = {
  가치투자: { label: "가치투자", ...NEUTRAL_BADGE },
  기술분석: { label: "기술분석", ...NEUTRAL_BADGE },
  모멘텀: { label: "모멘텀", ...NEUTRAL_BADGE },
  복합전략: { label: "복합전략", ...NEUTRAL_BADGE },
  ETF: { label: "ETF", ...NEUTRAL_BADGE },
  테마: { label: "테마", ...NEUTRAL_BADGE },
};

export function StrategyTemplatePreviewModal({
  example,
  onCancel,
  onGenerateStrategy,
}: {
  example: Example;
  onCancel: () => void;
  onGenerateStrategy: (prompt: string) => void;
}) {
  const style = CATEGORY_STYLE[example.category];
  // 예시 본문은 표시 언어로 보여주고, 그대로 파서에 보낸다(영어 프롬프트도 해석된다 — 2026-08-18 실측).
  const [promptText, setPromptText] = useState(t(example.prompt));

  useEffect(() => {
    setPromptText(t(example.prompt));
  }, [example.prompt]);

  const modal = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 backdrop-blur-[12px] [backdrop-filter:blur(12px)] [-webkit-backdrop-filter:blur(12px)] animate-fade-in lg:px-4 lg:py-0"
      data-testid="strategy-template-preview-backdrop"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="strategy-template-preview-title"
        className="modal-enter max-h-[calc(100dvh-1.5rem)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/[0.08] bg-[#101010] p-4 shadow-2xl shadow-black/50 lg:max-h-none lg:p-5"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <span className={`inline-flex items-center rounded-md px-2 py-1 text-[10px] font-black ${style.bg} ${style.border} ${style.color}`}>
              {t(style.label)}
            </span>
            <h2 id="strategy-template-preview-title" className="text-lg font-black text-white lg:text-xl">
              {t(example.title)}
            </h2>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full px-3 py-1 text-xl font-black text-gray-500 transition-colors duration-200 hover:bg-white/[0.06] hover:text-white"
            aria-label={t("전략 미리보기 닫기")}
          >
            ×
          </button>
        </div>

        <div className="mt-5 rounded-2xl bg-black px-4 py-4">
          <textarea
            id="strategy-template-prompt"
            aria-label={t("백테스트 예시 내용")}
            value={promptText}
            onChange={(event) => setPromptText(event.target.value)}
            rows={8}
            className="w-full resize-none bg-transparent text-sm font-bold leading-relaxed text-gray-300 outline-none ring-0 placeholder:text-gray-700 focus:text-white focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0"
          />
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xl border border-white/[0.08] bg-[#171717] px-3 py-1.5 text-xs font-black text-gray-300 transition-colors duration-200 hover:border-white/[0.14] hover:bg-[#1d1d1d] hover:text-white"
          >
            {t("취소")}
          </button>
          <button
            type="button"
            onClick={() => onGenerateStrategy(promptText.trim())}
            disabled={!promptText.trim()}
            className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--chat-accent)] px-4 py-2 text-xs font-black text-[var(--chat-accent-ink)] transition-colors duration-200 hover:brightness-110 active:translate-y-[1px] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Sparkle size={14} weight="fill" />
            {t("예시로 시작")}
          </button>
        </div>
      </div>
    </div>
  );

  if (typeof document === "undefined") return modal;
  return createPortal(modal, document.body);
}
