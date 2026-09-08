// 가상계좌 금액 표기 — 계좌 통화(KRW/USD) 기준.
//
// 계좌의 금액 숫자는 통화 단위 그대로다(/us 생성 계좌=USD, 기본 KRW — 2026-08-26
// VirtualAccount.currency). 원화 고정 표기("{0}원")를 USD 계좌에 쓰면 $10,000이
// "10,000원"으로 오독되므로, 계좌 금액 표기는 반드시 이 헬퍼를 거친다.

import { formatCompactNumberEn, t } from "@/lib/i18n";
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

/**
 * 원화 축약 표기(억/만): 2,932만 · 1.5억 · 9,500. 영어 화면이면 K/M 축약(formatCompactNumberEn).
 * 대시보드·통계 요약·차트 축이 같은 규칙을 쓴다 — 2026-09-08 이전에는 파일마다 자기 판이 있어
 * 만 단위 자릿수 구분(1234만 vs 1,234만)과 부호 처리가 제각각이었다.
 * `signed`면 양수에 +를 붙인다(손익 표시).
 */
export function formatKrwCompact(value: number, options?: { signed?: boolean }): string {
  const plus = options?.signed && value > 0 ? "+" : "";
  const compactEn = formatCompactNumberEn(value);
  if (compactEn !== null) return `${plus}${compactEn}`;
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : plus;
  if (abs >= 100_000_000) return t("{0}{1}억", sign, (abs / 100_000_000).toFixed(1));
  if (abs >= 10_000) return t("{0}{1}만", sign, Math.round(abs / 10_000).toLocaleString("ko-KR"));
  return `${sign}${KO_FMT.format(abs)}`;
}
