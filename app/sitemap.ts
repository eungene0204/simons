import type { MetadataRoute } from "next";

// 공개 페이지만 담는다 — 지역별 진입점을 모두 노출해 양쪽 서비스가 각각 색인되게 한다.
export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.DOMAIN ? `https://${process.env.DOMAIN}` : "https://www.nullstock.im";
  return ["/", "/us", "/pricing", "/us/pricing"].map((path) => ({
    url: `${base}${path === "/" ? "" : path}`,
    changeFrequency: "weekly",
  }));
}
