"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Sparkle, Spinner, X } from "phosphor-react";
import { getLocale, t } from "@/lib/i18n";
import StrategyVersionHistory from "./StrategyVersionHistory";
import { useRegion, useRegionHref } from "@/lib/geo/useRegion";
import { US_EXAMPLES } from "./usExamples";
import { EXAMPLES, type Example, type ExampleCategory, type ExampleLevel } from "./strategyExamples";

export { EXAMPLES };
export type { Example, ExampleCategory, ExampleLevel };

type StrategyTab = "examples" | "my-strategies";

interface SavedStrategy {
  id: string;
  name: string;
  description: string | null;
  type: string;
  universe: string;
  aiScore: number | null;
  avgReturnPct: number;
  accountCount: number;
  createdAt: string;
}

const DEFAULT_VISIBLE_COUNT = 20;
// 시작 말풍선은 첫 줄(xl 5열) 안에서만 고른다 — 20장 중 아무 데나 붙이면 화면 아래에 묻힌다.
const START_BUBBLE_CANDIDATE_COUNT = 5;
// 사업자 정보는 두 줄로 나눠 표시한다 — 대표까지 첫 줄, 주소·연락처는 다음 줄 (2026-09-03 지시).
const BUSINESS_INFO_LINE_1 =
  "상호명 : 널스페이스   사업자등록번호 : 898-50-00737   통신판매업신고번호 : 2026-서울서대문-0758   대표 : 이응준";
const BUSINESS_INFO_LINE_2 =
  "주소 : 서울특별시 서대문구 이화여대7길 37, 3층 S88호   이메일 : support@nullstock.im";
// 글로벌(/us) 푸터 — 사업자 정보(상호·대표·주소·사업자등록번호·통신판매업신고번호)는
// 한국 전자상거래법상 표기라 해외 사용자에게는 표시하지 않고 연락처만 남긴다
// (2026-08-25 지시). 한국 푸터는 법정 표기 유지.
const US_BUSINESS_INFO_TEXT = "E-mail: support@nullstock.im";
const BUSINESS_EMAIL = "support@nullstock.im";

function withEmailLink(info: string) {
  const emailIndex = info.indexOf(BUSINESS_EMAIL);
  if (emailIndex < 0) {
    return <>{info}</>;
  }
  return (
    <>
      {info.slice(0, emailIndex)}
      <a
        href={`mailto:${BUSINESS_EMAIL}`}
        className="underline underline-offset-4 transition-colors hover:text-white"
      >
        {BUSINESS_EMAIL}
      </a>
      {info.slice(emailIndex + BUSINESS_EMAIL.length)}
    </>
  );
}

function BusinessInfoText() {
  const region = useRegion();
  if (region === "us") {
    return withEmailLink(US_BUSINESS_INFO_TEXT);
  }
  return (
    <>
      <span className="block">{t(BUSINESS_INFO_LINE_1)}</span>
      <span className="block">{withEmailLink(t(BUSINESS_INFO_LINE_2))}</span>
    </>
  );
}


/** 예시 카드 노출 순서를 섞는다(Fisher-Yates) — 첫 화면이 항상 같은 예시만 보여주지
 * 않도록. 서버·클라이언트가 다른 순서를 만들면 하이드레이션이 깨지므로 호출은 마운트
 * 이후(useEffect)에만 한다. */
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

const TAB_META: Record<StrategyTab, { label: string }> = {
  examples: {
    label: "백테스트 예시",
  },
  "my-strategies": {
    label: "내 전략",
  },
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

export function StrategyExampleTabs({
  onSelectExample,
  onPreviewOpenChange,
}: {
  onSelectExample: (prompt: string) => void;
  onPreviewOpenChange?: (isOpen: boolean) => void;
}) {
  const regionHref = useRegionHref();
  const region = useRegion();
  // /us는 미국 시장 예시(usExamples.ts), 한국은 기존 예시 — 지역이 예시 집합을 결정한다.
  const baseExamples = region === "us" ? US_EXAMPLES : EXAMPLES;
  const [activeTab, setActiveTab] = useState<StrategyTab>("examples");
  const [myStrategies, setMyStrategies] = useState<SavedStrategy[]>([]);
  const [isLoadingStrategies, setIsLoadingStrategies] = useState(false);
  const [hasLoadedStrategies, setHasLoadedStrategies] = useState(false);
  const [strategiesError, setStrategiesError] = useState<string | null>(null);
  const [deletingStrategyIds, setDeletingStrategyIds] = useState<Set<string>>(() => new Set());
  // 버전 이력(2026-09-23) — 카드 하나만 펼친다(목록이 길어 여러 개가 열리면 읽기 어렵다).
  const [openVersionStrategyId, setOpenVersionStrategyId] = useState<string | null>(null);
  const [selectedExample, setSelectedExample] = useState<Example | null>(null);
  const [exampleContentHeight, setExampleContentHeight] = useState<number | null>(null);
  const [orderedExamples, setOrderedExamples] = useState<Example[]>(baseExamples);
  const [startBubbleIndex, setStartBubbleIndex] = useState<number | null>(null);
  const examplesContentRef = useRef<HTMLDivElement>(null);

  // 마운트 이후에만 섞는다 — 서버 렌더 결과와 순서가 어긋나면 하이드레이션이 깨진다.
  useEffect(() => {
    setOrderedExamples(shuffleExamples(baseExamples));
    const candidateCount = Math.min(START_BUBBLE_CANDIDATE_COUNT, baseExamples.length);
    setStartBubbleIndex(Math.floor(Math.random() * candidateCount));
  }, [baseExamples]);

  const visibleExamples = orderedExamples.slice(0, DEFAULT_VISIBLE_COUNT);

  useEffect(() => {
    if (activeTab !== "my-strategies" || hasLoadedStrategies) return;

    let ignore = false;
    setIsLoadingStrategies(true);
    setStrategiesError(null);

    fetch("/api/dashboard/strategy-list", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to load strategies");
        }
        return response.json();
      })
      .then((data: { strategies?: SavedStrategy[] }) => {
        if (ignore) return;
        setMyStrategies(Array.isArray(data.strategies) ? data.strategies : []);
        setHasLoadedStrategies(true);
      })
      .catch(() => {
        if (ignore) return;
        setStrategiesError(t("전략 목록을 불러오지 못했습니다."));
      })
      .finally(() => {
        if (!ignore) {
          setIsLoadingStrategies(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [activeTab, hasLoadedStrategies]);

  useEffect(() => {
    return () => {
      onPreviewOpenChange?.(false);
    };
  }, [onPreviewOpenChange]);

  useEffect(() => {
    if (activeTab !== "examples" || !examplesContentRef.current) return;

    const examplesContent = examplesContentRef.current;
    const updateHeight = () => {
      const nextHeight = examplesContent.getBoundingClientRect().height;
      if (nextHeight > 0) {
        setExampleContentHeight(nextHeight);
      }
    };

    updateHeight();
    if (typeof ResizeObserver === "undefined") return;

    const resizeObserver = new ResizeObserver(updateHeight);
    resizeObserver.observe(examplesContent);
    return () => resizeObserver.disconnect();
  }, [activeTab]);

  const hasMoreExamples = DEFAULT_VISIBLE_COUNT < baseExamples.length;

  const handleDeleteStrategy = async (strategyId: string) => {
    setDeletingStrategyIds((prev) => {
      const next = new Set(prev);
      next.add(strategyId);
      return next;
    });

    try {
      const response = await fetch(`/api/strategy/${strategyId}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Failed to delete strategy");
      }
      setMyStrategies((prev) => prev.filter((strategy) => strategy.id !== strategyId));
    } catch (error) {
      console.error("Failed to delete strategy:", error);
    } finally {
      setDeletingStrategyIds((prev) => {
        const next = new Set(prev);
        next.delete(strategyId);
        return next;
      });
    }
  };

  const isPreviewOpen = Boolean(selectedExample);
  const backgroundBlurClass = isPreviewOpen
    ? "pointer-events-none select-none blur-[6px] transition-[filter,opacity] duration-200"
    : "transition-[filter,opacity] duration-200";

  return (
    <div className="w-full space-y-3">
      <div
        className={`space-y-3 ${backgroundBlurClass}`}
        data-testid="strategy-example-tabs-background"
      >
        <div className="space-y-2 text-center">
          <div className="mx-auto inline-flex w-full max-w-2xl rounded-2xl border border-white/[0.06] bg-[#101010] p-1">
            {(Object.keys(TAB_META) as StrategyTab[]).map((tab) => {
              const isActive = tab === activeTab;
              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => {
                    if (tab === "my-strategies" && !hasLoadedStrategies) {
                      setIsLoadingStrategies(true);
                    }
                    setActiveTab(tab);
                  }}
                  className={`flex-1 rounded-xl px-3 py-2.5 text-xs font-black ${
                    isActive
                      ? "bg-white/[0.12] text-white"
                      : "text-gray-400 hover:bg-[#171717] hover:text-white"
                    }`}
                >
                  {t(TAB_META[tab].label)}
                </button>
              );
            })}
          </div>
        </div>

        <div
          data-testid="strategy-tab-content"
          style={activeTab === "my-strategies" && exampleContentHeight
            ? { height: `${exampleContentHeight}px` }
            : undefined}
        >
          {activeTab === "examples" ? (
            <div ref={examplesContentRef} className="space-y-3" data-testid="strategy-examples-content">
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-5">
                {visibleExamples.map((example, index) => {
                  const style = CATEGORY_STYLE[example.category];
                  const hasStartBubble = index === startBubbleIndex;
                  return (
                    <button
                      key={example.title}
                      type="button"
                      onClick={() => {
                        setSelectedExample(example);
                        onPreviewOpenChange?.(true);
                      }}
                      className={`group relative space-y-1.5 rounded-2xl border bg-[#121212] px-3 py-3 text-left transition-all duration-200 hover:bg-[#171717] ${
                        hasStartBubble
                          ? "border-[var(--chat-accent-line)] shadow-[0_0_20px_var(--chat-accent-soft)]"
                          : "border-white/[0.05] hover:border-white/[0.12]"
                      }`}
                      data-testid="strategy-example-card"
                    >
                      {hasStartBubble && (
                        <span
                          className="animate-fade-in pointer-events-none absolute right-3 top-0 z-10 -translate-y-1/2 whitespace-nowrap rounded-lg bg-[var(--chat-accent)] px-2 py-1 text-[10px] font-black text-[var(--chat-accent-ink)] shadow-lg"
                          data-testid="strategy-example-start-bubble"
                        >
                          {t("예시로 시작해 보세요!")}
                          <span
                            aria-hidden="true"
                            className="absolute -bottom-1 right-4 h-2 w-2 rotate-45 bg-[var(--chat-accent)]"
                          />
                        </span>
                      )}
                      <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[9px] font-black ${style.bg} ${style.border} ${style.color}`}>
                        {t(style.label)}
                      </span>
                      <p className="text-xs font-black leading-snug text-white/85 group-hover:text-white">{t(example.title)}</p>
                      <p className="line-clamp-3 text-[11px] font-bold leading-relaxed text-gray-400 group-hover:text-gray-300">
                        {t(example.prompt)}
                      </p>
                    </button>
                  );
                })}
              </div>

              {hasMoreExamples && (
                <div className="flex justify-center">
                  <Link
                    href={regionHref("/analytics/templates")}
                    className="rounded-2xl border border-white/[0.08] bg-[#121212] px-4 py-2 text-xs font-black text-gray-300 transition-colors duration-200 hover:border-white/[0.14] hover:bg-[#171717] hover:text-white"
                  >
                    {t("전체 보기")}
                  </Link>
                </div>
              )}
            </div>
          ) : (
            <div className="h-full overflow-y-auto" data-testid="strategy-my-content">
              {isLoadingStrategies ? (
                <div
                  className="flex flex-col items-center justify-center gap-3 py-10"
                  role="status"
                  aria-live="polite"
                  data-testid="strategy-my-loading"
                >
                  <Spinner
                    size={24}
                    className="animate-spin text-gray-500 motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                  <p className="text-xs font-bold text-gray-500">{t("전략 목록을 불러오는 중입니다...")}</p>
                </div>
              ) : strategiesError ? (
                <div className="py-8 text-center">
                  <p className="text-sm font-black text-white">{t("전략 목록을 불러올 수 없습니다")}</p>
                  <p className="mt-1 text-xs font-bold text-gray-500">{strategiesError}</p>
                </div>
              ) : myStrategies.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-sm font-black text-white">{t("아직 저장된 전략이 없습니다")}</p>
                  <p className="mt-1 text-xs font-bold text-gray-500">{t("전략을 생성하고 저장하면 여기에서 확인할 수 있습니다.")}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  {myStrategies.map((strategy) => {
                    const isDeleting = deletingStrategyIds.has(strategy.id);
                    return (
                      <div key={strategy.id} className="relative group">
                        <a
                          href={regionHref(`/analytics/${strategy.id}`)}
                          className="block rounded-2xl border border-white/[0.05] bg-[#121212] px-4 py-4 pr-14 transition-all duration-200 hover:border-white/[0.12] hover:bg-[#171717]"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-black text-white/85 group-hover:text-white">{strategy.name}</p>
                            </div>
                          </div>
                          <p className="mt-3 line-clamp-2 text-xs font-bold leading-relaxed text-gray-400">
                            {strategy.description || t("저장된 전략 상세 결과로 이동합니다.")}
                          </p>
                          <div className="mt-3 flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-gray-600">
                            <span>{t("{0}개 계좌 연결", strategy.accountCount)}</span>
                            <span>{new Date(strategy.createdAt).toLocaleDateString(getLocale())}</span>
                          </div>
                        </a>
                        <button
                          type="button"
                          onClick={() => void handleDeleteStrategy(strategy.id)}
                          disabled={isDeleting}
                          aria-label={t("{0} 전략 삭제", strategy.name)}
                          className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-md bg-white/[0.06] text-gray-500 transition-colors hover:bg-white/[0.10] hover:text-gray-200 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <X size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            setOpenVersionStrategyId((prev) => (prev === strategy.id ? null : strategy.id))
                          }
                          aria-expanded={openVersionStrategyId === strategy.id}
                          className="absolute bottom-3 right-3 rounded-md bg-white/[0.06] px-2 py-1 text-[10px] font-black uppercase tracking-widest text-gray-500 transition-colors hover:bg-white/[0.10] hover:text-gray-200"
                        >
                          {t("버전 이력")}
                        </button>
                        {openVersionStrategyId === strategy.id ? (
                          <div className="mt-2 rounded-2xl border border-white/[0.05] bg-[#101010]">
                            <StrategyVersionHistory strategyId={strategy.id} />
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        <footer
          aria-label={t("전략연구소 이용 안내")}
          className="border-t border-white/[0.06] pt-4 text-center"
        >
          {region !== "us" && (
            <Link
              href="/guide"
              className="mb-3 mr-4 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline"
            >
              {t("백테스트 가이드")}
            </Link>
          )}
          {region !== "us" && (
            <Link href="/board" className="mb-3 mr-4 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline">
              {t("자유게시판")}
            </Link>
          )}
          <Link
            href={regionHref("/?legal=terms")}
            className="mb-3 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline"
          >
            {t("이용약관")}
          </Link>
          <Link
            href={regionHref("/?legal=privacy")}
            className="mb-3 ml-4 inline-flex text-xs font-black text-gray-400 underline-offset-4 transition-colors hover:text-white hover:underline"
          >
            {t("개인정보처리방침")}
          </Link>
          <div className="mx-auto mb-3 max-w-6xl text-xs font-bold leading-relaxed text-gray-500">
            <BusinessInfoText />
          </div>
          <p className="mx-auto max-w-5xl text-xs font-bold leading-relaxed text-gray-600">
            <span className="block">
              {t("널스탁에서 제공하는 투자 정보는 고객의 투자 판단을 위한 단순 참고용일 뿐입니다. 백테스트 입력 예시에 쓰인 수치는 단순 예시값이며, 투자 추천이나 미래 성과를 의미하지 않습니다.")}
            </span>
            <span className="mt-1 block">
              {t("모든 투자 판단과 그에 따른 책임은 이용자 본인에게 있습니다")}
            </span>
          </p>
          <p className="mt-3 text-xs font-bold text-gray-600">
            © 2026 nullStock. All rights reserved.
          </p>
        </footer>
      </div>

      {selectedExample && (
        <StrategyTemplatePreviewModal
          example={selectedExample}
          onCancel={() => {
            setSelectedExample(null);
            onPreviewOpenChange?.(false);
          }}
          onGenerateStrategy={(prompt) => {
            onSelectExample(prompt);
            setSelectedExample(null);
            onPreviewOpenChange?.(false);
          }}
        />
      )}
    </div>
  );
}
