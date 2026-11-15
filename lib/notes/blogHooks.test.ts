import { describe, expect, it } from "vitest";
import type { GuideArticle } from "@/lib/guide/articles";
import { BLOG_HOOKS } from "./blogHooks";
import { SEED_NOTES } from "./notes";

function noteText(note: GuideArticle): string {
  const parts = [note.title, note.description, note.summary];
  for (const section of note.sections) {
    parts.push(section.heading, ...section.paragraphs, ...(section.bullets ?? []));
    if (section.table) parts.push(...section.table.headers, ...section.table.rows.flat(), section.table.caption);
  }
  for (const item of note.faq ?? []) parts.push(item.question, item.answer);
  return parts.join("\n").replace(/,/g, "");
}

describe("BLOG_HOOKS", () => {
  const notes = new Map(SEED_NOTES.map((note) => [note.slug, note]));

  it("only names notes that exist", () => {
    expect(Object.keys(BLOG_HOOKS).filter((slug) => !notes.has(slug))).toEqual([]);
  });

  // 블로그 제목·첫 문장은 손으로 쓴 문구라 수치를 옮기다 틀릴 수 있다 — 모든 숫자가 노트 본문에 있어야 한다.
  it("uses only numbers that appear in the note", () => {
    const missing: string[] = [];
    for (const [slug, hook] of Object.entries(BLOG_HOOKS)) {
      const text = noteText(notes.get(slug)!);
      for (const token of `${hook.title} ${hook.lead}`.match(/\d[\d,]*(?:\.\d+)?/g) ?? []) {
        if (!text.includes(token.replace(/,/g, ""))) missing.push(`${slug}: ${token}`);
      }
    }
    expect(missing).toEqual([]);
  });

  // 규제 안전 원칙 — 추천·우열·보장, 낚시성 과장 표현을 쓰지 않는다.
  it("avoids recommendation and sensational wording", () => {
    for (const hook of Object.values(BLOG_HOOKS)) {
      expect(`${hook.title} ${hook.lead}`).not.toMatch(/추천|유망|권장|보장|적합|우수|유리|최고|최악|충격|수익 낸/);
    }
  });

  // 피드엔 제목만 보인다 — 명령('사라?')·앞날('더 오를까?')로 묻지 않고 지난 결과를 묻는다(2026-11-15 계약 검토).
  it("asks about past results, not what to buy next", () => {
    for (const hook of Object.values(BLOG_HOOKS)) {
      expect(hook.title).not.toMatch(/사라\?|오를까\?|갈까\?|될까\?|사면\?|팔면\?/);
    }
  });
});
