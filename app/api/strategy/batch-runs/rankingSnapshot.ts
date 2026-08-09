import { profitFactorForRanking } from "@/lib/format-profit-factor";

/**
 * 일괄 실행 후보의 랭킹 스냅샷 생성.
 *
 * route.ts가 아니라 별도 모듈에 두는 이유: Next.js App Router의 route 파일은 HTTP
 * 메서드 핸들러와 정해진 설정 필드 외의 export를 허용하지 않아, 여기 있던 함수를
 * 테스트용으로 export하자 프로덕션 빌드가 깨졌다("buildRankingSnapshot" is not a
 * valid Route export field). 테스트가 필요한 순수 함수는 이 파일에 둔다.
 */
export type RankingCandidate = {
  id?: string;
  strategyId?: string | null;
  strategyName: string;
  status: string;
  metrics?: any;
};

export function buildRankingSnapshot<T extends RankingCandidate>(candidates: T[]) {
  const ranked = candidates
    .filter((candidate) => candidate.metrics)
    .slice()
    .sort((left, right) => {
      const leftValue = Number(left.metrics?.cagr ?? 0);
      const rightValue = Number(right.metrics?.cagr ?? 0);
      if (leftValue === rightValue) {
        return left.strategyName.localeCompare(right.strategyName, "ko");
      }
      return rightValue - leftValue;
    });

  const rankByCandidateId = new Map<string, number>();
  const snapshot = ranked.map((candidate, index) => {
    rankByCandidateId.set(candidate.id ?? `${candidate.strategyName}_${index}`, index + 1);
    return {
      rank: index + 1,
      strategyId: candidate.strategyId ?? "unknown",
      name: candidate.strategyName,
      status: candidate.status,
      cagr: Number(candidate.metrics?.cagr ?? 0),
      totalReturn: Number(candidate.metrics?.totalReturn ?? 0),
      sharpe: Number(candidate.metrics?.sharpe ?? 0),
      maxDrawdown: Number(candidate.metrics?.maxDrawdown ?? 0),
      // null(=손실 0건이라 ∞)을 0(최악)으로 접지 않는다 — RunAllTestsModal의
      // 클라이언트 스냅샷과 같은 999 상한 접기 규약
      profitFactor: profitFactorForRanking(candidate.metrics?.profitFactor) ?? 0,
      trades: Number(candidate.metrics?.trades ?? 0),
    };
  });

  const normalizedCandidates = candidates.map((candidate) => ({
    ...candidate,
    rank: candidate.metrics ? rankByCandidateId.get(candidate.id ?? "") ?? null : null,
  }));

  return {
    rankingSnapshot: snapshot,
    candidates: normalizedCandidates,
  };
}
