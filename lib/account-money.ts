// 가상계좌 금액 표기 — 계좌 통화(KRW/USD) 기준.
//
// 계좌의 금액 숫자는 통화 단위 그대로다(/us 생성 계좌=USD, 기본 KRW — 2026-08-26
// VirtualAccount.currency). 원화 고정 표기("{0}원")를 USD 계좌에 쓰면 $10,000이
// "10,000원"으로 오독되므로, 계좌 금액 표기는 반드시 이 헬퍼를 거친다.

import { t } from "@/lib/i18n";
import { formatUsd } from "@/lib/us-symbols";

export type AccountCurrency = "KRW" | "USD";

const KO_FMT = new Intl.NumberFormat("ko-KR");

export function isUsdAccount(currency?: string | null): boolean {
  return currency === "USD";
}

/** 금액: $12,345 / 12,345원 */
export function formatAccountMoney(value: number, currency?: string | null): string {
  if (isUsdAccount(currency)) return formatUsd(value);
  return t("{0}원", KO_FMT.format(Math.round(value)));
}

/** 부호 있는 손익: +$1,234 / +1,234원 (0은 부호 없음) */
export function formatAccountSignedMoney(value: number, currency?: string | null): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (isUsdAccount(currency)) return `${sign}${formatUsd(abs)}`;
  return t("{0}{1}원", sign, KO_FMT.format(Math.round(abs)));
}
