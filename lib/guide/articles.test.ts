import { describe, expect, it } from "vitest";
import {
  GUIDE_ARTICLES,
  GUIDE_DESCRIPTION,
  GUIDE_DISCLAIMER,
  GUIDE_TITLE,
  getGuideArticle,
  guideArticlePath,
} from "./articles";
import { buildGuideArticleJsonLd, buildGuideIndexJsonLd } from "./jsonLd";

function allText(): string {
  return [
    GUIDE_TITLE,
    GUIDE_DESCRIPTION,
    GUIDE_DISCLAIMER,
    ...GUIDE_ARTICLES.flatMap((article) => [
      article.title,
      article.description,
      article.summary,
      ...article.sections.flatMap((section) => [
        section.heading,
        ...section.paragraphs,
        ...(section.bullets ?? []),
      ]),
    ]),
  ].join("\n");
}

describe("guide articles", () => {
  it("has unique URL-safe slugs and resolves each by slug", () => {
    const slugs = GUIDE_ARTICLES.map((article) => article.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    for (const slug of slugs) {
      expect(slug).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
      expect(getGuideArticle(slug)?.slug).toBe(slug);
      expect(guideArticlePath(slug)).toBe(`/guide/${slug}`);
    }
    expect(getGuideArticle("no-such-article")).toBeUndefined();
  });

  it("points related links only at existing, other articles", () => {
    for (const article of GUIDE_ARTICLES) {
      expect(article.related.length).toBeGreaterThan(0);
      for (const slug of article.related) {
        expect(slug).not.toBe(article.slug);
        expect(getGuideArticle(slug)).toBeDefined();
      }
    }
  });

  it("gives every article a title, description, summary and non-empty sections", () => {
    for (const article of GUIDE_ARTICLES) {
      expect(article.title).toMatch(/백테스트|워크포워드|몬테카를로/);
      expect(article.description.length).toBeGreaterThan(50);
      expect(article.summary.length).toBeGreaterThan(50);
      expect(article.updated >= article.published).toBe(true);
      expect(article.sections.length).toBeGreaterThanOrEqual(5);
      for (const section of article.sections) {
        expect(section.paragraphs.length + (section.bullets?.length ?? 0)).toBeGreaterThan(0);
      }
    }
  });

  it("never uses recommendation, forecast or guarantee wording (regulatory guard)", () => {
    const text = allText();
    expect(text).not.toMatch(/추천|유망|권장|전망|수익률 보장|수익 보장|고수익|적합|우수|유리|좋은 (전략|종목|투자)/);
    // '보장'은 '보장되지 않습니다'·'보장하지는 않습니다'·'보장이 없습니다'(면책)로만 쓴다.
    const guarantees = text.match(/보장.{0,6}/g) ?? [];
    for (const match of guarantees) expect(match).toMatch(/^보장(되지|하지는?) ?않|^보장이 없/);
  });

  it("keeps the disclaimer saying results are past-data simulation", () => {
    expect(GUIDE_DISCLAIMER).toMatch(/과거 데이터/);
    expect(GUIDE_DISCLAIMER).toMatch(/보장되지 않/);
  });
});

describe("guide JSON-LD", () => {
  it("describes an article with breadcrumbs under the given base URL", () => {
    const article = GUIDE_ARTICLES[0];
    const graph = (buildGuideArticleJsonLd(article, "https://example.test") as { "@graph": Array<Record<string, unknown>> })[
      "@graph"
    ];
    expect(graph[0]).toMatchObject({
      "@type": "Article",
      headline: article.title,
      inLanguage: "ko-KR",
      mainEntityOfPage: `https://example.test/guide/${article.slug}`,
      publisher: { "@id": "https://example.test/#organization" },
    });
    const crumbs = graph[1].itemListElement as Array<{ position: number; item: string }>;
    expect(crumbs.map((c) => c.item)).toEqual([
      "https://example.test",
      "https://example.test/guide",
      `https://example.test/guide/${article.slug}`,
    ]);
  });

  it("lists every article on the index page graph", () => {
    const graph = (buildGuideIndexJsonLd(GUIDE_ARTICLES, "https://example.test") as { "@graph": Array<Record<string, unknown>> })[
      "@graph"
    ];
    const list = (graph[0].mainEntity as { itemListElement: Array<{ url: string }> }).itemListElement;
    expect(list.map((item) => item.url)).toEqual(
      GUIDE_ARTICLES.map((article) => `https://example.test/guide/${article.slug}`),
    );
  });
});
