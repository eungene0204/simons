"use client";

import { useLanguage } from "./LanguageProvider";
import type { Language } from "./index";

const OPTIONS: Array<{ value: Language; label: string; title: string }> = [
  { value: "ko", label: "KR", title: "한국어" },
  { value: "en", label: "EN", title: "English" },
];

/**
 * KR / EN 표시 언어 토글. 상단 내비게이션의 프로필 사진 왼쪽에 놓인다.
 * 선택 즉시 언어를 영속하고 새로고침해 전체 화면을 새 언어로 다시 그린다.
 */
export default function LanguageToggle({
  className = "",
  size = "sm",
}: {
  className?: string;
  size?: "sm" | "md";
}) {
  const { language, switchLanguage } = useLanguage();
  const segment =
    size === "md" ? "px-3 py-1.5 text-xs" : "px-2.5 py-1 text-[11px]";

  return (
    <div
      role="group"
      aria-label="Language"
      data-testid="language-toggle"
      className={`flex flex-shrink-0 items-center rounded-full border border-white/[0.08] bg-black/40 p-0.5 ${className}`}
    >
      {OPTIONS.map((option) => {
        const isActive = option.value === language;
        return (
          <button
            key={option.value}
            type="button"
            lang={option.value}
            title={option.title}
            aria-pressed={isActive}
            onClick={() => switchLanguage(option.value)}
            className={`rounded-full font-black tracking-wide transition-colors duration-200 ${segment} ${
              isActive
                ? "bg-white text-black"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
