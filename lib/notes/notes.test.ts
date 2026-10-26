import { describe, expect, it } from "vitest";
import { getGuideArticle } from "@/lib/guide/articles";
import { buildGuideArticleJsonLd } from "@/lib/guide/jsonLd";
import { NOTES_DISCLAIMER, SEED_NOTES as NOTES, buildNotesCollection, notePath } from "./notes";

const NOTES_COLLECTION = buildNotesCollection(NOTES);
const getNote = NOTES_COLLECTION.find;

function allText(): string {
  return [
    NOTES_DISCLAIMER,
    ...NOTES.flatMap((note) => [
      note.title,
      note.description,
      note.summary,
      ...note.sections.flatMap((section) => [
        section.heading,
        ...section.paragraphs,
        ...(section.bullets ?? []),
        ...(section.table ? [section.table.caption, section.table.footnote ?? "", ...section.table.rows.flat()] : []),
      ]),
      ...(note.faq ?? []).flatMap((item) => [item.question, item.answer]),
    ]),
  ].join("\n");
}

describe("research notes", () => {
  it("has unique URL-safe slugs that resolve under /notes", () => {
    const slugs = NOTES.map((note) => note.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    for (const slug of slugs) {
      expect(slug).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
      expect(getNote(slug)?.slug).toBe(slug);
      expect(notePath(slug)).toBe(`/notes/${slug}`);
    }
  });

  it("links related reading only to existing notes or guide articles", () => {
    for (const note of NOTES) {
      for (const slug of note.related) {
        expect(getNote(slug) ?? getGuideArticle(slug)).toBeDefined();
      }
    }
  });

  it("keeps every table rectangular and records engine version and calculation date", () => {
    for (const note of NOTES) {
      const tables = note.sections.flatMap((section) => (section.table ? [section.table] : []));
      expect(tables.length).toBeGreaterThan(0);
      for (const table of tables) {
        for (const row of table.rows) expect(row).toHaveLength(table.headers.length);
        expect(table.footnote).toMatch(/엔진 v\d+\.\d+\.\d+/);
        expect(table.footnote).toMatch(/\d{4}-\d{2}-\d{2}에 계산/);
      }
    }
  });

  it("states in the summary the exact CAGR figures that appear in its tables", () => {
    const note = getNote("cost-sensitivity-ma-crossover")!;
    const cells = note.sections.flatMap((s) => s.table?.rows.flat() ?? []);
    for (const figure of ["16.8%", "13.8%", "6.2%", "−5.4%"]) {
      expect(note.summary).toContain(figure);
      expect(cells).toContain(figure);
    }
  });

  it("keeps every myth-series summary consistent with its result table", () => {
    const myths = NOTES.filter((note) => note.slug.startsWith("myth-"));
    expect(myths).toHaveLength(27);
    for (const note of myths) {
      const rows = note.sections.flatMap((s) => s.table?.rows ?? []);
      const ret = rows.find((row) => row[0] === "투자 수익률")?.[1];
      const cagr = rows.find((row) => row[0] === "CAGR")?.[1];
      expect(ret).toBeDefined();
      expect(note.summary).toContain(ret!);
      expect(note.summary).toContain(cagr!);
      expect(note.title).toContain(`#${Number(note.slug.slice(5, 7))}`);
    }
  });

  it("never uses recommendation, ranking, forecast or guarantee wording (regulatory guard)", () => {
    const text = allText();
    expect(text).not.toMatch(/추천|유망|권장|전망|수익률 보장|수익 보장|고수익|적합|우수|유리|좋은 (전략|종목|투자)/);
    const guarantees = text.match(/보장.{0,6}/g) ?? [];
    for (const match of guarantees) expect(match).toMatch(/^보장(되지|하지는?) ?않|^보장이 없/);
  });

  it("emits Article, breadcrumbs under /notes, and FAQPage with the visible FAQ strings", () => {
    for (const note of NOTES) {
      const graph = (buildGuideArticleJsonLd(note, "https://example.test", NOTES_COLLECTION) as {
        "@graph": Array<Record<string, unknown>>;
      })["@graph"];
      expect(graph[0]).toMatchObject({ "@type": "Article", mainEntityOfPage: `https://example.test/notes/${note.slug}` });
      const crumbs = graph[1].itemListElement as Array<{ item: string }>;
      expect(crumbs.map((c) => c.item)).toEqual([
        "https://example.test",
        "https://example.test/notes",
        `https://example.test/notes/${note.slug}`,
      ]);
      const faq = graph.find((node) => node["@type"] === "FAQPage") as {
        mainEntity: Array<{ name: string; acceptedAnswer: { text: string } }>;
      };
      expect(faq.mainEntity.map((q) => [q.name, q.acceptedAnswer.text])).toEqual(
        note.faq!.map((item) => [item.question, item.answer]),
      );
    }
  });
});
