"use client";

import { useEffect, useState } from "react";
import { Trash, X, Spinner } from "phosphor-react";
import {
  deleteSavedValidation,
  listSavedValidations,
  type SavedValidationSummary,
} from "@/lib/validation-storage";

interface SavedValidationsModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (item: SavedValidationSummary) => void;
}

const MODEL_LABELS: Record<string, string> = {
  walkForward: "워크포워드",
  monteCarlo: "몬테카를로",
};

function formatDate(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatPercent(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(1)}%`;
}

function summaryLine(item: SavedValidationSummary): string {
  const s = item.summary ?? {};
  if (item.modelType === "walkForward") {
    const wfe = s.wfeValid === false ? "해석 불가" : formatPercent(s.wfe);
    return `WFE ${wfe} · ${s.nSplits ?? "-"}개 구간`;
  }
  return `중앙 CAGR ${formatPercent(s.medianCagr)} · ${(s.iterations as number)?.toLocaleString?.() ?? "-"}회`;
}

// 저장된 검증 결과 목록(불러오기/삭제).
export default function SavedValidationsModal({ open, onClose, onSelect }: SavedValidationsModalProps) {
  const [items, setItems] = useState<SavedValidationSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    listSavedValidations()
      .then((rows) => {
        if (!cancelled) setItems(rows);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "목록을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const handleDelete = async (id: string) => {
    try {
      await deleteSavedValidation(id);
      setItems((prev) => prev.filter((row) => row.id !== id));
    } catch {
      setError("삭제에 실패했습니다.");
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-2 lg:p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="저장된 검증 결과"
    >
      <div
        data-testid="saved-validations-panel"
        className="flex max-h-[calc(100dvh-1rem)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/[0.10] bg-[#111112] lg:max-h-[80vh]"
        onClick={(event) => event.stopPropagation()}
      >
        <div
          data-testid="saved-validations-header"
          className="flex items-center justify-between border-b border-white/[0.08] px-4 py-3 lg:px-5 lg:py-4"
        >
          <h3 className="text-base font-black text-white">저장된 검증 결과</h3>
          <button
            type="button"
            aria-label="닫기"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-400 hover:bg-white/[0.06] hover:text-white"
          >
            <X className="h-4 w-4" weight="bold" />
          </button>
        </div>

        <div
          data-testid="saved-validations-list"
          className="min-h-0 flex-1 overflow-y-auto p-3 lg:p-4"
        >
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-12 text-sm font-bold text-gray-400">
              <Spinner className="h-4 w-4 animate-spin" /> 불러오는 중...
            </div>
          )}
          {!isLoading && error && (
            <p className="px-2 py-8 text-center text-sm font-bold text-red-300">{error}</p>
          )}
          {!isLoading && !error && items.length === 0 && (
            <p className="px-2 py-12 text-center text-sm font-bold text-gray-500">
              저장된 검증 결과가 없습니다.
            </p>
          )}
          {!isLoading && !error && items.length > 0 && (
            <ul className="space-y-2">
              {items.map((item) => (
                <li key={item.id}>
                  <div className="group flex items-center gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] p-3 transition-colors hover:border-white/20 hover:bg-white/[0.06]">
                    <button
                      type="button"
                      onClick={() => onSelect(item)}
                      className="flex min-w-0 flex-1 flex-col items-start text-left"
                    >
                      <div className="flex w-full min-w-0 items-center gap-2">
                        <span
                          className={`shrink-0 whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-black uppercase tracking-widest ${
                            item.modelType === "walkForward"
                              ? "bg-sky-500/15 text-sky-300"
                              : "bg-violet-500/15 text-violet-300"
                          }`}
                        >
                          {MODEL_LABELS[item.modelType] ?? item.modelType}
                        </span>
                        <span className="min-w-0 truncate text-sm font-black text-white">{item.strategyName}</span>
                      </div>
                      <span className="mt-1 text-xs font-bold text-gray-400">{summaryLine(item)}</span>
                      <span className="mt-0.5 text-[11px] font-bold text-gray-600">{formatDate(item.createdAt)}</span>
                    </button>
                    <button
                      type="button"
                      aria-label="삭제"
                      onClick={() => void handleDelete(item.id)}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-500 opacity-100 transition-opacity hover:bg-red-500/10 hover:text-red-300 lg:opacity-0 lg:group-hover:opacity-100"
                    >
                      <Trash className="h-4 w-4" weight="bold" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
