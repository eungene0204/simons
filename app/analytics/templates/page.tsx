"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  CATEGORY_STYLE,
  EXAMPLES,
  StrategyTemplatePreviewModal,
  shuffleExamples,
  type Example,
  type ExampleCategory,
} from "@/components/strategy/StrategyExampleTabs";
import { beginStrategyChatNavigation } from "../new/chatNavigation";
import { t } from "@/lib/i18n";

type TemplateCategoryTab = "전체" | ExampleCategory;

const CATEGORY_TABS: TemplateCategoryTab[] = [
  "전체",
  "가치투자",
  "기술분석",
  "모멘텀",
  "복합전략",
  "ETF",
  "테마",
];
const INITIAL_TEMPLATE_COUNT = 24;
const TEMPLATE_PAGE_SIZE = 24;

export default function StrategyTemplatesPage() {
  const router = useRouter();
  const [activeCategory, setActiveCategory] = useState<TemplateCategoryTab>("전체");
  const [selectedExample, setSelectedExample] = useState<Example | null>(null);
  const [visibleCount, setVisibleCount] = useState(INITIAL_TEMPLATE_COUNT);
  const [orderedExamples, setOrderedExamples] = useState<Example[]>(EXAMPLES);

  // 마운트 이후에만 섞는다 — 서버 렌더 결과와 순서가 어긋나면 하이드레이션이 깨진다.
  useEffect(() => {
    setOrderedExamples(shuffleExamples(EXAMPLES));
  }, []);

  const filteredExamples = activeCategory === "전체"
    ? orderedExamples
    : orderedExamples.filter((example) => example.category === activeCategory);
  const visibleExamples = filteredExamples.slice(0, visibleCount);
  const hasMoreExamples = visibleCount < filteredExamples.length;
  const backgroundBlurClass = selectedExample
    ? "pointer-events-none select-none blur-[6px] transition-[filter,opacity] duration-200"
    : "transition-[filter,opacity] duration-200";

  const handleSelectTemplate = (prompt: string) => {
    beginStrategyChatNavigation(prompt, (url) => router.push(url));
  };

  return (
    <DashboardLayout userName="">
      <main
        className="px-6 py-12"
        style={{ minHeight: "calc(100vh - var(--top-menu-bar-height, 76px))" }}
      >
        <div
          className={`mx-auto w-full max-w-[80rem] space-y-8 ${backgroundBlurClass}`}
          data-testid="strategy-templates-page-background"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-3">
              <div className="space-y-2">
                <h1 className="text-3xl font-black text-white">{t("백테스트 입력 예시")}</h1>
                <p className="text-sm font-bold text-gray-500">
                  {t("가정한 조건을 선택하고 직접 수정한 뒤 과거 데이터로 실험할 수 있습니다")}
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-1 rounded-[1.45rem] border border-white/[0.06] bg-[#101010] p-1 sm:grid-cols-4 lg:grid-cols-7">
            {CATEGORY_TABS.map((category) => {
              const isActive = activeCategory === category;
              const style = category === "전체" ? null : CATEGORY_STYLE[category];

              return (
                <button
                  key={category}
                  type="button"
                  aria-label={t("{0} 백테스트 예시 보기", t(category))}
                  aria-pressed={isActive}
                  onClick={() => {
                    setActiveCategory(category);
                    setVisibleCount(INITIAL_TEMPLATE_COUNT);
                  }}
                  className={`h-10 rounded-[1.15rem] px-3 text-sm font-black transition-all duration-200 ${
                    isActive
                      ? "bg-[var(--main-blue)] text-white shadow-[0_14px_34px_rgba(59,130,246,0.2)]"
                      : "text-gray-500 hover:bg-white/[0.04] hover:text-white"
                  }`}
                >
                  {t(style?.label ?? category)}
                </button>
              );
            })}
          </div>

          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2 xl:grid-cols-3">
              {visibleExamples.map((example) => {
                const style = CATEGORY_STYLE[example.category];

                return (
                  <button
                    key={example.title}
                    type="button"
                    onClick={() => setSelectedExample(example)}
                    className="group space-y-2 rounded-2xl border border-white/[0.05] bg-[#121212] px-4 py-4 text-left transition-all duration-200 hover:border-white/[0.12] hover:bg-[#171717]"
                  >
                    <span className={`inline-flex items-center rounded-md px-2 py-1 text-[10px] font-black ${style.bg} ${style.border} ${style.color}`}>
                      {t(style.label)}
                    </span>
                    <p className="text-sm font-black leading-snug text-white/85 group-hover:text-white">
                      {t(example.title)}
                    </p>
                    <p className="line-clamp-5 text-xs font-bold leading-relaxed text-gray-400 group-hover:text-gray-300">
                      {t(example.prompt)}
                    </p>
                  </button>
                );
              })}
            </div>

            {hasMoreExamples && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={() => setVisibleCount((count) => count + TEMPLATE_PAGE_SIZE)}
                  className="rounded-2xl border border-white/[0.08] bg-[#121212] px-5 py-2.5 text-xs font-black text-gray-300 transition-colors duration-200 hover:border-white/[0.14] hover:bg-[#171717] hover:text-white"
                >
                  {t("더 보기")}
                </button>
              </div>
            )}
          </div>

          <footer
            aria-label={t("백테스트 입력 예시 안내")}
            className="border-t border-white/[0.06] pt-5 text-center"
          >
            <p className="text-xs font-bold leading-relaxed text-gray-600">
              {t("백테스트 입력 예시에 쓰인 수치는 단순 예시값이며, 투자 추천이나 미래 성과를 의미하지 않습니다.")}
            </p>
          </footer>
        </div>

        {selectedExample && (
          <StrategyTemplatePreviewModal
            example={selectedExample}
            onCancel={() => setSelectedExample(null)}
            onGenerateStrategy={(prompt) => {
              handleSelectTemplate(prompt);
              setSelectedExample(null);
            }}
          />
        )}
      </main>
    </DashboardLayout>
  );
}
