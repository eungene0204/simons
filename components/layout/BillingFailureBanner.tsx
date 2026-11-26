"use client";

// 자동결제 실패 배너(2026-11-26) — 정기결제가 처리되지 않은 구독자에게 상단 메뉴 아래 한 줄로 알린다.
// 메일 발송 계정(SMTP)이 없어 사이트 안 안내가 유일한 통로다. 닫으면 이 탭에서는 다시 띄우지 않는다
// (다음 방문·새 탭에서는 상태가 남아 있으면 다시 보인다).

import { useEffect, useState } from "react";
import { getLanguage, t } from "@/lib/i18n";

type BillingFailure = {
  planName: string;
  failCount: number;
  maxFailCount: number;
  nextRetryAt: string | null;
};

const DISMISS_KEY = "ns_billing_failure_dismissed";
const SUPPORT_EMAIL = "support@nullstock.im";

function formatRetry(iso: string): string {
  return new Intl.DateTimeFormat(getLanguage() === "en" ? "en-US" : "ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export default function BillingFailureBanner() {
  const [failure, setFailure] = useState<BillingFailure | null>(null);

  useEffect(() => {
    let disposed = false;
    try {
      if (sessionStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      // 저장소 차단 환경 — 닫기 기억 없이 동작한다.
    }
    fetch("/api/user/billing-status", { cache: "no-store", credentials: "same-origin" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!disposed && data?.failure) setFailure(data.failure as BillingFailure);
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, []);

  if (!failure) return null;

  const dismiss = () => {
    setFailure(null);
    try {
      sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // 무시
    }
  };

  return (
    <div
      role="alert"
      data-testid="billing-failure-banner"
      className="flex items-start gap-3 border-t border-[var(--error-red-line)] bg-[var(--chat-artifact-surface)] px-4 py-2.5 text-xs font-bold text-[var(--text-label)]"
    >
      <p className="flex-1 leading-5">
        <span className="font-black text-[var(--error-red)]">
          {t("자동결제가 처리되지 않았습니다")} ({failure.failCount}/{failure.maxFailCount})
        </span>{" "}
        {failure.nextRetryAt && (
          <>
            {t("다음 결제 시도")}: {formatRetry(failure.nextRetryAt)}.{" "}
          </>
        )}
        {t("연속으로 처리되지 않으면 Free 플랜으로 전환됩니다. 카드 한도·유효기간을 확인해 주시고, 결제 수단 변경은 고객센터로 문의해 주세요.")}{" "}
        <a href={`mailto:${SUPPORT_EMAIL}`} className="underline underline-offset-2 hover:text-white">
          {SUPPORT_EMAIL}
        </a>
      </p>
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("닫기")}
        className="shrink-0 rounded px-1.5 text-[var(--text-label)] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
      >
        ×
      </button>
    </div>
  );
}
