// 백테스트 가이드 구조화 데이터(JSON-LD) — 글은 Article, 목록은 CollectionPage.
// 조직 노드는 홈 JSON-LD(`buildHomeJsonLd`)의 `@id`를 그대로 가리킨다.

import { SITE_NAME, siteUrl } from "@/lib/seo/site";
import {
  GUIDE_BASE_PATH,
  GUIDE_COLLECTION,
  GUIDE_DESCRIPTION,
  GUIDE_TITLE,
  guideArticlePath,
  type ArticleCollection,
  type GuideArticle,
} from "./articles";

export function buildGuideArticleJsonLd(
  article: GuideArticle,
  base: string = siteUrl(),
  collection: ArticleCollection = GUIDE_COLLECTION,
): Record<string, unknown> {
  const url = `${base}${collection.basePath}/${article.slug}`;
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
          { "@type": "ListItem", position: 2, name: collection.title, item: `${base}${collection.basePath}` },
          { "@type": "ListItem", position: 3, name: article.title, item: url },
        ],
      },
      // 화면의 FAQ 섹션과 같은 문자열만 싣는다 — 가시 텍스트와 다른 구조화 데이터 금지.
      ...(article.faq?.length
        ? [
            {
              "@type": "FAQPage",
              "@id": `${url}#faq`,
              inLanguage: "ko-KR",
              mainEntity: article.faq.map((item) => ({
                "@type": "Question",
                name: item.question,
                acceptedAnswer: { "@type": "Answer", text: item.answer },
              })),
            },
          ]
        : []),
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
