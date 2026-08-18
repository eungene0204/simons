"use client";

import { useRef, useState } from "react";
import { Check, FloppyDisk, Spinner, WarningCircle } from "phosphor-react";
import { t } from "@/lib/i18n";

type SaveState = "idle" | "saving" | "saved" | "error";

interface SaveValidationButtonProps {
  onSave: () => Promise<void>;
  disabled?: boolean;
  label?: string;
}

// 워크포워드·몬테카를로 검증 결과 저장 버튼(상태 피드백 공용).
export default function SaveValidationButton({
  onSave,
  disabled = false,
  label = t("결과 저장"),
}: SaveValidationButtonProps) {
  const [state, setState] = useState<SaveState>("idle");
  const revertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleRevert = () => {
    if (revertTimerRef.current) clearTimeout(revertTimerRef.current);
    revertTimerRef.current = setTimeout(() => setState("idle"), 2500);
  };

  const handleClick = async () => {
    if (state === "saving") return;
    setState("saving");
    try {
      await onSave();
      setState("saved");
    } catch {
      setState("error");
    }
    scheduleRevert();
  };

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={disabled || state === "saving"}
      className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-black transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
        state === "saved"
          ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
          : state === "error"
            ? "border-red-400/40 bg-red-500/10 text-red-300"
            : "border-white/15 bg-white/[0.04] text-gray-200 hover:bg-white/[0.08]"
      }`}
    >
      {state === "saving" && <Spinner className="h-4 w-4 animate-spin" />}
      {state === "saved" && <Check className="h-4 w-4" weight="bold" />}
      {state === "error" && <WarningCircle className="h-4 w-4" weight="bold" />}
      {state === "idle" && <FloppyDisk className="h-4 w-4" weight="bold" />}
      {state === "saving" ? t("저장 중...") : state === "saved" ? t("저장됨") : state === "error" ? t("저장 실패") : label}
    </button>
  );
}
