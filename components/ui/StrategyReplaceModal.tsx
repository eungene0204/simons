"use client";

import { useEffect, useMemo, useState } from "react";
import { X, CheckCircle, ArrowsClockwise } from "phosphor-react";
import { t } from "@/lib/i18n";

interface StrategyItem {
  id: string;
  name: string;
  description?: string | null;
  type?: string;
  universe?: string;
  aiScore?: number | null;
  createdAt?: string;
}

interface StrategyReplaceModalProps {
  isOpen: boolean;
  currentStrategyId?: string;
  currentStrategyName?: string;
  onClose: () => void;
  onReplace: (strategy: StrategyItem) => Promise<void> | void;
}

export default function StrategyReplaceModal({
  isOpen,
  currentStrategyId,
  currentStrategyName,
  onClose,
  onReplace,
}: StrategyReplaceModalProps) {
  const [strategies, setStrategies] = useState<StrategyItem[]>([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError("");
    fetch("/api/strategy")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: StrategyItem[]) => {
        setStrategies(data);
        const fallback = data.find((s) => s.id === currentStrategyId) ?? data[0];
        setSelectedStrategyId(fallback?.id ?? "");
      })
      .catch(() => {
        setStrategies([]);
        setSelectedStrategyId("");
        setError(t("저장된 전략을 불러오지 못했습니다."));
      })
      .finally(() => setLoading(false));
  }, [isOpen, currentStrategyId]);

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.id === selectedStrategyId),
    [strategies, selectedStrategyId]
  );

  const handleReplace = async () => {
    if (!selectedStrategy) return;
    setSaving(true);
    setError("");
    try {
      await onReplace(selectedStrategy);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("전략 교체에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4">
      <div className="w-full max-w-3xl max-h-[85vh] overflow-hidden rounded-2xl border border-white/[0.08] bg-[#121212] shadow-2xl flex flex-col">
        <div className="flex items-center justify-between border-b border-white/[0.08] px-5 py-4">
          <div>
            <h2 className="text-lg font-black text-white">{t("전략 교체")}</h2>
            <p className="text-xs font-medium text-gray-500 mt-1">
              {t("저장된 전략 중 하나를 선택해 계좌에 연결합니다.")}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-white/[0.08] p-2 text-gray-500 hover:text-white hover:border-white/[0.16] transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{t("현재 전략")}</p>
            <p className="mt-1 text-sm font-bold text-white">
              {currentStrategyName ?? t("연결된 전략 없음")}
            </p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16 text-sm text-gray-500">
              <ArrowsClockwise size={18} className="mr-2 animate-spin" />
              {t("저장된 전략을 불러오는 중입니다.")}
            </div>
          ) : strategies.length === 0 ? (
            <div className="rounded-xl border border-dashed border-white/[0.08] bg-white/[0.02] py-14 text-center">
              <p className="text-sm font-bold text-gray-500">{t("저장된 전략이 없습니다.")}</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {strategies.map((strategy) => {
                const isSelected = selectedStrategyId === strategy.id;
                const isCurrent = strategy.id === currentStrategyId;
                return (
                  <button
                    key={strategy.id}
                    type="button"
                    onClick={() => setSelectedStrategyId(strategy.id)}
                    className={`w-full rounded-xl border p-4 text-left transition-all duration-200 ${
                      isSelected
                        ? "border-sky-400/40"
                        : "border-white/[0.06] hover:border-white/[0.12]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-bold text-white">{strategy.name}</p>
                          {isCurrent && (
                            <span className="rounded-md bg-white/[0.08] px-2 py-0.5 text-[10px] font-bold text-gray-400">
                              {t("현재")}
                            </span>
                          )}
                        </div>
                        <p className="mt-1 line-clamp-2 text-xs font-medium text-gray-500">
                          {strategy.description || t("설명이 없습니다.")}
                        </p>
                      </div>
                      {isSelected && <CheckCircle size={18} className="flex-shrink-0 text-sky-400" />}
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {error && (
            <p className="mt-4 text-xs font-bold text-[var(--main-blue)]">{error}</p>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.08] px-5 py-4">
          <button
            onClick={onClose}
            className="rounded-xl border border-white/[0.08] px-4 py-2 text-xs font-bold text-gray-400 hover:text-white hover:border-white/[0.16] transition-colors"
          >
            {t("닫기")}
          </button>
          <button
            onClick={handleReplace}
            disabled={!selectedStrategy || selectedStrategy.id === currentStrategyId || saving}
            className="rounded-xl bg-white px-4 py-2 text-xs font-black text-black transition-colors disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saving ? t("교체 중...") : t("전략 교체")}
          </button>
        </div>
      </div>
    </div>
  );
}
