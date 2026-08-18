import { t } from "@/lib/i18n";
// 플랜 사용량 표시 공용 헬퍼 — TopNavigation(내 플랜 모달)과 SettingsModal(사용량 탭)이 공유

export function formatLimit(limit: number | null) {
  return limit == null ? t("무제한") : `${limit.toLocaleString("ko-KR")}`;
}

/** 백테스트 횟수 리셋(사용량 주기 종료)까지 남은 시간 — 24시간 이하면 시간(h), 그 외는 일 단위 */
export function formatBacktestResetIn(
  endIso?: string | null,
  now: Date = new Date()
) {
  if (!endIso) return null;

  const end = new Date(endIso);
  if (Number.isNaN(end.getTime())) return null;

  const diffMs = end.getTime() - now.getTime();
  if (diffMs <= 0) return null;

  const hours = Math.ceil(diffMs / (60 * 60 * 1000));
  if (hours <= 24) return `Reset in ${hours}h`;

  const days = Math.ceil(diffMs / (24 * 60 * 60 * 1000));
  return `Reset in ${days} day${days > 1 ? "s" : ""}`;
}

export function getUsagePercent(
  used: number,
  limit: number | null,
  unlimited = false
) {
  if (unlimited || limit == null) return 0;
  if (limit <= 0) return used > 0 ? 100 : 0;
  return Math.min(100, Math.max(0, Math.round((used / limit) * 100)));
}

export function formatUsageValue(
  used: number,
  limit: number | null,
  unlimited = false
) {
  return `${used.toLocaleString("ko-KR")} / ${
    unlimited ? t("무제한") : formatLimit(limit)
  }`;
}
