import { describe, expect, it } from "vitest";
import { getGuideArticle } from "@/lib/guide/articles";
import { buildGuideArticleJsonLd } from "@/lib/guide/jsonLd";
import { METHODOLOGY_ARTICLE, METHODOLOGY_COLLECTION, METHODOLOGY_DISCLAIMER, METHODOLOGY_PATH } from "./methodology";

function allText(): string {
  const a = METHODOLOGY_ARTICLE;
  return [
    METHODOLOGY_DISCLAIMER,
    a.title,
    a.description,
    a.summary,
    ...a.sections.flatMap((s) => [
      s.heading,
      ...s.paragraphs,
      ...(s.bullets ?? []),
      ...(s.table ? [s.table.caption, s.table.footnote ?? "", ...s.table.rows.flat()] : []),
    ]),
    ...(a.faq ?? []).flatMap((item) => [item.question, item.answer]),
  ].join("\n");
}

describe("methodology page", () => {
  it("lives at the top-level /methodology path with a two-level breadcrumb", () => {
    expect(`${METHODOLOGY_COLLECTION.basePath}/${METHODOLOGY_ARTICLE.slug}`).toBe(METHODOLOGY_PATH);
    const graph = (buildGuideArticleJsonLd(METHODOLOGY_ARTICLE, "https://example.test", METHODOLOGY_COLLECTION) as {
      "@graph": Array<Record<string, unknown>>;
    })["@graph"];
    expect(graph[0]).toMatchObject({ "@type": "Article", mainEntityOfPage: "https://example.test/methodology" });
    const crumbs = graph.find((node) => node["@type"] === "BreadcrumbList")!.itemListElement as Array<{ item: string }>;
    expect(crumbs.map((c) => c.item)).toEqual(["https://example.test", "https://example.test/methodology"]);
  });

  it("links related reading only to existing guide articles", () => {
    for (const slug of METHODOLOGY_ARTICLE.related) expect(getGuideArticle(slug)).toBeDefined();
  });

  // 엔진 정본 backend/engine/transaction_tax.py::KR_SELL_TAX_SCHEDULE와 같은 값이어야 한다.
  it("lists the statutory sell-tax schedule the engine applies", () => {
    const table = METHODOLOGY_ARTICLE.sections.find((s) => s.table)!.table!;
    expect(table.rows.map((row) => row[1])).toEqual(["0.30%", "0.25%", "0.23%", "0.20%", "0.18%", "0.15%"]);
    expect(table.footnote).toMatch(/엔진 v\d+\.\d+\.\d+/);
  });

  it("writes every section heading as a reader's question (answer-shaped headings)", () => {
    for (const section of METHODOLOGY_ARTICLE.sections) expect(section.heading).toMatch(/\?$/);
  });

  it("never uses recommendation, forecast or guarantee wording (regulatory guard)", () => {
    const text = allText();
    expect(text).not.toMatch(/추천|유망|권장|전망|수익률 보장|수익 보장|고수익|적합|우수|유리|좋은 (전략|종목|투자)/);
    const guarantees = text.match(/보장.{0,6}/g) ?? [];
    for (const match of guarantees) expect(match).toMatch(/^보장(되지|하지는?) ?않|^보장이 없/);
  });
});
