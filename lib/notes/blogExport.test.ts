import { describe, expect, it } from "vitest";
import type { GuideArticle } from "@/lib/guide/articles";
import { SITE_SUMMARY_KO } from "@/lib/seo/site";
import { BLOG_SOURCE_LINE, blogTags, buildBlogExport } from "./blogExport";
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
    {
      heading: "출발한 기사",
      paragraphs: ["규칙 설명"],
      source: { label: "기사 제목", href: "https://news.example/a" },
    },
    {
      heading: "결과",
      paragraphs: ["결과 설명"],
      table: { caption: "결과 표", headers: ["지표", "값"], rows: [["CAGR", "12.4%"]], footnote: "각주" },
      images: [{ src: "/notes/news/sample-note/overview.webp", alt: "결과 화면", caption: "수익 곡선", width: 1400, height: 800 }],
    },
    { heading: "결과 해석", paragraphs: ["해석 문단"] },
    { heading: "읽을 때 주의할 점", paragraphs: ["주의 문단"] },
  ],
  faq: [{ question: "자주 묻는 질문?", answer: "답" }],
};

describe("buildBlogExport", () => {
  // 2026-11-08 — 요약·표·해석만 옮긴 복사본이 빈약하다는 지적으로 본문 절을 모두 싣는다.
  it("carries every section in page order", () => {
    const { text } = buildBlogExport(NOTE, "https://example.test");
    expect(text).toContain("결과 표\n\n지표 | 값\nCAGR | 12.4%\n\n각주");
    const order = ["■ 출발한 기사", "■ 결과\n", "■ 결과 해석", "■ 읽을 때 주의할 점"].map((h) => text.indexOf(h));
    expect(order.every((at) => at >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(text).toContain("규칙 설명");
    expect(text).toContain("주의 문단");
  });

  // 2026-11-08 — 답변 엔진이 발췌하는 앞부분을 직답으로 시작하고, 글마다 수치가 다른 FAQ를 본문 뒤에 싣는다.
  it("opens with the title and direct answer, then links the original", () => {
    const { text } = buildBlogExport(NOTE, "https://example.test");
    expect(text.startsWith(NOTE.title)).toBe(true);
    expect(text.indexOf(NOTE.summary)).toBeLessThan(text.indexOf("원문: https://example.test"));
    expect(text.indexOf("원문: https://example.test")).toBeLessThan(text.indexOf("■ 출발한 기사"));
  });

  it("carries the FAQ after the sections in both formats", () => {
    const { html, text } = buildBlogExport(NOTE, "https://example.test");
    expect(text).toContain("■ 자주 묻는 질문\n\nQ. 자주 묻는 질문?\nA. 답");
    expect(text.indexOf("■ 읽을 때 주의할 점")).toBeLessThan(text.indexOf("■ 자주 묻는 질문"));
    expect(html).toContain("Q. 자주 묻는 질문?</p>");
    expect(html).toContain("A. 답</p>");
    expect(buildBlogExport({ ...NOTE, faq: undefined }, "https://example.test").text).not.toContain("■ 자주 묻는 질문");
  });

  it("keeps the source link and puts photos at absolute addresses", () => {
    const { html, text } = buildBlogExport(NOTE, "https://example.test");
    expect(html).toContain('출처: <a href="https://news.example/a">기사 제목</a>');
    expect(html).toContain('<img src="https://example.test/notes/news/sample-note/overview.webp" alt="결과 화면"');
    expect(text).toContain("[사진] 수익 곡선: https://example.test/notes/news/sample-note/overview.webp");
  });

  it("ends with blog tags for the note's series", () => {
    expect(blogTags("myth-40-ma200-hold")).toContain("속설검증");
    expect(blogTags("news-20261107-food-surprise")).toContain("뉴스전략");
    expect(buildBlogExport(NOTE, "https://example.test").text.endsWith("#널스탁 #백테스트 #퀀트투자 #주식백테스트 #퀀트연구")).toBe(true);
  });

  it("links the original note twice, and closes with the shared summary and tags, without the full disclaimer", () => {
    const { html, text } = buildBlogExport(NOTE, "https://example.test");
    const url = "https://example.test/notes/sample-note?utm_source=naver_blog&amp;utm_medium=referral&amp;utm_campaign=sample-note";
    const plainUrl = "https://example.test/notes/sample-note?utm_source=naver_blog&utm_medium=referral&utm_campaign=sample-note";
    expect(text).toContain(`원문: ${plainUrl}`);
    expect(text).toContain(`${SITE_SUMMARY_KO}\n\n#널스탁`);
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
    expect(buildBlogExport(NOTE).text).toContain("원문: https://www.nullstock.im/notes/sample-note?utm_source=naver_blog");
  });

  it("gives every seed note a result table in its export", () => {
    for (const note of SEED_NOTES) expect(buildBlogExport(note).html).toContain("<table");
  });
});
