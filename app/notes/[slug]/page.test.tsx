import { afterEach, describe, expect, it, vi } from "vitest";
import type { GuideArticle } from "@/lib/guide/articles";

const NOTE: GuideArticle = {
  slug: "sample-note",
  title: "샘플 백테스트",
  description: "설명",
  summary: "요약",
  published: "2026-11-01",
  updated: "2026-11-01",
  related: [],
  sections: [],
};

vi.mock("@/lib/notes/notesStore", () => ({
  listNotes: async () => [NOTE],
  findNote: async () => NOTE,
}));

async function renderedHeaderAction() {
  const { default: NoteRoute } = await import("./page");
  const element = await NoteRoute({ params: { slug: NOTE.slug } });
  return (element as { props: { headerAction?: unknown } }).props.headerAction;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("note page blog copy button", () => {
  it("is offered in local development", async () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(await renderedHeaderAction()).toBeTruthy();
  });

  it("is never offered in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(await renderedHeaderAction()).toBeUndefined();
  });
});
