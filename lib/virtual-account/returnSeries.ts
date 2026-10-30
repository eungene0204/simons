// 가상계좌 일별 수익률 계열 — 서버·클라이언트 공용 순수 계산.
//
// 수익률 = (총 자산 − 총 납입액) ÷ 총 납입액 × 100. 계좌 카드·상세의 총 자산 손익과 같은 기준이다
// (적립식 계좌는 납입이 늘어도 수익으로 잡히지 않는다).

export interface SnapshotPoint {
  /** 계좌 시장 기준 날짜 YYYY-MM-DD */
  date: string;
  totalValue: number;
  totalContributed: number;
}

export interface ReturnPoint {
  /** YYYY-MM-DD */
  time: string;
  /** 수익률(%) */
  returnPct: number;
}

export type ReturnRange = "1m" | "3m" | "all";

export const RETURN_RANGE_DAYS: Record<Exclude<ReturnRange, "all">, number> = {
  "1m": 30,
  "3m": 91,
};

export function isReturnRange(value: unknown): value is ReturnRange {
  return value === "1m" || value === "3m" || value === "all";
}

function toReturnPct(totalValue: number, contributed: number): number | null {
  if (!Number.isFinite(totalValue) || !(contributed > 0)) return null;
  return +(((totalValue - contributed) / contributed) * 100).toFixed(4);
}

/**
 * 저장된 일별 값(+ 오늘의 현재 값)을 수익률 점으로 바꾼다. 같은 날짜는 뒤의 값이 이긴다 —
 * `today` 가 있으면 오늘 점으로 붙여 그래프 끝이 지금 값이 된다.
 */
export function buildReturnSeries(snapshots: SnapshotPoint[], today?: SnapshotPoint): ReturnPoint[] {
  const byDate = new Map<string, number>();
  for (const s of today ? [...snapshots, today] : snapshots) {
    const pct = toReturnPct(s.totalValue, s.totalContributed);
    if (pct != null) byDate.set(s.date, pct);
  }
  return [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([time, returnPct]) => ({ time, returnPct }));
}
