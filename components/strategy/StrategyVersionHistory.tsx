"use client";

import { useCallback, useEffect, useState } from "react";

import { t, getLocale } from "@/lib/i18n";

// 내 전략 버전 이력(2026-09-23) — 같은 이름으로 저장할 때마다 남은 설정 스냅샷.
// 전략 행의 id는 DSL 해시라 내용을 고치면 다른 행이 된다 — 이력은 사용자+이름 계보로 묶인다
// (정본: lib/server/strategyVersions.ts).
interface VersionRow {
  id: string;
  version: number;
  strategyId: string;
  name: string;
  description: string | null;
  createdAt: string;
  isCurrent: boolean;
}

export default function StrategyVersionHistory({
  strategyId,
  onRestored,
}: {
  strategyId: string;
  onRestored?: () => void;
}) {
  const [versions, setVersions] = useState<VersionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/strategy/${strategyId}/versions`, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      setVersions(Array.isArray(data.versions) ? data.versions : []);
    } catch {
      setError(t("버전 이력을 불러오지 못했습니다."));
    }
  }, [strategyId]);

  useEffect(() => {
    void load();
  }, [load]);

  const restore = useCallback(
    async (versionId: string) => {
      setRestoringId(versionId);
      setError(null);
      try {
        const res = await fetch(`/api/strategy/${strategyId}/versions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ versionId }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error ?? t("되돌리기에 실패했습니다."));
        // 저장은 기존 경로가 한 번만 담당한다 — 여기서 별도 저장 규칙을 만들지 않는다.
        const saved = await fetch("/api/strategy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data.settings),
        });
        if (!saved.ok) throw new Error(t("되돌리기에 실패했습니다."));
        await load();
        onRestored?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : t("되돌리기에 실패했습니다."));
      } finally {
        setRestoringId(null);
      }
    },
    [strategyId, load, onRestored],
  );

  if (error) {
    return <p className="px-4 py-3 text-xs font-bold text-[var(--main-blue)]">{error}</p>;
  }
  if (versions == null) {
    return <p className="px-4 py-3 text-xs font-bold text-gray-500">{t("불러오는 중…")}</p>;
  }
  if (versions.length === 0) {
    return (
      <p className="px-4 py-3 text-xs font-bold text-gray-500">
        {t("저장된 버전 이력이 없습니다. 이 전략을 다시 저장하면 그때부터 이력이 쌓입니다.")}
      </p>
    );
  }

  return (
    <ul className="divide-y divide-white/[0.04]">
      {versions.map((v) => (
        <li key={v.id} className="flex items-center justify-between gap-3 px-4 py-2">
          <div className="min-w-0">
            <p className="truncate text-xs font-bold text-white/80">
              {t("버전 {0}", v.version)}
              {v.isCurrent ? (
                <span className="ml-2 text-[10px] font-black uppercase tracking-widest text-[var(--chat-accent)]">
                  {t("현재")}
                </span>
              ) : null}
            </p>
            <p className="truncate text-[11px] font-bold text-gray-500">
              {new Date(v.createdAt).toLocaleString(getLocale())}
            </p>
          </div>
          {v.isCurrent ? null : (
            <button
              type="button"
              onClick={() => void restore(v.id)}
              disabled={restoringId != null}
              className="flex-shrink-0 rounded-lg bg-white/[0.06] px-3 py-1 text-[11px] font-black text-gray-200 transition-colors hover:bg-white/[0.10] disabled:opacity-50"
            >
              {restoringId === v.id ? t("되돌리는 중…") : t("이 버전으로 되돌리기")}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
