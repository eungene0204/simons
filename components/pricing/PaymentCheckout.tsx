"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  loadTossPayments,
  type TossPaymentsPayment,
} from "@tosspayments/tosspayments-sdk";
import { PLANS, PlanId } from "@/lib/plans";

interface PaymentOrderInfo {
  orderId: string;
  orderName: string;
  amount: number;
  customerKey: string;
  customerEmail: string;
  customerName: string;
}

interface PaymentCheckoutProps {
  planId: PlanId;
}

// 토스페이먼츠 자동결제(빌링) 체크아웃.
// 흐름: 주문 생성(/api/payment/order) → requestBillingAuth로 카드 등록창 호출 →
// successUrl(/pricing/success)에서 서버가 빌링키 발급 + 첫 달 결제 승인(/api/payment/confirm).
// 이후 매월 서버 갱신 잡이 빌링키로 자동 청구한다.
export default function PaymentCheckout({ planId }: PaymentCheckoutProps) {
  const [payment, setPayment] = useState<TossPaymentsPayment | null>(null);
  const [order, setOrder] = useState<PaymentOrderInfo | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initializedRef = useRef(false);

  const plan = PLANS[planId];

  useEffect(() => {
    // React StrictMode 이중 실행으로 주문이 중복 생성되지 않도록 가드
    if (initializedRef.current) return;
    initializedRef.current = true;

    (async () => {
      try {
        const res = await fetch("/api/payment/order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ planId }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(data?.error ?? "결제 주문 생성에 실패했습니다.");
        }
        const info: PaymentOrderInfo = await res.json();
        setOrder(info);

        const clientKey = process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY;
        if (!clientKey) {
          throw new Error("NEXT_PUBLIC_TOSS_CLIENT_KEY 환경변수가 설정되지 않았습니다.");
        }
        const tossPayments = await loadTossPayments(clientKey);
        setPayment(tossPayments.payment({ customerKey: info.customerKey }));
      } catch (e) {
        setError(e instanceof Error ? e.message : "결제 준비에 실패했습니다.");
      }
    })();
  }, [planId]);

  const handleRegisterCard = async () => {
    if (!payment || !order || requesting) return;
    setRequesting(true);
    setError(null);
    try {
      // 자동결제(빌링)는 카드 등록창에서 카드를 한 번 등록하고, 결제 승인은 서버에서 수행한다
      await payment.requestBillingAuth({
        method: "CARD",
        successUrl: `${window.location.origin}/pricing/success?orderId=${order.orderId}`,
        failUrl: `${window.location.origin}/pricing/fail`,
        customerEmail: order.customerEmail,
        customerName: order.customerName,
      });
    } catch (e) {
      // 구매자가 카드 등록창을 닫는 등 요청 단계에서 중단된 경우
      setError(e instanceof Error ? e.message : "카드 등록이 중단되었습니다.");
      setRequesting(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="text-center">
        <h1 className="text-3xl font-black tracking-[-0.04em] text-white md:text-4xl">
          {plan.name} 플랜 구독 결제
        </h1>
        <p className="mt-2 text-sm font-bold text-gray-500">
          월 ₩{plan.monthlyPrice.toLocaleString("ko-KR")} (VAT 포함) · 정기결제
        </p>
      </div>

      {error ? (
        <div className="mt-8 rounded-2xl border border-white/[0.08] bg-[#0a0a0a] p-6 text-center">
          <p className="text-sm font-black text-[var(--main-red)]">{error}</p>
          <Link
            href="/pricing"
            className="mt-4 inline-block rounded-2xl border border-white/[0.12] px-6 py-3 text-sm font-black text-white hover:bg-white/[0.06]"
          >
            요금제 페이지로 돌아가기
          </Link>
        </div>
      ) : null}

      {/* 자동 갱신 결제 조건 고지 — 결제 전 화면 고지(약관 제12조 1·7항) */}
      <div className="mt-8 rounded-3xl border border-white/[0.08] bg-[#0a0a0a] p-6">
        <dl className="space-y-3 text-sm font-bold">
          <div className="flex justify-between">
            <dt className="text-gray-500">상품</dt>
            <dd className="text-white">널스탁 {plan.name} 플랜 월 이용료</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-gray-500">결제 금액</dt>
            <dd className="text-white">월 ₩{plan.monthlyPrice.toLocaleString("ko-KR")} (VAT 포함)</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-gray-500">결제 방식</dt>
            <dd className="text-white">신용·체크카드 자동결제 (매월 갱신)</dd>
          </div>
        </dl>
        <ul className="mt-5 space-y-1.5 border-t border-white/[0.08] pt-4 text-xs font-bold leading-relaxed text-gray-500">
          <li>· 카드 등록 후 첫 달 이용료가 즉시 결제되고 {plan.name} 플랜이 적용됩니다.</li>
          <li>· 해지하지 않는 한 매월 같은 날짜에 등록한 카드로 자동 결제됩니다.</li>
          <li>· 요금제 페이지에서 언제든 해지할 수 있으며, 해지해도 이미 결제된 기간에는 계속 이용할 수 있고 다음 결제일부터 청구되지 않습니다.</li>
          <li>· 환불 조건은 이용약관 제12조(환불 정책)를 따릅니다.</li>
        </ul>
      </div>

      <button
        type="button"
        disabled={!payment || !order || requesting}
        onClick={() => void handleRegisterCard()}
        className="mt-6 w-full rounded-2xl bg-blue-600 px-4 py-4 text-sm font-black text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {requesting ? "카드 등록창 여는 중..." : "카드 등록하고 구독 시작하기"}
      </button>

      <p className="mt-4 text-center text-xs font-bold text-gray-600">
        위 버튼을 누르면 자동결제 조건에 동의하고 카드 등록창으로 이동합니다.
      </p>
    </div>
  );
}
