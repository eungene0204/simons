"use client";

// 글로벌 서비스(/us) 구독 승인 복귀 화면 — PayPal 승인 뒤 return_url로 돌아온 사용자에게
// 결과를 보여준다.
//
// 유료 전환의 정본은 웹훅이다. 이 화면은 사용자가 결과를 즉시 보도록 sync 라우트를 한 번
// 호출할 뿐이며(웹훅과 같은 멱등 경로), 아직 활성화 전이면 처리 중임을 알린다 — 승인
// 직후에는 PayPal 쪽 상태가 잠깐 APPROVAL_PENDING에 머무를 수 있다.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { regionRequestHeaders, useRegionHref } from "@/lib/geo/useRegion";
import { US_PRICING } from "@/lib/pricing/us";
import { isValidPlanId } from "@/lib/plans";
import { trackEvent } from "@/lib/analytics";

type Status = "checking" | "active" | "pending" | "error";

export default function UsPaymentSuccess() {
  const regionHref = useRegionHref();
  const [status, setStatus] = useState<Status>("checking");
  const [planId, setPlanId] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const requestedRef = useRef(false);

  useEffect(() => {
    // StrictMode 이중 실행으로 같은 요청이 두 번 나가지 않도록 가드
    if (requestedRef.current) return;
    requestedRef.current = true;

    (async () => {
      try {
        const res = await fetch("/api/payment/paypal/subscription/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...regionRequestHeaders() },
          credentials: "same-origin",
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          throw new Error(data?.error ?? "We could not confirm your subscription.");
        }
        if (data?.status === "ACTIVE") {
          const activePlanId = typeof data.planId === "string" ? data.planId : "";
          setPlanId(activePlanId);
          setStatus("active");

          // 구독이 ACTIVE로 확인된 시점에만 보낸다(승인 복귀만으로는 미확정 —
          // pending이면 웹훅이 정본으로 처리하므로 이 화면에서는 보내지 않는다).
          trackEvent("subscription_start", {
            plan_name: activePlanId || "unknown",
            billing_period: "monthly",
            value: isValidPlanId(activePlanId) ? US_PRICING.monthlyPrice[activePlanId] : 0,
            currency: "USD",
          });
        } else {
          setStatus("pending");
        }
      } catch (e) {
        setStatus("error");
        setMessage(e instanceof Error ? e.message : "We could not confirm your subscription.");
      }
    })();
  }, []);

  return (
    <div className="mx-auto w-full max-w-xl rounded-3xl border border-white/[0.08] bg-[#0a0a0a] px-8 py-12 text-center">
      {status === "checking" ? (
        <>
          <h1 className="text-2xl font-black tracking-tight text-white">Confirming your subscription...</h1>
          <p className="mt-3 text-sm font-bold text-gray-500">This only takes a moment.</p>
        </>
      ) : null}

      {status === "active" ? (
        <>
          <h1 className="text-2xl font-black tracking-tight text-[var(--main-green,#22c55e)]">
            Subscription active
          </h1>
          <p className="mt-3 text-sm font-bold text-gray-400">
            {planId ? `Your ${planId} plan is now active.` : "Your plan is now active."}
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Link
              href={regionHref("/pricing")}
              className="rounded-2xl border border-white/[0.12] px-6 py-3 text-sm font-black text-white hover:bg-white/[0.06]"
            >
              View plans
            </Link>
            <Link
              href={regionHref("/dashboard")}
              className="rounded-2xl bg-blue-600 px-6 py-3 text-sm font-black text-white hover:bg-blue-500"
            >
              Go to dashboard
            </Link>
          </div>
        </>
      ) : null}

      {status === "pending" ? (
        <>
          <h1 className="text-2xl font-black tracking-tight text-white">Subscription is being processed</h1>
          <p className="mt-3 text-sm font-bold text-gray-400">
            PayPal has not confirmed the subscription yet. Your plan will update automatically once it
            does — you can close this page.
          </p>
          <Link
            href={regionHref("/pricing")}
            className="mt-8 inline-block rounded-2xl border border-white/[0.12] px-6 py-3 text-sm font-black text-white hover:bg-white/[0.06]"
          >
            View plans
          </Link>
        </>
      ) : null}

      {status === "error" ? (
        <>
          <h1 className="text-2xl font-black tracking-tight text-[var(--main-red)]">
            We could not confirm your subscription
          </h1>
          <p className="mt-3 text-sm font-bold text-gray-400">{message}</p>
          <Link
            href={regionHref("/pricing")}
            className="mt-8 inline-block rounded-2xl border border-white/[0.12] px-6 py-3 text-sm font-black text-white hover:bg-white/[0.06]"
          >
            Back to plans
          </Link>
        </>
      ) : null}
    </div>
  );
}
