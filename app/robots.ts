import type { MetadataRoute } from "next";
import { robotsDisallowPaths, siteUrl } from "@/lib/seo/site";

// 공개 랜딩·요금제만 색인한다. 로그인 뒤 앱 화면(대시보드·백테스트·가상계좌 등)은 양 지역
// 프리픽스 모두 차단한다 — 정본 목록은 lib/seo/site.ts의 PRIVATE_PATHS.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: robotsDisallowPaths() }],
    sitemap: `${siteUrl()}/sitemap.xml`,
  };
}
