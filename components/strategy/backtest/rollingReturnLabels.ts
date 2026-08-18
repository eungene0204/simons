import { t } from "@/lib/i18n";

// 롤링 수익률 표·그래프가 다루는 투자 기간(개월).
export const ROLLING_WINDOW_OPTIONS: readonly number[] = [1, 3, 6, 12, 24, 36];

// "{0}년"은 사전에서 연도 라벨(2024년→2024)로 쓰이므로 기간 라벨은 별도 키를 쓴다.
const YEAR_LABELS: Record<number, () => string> = {
  12: () => t("1년"),
  24: () => t("2년"),
  36: () => t("3년"),
};

export function rollingWindowLabel(months: number): string {
  return YEAR_LABELS[months]?.() ?? t("{0}개월", months);
}
