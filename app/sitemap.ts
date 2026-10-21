import type { MetadataRoute } from "next";
import { GUIDE_ARTICLES, GUIDE_BASE_PATH, guideArticlePath } from "@/lib/guide/articles";
import { NOTES_BASE_PATH, notePath } from "@/lib/notes/notes";
import { listNotes } from "@/lib/notes/notesStore";
import { HOME_LANGUAGE_ALTERNATES, siteUrl } from "@/lib/seo/site";

// 공개 페이지만 담는다 — 지역별 진입점을 모두 노출해 양쪽 서비스가 각각 색인되게 한다.
// 한국 요금제(`/pricing`)는 비로그인 요청을 `/`로 리다이렉트하므로 넣지 않는다(리다이렉트 URL은
// 서치콘솔에서 오류로 잡힌다). 공개로 바뀌면 여기에 추가한다.
// 연구노트가 DB에 있으므로 요청 시 생성한다(빌드 시점에 DB를 읽지 않는다).
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const notes = await listNotes();
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
    // 백테스트 가이드(한국어 전용 공개 글) — 검색어 '백테스트'에 답하는 본문 페이지.
    { url: absolute(GUIDE_BASE_PATH), changeFrequency: "monthly", priority: 0.8 },
    ...GUIDE_ARTICLES.map((article) => ({
      url: absolute(guideArticlePath(article.slug)),
      lastModified: article.updated,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
    // 연구노트는 글이 생긴 뒤부터 노출한다(빈 목록은 noindex라 사이트맵에도 넣지 않는다).
    ...(notes.length > 0
      ? [
          { url: absolute(NOTES_BASE_PATH), changeFrequency: "monthly" as const, priority: 0.8 },
          ...notes.map((note) => ({
            url: absolute(notePath(note.slug)),
            lastModified: note.updated,
            changeFrequency: "monthly" as const,
            priority: 0.7,
          })),
        ]
      : []),
  ];
}
