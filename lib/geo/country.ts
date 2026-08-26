// 최초 방문 지오 판별 — 미들웨어가 루트(`/`) 첫 진입 시 어느 지역 서비스로 보낼지 정한다.
//
// 신호 우선순위:
//   1. 프록시/CDN 국가 헤더 (Cloudflare `cf-ipcountry` 등) — 현재 배포(Vultr + Caddy 직결)엔
//      아직 없지만, 앞단에 CDN/GeoIP가 붙는 즉시 이 코드가 그대로 동작한다.
//   2. Accept-Language 폴백 — 한국어가 선호 언어에 없으면 글로벌 서비스로 본다.
// 신호가 전혀 없으면 한국 서비스(기본)에 남긴다.
//
// 검색엔진 크롤러는 리다이렉트하지 않는다 — 지오 리다이렉트가 걸리면 크롤러(대부분 해외 IP)가
// 한국 서비스를 색인하지 못한다. 양쪽 색인은 hreflang(alternates)으로 안내한다.

import { DEFAULT_REGION, type Region } from "./region";

const COUNTRY_HEADERS = [
  "cf-ipcountry",
  "x-vercel-ip-country",
  "x-geo-country",
] as const;

const BOT_PATTERN =
  /bot|crawler|spider|crawling|slurp|yeti|daum|kakaotalk-scrap|facebookexternalhit|twitterbot|linkedinbot|embedly|quora link preview|pinterest|whatsapp|telegrambot/i;

type HeaderReader = (name: string) => string | null;

/** 프록시/CDN이 실어 준 ISO 3166-1 alpha-2 국가 코드. 없으면 null. */
export function countryFromHeaders(getHeader: HeaderReader): string | null {
  for (const name of COUNTRY_HEADERS) {
    const value = getHeader(name)?.trim().toUpperCase();
    if (value && value.length === 2 && value !== "XX") return value;
  }
  return null;
}

/** Accept-Language에 한국어가 포함되는지. 헤더가 없으면 null(신호 없음). */
export function prefersKorean(acceptLanguage: string | null): boolean | null {
  if (!acceptLanguage?.trim()) return null;
  return /(^|,|;|\s)ko(-[a-z]{2})?\b/i.test(acceptLanguage);
}

export function isKnownBot(userAgent: string | null): boolean {
  return userAgent !== null && BOT_PATTERN.test(userAgent);
}

/** 최초 방문 요청이 향해야 할 지역. 국가 헤더 → Accept-Language → 기본(kr) 순. */
export function resolvePreferredRegion(getHeader: HeaderReader): Region {
  const country = countryFromHeaders(getHeader);
  if (country) return country === "KR" ? "kr" : "us";

  const korean = prefersKorean(getHeader("accept-language"));
  if (korean === false) return "us";
  return DEFAULT_REGION;
}
