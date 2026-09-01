import { t } from "@/lib/i18n";

/**
 * 매매사유 세그먼트 렌더러.
 *
 * 엔진은 거래 내역의 사유를 완성 문장이 아니라 **한국어 정본 템플릿 + 인자**로 내려보낸다
 * (backend/engine/trade_reason.py). 값이 박힌 문장은 값마다 사전 키가 달라져 번역할 수
 * 없기 때문이다. 여기서 템플릿을 t()로 번역하고 인자를 꽂아 표시 문장을 만든다.
 *
 * 금액 인자(`m`)는 통화가 지역마다 달라 값만 실려 온다 — 표기는 호출부가 준 formatMoney가
 * 만든다(한국 결과는 "1,013원", 미국 결과는 "$1,013").
 */
/**
 * 프론트가 이름으로 알아봐야 하는 백엔드 정본 템플릿.
 * (tests/trade-reason-i18n.test.ts가 backend/engine/trade_reason.py에 같은 문구가
 *  있는지 대조한다 — 백엔드에서 문구가 바뀌면 게이트가 깨진다.)
 */
export const REASON_TEMPLATE = {
  exitStrategySignal: "전략 매도 조건 충족",
  breakoutHigh: "{0}일 신고가 돌파",
  breakoutLow: "{0}일 신저가 돌파",
  breakoutHigh52w: "52주 신고가 돌파",
  breakoutLow52w: "52주 신저가 돌파",
} as const;

export type TradeReasonSegment =
  | { t: string; a?: unknown[]; m?: number[] }
  | { s: string };

/** 세그먼트 배열인지 확인한다(과거 결과는 평문 문자열이라 없을 수 있다). */
export function isTradeReasonSegments(value: unknown): value is TradeReasonSegment[] {
  return (
    Array.isArray(value) &&
    value.every((seg) => !!seg && typeof seg === "object" && ("t" in seg || "s" in seg))
  );
}

function renderArg(arg: unknown, isMoney: boolean, formatMoney: (v: number) => string): string {
  if (isTradeReasonSegments(arg)) return renderTradeReasonSegments(arg, formatMoney);
  if (arg && typeof arg === "object" && ("t" in arg || "s" in arg)) {
    return renderTradeReasonSegments([arg as TradeReasonSegment], formatMoney);
  }
  if (isMoney) return formatMoney(Number(arg));
  return String(arg);
}

export function renderTradeReasonSegments(
  segments: TradeReasonSegment[],
  formatMoney: (v: number) => string
): string {
  return segments
    .map((seg) => {
      if ("s" in seg) return seg.s;
      const money = new Set(seg.m ?? []);
      const args = (seg.a ?? []).map((arg, i) => renderArg(arg, money.has(i), formatMoney));
      return t(seg.t, ...args);
    })
    .join("");
}

/**
 * 사유 표시 문장. 구조화 파츠가 있으면 번역해 렌더링하고, 없으면(구버전 결과 등)
 * 백엔드가 준 한국어 문장을 그대로 쓴다.
 */
export function tradeReasonText(
  reason: string | null | undefined,
  parts: unknown,
  formatMoney: (v: number) => string
): string {
  if (isTradeReasonSegments(parts) && parts.length > 0) {
    return renderTradeReasonSegments(parts, formatMoney);
  }
  return reason ?? "";
}

/** 사유 파츠의 첫 템플릿 — 어떤 종류의 사유인지 판별할 때 쓴다(엔진과 같은 기준). */
export function firstReasonTemplate(parts: unknown): string | null {
  if (!isTradeReasonSegments(parts)) return null;
  for (const seg of parts) {
    if ("t" in seg) return seg.t;
  }
  return null;
}
