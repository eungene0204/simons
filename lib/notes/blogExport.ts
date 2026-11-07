// 연구노트 → 블로그(네이버 스마트에디터) 붙여 넣기용 요약판 — 로컬 개발 화면의 복사 버튼만 쓴다.
//
// 전문을 옮기면 네이버가 유사 문서로 보고 노출을 낮추므로 요약판만 만든다(2026-11-06 사용자 결정):
// 원문 링크 → 요약 → 표가 있는 절 → 해석 절 → 원문 링크·소개 문장. 면책 전문은 싣지 않는다(2026-11-06 사용자 지시). 에디터가 클래스·외부 CSS를 버리므로
// 서식은 전부 인라인 스타일로 쓰고, 서식을 못 받는 곳을 위해 같은 내용의 일반 텍스트도 함께 만든다.
// 노트 요약에는 '널스탁'이 없어서(64편 중 0편, 2026-11-06 실측) 답변 엔진이 앞부분만 발췌하면 출처가 끊긴다 —
// 제목 바로 아래에 출처 한 줄을, 끝에 사이트 공통 소개 문장(SITE_SUMMARY_KO)을 고정으로 붙인다.

import type { GuideArticle, GuideSection } from "@/lib/guide/articles";
import { DEFAULT_SITE_URL, SITE_SUMMARY_KO } from "@/lib/seo/site";
import { notePath } from "./notes";

/** 표 없이도 요약판에 싣는 절 — 노트 생성기가 결과를 풀어 쓰는 절의 제목들이다. */
const INTERPRETATION_HEADINGS = new Set([
  "결과 해석",
  "숫자에서 관측된 것",
  "두 결과를 나란히 읽으면",
  "읽는 법",
  "순위가 유지됐는지 읽는 법",
]);

/** 제목 바로 아래 출처 한 줄 — 요약을 발췌해도 계산 주체가 같이 읽히도록 요약 앞에 둔다. */
export const BLOG_SOURCE_LINE = "널스탁 퀀트 연구노트에서 옮긴 요약입니다. 아래 수치는 널스탁 백테스트 엔진으로 과거 데이터를 계산한 결과입니다.";

export type BlogExport = { html: string; text: string };

function blogSections(note: GuideArticle): GuideSection[] {
  return note.sections.filter((section) => section.table || INTERPRETATION_HEADINGS.has(section.heading));
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const P = "margin:0 0 12px;line-height:1.8;";
// 스마트에디터는 붙여 넣은 문단의 여백(margin)을 버려 문단이 줄 바꿈 하나로 붙는다 — 블록 사이에 빈 문단을 직접 넣는다.
const BLANK = "<p><br></p>";
const CELL = "border:1px solid #d0d0d0;padding:6px 10px;text-align:left;";

function sectionHtml(section: GuideSection): string {
  const parts = [`<h3 style="margin:24px 0 10px;font-size:19px;font-weight:bold;">${escapeHtml(section.heading)}</h3>`];
  for (const paragraph of section.paragraphs) parts.push(`<p style="${P}">${escapeHtml(paragraph)}</p>`);
  if (section.bullets?.length) {
    parts.push(`<ul>${section.bullets.map((item) => `<li style="line-height:1.8;">${escapeHtml(item)}</li>`).join("")}</ul>`);
  }
  const table = section.table;
  if (table) {
    const head = table.headers
      .map((cell) => `<th style="${CELL}background:#f3f3f3;font-weight:bold;">${escapeHtml(cell)}</th>`)
      .join("");
    const body = table.rows
      .map((row) => `<tr>${row.map((cell) => `<td style="${CELL}">${escapeHtml(cell)}</td>`).join("")}</tr>`)
      .join("");
    parts.push(`<p style="${P}font-weight:bold;">${escapeHtml(table.caption)}</p>`);
    parts.push(`<table style="border-collapse:collapse;margin:0 0 8px;"><tr>${head}</tr>${body}</table>`);
    if (table.footnote) parts.push(`<p style="${P}font-size:13px;color:#666;">${escapeHtml(table.footnote)}</p>`);
  }
  return parts.join(BLANK);
}

function sectionText(section: GuideSection): string {
  const lines = [`■ ${section.heading}`, ...section.paragraphs, ...(section.bullets ?? []).map((item) => `- ${item}`)];
  const table = section.table;
  if (table) {
    lines.push(table.caption, [table.headers, ...table.rows].map((row) => row.join(" | ")).join("\n"));
    if (table.footnote) lines.push(table.footnote);
  }
  return lines.join("\n\n");
}

export function buildBlogExport(note: GuideArticle, base: string = DEFAULT_SITE_URL): BlogExport {
  // 블로그에서 들어온 방문을 집계할 수 있게 원문 링크에 유입 출처를 붙인다.
  const utm = new URLSearchParams({ utm_source: "naver_blog", utm_medium: "referral", utm_campaign: note.slug });
  const url = `${base}${notePath(note.slug)}?${utm.toString()}`;
  const sections = blogSections(note);
  const link = `<a href="${escapeHtml(url)}">${escapeHtml(url)}</a>`;

  const html = [
    `<p style="${P}">원문: ${link}</p>`,
    `<h2 style="margin:16px 0 12px;font-size:22px;font-weight:bold;">${escapeHtml(note.title)}</h2>`,
    `<p style="${P}">${escapeHtml(BLOG_SOURCE_LINE)}</p>`,
    `<p style="${P}font-weight:bold;">${escapeHtml(note.summary)}</p>`,
    ...sections.map(sectionHtml),
    `<p style="margin:24px 0 12px;line-height:1.8;">규칙과 설정, 읽을 때 주의할 점까지 담은 전체 기록은 원문에서 볼 수 있습니다: ${link}</p>`,
    `<p style="${P}">${escapeHtml(SITE_SUMMARY_KO)}</p>`,
  ].join(BLANK);

  const text = [
    `원문: ${url}`,
    note.title,
    BLOG_SOURCE_LINE,
    note.summary,
    ...sections.map(sectionText),
    `규칙과 설정, 읽을 때 주의할 점까지 담은 전체 기록은 원문에서 볼 수 있습니다: ${url}`,
    SITE_SUMMARY_KO,
  ].join("\n\n");

  return { html, text };
}
