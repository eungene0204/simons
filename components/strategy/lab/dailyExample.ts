// "오늘 둘러볼 예시" — 예시 전체에서 날짜마다 하나를 고른다.
// 성과·수익으로 거르지 않는다(성과 기준 선별은 전략 추천에 해당 — CLAUDE.md 규제 안전 원칙).
// 같은 날에는 누구에게나 같은 예시가 나오도록 날짜 문자열로만 정한다.

/** 사용자 기기 기준 날짜 키(YYYY-MM-DD). */
export function localDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** 날짜 키를 FNV-1a로 섞어 0..count-1 중 하나를 고른다. count가 0이면 -1. */
export function dailyExampleIndex(count: number, dateKey: string): number {
  if (count <= 0) return -1;
  let hash = 0x811c9dc5;
  for (let i = 0; i < dateKey.length; i++) {
    hash ^= dateKey.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash % count;
}
