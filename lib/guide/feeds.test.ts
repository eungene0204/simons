import { describe, expect, it } from "vitest";
import { GUIDE_ARTICLES } from "./articles";
import { NOTES, NOTES_DISCLAIMER } from "@/lib/notes/notes";
import { buildGuideRss, buildLlmsTxt } from "./feeds";

const BASE = "https://example.test";

describe("llms.txt", () => {
  it("links the guide index and every article with its summary", () => {
    const text = buildLlmsTxt(GUIDE_ARTICLES, BASE, []);
    expect(text.startsWith("# 널스탁")).toBe(true);
    expect(text).toContain(`(${BASE}/guide)`);
    for (const article of GUIDE_ARTICLES) {
      expect(text).toContain(`[${article.title}](${BASE}/guide/${article.slug}): ${article.summary}`);
    }
    expect(text).toMatch(/보장되지 않/);
    expect(text).not.toContain("## 연구노트");
  });

  it("adds a research-notes section once notes exist", () => {
    const text = buildLlmsTxt(GUIDE_ARTICLES, BASE, NOTES);
    expect(text).toContain("## 연구노트");
    expect(text).toContain(NOTES_DISCLAIMER);
    expect(text).toContain(`(${BASE}/notes)`);
    for (const note of NOTES) {
      expect(text).toContain(`[${note.title}](${BASE}/notes/${note.slug}): ${note.summary}`);
    }
  });
});

describe("guide RSS", () => {
  it("has one item per article, newest first, with absolute permalinks", () => {
    const xml = buildGuideRss(GUIDE_ARTICLES, BASE, []);
    expect(xml.startsWith('<?xml version="1.0"')).toBe(true);
    expect((xml.match(/<item>/g) ?? []).length).toBe(GUIDE_ARTICLES.length);
    for (const article of GUIDE_ARTICLES) {
      expect(xml).toContain(`<guid isPermaLink="true">${BASE}/guide/${article.slug}</guid>`);
    }
    expect(xml).toContain(`<atom:link href="${BASE}/feed.xml"`);
  });

  it("includes research notes with their /notes permalinks", () => {
    const xml = buildGuideRss(GUIDE_ARTICLES, BASE, NOTES);
    expect((xml.match(/<item>/g) ?? []).length).toBe(GUIDE_ARTICLES.length + NOTES.length);
    for (const note of NOTES) {
      expect(xml).toContain(`<guid isPermaLink="true">${BASE}/notes/${note.slug}</guid>`);
    }
  });

  it("escapes XML special characters", () => {
    const xml = buildGuideRss([{ ...GUIDE_ARTICLES[0], title: 'A & B <C> "D"' }], BASE, []);
    expect(xml).toContain("A &amp; B &lt;C&gt; &quot;D&quot;");
  });
});
