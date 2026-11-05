import { afterEach, describe, expect, it, vi } from "vitest";

const findMany = vi.fn();
const unstableCache = vi.fn((fn: unknown) => fn);

vi.mock("@/lib/prisma", () => ({ prisma: { researchNote: { findMany } } }));
vi.mock("next/cache", () => ({ unstable_cache: unstableCache }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
  unstableCache.mockClear();
  findMany.mockReset();
});

describe("listNotes 캐시", () => {
  // 회귀: 며칠 켜 둔 dev 서버가 만료된 캐시(옛 목록)를 먼저 내줘 새로 넣은 노트가 로컬에서만 빠져 보였다.
  it("개발 환경에서는 캐시 없이 매 요청 DB를 읽는다", async () => {
    vi.stubEnv("NODE_ENV", "development");
    findMany.mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    const { listNotes } = await import("./notesStore");
    await listNotes();
    await listNotes();
    expect(unstableCache).not.toHaveBeenCalled();
    expect(findMany).toHaveBeenCalledTimes(2);
  });

  it("운영에서는 unstable_cache로 감싼다", async () => {
    vi.stubEnv("NODE_ENV", "production");
    await import("./notesStore");
    expect(unstableCache).toHaveBeenCalledWith(expect.any(Function), ["research-notes-list"], {
      revalidate: 300,
      tags: ["research-notes"],
    });
  });
});
