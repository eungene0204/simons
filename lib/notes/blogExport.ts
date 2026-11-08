// 연구노트 → 블로그(네이버 스마트에디터) 붙여 넣기용 요약판 — 로컬 개발 화면의 복사 버튼만 쓴다.
//
// 2026-11-06엔 유사 문서 판정을 피하려고 요약·표·해석 절만 옮겼지만 내용이 빈약해, 2026-11-08 사용자 결정으로 본문 절을
// 모두 싣는다: 제목 → 출처 한 줄 → 요약 → 원문 링크 → 모든 절(노트의 절 순서 그대로) → FAQ → 원문 링크·소개 문장 → 태그.
// 네이버 AI 브리핑 등 답변 엔진이 앞부분을 발췌하므로 요약(직답)을 링크보다 앞에 두고, 글마다 수치가 다른 FAQ도 싣는다(2026-11-08 사용자 지시).
// 관련 글 목록·면책 전문은 싣지 않는다(면책 제외는 2026-11-06 사용자 지시). 에디터가 클래스·외부 CSS를 버리므로
// 서식은 전부 인라인 스타일로 쓰고, 서식을 못 받는 곳을 위해 같은 내용의 일반 텍스트도 함께 만든다.
// 노트 요약에는 '널스탁'이 없어서(64편 중 0편, 2026-11-06 실측) 답변 엔진이 앞부분만 발췌하면 출처가 끊긴다 —
// 제목 바로 아래에 출처 한 줄을, 끝에 사이트 공통 소개 문장(SITE_SUMMARY_KO)을 고정으로 붙인다.

import type { GuideArticle, GuideFaq, GuideSection } from "@/lib/guide/articles";
import { DEFAULT_SITE_URL, SITE_SUMMARY_KO } from "@/lib/seo/site";
import { notePath } from "./notes";

/** 제목 바로 아래 출처 한 줄 — 요약을 발췌해도 계산 주체가 같이 읽히도록 요약 앞에 둔다. */
export const BLOG_SOURCE_LINE = "널스탁 퀀트 연구노트의 기록을 옮긴 글입니다. 아래 수치는 널스탁 백테스트 엔진으로 과거 데이터를 계산한 결과입니다.";

export type BlogExport = { html: string; text: string };

/** 끝에 붙이는 블로그 태그 — 공통 태그에 노트 묶음(slug 접두사) 태그를 더한다. */
export function blogTags(slug: string): string[] {
  const series = slug.startsWith("myth-") ? ["속설검증", "매매속설"] : slug.startsWith("news-") ? ["뉴스전략", "업종백테스트"] : ["퀀트연구"];
  return ["널스탁", "백테스트", "퀀트투자", "주식백테스트", ...series];
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const P = "margin:0 0 12px;line-height:1.8;";
// 스마트에디터는 붙여 넣은 문단의 여백(margin)을 버려 문단이 줄 바꿈 하나로 붙는다 — 블록 사이에 빈 문단을 직접 넣는다.
const BLANK = "<p><br></p>";
const CELL = "border:1px solid #d0d0d0;padding:6px 10px;text-align:left;";
const H3 = "margin:24px 0 10px;font-size:19px;font-weight:bold;";
const FAQ_HEADING = "자주 묻는 질문";

function faqHtml(faq: GuideFaq[]): string {
  return [
    `<h3 style="${H3}">${FAQ_HEADING}</h3>`,
    ...faq.flatMap((item) => [
      `<p style="${P}font-weight:bold;">Q. ${escapeHtml(item.question)}</p>`,
      `<p style="${P}">A. ${escapeHtml(item.answer)}</p>`,
    ]),
  ].join(BLANK);
}

function faqText(faq: GuideFaq[]): string {
  return [`■ ${FAQ_HEADING}`, ...faq.map((item) => `Q. ${item.question}\nA. ${item.answer}`)].join("\n\n");
}

function sectionHtml(section: GuideSection, base: string): string {
  const parts = [`<h3 style="${H3}">${escapeHtml(section.heading)}</h3>`];
  for (const paragraph of section.paragraphs) parts.push(`<p style="${P}">${escapeHtml(paragraph)}</p>`);
  if (section.source) {
    parts.push(`<p style="${P}">출처: <a href="${escapeHtml(section.source.href)}">${escapeHtml(section.source.label)}</a></p>`);
  }
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
  // 사진은 원문 사이트의 절대 주소로 건다 — 에디터가 붙여 넣을 때 가져가거나, 못 가져가면 자리만 남는다.
  for (const image of section.images ?? []) {
    parts.push(`<p style="${P}"><img src="${escapeHtml(base + image.src)}" alt="${escapeHtml(image.alt)}" width="${image.width}" style="max-width:100%;height:auto;"></p>`);
    if (image.caption) parts.push(`<p style="${P}font-size:13px;color:#666;">${escapeHtml(image.caption)}</p>`);
  }
  return parts.join(BLANK);
}

function sectionText(section: GuideSection, base: string): string {
  const lines = [`■ ${section.heading}`, ...section.paragraphs];
  if (section.source) lines.push(`출처: ${section.source.label} ${section.source.href}`);
  if (section.bullets?.length) lines.push(section.bullets.map((item) => `- ${item}`).join("\n"));
  const table = section.table;
  if (table) {
    lines.push(table.caption, [table.headers, ...table.rows].map((row) => row.join(" | ")).join("\n"));
    if (table.footnote) lines.push(table.footnote);
  }
  for (const image of section.images ?? []) lines.push(`[사진] ${image.caption ?? image.alt}: ${base}${image.src}`);
  return lines.join("\n\n");
}

export function buildBlogExport(note: GuideArticle, base: string = DEFAULT_SITE_URL): BlogExport {
  // 블로그에서 들어온 방문을 집계할 수 있게 원문 링크에 유입 출처를 붙인다.
  const utm = new URLSearchParams({ utm_source: "naver_blog", utm_medium: "referral", utm_campaign: note.slug });
  const url = `${base}${notePath(note.slug)}?${utm.toString()}`;
  const sections = note.sections;
  const tags = blogTags(note.slug).map((tag) => `#${tag}`).join(" ");
  const link = `<a href="${escapeHtml(url)}">${escapeHtml(url)}</a>`;

  const faq = note.faq ?? [];
  const closing = "관련 기록과 같은 문장으로 다시 계산하는 링크는 원문에 있습니다";

  const html = [
    `<h2 style="margin:16px 0 12px;font-size:22px;font-weight:bold;">${escapeHtml(note.title)}</h2>`,
    `<p style="${P}">${escapeHtml(BLOG_SOURCE_LINE)}</p>`,
    `<p style="${P}font-weight:bold;">${escapeHtml(note.summary)}</p>`,
    `<p style="${P}">원문: ${link}</p>`,
    ...sections.map((section) => sectionHtml(section, base)),
    ...(faq.length > 0 ? [faqHtml(faq)] : []),
    `<p style="margin:24px 0 12px;line-height:1.8;">${closing}: ${link}</p>`,
    `<p style="${P}">${escapeHtml(SITE_SUMMARY_KO)}</p>`,
    `<p style="${P}">${escapeHtml(tags)}</p>`,
  ].join(BLANK);

  const text = [
    note.title,
    BLOG_SOURCE_LINE,
    note.summary,
    `원문: ${url}`,
    ...sections.map((section) => sectionText(section, base)),
    ...(faq.length > 0 ? [faqText(faq)] : []),
    `${closing}: ${url}`,
    SITE_SUMMARY_KO,
    tags,
  ].join("\n\n");

  return { html, text };
}
