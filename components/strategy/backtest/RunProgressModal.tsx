"use client";

import type { ReactNode } from "react";
import { ArrowsClockwise, Warning } from "phosphor-react";
import { t } from "@/lib/i18n";

interface RunProgressModalProps {
  open: boolean;
  title: string;
  isRunning: boolean;
  progressRatio?: number;
  progressLabel?: string;
  /** 현재 어떤 작업을 하고 있는지 보여주는 추가 정보 (예: IS/OOS 구간 날짜) */
  detail?: ReactNode;
  error?: string | null;
  onCancel?: () => void;
  onClose: () => void;
}

export default function RunProgressModal({
  open,
  title,
  isRunning,
  progressRatio,
  progressLabel,
  detail,
  error,
  onCancel,
  onClose,
}: RunProgressModalProps) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="run-progress-modal-title"
      className="fixed inset-0 z-[10010] flex items-center justify-center bg-black/70 p-2 lg:px-4 lg:py-0"
    >
      <div
        data-testid="run-progress-modal-panel"
        className="max-h-[calc(100dvh-1rem)] w-full max-w-sm overflow-y-auto rounded-xl border border-white/[0.10] bg-[#111111] p-4 shadow-[0_24px_80px_rgba(0,0,0,0.65)] lg:max-h-none lg:overflow-visible lg:p-6"
      >
        <div className="flex items-center gap-2">
          {isRunning && !error && (
            <ArrowsClockwise className="h-4 w-4 shrink-0 animate-spin text-[var(--main-blue)]" />
          )}
          <p id="run-progress-modal-title" className="text-sm font-black text-white">
            {title}
          </p>
        </div>

        {error ? (
          <div className="mt-5 flex items-start gap-3">
            <Warning className="mt-0.5 h-4 w-4 shrink-0 text-[var(--main-blue)]" />
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-widest text-[var(--main-blue)]">{t("실행 오류")}</p>
              <p className="mt-1 break-words text-sm font-black leading-6 text-white">{error}</p>
            </div>
          </div>
        ) : (
          <div className="mt-5">
            <div
              role="progressbar"
              aria-label={title}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progressRatio !== undefined ? Math.round(progressRatio * 100) : undefined}
              className="h-2 w-full overflow-hidden rounded-full bg-white/[0.08]"
            >
              <div
                className="h-full rounded-full bg-[var(--main-blue)] transition-[width]"
                style={{ width: `${Math.round((progressRatio ?? 0) * 100)}%` }}
              />
            </div>
            {progressLabel && (
              <p className="mt-2 text-xs font-bold tabular-nums text-gray-400">{progressLabel}</p>
            )}
            {detail && (
              <div className="mt-3 break-words space-y-1 rounded-lg border border-white/[0.06] bg-white/[0.03] px-3 py-2.5 text-xs font-bold leading-5 text-gray-300">
                {detail}
              </div>
            )}
          </div>
        )}

        <div className="mt-6 flex items-center justify-end gap-2">
          {isRunning && !error && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm font-black text-gray-400 transition-colors hover:bg-white/[0.03] hover:text-white"
            >
              {t("취소")}
            </button>
          )}
          {!isRunning && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md bg-[var(--main-blue)] px-4 py-2 text-sm font-black text-white transition-opacity hover:opacity-90"
            >
              {t("닫기")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
