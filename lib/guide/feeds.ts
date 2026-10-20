// 가이드 글 목록에서 llms.txt·RSS를 만든다 — 글 데이터(`articles.ts`)가 유일한 원천이다.

import { SITE_DESCRIPTION, SITE_NAME, siteUrl } from "@/lib/seo/site";
import { NOTES, NOTES_BASE_PATH, NOTES_DESCRIPTION, NOTES_DISCLAIMER, NOTES_TITLE, notePath } from "@/lib/notes/notes";
import {
  GUIDE_ARTICLES,
  GUIDE_BASE_PATH,
  GUIDE_DESCRIPTION,
  GUIDE_DISCLAIMER,
  GUIDE_TITLE,
  guideArticlePath,
  type GuideArticle,
} from "./articles";

export function buildLlmsTxt(
  articles: GuideArticle[] = GUIDE_ARTICLES,
  base: string = siteUrl(),
  notes: GuideArticle[] = NOTES,
): string {
  const lines = [
    `# ${SITE_NAME.ko}`,
    "",
    `> ${SITE_DESCRIPTION.ko}`,
    "",
    GUIDE_DISCLAIMER,
    "",
    `## ${GUIDE_TITLE}`,
    "",
    GUIDE_DESCRIPTION,
    "",
    `- [${GUIDE_TITLE} 목록](${base}${GUIDE_BASE_PATH})`,
    ...articles.map(
      (article) => `- [${article.title}](${base}${guideArticlePath(article.slug)}): ${article.summary}`,
    ),
    "",
    // 연구노트는 글이 생긴 뒤부터 싣는다.
    ...(notes.length > 0
      ? [
          `## ${NOTES_TITLE}`,
          "",
          NOTES_DESCRIPTION,
          "",
          NOTES_DISCLAIMER,
          "",
          `- [${NOTES_TITLE} 목록](${base}${NOTES_BASE_PATH})`,
          ...notes.map((note) => `- [${note.title}](${base}${notePath(note.slug)}): ${note.summary}`),
          "",
        ]
      : []),
  ];
  return lines.join("\n");
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function buildGuideRss(
  articles: GuideArticle[] = GUIDE_ARTICLES,
  base: string = siteUrl(),
  notes: GuideArticle[] = NOTES,
): string {
  const entries = [
    ...articles.map((article) => ({ article, path: guideArticlePath(article.slug) })),
    ...notes.map((article) => ({ article, path: notePath(article.slug) })),
  ];
  const sorted = [...entries].sort((a, b) => (a.article.updated < b.article.updated ? 1 : -1));
  const lastBuild = sorted[0] ? new Date(`${sorted[0].article.updated}T00:00:00+09:00`).toUTCString() : "";
  const items = sorted
    .map(({ article, path }) => {
      const url = `${base}${path}`;
      return [
        "<item>",
        `<title>${escapeXml(article.title)}</title>`,
        `<link>${url}</link>`,
        `<guid isPermaLink="true">${url}</guid>`,
        `<pubDate>${new Date(`${article.published}T00:00:00+09:00`).toUTCString()}</pubDate>`,
        `<description>${escapeXml(article.description)}</description>`,
        "</item>",
      ].join("\n");
    })
    .join("\n");
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    "<channel>",
    `<title>${escapeXml(`${GUIDE_TITLE}·${NOTES_TITLE} | ${SITE_NAME.ko}`)}</title>`,
    `<link>${base}${GUIDE_BASE_PATH}</link>`,
    `<atom:link href="${base}/feed.xml" rel="self" type="application/rss+xml" />`,
    `<description>${escapeXml(GUIDE_DESCRIPTION)}</description>`,
    "<language>ko-KR</language>",
    lastBuild ? `<lastBuildDate>${lastBuild}</lastBuildDate>` : "",
    items,
    "</channel>",
    "</rss>",
    "",
  ].join("\n");
}
