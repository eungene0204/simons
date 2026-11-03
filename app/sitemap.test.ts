import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GUIDE_ARTICLES } from "@/lib/guide/articles";
import { SEED_NOTES as NOTES } from "@/lib/notes/notes";
import { listNotes } from "@/lib/notes/notesStore";
import sitemap from "./sitemap";

vi.mock("@/lib/notes/notesStore", () => ({ listNotes: vi.fn() }));

beforeEach(() => {
  vi.mocked(listNotes).mockResolvedValue(NOTES);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("sitemap", () => {
  it("lists only public entry points and leaves out /us while the global service is blocked", async () => {
    vi.stubEnv("DOMAIN", "");
    const entries = await sitemap();
    const urls = entries.map((entry) => entry.url);

    expect(urls).toEqual([
      "https://www.nullstock.im",
      "https://www.nullstock.im/guide",
      ...GUIDE_ARTICLES.map((article) => `https://www.nullstock.im/guide/${article.slug}`),
      "https://www.nullstock.im/notes",
      ...NOTES.map((note) => `https://www.nullstock.im/notes/${note.slug}`),
    ]);
    // 한국 요금제는 비로그인 요청을 `/`로 리다이렉트한다 — 리다이렉트 URL은 사이트맵에 넣지 않는다.
    expect(urls).not.toContain("https://www.nullstock.im/pricing");

    // 2026-11-04 — `/us`가 404인 동안(US_REGION_BLOCKED) 404 URL·hreflang을 안내하지 않는다.
    const home = entries[0];
    expect(home.priority).toBe(1);
    expect(home.alternates).toBeUndefined();
    expect(urls.some((url) => url.includes("/us"))).toBe(false);
  });

  it("omits /notes while the DB has no notes (an empty list is noindex)", async () => {
    vi.mocked(listNotes).mockResolvedValue([]);
    const urls = (await sitemap()).map((entry) => entry.url);
    expect(urls.some((url) => url.includes("/notes"))).toBe(false);
  });

  it("follows the DOMAIN env for absolute URLs", async () => {
    vi.stubEnv("DOMAIN", "staging.nullstock.im");
    expect((await sitemap())[0].url).toBe("https://staging.nullstock.im");
  });
});
