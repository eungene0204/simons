"use client";

import { useCallback, useId, useRef, useState, type ReactNode } from "react";
import { t } from "@/lib/i18n";
import { useDialogBehavior } from "@/lib/hooks/useDialogBehavior";

export type ConfirmOptions = {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** 되돌릴 수 없는 동작(삭제·해지·청산) — §10 삭제 버튼 스타일(빨간 테두리·글자, 투명 면). */
  danger?: boolean;
};

type ConfirmDialogProps = ConfirmOptions & {
  onConfirm: () => void;
  onCancel: () => void;
};

// 브라우저 기본 window.confirm을 대체하는 앱 내 확인 대화(2026-09-08 — 강제청산·구독 해지·
// 계정 삭제가 스타일도 번역도 안 되는 기본 대화로 나가던 결함). Esc·포커스 트랩·포커스 복귀는
// useDialogBehavior가 맡는다. 첫 포커스는 DOM 순서상 앞에 있는 '취소'에 놓인다 — 실수로
// Enter를 눌러도 되돌릴 수 없는 동작이 실행되지 않게.
export default function ConfirmDialog({
  title,
  message,
  confirmLabel,
  cancelLabel,
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const messageId = useId();
  useDialogBehavior({ open: true, onClose: onCancel, containerRef: panelRef });

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
      <div
        ref={panelRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={message ? messageId : undefined}
        tabIndex={-1}
        data-testid="confirm-dialog"
        className="w-full max-w-sm rounded-2xl border border-white/[0.08] bg-[var(--background)] p-6 shadow-2xl shadow-black/50"
      >
        <p id={titleId} className="text-lg font-black leading-snug text-white">
          {title}
        </p>
        {message && (
          <p id={messageId} className="mt-2 text-sm font-bold leading-relaxed text-gray-400">
            {message}
          </p>
        )}
        <div className="mt-6 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xl border border-white/[0.12] px-4 py-2.5 text-sm font-bold text-gray-200 transition-colors hover:bg-white/[0.06]"
          >
            {cancelLabel ?? t("취소")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={
              danger
                ? "rounded-xl border border-red-500/50 px-4 py-2.5 text-sm font-black text-red-400 transition-colors hover:bg-red-500/10"
                : "rounded-xl bg-[var(--chat-accent)] px-4 py-2.5 text-sm font-black text-[var(--chat-accent-ink)] transition-colors hover:bg-[#f5c04a]"
            }
          >
            {confirmLabel ?? t("확인")}
          </button>
        </div>
      </div>
    </div>
  );
}

type PendingConfirm = ConfirmOptions & { resolve: (value: boolean) => void };

/**
 * `const { confirm, dialog } = useConfirmDialog();`
 * `if (!(await confirm({ title: "...", danger: true }))) return;`
 * `dialog`는 컴포넌트 트리 어딘가에 한 번 렌더한다.
 */
export function useConfirmDialog(): {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  dialog: ReactNode;
} {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const pendingRef = useRef<PendingConfirm | null>(null);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      // 이미 열린 확인창이 있으면 그 약속은 '취소'로 끝낸다 — 매달린 채 남지 않게.
      pendingRef.current?.resolve(false);
      const next = { ...options, resolve };
      pendingRef.current = next;
      setPending(next);
    });
  }, []);

  const settle = useCallback((value: boolean) => {
    const current = pendingRef.current;
    pendingRef.current = null;
    setPending(null);
    current?.resolve(value);
  }, []);

  const dialog = pending ? (
    <ConfirmDialog
      title={pending.title}
      message={pending.message}
      confirmLabel={pending.confirmLabel}
      cancelLabel={pending.cancelLabel}
      danger={pending.danger}
      onConfirm={() => settle(true)}
      onCancel={() => settle(false)}
    />
  ) : null;

  return { confirm, dialog };
}
