import { describe, expect, it } from "vitest";
import { getGuideArticle } from "@/lib/guide/articles";
import { buildGuideArticleJsonLd } from "@/lib/guide/jsonLd";
import { NOTES_DISCLAIMER, SEED_NOTES as NOTES, buildNotesCollection, notePath } from "./notes";
import { mythNoteDataset, mythNoteOpenPrompt, mythNoteSeoTitle } from "./mythNotes";
import { CLASSIC_NOTES, CLASSIC_SLUG_BY_RULE, classicNoteDataset } from "./classicNotes";
import { CLASSIC_RESULTS } from "./classicResults";

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
    expect(myths).toHaveLength(32);
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

describe("mythNoteSeoTitle", () => {
  // 2026-11-04 — 속설 글 제목(h1)이 브랜드 포함 60자를 넘어 검색 결과에서 잘렸다. `<title>`은 속설 문구를 앞세워 짧게.
  it("front-loads the myth phrase, which also appears in the note body", () => {
    const myths = NOTES.filter((note) => note.slug.startsWith("myth-"));
    for (const note of myths) {
      const title = mythNoteSeoTitle(note.slug);
      expect(title).toMatch(/^“.+” 백테스트 결과$/);
      const phrase = title!.slice(1, title!.indexOf("”"));
      expect(note.sections.flatMap((section) => section.paragraphs).join(" ")).toContain(phrase);
      // 가장 긴 속설 문구(33자)도 브랜드 포함 52자 안 — 종전 최장 67자.
      expect(`${title} | 널스탁`.length).toBeLessThanOrEqual(52);
    }
  });

  it("leaves non-myth notes to their own title", () => {
    expect(mythNoteSeoTitle("cost-sensitivity-ma-crossover")).toBeUndefined();
  });
});

describe("myth-note reproduction and dataset", () => {
  const myths = NOTES.filter((note) => note.slug.startsWith("myth-"));

  it("reuses the exact input sentence written in the note for the open link", () => {
    for (const note of myths) {
      const prompt = mythNoteOpenPrompt(note.slug);
      if (!prompt) continue;
      const quoted = note.sections.flatMap((section) => section.paragraphs).join(" ").replace(/[“”]/g, "");
      expect(quoted).toContain(prompt);
      expect(prompt.length).toBeLessThanOrEqual(1000);
    }
    expect(mythNoteOpenPrompt("cost-sensitivity-ma-crossover")).toBeUndefined();
  });

  it("links each myth Article to a Dataset covering the backtest period", () => {
    for (const note of myths) {
      const dataset = mythNoteDataset(note.slug);
      expect(dataset?.temporalCoverage).toMatch(/^\d{4}-\d{2}-\d{2}\/\d{4}-\d{2}-\d{2}$/);
      const graph = (buildGuideArticleJsonLd(note, "https://example.test", NOTES_COLLECTION, dataset) as {
        "@graph": Array<Record<string, unknown>>;
      })["@graph"];
      const url = `https://example.test/notes/${note.slug}`;
      expect(graph[0].isBasedOn).toEqual({ "@id": `${url}#dataset` });
      expect(graph.find((node) => node["@type"] === "Dataset")).toMatchObject({
        "@id": `${url}#dataset`,
        temporalCoverage: dataset!.temporalCoverage,
      });
    }
    expect(mythNoteDataset("cost-sensitivity-ma-crossover")).toBeUndefined();
  });
});

describe("classic-technique notes (KOSPI 3y)", () => {
  it("has nine notes, each resolving under /notes with a question title", () => {
    expect(CLASSIC_NOTES).toHaveLength(9);
    for (const note of CLASSIC_NOTES) {
      expect(getNote(note.slug)?.slug).toBe(note.slug);
      expect(note.title).toMatch(/KOSPI 최근 3년 백테스트하면 수익이 났을까\?$/);
    }
  });

  it("states the generated figures, the start-date range and the short disclaimer in each summary", () => {
    const results = Object.values(CLASSIC_RESULTS);
    for (const [index, note] of CLASSIC_NOTES.entries()) {
      const r = results.find((item) => note.summary.includes(`${item.start}~${item.end}`) && note.summary.includes(item.ret))!;
      expect(r, note.slug).toBeDefined();
      for (const figure of [r.cagr, r.mdd, r.win, r.trades, r.benchCagr, ...r.retRange]) expect(note.summary).toContain(figure);
      expect(note.summary).toMatch(/미래 수익을 보장하지 않습니다\.$/);
      expect(index).toBeGreaterThanOrEqual(0);
    }
  });

  it("shows every start-date run, including the worst one, in a table", () => {
    for (const note of CLASSIC_NOTES) {
      const table = note.sections.find((s) => s.heading === "시작일을 하루씩 바꿔 본 결과")?.table;
      expect(table?.rows.length).toBe(5);
    }
  });

  it("links each note to a Dataset covering the backtest window", () => {
    for (const note of CLASSIC_NOTES) {
      expect(classicNoteDataset(note.slug)?.temporalCoverage).toBe("2023-11-03/2026-11-03");
    }
    expect(classicNoteDataset("myth-09-ma-5-20-cross")).toBeUndefined();
  });

  it("maps every result rule to its note slug for the raw-result upload", () => {
    expect(Object.keys(CLASSIC_SLUG_BY_RULE).sort()).toEqual(Object.keys(CLASSIC_RESULTS).sort());
    expect(Object.values(CLASSIC_SLUG_BY_RULE).sort()).toEqual(CLASSIC_NOTES.map((note) => note.slug).sort());
  });
});
