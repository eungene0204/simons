"use client";

import { useEffect, useRef } from "react";
import { X } from "phosphor-react";
import { t } from "@/lib/i18n";
import type { SectionKey } from "@/lib/strategy-graph/types";
import { SECTION_LABELS } from "@/lib/strategy-graph/transformSections";
import { STAGE_FAMILY } from "./labGraph";
import { FAMILY_ICON } from "./StrategyNode";
import type { CanvasBlockOption } from "./StrategyCanvas";

type BlockTrayProps = {
  open: boolean;
  stages: readonly SectionKey[];
  stage: SectionKey;
  onStageChange: (stage: SectionKey) => void;
  /** 칸별 블록(되묻기 칩과 같은 선택지 — 값이 정해져 있다). */
  options: (stage: SectionKey) => CanvasBlockOption[];
  /** 블록을 고르면 그 즉시 전략에 포함한다. */
  onPick: (stage: SectionKey, key: string) => void;
  /** 응답을 기다리는 중 — 블록을 고를 수 없다. */
  disabled?: boolean;
  onClose: () => void;
};

// 캔버스 위에서 내려오는 블록 트레이 — 칸을 고르면 그 칸에서 쓸 수 있는 옵션이 블록 모양으로 나열된다.
// 닫혀 있을 때는 위로 올라가 보이지 않고(invisible) 탭 이동에서도 빠진다. 움직임은 감속 설정에서 꺼진다.
export default function BlockTray({ open, stages, stage, onStageChange, options: optionsFor, onPick, onClose, disabled = false }: BlockTrayProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  // 트레이 밖을 누르거나 Esc를 누르면 접는다. 여는 버튼(data-block-tray-toggle)은 제외한다 —
  // 누르는 순간 접었다가 click이 다시 여는 깜박임을 막고, 토글이 그 버튼의 몫이 되게 한다.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Element | null;
      if (!target || rootRef.current?.contains(target) || target.closest("[data-block-tray-toggle]")) return;
      onClose();
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open, onClose]);

  const options = optionsFor(stage);
  const Icon = FAMILY_ICON[STAGE_FAMILY[stage]];

  return (
    <div
      ref={rootRef}
      className={`absolute inset-x-0 top-0 z-20 border-b border-[var(--lab-border)] bg-[var(--lab-panel)] transition-transform duration-200 ease-out motion-reduce:transition-none ${
        open ? "translate-y-0" : "invisible -translate-y-full"
      }`}
      data-testid="lab-block-tray"
      data-open={open ? "true" : "false"}
      aria-hidden={!open}
      role="region"
      aria-label={t("블록 추가")}
    >
      <div className="flex items-center gap-2 px-3 pt-2">
        <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto" role="tablist" aria-label={t("칸 선택")}>
          {stages.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={stage === key}
              onClick={() => onStageChange(key)}
              className={`flex-shrink-0 rounded-md px-2.5 py-1 text-xs font-black transition-colors ${
                stage === key ? "bg-white/[0.12] text-white" : "text-[var(--text-label)] hover:text-white"
              }`}
            >
              {t(SECTION_LABELS[key])}
            </button>
          ))}
        </div>
        <button type="button" onClick={onClose} className="lab-icon-button flex-shrink-0" aria-label={t("블록 트레이 닫기")} title={t("블록 트레이 닫기")}>
          <X size={14} weight="bold" />
        </button>
      </div>
      <div className="flex gap-2 overflow-x-auto px-3 pb-3 pt-2" role="group" aria-label={t("{0} 옵션", t(SECTION_LABELS[stage]))}>
        {disabled && options.length > 0 && (
          <p className="flex-shrink-0 self-center pr-1 text-[11px] font-bold text-[var(--text-label)]">{t("응답을 기다리는 중입니다.")}</p>
        )}
        {options.map((option) => (
          <button
            key={option.key}
            type="button"
            onClick={() => onPick(stage, option.key)}
            disabled={disabled}
            tabIndex={open ? 0 : -1}
            data-testid="lab-block-option"
            className="flex w-[132px] flex-shrink-0 flex-col items-center gap-1.5 rounded-xl border border-[var(--lab-border)] bg-[var(--lab-node)] px-2 py-2.5 text-center transition-colors hover:border-[var(--lab-border-strong)] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
          >
            <Icon size={20} weight="duotone" className="text-white" />
            <span className="line-clamp-3 text-xs font-black leading-tight text-white">{t(option.label)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
