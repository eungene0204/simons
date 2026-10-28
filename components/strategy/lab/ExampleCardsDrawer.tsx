"use client";

import Link from "next/link";
import { memo, useMemo, useState } from "react";
import { t } from "@/lib/i18n";
import { useRegion, useRegionHref } from "@/lib/geo/useRegion";
import { EXAMPLES, type Example, type ExampleCategory } from "@/components/strategy/strategyExamples";
import { US_EXAMPLES } from "@/components/strategy/usExamples";
import { StrategyLabLegalFooter } from "@/components/strategy/StrategyLabLegalFooter";

type ExampleCardsDrawerProps = {
  /** 카드를 고르면 예시 문장을 입력창에 채운다(자동 전송하지 않는다). */
  onPick: (prompt: string) => void;
};

// 시작 화면과 같은 장수만 보여 주고 나머지는 템플릿 페이지로 잇는다(서랍 DOM을 가볍게 둔다).
const VISIBLE_COUNT = 20;

const LEVEL_LABEL: Record<Example["level"], string> = {
  beginner: "입문",
  intermediate: "중급",
  expert: "고급",
};

// 우측 서랍 — "전략 예시"(추천이 아니다). 카드의 태그는 예시 정의에 이미 있는 분류·난이도만 쓴다
// — 예시 문장을 읽어 어떤 노드가 쓰일지 짐작해 태그를 만들지 않는다(문장 의미는 해석 레인 소관).
function ExampleCardsDrawer({ onPick }: ExampleCardsDrawerProps) {
  const region = useRegion();
  const regionHref = useRegionHref();
  const examples = region === "us" ? US_EXAMPLES : EXAMPLES;
  const categories = useMemo(() => Array.from(new Set(examples.map((e) => e.category))), [examples]);
  const [category, setCategory] = useState<ExampleCategory | "all">("all");
  const matching = category === "all" ? examples : examples.filter((e) => e.category === category);
  const visible = matching.slice(0, VISIBLE_COUNT);

  return (
    <div className="flex h-full flex-col" data-testid="lab-examples">
      <div className="border-b border-[var(--lab-border)] px-3 pb-2 pt-3">
        <p className="text-xs font-black text-white">{t("전략 예시")}</p>
        <p className="mt-0.5 text-[11px] font-bold leading-relaxed text-[var(--text-label)]">
          {t("카드를 누르면 예시 문장이 입력창에 채워집니다.")}
        </p>
        <div className="mt-2 flex flex-wrap gap-1" role="tablist" aria-label={t("예시 분류")}>
          {(["all", ...categories] as const).map((c) => (
            <button
              key={c}
              type="button"
              role="tab"
              aria-selected={category === c}
              onClick={() => setCategory(c)}
              className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${
                category === c ? "bg-white/[0.12] text-white" : "text-[var(--text-label)] hover:text-white"
              }`}
            >
              {c === "all" ? t("전체") : t(c)}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <ul className="space-y-2">
          {visible.map((example) => (
            <li key={`${example.category}:${example.title}`}>
              <button
                type="button"
                onClick={() => onPick(t(example.prompt))}
                className="w-full rounded-xl border border-[var(--lab-border)] bg-[var(--lab-node)] p-3 text-left transition-colors hover:border-[var(--lab-border-strong)]"
                data-testid="lab-example-card"
              >
                <p className="text-xs font-black text-white">{t(example.title)}</p>
                <p className="mt-1 line-clamp-2 text-[11px] font-bold leading-relaxed text-gray-400">{t(example.prompt)}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-bold text-gray-400">{t(example.category)}</span>
                  <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-bold text-gray-400">{t(LEVEL_LABEL[example.level])}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
        {matching.length > visible.length && (
          <Link
            href={regionHref("/analytics/templates")}
            className="mt-2 block rounded-lg border border-[var(--lab-border)] px-3 py-1.5 text-center text-xs font-black text-gray-300 hover:text-white"
          >
            {t("전체 보기")}
          </Link>
        )}
        {/* 시작 화면에 있던 이용 안내(약관·사업자 정보·투자 유의 문구)를 예시 목록 끝에 둔다. */}
        <StrategyLabLegalFooter className="mt-4" />
      </div>
    </div>
  );
}

export default memo(ExampleCardsDrawer);
