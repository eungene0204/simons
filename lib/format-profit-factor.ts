/**
 * 손익비(Profit Factor) 표시 규칙 — 손실 거래가 0건이면 총이익÷총손실의 분모가 0이라
 * 값이 정의되지 않는다(무한대). 엔진은 그 경우 null을 내려보낸다.
 *
 * 과거에는 백엔드가 무한대를 0.0으로 뭉개는 바람에 **전승한 전략이 손익비 0(최악)으로**
 * 표시됐다. null과 0은 정반대의 의미이므로 절대 `?? 0`으로 합치지 않는다.
 */

/** 손익비를 화면 문자열로. null(손실 0건) → "∞", 값 없음 → "—" */
export function formatProfitFactor(v: number | null | undefined, decimals = 2): string {
  if (v === null) return "∞";
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(decimals);
}

/**
 * 손익비를 점수화·정렬용 수치로 환산. null(=∞)은 상한값으로 접는다.
 * 값 자체를 저장하거나 표시할 때 쓰면 안 된다 — 표시는 formatProfitFactor.
 */
export function profitFactorForRanking(
  v: number | null | undefined,
  infinityAs = 999
): number | undefined {
  if (v === null) return infinityAs;
  return v ?? undefined;
}
