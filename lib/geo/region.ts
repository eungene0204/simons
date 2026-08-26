// 지역(Region) 코어 — 서비스는 경로로 지역이 갈린다.
//
// - `/` 트리        → 한국 서비스(kr, 한국어, KRW)
// - `/us` 트리      → 글로벌 서비스(us, 영어, USD)
//
// 지역의 단일 진실 원천은 URL 경로다. 미들웨어가 `/us/*`를 내부적으로 같은 라우트
// 트리로 rewrite 하면서 요청 헤더(REGION_HEADER)에 지역을 실어 주고, 서버 코드는
// 그 헤더(없으면 지역 쿠키)를 읽는다. 클라이언트는 브라우저 경로에서 파생한다.
// 이 모듈은 순수 함수만 담는다(next 의존 없음) — 미들웨어·서버·클라이언트가 공유한다.

export type Region = "kr" | "us";

export const DEFAULT_REGION: Region = "kr";
export const SUPPORTED_REGIONS: readonly Region[] = ["kr", "us"];

/** 마지막으로 방문한 지역 — 재방문 시 지오 리다이렉트보다 사용자의 선택을 우선하기 위한 쿠키. */
export const REGION_COOKIE = "nullstock.region";
/** 미들웨어가 rewrite 요청에 실어 주는 내부 헤더(외부 입력은 미들웨어가 제거한다). */
export const REGION_HEADER = "x-nullstock-region";

export const US_PATH_PREFIX = "/us";

/** 지역별 표시 언어. 언어 토글은 없다 — 지역이 곧 언어다. */
export const REGION_LANGUAGE: Record<Region, "ko" | "en"> = {
  kr: "ko",
  us: "en",
};

/** 지역별 결제 통화. */
export const REGION_CURRENCY: Record<Region, "KRW" | "USD"> = {
  kr: "KRW",
  us: "USD",
};

export function isRegion(value: unknown): value is Region {
  return value === "kr" || value === "us";
}

/** 브라우저/요청 경로에서 지역을 파생한다. `/us` 및 `/us/...`만 글로벌 서비스다. */
export function regionFromPathname(pathname: string | null | undefined): Region {
  if (!pathname) return DEFAULT_REGION;
  if (pathname === US_PATH_PREFIX || pathname.startsWith(`${US_PATH_PREFIX}/`)) {
    return "us";
  }
  return DEFAULT_REGION;
}

/** `/us/backtest` → `/backtest`, `/us` → `/`. 미들웨어 rewrite 대상 경로 계산용. */
export function stripRegionPrefix(pathname: string): string {
  if (pathname === US_PATH_PREFIX) return "/";
  if (pathname.startsWith(`${US_PATH_PREFIX}/`)) {
    return pathname.slice(US_PATH_PREFIX.length);
  }
  return pathname;
}

/**
 * 내부 링크에 지역 프리픽스를 부여한다. kr은 그대로, us는 `/us`를 앞에 붙인다.
 * 루트 상대 경로(`/...`)만 대상이며 외부 URL·해시·이미 프리픽스된 경로는 손대지 않는다.
 * 쿼리·해시는 보존한다: `withRegionPath("us", "/?legal=terms")` → `/us?legal=terms`.
 */
export function withRegionPath(region: Region, href: string): string {
  if (region !== "us") return href;
  if (!href.startsWith("/")) return href;
  if (regionFromPathname(href) === "us") return href;

  const cutIndex = href.search(/[?#]/);
  const path = cutIndex === -1 ? href : href.slice(0, cutIndex);
  const suffix = cutIndex === -1 ? "" : href.slice(cutIndex);
  return `${US_PATH_PREFIX}${path === "/" ? "" : path}${suffix}`;
}
