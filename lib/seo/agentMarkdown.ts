// 공개 설명 글의 마크다운 판 — AI 에이전트가 `Accept: text/markdown`으로 요청하면 HTML 대신 준다.
// 화면과 같은 정본(가이드·연구노트·방법론 데이터)에서 만든다. 문구는 정본을 그대로 옮기므로
// 규제 안전 표현(면책 고지 포함)도 화면과 같다.

import {
  GUIDE_ARTICLES,
  GUIDE_BASE_PATH,
  GUIDE_COLLECTION,
  GUIDE_DESCRIPTION,
  GUIDE_DISCLAIMER,
  GUIDE_TITLE,
  getGuideArticle,
  guideArticlePath,
  type ArticleCollection,
  type GuideArticle,
  type GuideTable,
} from "@/lib/guide/articles";
import { buildLlmsTxt } from "@/lib/guide/feeds";
import { METHODOLOGY_ARTICLE, METHODOLOGY_COLLECTION, METHODOLOGY_PATH } from "@/lib/methodology/methodology";
import {
  buildNotesCollection,
  notePath,
  NOTES_BASE_PATH,
  NOTES_DESCRIPTION,
  NOTES_DISCLAIMER,
  NOTES_TITLE,
} from "@/lib/notes/notes";

function absolute(base: string, href: string): string {
  return /^https?:\/\//.test(href) ? href : `${base}${href}`;
}

function tableCell(text: string): string {
  return text.replace(/\|/g, "\\|").replace(/\n/g, " ");
}

function tableMarkdown(table: GuideTable): string[] {
  return [
    `**${table.caption}**`,
    "",
    `| ${table.headers.map(tableCell).join(" | ")} |`,
    `| ${table.headers.map(() => "---").join(" | ")} |`,
    ...table.rows.map((row) => `| ${row.map(tableCell).join(" | ")} |`),
    ...(table.footnote ? ["", table.footnote] : []),
    "",
  ];
}

export function articleMarkdown(
  article: GuideArticle,
  collection: ArticleCollection,
  path: string,
  base: string,
): string {
  const lines: string[] = [
    `# ${article.title}`,
    "",
    `> ${article.summary}`,
    "",
    ...(collection.summaryNote ? [collection.summaryNote, ""] : []),
    collection.disclaimer,
    "",
    `- 원문: ${absolute(base, path)}`,
    `- 게시: ${article.published} · 수정: ${article.updated}`,
    "",
  ];
  for (const section of article.sections) {
    lines.push(`## ${section.heading}`, "");
    for (const paragraph of section.paragraphs) lines.push(paragraph, "");
    if (section.bullets?.length) lines.push(...section.bullets.map((bullet) => `- ${bullet}`), "");
    if (section.table) lines.push(...tableMarkdown(section.table));
    for (const image of section.images ?? []) {
      lines.push(`![${image.alt}](${absolute(base, image.src)})`, ...(image.caption ? [image.caption] : []), "");
    }
    if (section.source) lines.push(`출처: [${section.source.label}](${section.source.href})`, "");
  }
  if (article.faq?.length) {
    lines.push("## 자주 묻는 질문", "");
    for (const item of article.faq) lines.push(`### ${item.question}`, "", item.answer, "");
  }
  if (collection.linksMethodology) {
    lines.push(`계산 가정과 데이터 출처: ${absolute(base, METHODOLOGY_PATH)}`, "");
  }
  return lines.join("\n");
}

function indexMarkdown(
  title: string,
  description: string,
  disclaimer: string,
  path: string,
  items: { title: string; href: string; summary: string }[],
  base: string,
): string {
  return [
    `# ${title}`,
    "",
    `> ${description}`,
    "",
    disclaimer,
    "",
    `- 원문: ${absolute(base, path)}`,
    "",
    ...items.map((item) => `- [${item.title}](${absolute(base, item.href)}): ${item.summary}`),
    "",
  ].join("\n");
}

/** 경로에 맞는 마크다운 — 제공하지 않는 경로·없는 글이면 null. `notes`는 DB에서 읽은 공개 노트 목록. */
export function agentMarkdownFor(pathname: string, base: string, notes: GuideArticle[]): string | null {
  const path = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
  if (path === "/") return buildLlmsTxt(GUIDE_ARTICLES, base, notes);
  if (path === METHODOLOGY_PATH) return articleMarkdown(METHODOLOGY_ARTICLE, METHODOLOGY_COLLECTION, path, base);
  if (path === GUIDE_BASE_PATH) {
    return indexMarkdown(
      GUIDE_TITLE,
      GUIDE_DESCRIPTION,
      GUIDE_DISCLAIMER,
      path,
      GUIDE_ARTICLES.map((article) => ({ title: article.title, href: guideArticlePath(article.slug), summary: article.summary })),
      base,
    );
  }
  if (path === NOTES_BASE_PATH) {
    return indexMarkdown(
      NOTES_TITLE,
      NOTES_DESCRIPTION,
      NOTES_DISCLAIMER,
      path,
      notes.map((note) => ({ title: note.title, href: notePath(note.slug), summary: note.summary })),
      base,
    );
  }
  const [, section, slug] = path.split("/");
  if (section === GUIDE_BASE_PATH.slice(1) && slug) {
    const article = getGuideArticle(slug);
    return article ? articleMarkdown(article, GUIDE_COLLECTION, path, base) : null;
  }
  if (section === NOTES_BASE_PATH.slice(1) && slug) {
    const collection = buildNotesCollection(notes);
    const note = collection.find(slug);
    return note ? articleMarkdown(note, collection, path, base) : null;
  }
  return null;
}
