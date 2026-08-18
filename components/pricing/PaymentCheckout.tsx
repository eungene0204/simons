"use client";

import { useEffect, useRef, useState } from "react";
import { X, CreditCard } from "phosphor-react";
import {
  loadTossPayments,
  type TossPaymentsPayment,
} from "@tosspayments/tosspayments-sdk";
import { PLANS, PlanId } from "@/lib/plans";
import { t } from "@/lib/i18n";

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
  onClose: () => void;
}

// 토스페이먼츠 자동결제(빌링) 체크아웃 모달.
// 흐름: 주문 생성(/api/payment/order) → requestBillingAuth로 카드 등록창 호출 →
// successUrl(/pricing/success)에서 서버가 빌링키 발급 + 첫 달 결제 승인(/api/payment/confirm).
// 이후 매월 서버 갱신 잡이 빌링키로 자동 청구한다.
// requestBillingAuth는 브라우저 전체를 토스 카드 등록창으로 리다이렉트하므로,
// 이 모달은 리다이렉트 직전의 주문 확인·자동갱신 고지 단계만 담당한다.
export default function PaymentCheckout({ planId, onClose }: PaymentCheckoutProps) {
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
          throw new Error(data?.error ?? t("결제 주문 생성에 실패했습니다."));
        }
        const info: PaymentOrderInfo = await res.json();
        setOrder(info);

        const clientKey = process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY;
        if (!clientKey) {
          throw new Error(t("NEXT_PUBLIC_TOSS_CLIENT_KEY 환경변수가 설정되지 않았습니다."));
        }
        const tossPayments = await loadTossPayments(clientKey);
        setPayment(tossPayments.payment({ customerKey: info.customerKey }));
      } catch (e) {
        setError(e instanceof Error ? e.message : t("결제 준비에 실패했습니다."));
      }
    })();
  }, [planId]);

  // Esc로 모달 닫기
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // 에러 메시지는 3초 후 자동으로 사라진다
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), 3000);
    return () => clearTimeout(timer);
  }, [error]);

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
      setError(e instanceof Error ? e.message : t("카드 등록이 중단되었습니다."));
      setRequesting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4 py-8"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t("{0} 플랜 구독 결제", plan.name)}
    >
      <div
        className="max-h-full w-full max-w-lg overflow-y-auto rounded-3xl border border-white/[0.08] bg-[#0a0a0a] p-6 text-white sm:p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-black tracking-[-0.04em] text-white">
              {t("{0} 플랜 구독 결제", plan.name)}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("닫기")}
            className="shrink-0 text-gray-400 transition-colors hover:text-white"
          >
            <X size={22} />
          </button>
        </div>

        {/* 자동 갱신 결제 조건 고지 — 결제 전 화면 고지(약관 제12조 1·7항) */}
        <div className="mt-6 rounded-3xl border border-white/[0.08] bg-[#050505] p-6">
          <dl className="space-y-3 text-sm font-bold">
            <div className="flex justify-between">
              <dt className="text-gray-500">{t("상품")}</dt>
              <dd className="text-white">{t("{0} 플랜", plan.name)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">{t("결제 금액")}</dt>
              <dd className="text-white">{t("월 ₩{0} (VAT 포함)", plan.monthlyPrice.toLocaleString("ko-KR"))}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">{t("결제 방식")}</dt>
              <dd className="text-white">{t("신용·체크카드 자동결제 (매월 갱신)")}</dd>
            </div>
          </dl>
          <ul className="mt-5 space-y-1.5 border-t border-white/[0.08] pt-4 text-xs font-bold leading-relaxed text-gray-500">
            <li>{t("· 환불 조건은 이용약관 제12조(환불 정책)를 따릅니다.")}</li>
            {error ? <li className="text-center text-[var(--main-red)]">{error}</li> : null}
          </ul>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex w-24 items-center justify-center rounded-lg border border-white/[0.12] px-4 py-2 text-xs font-black text-white transition-colors hover:bg-white/[0.06]"
          >
            {t("취소")}
          </button>
          <button
            type="button"
            disabled={!payment || !order || requesting}
            onClick={() => void handleRegisterCard()}
            className="flex w-24 items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-black text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <CreditCard size={14} weight="bold" />
            {requesting ? t("카드 등록창 여는 중...") : t("결제하기")}
          </button>
        </div>
      </div>
    </div>
  );
}
