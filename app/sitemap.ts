import type { MetadataRoute } from "next";
import { HOME_LANGUAGE_ALTERNATES, siteUrl } from "@/lib/seo/site";

// 공개 페이지만 담는다 — 지역별 진입점을 모두 노출해 양쪽 서비스가 각각 색인되게 한다.
// 한국 요금제(`/pricing`)는 비로그인 요청을 `/`로 리다이렉트하므로 넣지 않는다(리다이렉트 URL은
// 서치콘솔에서 오류로 잡힌다). 공개로 바뀌면 여기에 추가한다.
export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();
  const absolute = (path: string) => `${base}${path === "/" ? "" : path}`;
  const homeAlternates = {
    languages: Object.fromEntries(
      Object.entries(HOME_LANGUAGE_ALTERNATES).map(([lang, path]) => [lang, absolute(path)]),
    ),
  };
  return [
    { url: absolute("/"), changeFrequency: "weekly", priority: 1, alternates: homeAlternates },
    { url: absolute("/us"), changeFrequency: "weekly", priority: 1, alternates: homeAlternates },
    { url: absolute("/us/pricing"), changeFrequency: "monthly", priority: 0.6 },
  ];
}
