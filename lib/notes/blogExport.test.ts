import { describe, expect, it } from "vitest";
import type { GuideArticle } from "@/lib/guide/articles";
import { SITE_SUMMARY_KO } from "@/lib/seo/site";
import { BLOG_SOURCE_LINE, buildBlogExport } from "./blogExport";
import { NOTES_DISCLAIMER, SEED_NOTES } from "./notes";

const NOTE: GuideArticle = {
  slug: "sample-note",
  title: "샘플 <노트> 백테스트",
  description: "설명",
  summary: "요약 문단입니다.",
  published: "2026-11-01",
  updated: "2026-11-01",
  related: [],
  sections: [
    { heading: "검증한 속설과 규칙", paragraphs: ["규칙 설명"] },
    {
      heading: "결과",
      paragraphs: ["결과 설명"],
      table: { caption: "결과 표", headers: ["지표", "값"], rows: [["CAGR", "12.4%"]], footnote: "각주" },
    },
    { heading: "결과 해석", paragraphs: ["해석 문단"] },
    { heading: "읽을 때 주의할 점", paragraphs: ["주의 문단"] },
  ],
};

describe("buildBlogExport", () => {
  it("keeps only the summary, table sections and interpretation sections, in page order", () => {
    const { text } = buildBlogExport(NOTE, "https://example.test");
    expect(text).toContain("결과 표\n\n지표 | 값\nCAGR | 12.4%\n\n각주");
    expect(text.indexOf("■ 결과\n")).toBeLessThan(text.indexOf("■ 결과 해석"));
    expect(text).not.toContain("규칙 설명");
    expect(text).not.toContain("주의 문단");
  });

  it("links the original note first and last, and closes with the shared summary, without the full disclaimer", () => {
    const { html, text } = buildBlogExport(NOTE, "https://example.test");
    const url = "https://example.test/notes/sample-note?utm_source=naver_blog&amp;utm_medium=referral&amp;utm_campaign=sample-note";
    const plainUrl = "https://example.test/notes/sample-note?utm_source=naver_blog&utm_medium=referral&utm_campaign=sample-note";
    expect(text.startsWith(`원문: ${plainUrl}`)).toBe(true);
    expect(text.endsWith(SITE_SUMMARY_KO)).toBe(true);
    expect(text).not.toContain(NOTES_DISCLAIMER);
    expect(html).not.toContain("투자자문업자");
    expect(html.split(`<a href="${url}">`)).toHaveLength(3);
  });

  it("names 널스탁 before the summary so an excerpt keeps its source", () => {
    const { text } = buildBlogExport(NOTE, "https://example.test");
    expect(BLOG_SOURCE_LINE).toContain("널스탁");
    expect(text.indexOf(BLOG_SOURCE_LINE)).toBeLessThan(text.indexOf(NOTE.summary));
  });

  it("puts an empty paragraph between every block so the blog editor keeps paragraphs apart", () => {
    const { html, text } = buildBlogExport(NOTE, "https://example.test");
    const blocks = html.split("<p><br></p>");
    expect(blocks.length).toBeGreaterThan(8);
    for (const block of blocks) expect(block).not.toMatch(/<\/(p|h2|h3|table)></);
    expect(text).toContain("■ 결과 해석\n\n해석 문단");
  });

  it("escapes markup in note text", () => {
    const { html } = buildBlogExport(NOTE, "https://example.test");
    expect(html).toContain("샘플 &lt;노트&gt; 백테스트");
    expect(html).not.toContain("<노트>");
  });

  it("links production, not the local dev host, by default", () => {
    expect(buildBlogExport(NOTE).text.startsWith("원문: https://www.nullstock.im/notes/sample-note?utm_source=naver_blog")).toBe(true);
  });

  it("gives every seed note a result table in its export", () => {
    for (const note of SEED_NOTES) expect(buildBlogExport(note).html).toContain("<table");
  });
});
