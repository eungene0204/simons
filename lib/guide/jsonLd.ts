// 백테스트 가이드·연구노트 구조화 데이터(JSON-LD) — 글은 Article, 목록은 CollectionPage.
// 조직 노드는 홈 JSON-LD(`buildHomeJsonLd`)의 `@id`를 그대로 가리킨다.

import { SITE_NAME, siteUrl } from "@/lib/seo/site";
import {
  GUIDE_BASE_PATH,
  GUIDE_COLLECTION,
  GUIDE_DESCRIPTION,
  GUIDE_TITLE,
  type ArticleCollection,
  type GuideArticle,
} from "./articles";

/** 백테스트 기록 한 편이 근거로 삼은 결과 데이터 — Article의 isBasedOn으로 연결된다. */
export type BacktestDataset = {
  name: string;
  description: string;
  /** ISO 8601 구간(`YYYY-MM-DD/YYYY-MM-DD`). */
  temporalCoverage?: string;
  variableMeasured: string[];
};

export function buildGuideArticleJsonLd(
  article: GuideArticle,
  base: string = siteUrl(),
  collection: ArticleCollection = GUIDE_COLLECTION,
  dataset?: BacktestDataset,
): Record<string, unknown> {
  const url = `${base}${collection.basePath}/${article.slug}`;
  const organizationId = `${base}/#organization`;
  // basePath가 빈 묶음은 최상위 단독 페이지(방법론)라 경로가 홈 → 글 두 단계다.
  const crumbs = collection.basePath
    ? [{ name: collection.title, item: `${base}${collection.basePath}` }, { name: article.title, item: url }]
    : [{ name: article.title, item: url }];
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
        ...(dataset ? { isBasedOn: { "@id": `${url}#dataset` } } : {}),
      },
      ...(dataset
        ? [
            {
              "@type": "Dataset",
              "@id": `${url}#dataset`,
              name: dataset.name,
              description: dataset.description,
              inLanguage: "ko-KR",
              ...(dataset.temporalCoverage ? { temporalCoverage: dataset.temporalCoverage } : {}),
              variableMeasured: dataset.variableMeasured,
              creator: { "@id": organizationId },
              dateModified: article.updated,
            },
          ]
        : []),
      {
        "@type": "BreadcrumbList",
        itemListElement: [{ name: SITE_NAME.ko, item: base }, ...crumbs].map((crumb, index) => ({
          "@type": "ListItem",
          position: index + 1,
          ...crumb,
        })),
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

/** 목록 페이지 하나의 이름·설명·경로 — 가이드와 연구노트가 같은 CollectionPage 모양을 쓴다. */
export type ArticleIndexInfo = { basePath: string; title: string; description: string };

const GUIDE_INDEX: ArticleIndexInfo = {
  basePath: GUIDE_BASE_PATH,
  title: GUIDE_TITLE,
  description: GUIDE_DESCRIPTION,
};

export function buildGuideIndexJsonLd(
  articles: GuideArticle[],
  base: string = siteUrl(),
  index: ArticleIndexInfo = GUIDE_INDEX,
): Record<string, unknown> {
  const url = `${base}${index.basePath}`;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "CollectionPage",
        "@id": `${url}#page`,
        name: index.title,
        description: index.description,
        inLanguage: "ko-KR",
        url,
        isPartOf: { "@id": `${base}/#website` },
        mainEntity: {
          "@type": "ItemList",
          itemListElement: articles.map((article, index) => ({
            "@type": "ListItem",
            position: index + 1,
            name: article.title,
            url: `${url}/${article.slug}`,
          })),
        },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: SITE_NAME.ko, item: base },
          { "@type": "ListItem", position: 2, name: index.title, item: url },
        ],
      },
    ],
  };
}
