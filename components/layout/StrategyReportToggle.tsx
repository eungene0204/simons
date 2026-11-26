"use client";

// 설정 > 요금제의 '저장 전략 월간 리포트' 수신 토글(2026-11-26).
// 유료 플랜(PRO·PREMIUM)에서만 켤 수 있다. 이미 켠 사용자가 플랜을 내렸으면 끌 수 있게 그대로 보인다.

import { useEffect, useState } from "react";
import { t } from "@/lib/i18n";

type Setting = { optIn: boolean; eligible: boolean };

export default function StrategyReportToggle() {
  const [setting, setSetting] = useState<Setting | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    fetch("/api/user/strategy-report", { cache: "no-store", credentials: "same-origin" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!disposed && data && typeof data.optIn === "boolean") setSetting(data);
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, []);

  if (!setting || (!setting.eligible && !setting.optIn)) return null;

  const toggle = async () => {
    if (isSaving) return;
    setIsSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/user/strategy-report", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ optIn: !setting.optIn }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.error === "string" ? t(data.error) : t("설정을 저장하지 못했습니다."));
      setSetting(data as Setting);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("설정을 저장하지 못했습니다."));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section>
      <h3 className="text-lg font-black tracking-tight text-gray-200">{t("저장 전략 월간 리포트")}</h3>
      <div className="mt-4 flex items-center justify-between gap-5 py-1">
        <p className="text-sm font-bold text-gray-300">
          {t("매달 1일, 저장한 전략(최근 수정 5개)을 최신 데이터로 다시 백테스트한 결과를 메일로 받습니다.")}
        </p>
        <button
          type="button"
          role="switch"
          aria-checked={setting.optIn}
          aria-label={t("저장 전략 월간 리포트")}
          onClick={() => void toggle()}
          disabled={isSaving}
          data-testid="strategy-report-toggle"
          className={`relative h-6 w-11 flex-shrink-0 rounded-full transition-colors duration-200 disabled:opacity-60 ${
            setting.optIn ? "bg-[var(--main-green)]" : "bg-white/[0.15]"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform duration-200 ${
              setting.optIn ? "translate-x-[22px]" : "translate-x-0.5"
            }`}
          />
        </button>
      </div>
      <p className="text-xs font-bold text-gray-600">
        {t("월 백테스트 횟수에서 차감되지 않습니다.")}
      </p>
      {error && <p className="mt-2 text-xs font-bold text-red-300">{error}</p>}
    </section>
  );
}
