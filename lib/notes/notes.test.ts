import { describe, expect, it } from "vitest";
import { getGuideArticle } from "@/lib/guide/articles";
import { buildGuideArticleJsonLd } from "@/lib/guide/jsonLd";
import { existsSync } from "fs";
import { join } from "path";
import {
  NOTES_DISCLAIMER,
  NOTES_PAGE_SIZE,
  SEED_NOTES as NOTES,
  buildNotesCollection,
  notePath,
  notesListHref,
  paginateNotes,
  searchNotes,
} from "./notes";
import { mythNoteDataset, mythNoteOpenPrompt, mythNoteSeoTitle } from "./mythNotes";
import { NEWS_NOTES, newsNoteDataset, newsNoteOpenPrompt } from "./newsNotes";
import { CLASSIC_NOTES, CLASSIC_SUMMARY_SLUG, classicNoteDataset, classicNoteSlug } from "./classicNotes";
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
        section.source?.label ?? "",
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

  // 2026-11-09 사용자 지시: 노트 본문은 '규칙'이 아니라 '전략'이라고 쓴다(엔진·지수 자체의 규칙만 예외). 뉴스 편은 기사 제목을 그대로 실어 틀(newsNotes.ts)에서 맞춘다.
  it("calls a strategy 전략", () => {
    for (const note of NOTES.filter((n) => !n.slug.startsWith("news-"))) {
      const text = JSON.stringify([note.title, note.description, note.summary, note.sections, note.faq]).replace(/엔진 기본 규칙|편입·편출 규칙|문장에 없던 규칙/g, "");
      expect(text, note.slug).not.toContain("규칙");
    }
  });

  it("keeps every myth-series summary consistent with its result table", () => {
    const myths = NOTES.filter((note) => note.slug.startsWith("myth-"));
    expect(myths).toHaveLength(43);
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

describe("classic-technique notes (KOSPI·KOSDAQ 3y)", () => {
  const reports = CLASSIC_NOTES.filter((note) => /^(kospi|kosdaq)-3y-/.test(note.slug));
  const hubs = CLASSIC_NOTES.filter((note) => note.slug.startsWith("techniques-"));
  type Row = (typeof CLASSIC_RESULTS)["KOSPI"]["golden_cross_5_20"];
  const allResults = [...Object.values(CLASSIC_RESULTS.KOSPI), ...Object.values(CLASSIC_RESULTS.KOSDAQ)] as Row[];

  it("has ten techniques in two markets, five hubs and one summary, all under /notes", () => {
    expect(reports).toHaveLength(20);
    expect(hubs).toHaveLength(5);
    expect(getNote(CLASSIC_SUMMARY_SLUG)).toBeDefined();
    for (const note of reports) {
      expect(getNote(note.slug)?.slug).toBe(note.slug);
      expect(note.title, note.slug).toMatch(/(KOSPI|KOSDAQ) 최근 3년/);
      expect(note.title, note.slug).toMatch(/(났을까|였을까|컸을까|어땠을까|달랐을까)\?/);
    }
    // 2026-11-08 — 이웃한 글의 질문 표현이 겹치지 않는다.
    const endings = reports.map((note) => note.title.replace(/^.*전략(, |의 |을 |은 )/, "").replace(/(KOSPI|KOSDAQ) 최근 3년/, ""));
    expect(new Set(endings).size).toBe(7);
    endings.slice(1).forEach((ending, i) => expect(ending, reports[i + 1].slug).not.toBe(endings[i]));
  });

  it("keeps the slugs of the KOSPI notes published on 2026-11-04", () => {
    for (const base of ["golden-cross-5-20", "ma-alignment-5-20-60", "rsi-30-70", "macd-signal-cross", "bollinger-lower", "52-week-high", "dual-momentum-12m", "low-per-pbr-20", "magic-formula-20"]) {
      expect(getNote(`kospi-3y-${base}`)?.published).toBe("2026-11-04");
    }
  });

  // 2026-11-09 사용자 지시: 면책은 페이지 아래 안내가 맡는다. 본문·요약·FAQ에 반복하지 않는다.
  it("carries no future-return sentence in the body", () => {
    for (const note of NOTES) {
      expect(JSON.stringify([note.summary, note.sections, note.faq]), note.slug).not.toMatch(/미래 수익(을|은) 보장/);
    }
  });

  it("fits titles and descriptions within search snippet lengths", () => {
    for (const note of CLASSIC_NOTES) {
      expect(note.title.length, note.slug).toBeLessThanOrEqual(60);
      expect(note.description.length, note.slug).toBeLessThanOrEqual(155);
    }
  });

  it("states the generated figures, and the start-date range in each summary", () => {
    for (const note of reports) {
      const r = allResults.find((item) => note.summary.includes(`${item.start}~${item.end}`) && note.summary.includes(item.ret))!;
      expect(r, note.slug).toBeDefined();
      for (const figure of [r.cagr, r.mdd, r.win, r.trades, r.benchCagr, ...r.retRange]) expect(note.summary).toContain(figure);
    }
  });

  it("shows every start-date run, including the worst one, in a table", () => {
    for (const note of reports) {
      const table = note.sections.find((s) => s.heading === "시작일을 하루씩 바꿔 본 결과")?.table;
      expect(table?.rows.length).toBe(5);
    }
  });

  it("labels holding-period exits as such, not as sell signals", () => {
    const exits = getNote("kospi-3y-52-week-high")!.sections.find((s) => s.heading === "청산 내역")!.table!.rows.map((row) => row[0]);
    expect(exits).toContain("보유 기간 만료");
    expect(exits).not.toContain("매도 신호");
  });

  it("discloses data coverage for the fundamental rules and the engine price-repair defect", () => {
    const caveats = (slug: string) => getNote(slug)!.sections.find((s) => s.heading === "읽을 때 주의할 점")!.paragraphs.join(" ");
    expect(caveats("kosdaq-3y-magic-formula-20")).toContain("EV/EBIT 데이터가 전체 기간의 54.3%");
    expect(caveats("kosdaq-3y-magic-formula-20")).toMatch(/외부 재무 데이터 조회가 실패해 조건에서 빠진 종목이 \d+개/);
    expect(caveats("kosdaq-3y-bollinger-lower")).toContain("227100");
    // 2026-11-05 엔진 v16.47: 정리매매 첫날 폭락이 보정으로 덮이지 않고 실제 손실로 남는다.
    expect(caveats("kosdaq-3y-bollinger-lower")).toContain("−93.94%");
    expect(caveats("kospi-3y-golden-cross-5-20")).not.toContain("재무 값이 없는 종목");
  });

  it("puts every report of a family in its hub table and links them", () => {
    for (const hub of hubs) {
      const rows = hub.sections.find((s) => s.heading === "결과 한눈에 보기")!.table!.rows;
      expect(rows).toHaveLength(4);
      expect(hub.related).toHaveLength(4);
      for (const slug of hub.related) expect(getNote(slug)!.related[0]).toBe(hub.slug);
    }
  });

  it("counts the summary figures from the same results", () => {
    const summary = getNote(CLASSIC_SUMMARY_SLUG)!;
    const positive = allResults.filter((r) => !r.ret.startsWith("−")).length;
    const above = allResults.filter((r) => !r.below).length;
    expect(summary.summary).toContain(`20번의 계산 중 투자 수익률이 플러스였던 것은 ${positive}번`);
    expect(summary.summary).toContain(`보다 높았던 것은 ${above}번`);
    expect(summary.sections.find((s) => s.heading === "결과 표")!.table!.rows).toHaveLength(20);
  });

  it("links each report to a Dataset covering the backtest window", () => {
    for (const note of reports) {
      expect(classicNoteDataset(note.slug)?.temporalCoverage).toBe("2023-11-03/2026-11-03");
    }
    expect(classicNoteDataset(CLASSIC_SUMMARY_SLUG)).toBeUndefined();
    expect(classicNoteDataset("myth-09-ma-5-20-cross")).toBeUndefined();
  });

  it("maps every result row to its report slug for the raw-result upload", () => {
    for (const market of ["KOSPI", "KOSDAQ"] as const) {
      for (const rule of Object.keys(CLASSIC_RESULTS[market])) {
        expect(getNote(classicNoteSlug(market, rule)!)).toBeDefined();
      }
    }
    expect(classicNoteSlug("KOSPI", "unknown_rule")).toBeUndefined();
  });
});

// 2026-11-07 — 뉴스 전략 테스트(~/nullstock-news) 결과를 연구노트로 옮겼다(build_news_notes.py → newsNotes.data.json).
describe("news strategy notes", () => {
  it("adds the news notes with summaries matching their result tables", () => {
    expect(NEWS_NOTES).toHaveLength(63);
    for (const note of NEWS_NOTES) {
      expect(note.slug).toMatch(/^news-\d{8}-/);
      const rows = note.sections.flatMap((s) => s.table?.rows ?? []);
      for (const label of ["투자 수익률", "CAGR", "최대 낙폭", "승률"]) {
        const value = rows.find((row) => row[0] === label)?.[1];
        expect(value, `${note.slug} ${label}`).toBeDefined();
        expect(note.summary).toContain(value!);
      }
    }
  });

  it("links the source article and ships every photo it references", () => {
    for (const note of NEWS_NOTES) {
      const source = note.sections.find((s) => s.heading === "이 전략을 떠올린 기사")?.source;
      expect(source?.href).toMatch(/^https:\/\/(www\.yna\.co\.kr\/view|n\.news\.naver\.com\/article)\//);
      const images = note.sections.flatMap((s) => s.images ?? []);
      expect(images.length).toBeGreaterThan(0);
      for (const image of images) {
        expect(image.src).toMatch(new RegExp(`^/notes/news/${note.slug}/(overview|dist)\\.webp$`));
        expect(existsSync(join(process.cwd(), "public", image.src)), image.src).toBe(true);
      }
    }
  });

  it("keeps per-stock profit lines out of the interpretation", () => {
    for (const note of NEWS_NOTES) {
      const bullets = note.sections.find((s) => s.heading === "결과 해석")!.bullets!;
      expect(bullets.some((line) => line.startsWith("종목별"))).toBe(false);
    }
  });

  // 2026-11-05 사용자 지시 — 하단 면책과 겹치는 '미래 수익 보장' 문장을 노트 본문·FAQ에 쓰지 않는다.
  it("leaves the future-return sentence to the page disclaimer", () => {
    for (const note of NEWS_NOTES) {
      const text = JSON.stringify(note);
      expect(text, note.slug).not.toMatch(/미래 수익/);
    }
  });

  it("does not repeat forecast wording from a headline as the source link text", () => {
    const note = NEWS_NOTES.find((item) => item.slug === "news-20261030-semi-op-growth")!;
    expect(note.sections.find((s) => s.source)?.source).toMatchObject({ label: "기사 원문 보기" });
  });

  // 2026-11-08 — 모든 글이 같은 문장으로 시작·끝나지 않게 제목 표현을 돌려 쓴다.
  it("varies the question wording so neighbouring titles differ", () => {
    const wording = (title: string, name: string) => title.replace(name, "");
    const NAMES = NEWS_NOTES.map((note) => note.title.replace(/( 전략).*$|^.*백테스트에서 /, ""));
    const shapes = NEWS_NOTES.map((note, i) => wording(note.title, NAMES[i]).replace(/(KOS(PI|DAQ)( \d+)?|한국 주식) (\d+년|\d{4}~\d{4}년|최근 5년)/, ""));
    expect(new Set(shapes).size).toBeGreaterThanOrEqual(7);
    shapes.slice(1).forEach((shape, i) => expect(shape, NEWS_NOTES[i + 1].slug).not.toBe(shapes[i]));
  });

  // 2026-11-08 — AI 답변 엔진이 잘라 인용해도 뜻이 통하게 결론을 앞에 두고, 문답마다 규칙 이름·구간·수치를 자체로 갖는다.
  it("leads with the result and keeps each answer self-contained", () => {
    for (const note of NEWS_NOTES) {
      expect(note.title, note.slug).toMatch(/전략.*(KOS(PI|DAQ)( \d+)?|한국 주식) (\d+년|\d{4}~\d{4}년|최근 5년)|(KOS(PI|DAQ)( \d+)?|한국 주식) (\d+년|\d{4}~\d{4}년|최근 5년) 백테스트에서 .*전략/);
      expect(note.title, note.slug).toMatch(/(났을까|였을까|컸을까|어땠을까|달랐을까)\?/);
      expect(note.title, note.slug).not.toMatch(/효과가 있을까|유망할까|좋을까/);
      expect(note.summary.startsWith("널스탁 백테스트 기준,"), note.slug).toBe(true);
      expect(note.sections[0].table?.rows.some((row) => row[0] === "투자 수익률"), note.slug).toBe(true);
      const rows = note.sections[0].table!.rows;
      const value = (label: string) => rows.find((row) => row[0] === label)![1];
      const [returnFaq, riskFaq, ruleFaq] = note.faq!;
      expect(returnFaq.answer).toContain(value("투자 수익률"));
      expect(returnFaq.answer).toContain(value("기간"));
      expect(riskFaq.answer).toContain(value("최대 낙폭"));
      expect(ruleFaq.answer, note.slug).toMatch(/매수 조건 |리밸런싱 /);
    }
  });

  it("states the gap to the benchmark in the same arithmetic as the interpretation", () => {
    for (const note of NEWS_NOTES) {
      const gap = /와 ([+−][\d.]+%p) 차이가 났습니다/.exec(note.sections[0].paragraphs[0])?.[1];
      expect(gap, note.slug).toBeDefined();
      const bullets = note.sections.find((s) => s.heading === "결과 해석")!.bullets!;
      expect(bullets.find((line) => line.startsWith("벤치마크 비교")), note.slug).toContain(`${gap} 차이`);
    }
  });

  it("describes the backtest result as a dataset for every news note", () => {
    for (const note of NEWS_NOTES) {
      const dataset = newsNoteDataset(note.slug);
      expect(dataset?.temporalCoverage, note.slug).toMatch(/^\d{4}-\d{2}-\d{2}\/\d{4}-\d{2}-\d{2}$/);
      expect(dataset?.variableMeasured).toContain("최대 낙폭(MDD)");
    }
    expect(newsNoteDataset("myth-09-ma-5-20-cross")).toBeUndefined();
  });

  it("opens the exact input sentence quoted in the note", () => {
    for (const note of NEWS_NOTES) {
      const prompt = newsNoteOpenPrompt(note.slug);
      expect(prompt).toBeTruthy();
      expect(note.sections[1].paragraphs).toContain(`“${prompt}”`);
    }
    expect(newsNoteOpenPrompt("myth-09-ma-5-20-cross")).toBeUndefined();
  });
});

describe("notes list search and pages", () => {
  it("matches every search word in the title, description or summary, ignoring case", () => {
    const rsi = searchNotes(NOTES, "rsi 뉴스");
    expect(rsi.length).toBeGreaterThan(0);
    for (const note of rsi) {
      const text = `${note.title} ${note.description} ${note.summary}`.toLowerCase();
      expect(text).toContain("rsi");
      expect(text).toContain("뉴스");
    }
    expect(searchNotes(NOTES, "   ")).toBe(NOTES);
  });

  it("clamps the page into range and slices ten notes per page", () => {
    const last = Math.ceil(NOTES.length / NOTES_PAGE_SIZE);
    expect(paginateNotes(NOTES, 1).notes).toEqual(NOTES.slice(0, NOTES_PAGE_SIZE));
    expect(paginateNotes(NOTES, 999).page).toBe(last);
    expect(paginateNotes(NOTES, 0).page).toBe(1);
    expect(paginateNotes(NOTES, Number.NaN).page).toBe(1);
    expect(paginateNotes([], 3)).toMatchObject({ notes: [], page: 1, totalPages: 1, total: 0 });
  });

  it("drops page 1 and empty queries from list URLs", () => {
    expect(notesListHref(1)).toBe("/notes");
    expect(notesListHref(3)).toBe("/notes?page=3");
    expect(notesListHref(1, "반도체")).toBe(`/notes?q=${encodeURIComponent("반도체")}`);
  });
});
