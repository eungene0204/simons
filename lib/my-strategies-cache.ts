// 내 전략 목록의 클라이언트 캐시(2026-10-21) — 다른 페이지에 다녀온 뒤 다시 들어와도 목록을 즉시 그린다.
// 서버 조회가 원격 DB 왕복 여러 번이라 2~3초 걸려, 매번 로딩 화면을 보이면 너무 느렸다.
// 캐시는 먼저 보여 주기용일 뿐이다 — 화면은 항상 뒤에서 최신 목록을 받아 교체한다(저장·삭제가
// 다른 화면에서 일어나도 곧 바로잡힌다). 이 화면의 삭제·공개 전환은 캐시에도 바로 반영한다.

export interface SavedStrategy {
  id: string;
  name: string;
  description: string | null;
  type: string;
  universe: string;
  aiScore: number | null;
  avgReturnPct: number;
  accountCount: number;
  isPublic?: boolean;
  createdAt: string;
}

let cachedStrategies: SavedStrategy[] | null = null;
let inFlightRequest: Promise<SavedStrategy[]> | null = null;

export function getCachedMyStrategies() {
  return cachedStrategies;
}

export function setCachedMyStrategies(strategies: SavedStrategy[]) {
  cachedStrategies = strategies;
}

// 로그아웃·계정 전환처럼 캐시를 믿으면 안 되는 시점에 버린다.
export function invalidateMyStrategiesCache() {
  cachedStrategies = null;
  inFlightRequest = null;
}

// 실패하면 throw — 호출부가 캐시를 그대로 두고 안내할지 정한다.
export function refreshMyStrategiesCache(): Promise<SavedStrategy[]> {
  if (inFlightRequest) return inFlightRequest;

  inFlightRequest = fetch("/api/dashboard/strategy-list", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Failed to load strategies");
      }
      return response.json();
    })
    .then((data: { strategies?: SavedStrategy[] }) => {
      cachedStrategies = Array.isArray(data.strategies) ? data.strategies : [];
      return cachedStrategies;
    })
    .finally(() => {
      inFlightRequest = null;
    });

  return inFlightRequest;
}
