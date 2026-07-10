"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

interface PaymentSuccessProps {
  authKey: string;
  customerKey: string;
  orderId: string;
}

// 자동결제(빌링) successUrl 리다이렉트 페이지 — 카드 등록 인증 결과(authKey)를 서버
// 승인(/api/payment/confirm)으로 보내 빌링키 발급 + 첫 달 결제를 확정한다.
// 승인 전까지는 결제가 완료된 것이 아니므로 "승인 중" 상태를 명확히 보여준다.
export default function PaymentSuccess({ authKey, customerKey, orderId }: PaymentSuccessProps) {
  const [status, setStatus] = useState<"confirming" | "done" | "error">("confirming");
  const [message, setMessage] = useState<string>("");
  const [planName, setPlanName] = useState<string>("");
  const requestedRef = useRef(false);

  useEffect(() => {
    // StrictMode 이중 실행으로 승인 요청이 중복 전송되지 않도록 가드
    if (requestedRef.current) return;
    requestedRef.current = true;

    if (!authKey || !customerKey || !orderId) {
      setStatus("error");
      setMessage("결제 정보가 올바르지 않습니다.");
      return;
    }

    (async () => {
      try {
        const res = await fetch("/api/payment/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ authKey, customerKey, orderId }),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          throw new Error(data?.error ?? "결제 승인에 실패했습니다.");
        }
        setPlanName(data.planName ?? "");
        setStatus("done");
      } catch (e) {
        setStatus("error");
        setMessage(e instanceof Error ? e.message : "결제 승인에 실패했습니다.");
      }
    })();
  }, [authKey, customerKey, orderId]);

  return (
    <div className="mx-auto w-full max-w-xl rounded-3xl border border-white/[0.08] bg-[#0a0a0a] px-8 py-12 text-center">
      {status === "confirming" ? (
        <>
          <h1 className="text-2xl font-black tracking-tight text-white">결제 승인 중...</h1>
          <p className="mt-3 text-sm font-bold text-gray-500">
            결제를 확정하고 있습니다. 잠시만 기다려주세요.
          </p>
        </>
      ) : null}

      {status === "done" ? (
        <>
          <h1 className="text-2xl font-black tracking-tight text-[var(--main-green,#22c55e)]">
            결제가 완료되었습니다
          </h1>
          <p className="mt-3 text-sm font-bold text-gray-400">
            {planName ? `${planName} 플랜이 적용되었습니다.` : "플랜이 적용되었습니다."}
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <Link
              href="/pricing"
              className="rounded-2xl border border-white/[0.12] px-6 py-3 text-sm font-black text-white hover:bg-white/[0.06]"
            >
              요금제 확인
            </Link>
            <Link
              href="/dashboard"
              className="rounded-2xl bg-blue-600 px-6 py-3 text-sm font-black text-white hover:bg-blue-500"
            >
              대시보드로 이동
            </Link>
          </div>
        </>
      ) : null}

      {status === "error" ? (
        <>
          <h1 className="text-2xl font-black tracking-tight text-[var(--main-red)]">
            결제 승인에 실패했습니다
          </h1>
          <p className="mt-3 text-sm font-bold text-gray-400">{message}</p>
          <Link
            href="/pricing"
            className="mt-8 inline-block rounded-2xl border border-white/[0.12] px-6 py-3 text-sm font-black text-white hover:bg-white/[0.06]"
          >
            요금제 페이지에서 다시 시도
          </Link>
        </>
      ) : null}
    </div>
  );
}
