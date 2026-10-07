// 대화 기록(ChatQaLog)의 전략 카드 스냅샷 — 쓰기(/api/chat-log)와 읽기(콘솔)가 같은 형식을 쓴다.

const MAX_STRATEGY_SNAPSHOT = 200_000

export type StoredStrategySnapshot = {
  summaryItems: unknown[] | null
  parsed: unknown
  parsedOmitted?: boolean
  recovery?: { source: string; snapshotId: string; snapshotUpdatedAt: string; recoveredAt: string; snapshotHash: string }
}

/**
 * 그 턴에 보여 준 전략 카드(카드 항목 + 해석 원본)를 JSON 문자열로 만든다.
 * 너무 크면 원본을 빼고 카드 항목만 남긴다 — JSON을 중간에서 자르면 읽을 수 없다.
 */
export function strategySnapshotJson(value: unknown): string | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const snapshot = value as { summaryItems?: unknown; parsed?: unknown }
  const summaryItems = Array.isArray(snapshot.summaryItems) ? snapshot.summaryItems : null
  const full = JSON.stringify({ summaryItems, parsed: snapshot.parsed ?? null })
  if (full.length <= MAX_STRATEGY_SNAPSHOT) return full
  const itemsOnly = JSON.stringify({ summaryItems, parsed: null, parsedOmitted: true })
  return itemsOnly.length <= MAX_STRATEGY_SNAPSHOT ? itemsOnly : null
}

/** 저장된 JSON → 스냅샷(깨졌으면 null) */
export function parseStrategySnapshot(value: string | null | undefined): StoredStrategySnapshot | null {
  if (!value) return null
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' ? (parsed as StoredStrategySnapshot) : null
  } catch {
    return null
  }
}
