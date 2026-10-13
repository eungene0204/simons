// 백테스트 가이드 구조화 데이터(JSON-LD) — 글은 Article, 목록은 CollectionPage.
// 조직 노드는 홈 JSON-LD(`buildHomeJsonLd`)의 `@id`를 그대로 가리킨다.

import { SITE_NAME, siteUrl } from "@/lib/seo/site";
import {
  GUIDE_BASE_PATH,
  GUIDE_DESCRIPTION,
  GUIDE_TITLE,
  guideArticlePath,
  type GuideArticle,
} from "./articles";

export function buildGuideArticleJsonLd(
  article: GuideArticle,
  base: string = siteUrl(),
): Record<string, unknown> {
  const url = `${base}${guideArticlePath(article.slug)}`;
  const organizationId = `${base}/#organization`;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Article",
        "@id": `${url}#article`,
        headline: article.title,
        description: article.description,
        inLanguage: "ko-KR",
        datePublished: article.published,
        dateModified: article.updated,
        mainEntityOfPage: url,
        author: { "@id": organizationId },
        publisher: { "@id": organizationId },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: SITE_NAME.ko, item: base },
          { "@type": "ListItem", position: 2, name: GUIDE_TITLE, item: `${base}${GUIDE_BASE_PATH}` },
          { "@type": "ListItem", position: 3, name: article.title, item: url },
        ],
      },
    ],
  };
}

export function buildGuideIndexJsonLd(
  articles: GuideArticle[],
  base: string = siteUrl(),
): Record<string, unknown> {
  const url = `${base}${GUIDE_BASE_PATH}`;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "CollectionPage",
        "@id": `${url}#page`,
        name: GUIDE_TITLE,
        description: GUIDE_DESCRIPTION,
        inLanguage: "ko-KR",
        url,
        isPartOf: { "@id": `${base}/#website` },
        mainEntity: {
          "@type": "ItemList",
          itemListElement: articles.map((article, index) => ({
            "@type": "ListItem",
            position: index + 1,
            name: article.title,
            url: `${base}${guideArticlePath(article.slug)}`,
          })),
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: SITE_NAME.ko, item: base },
          { "@type": "ListItem", position: 2, name: GUIDE_TITLE, item: url },
        ],
      },
    ],
  };
}
