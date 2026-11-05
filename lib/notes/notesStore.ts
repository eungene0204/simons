// 연구노트 DB 조회 — 노트 정본은 ResearchNote 테이블이다(배포 없이 행만 넣으면 반영).
// 목록은 5분 캐시한다(unstable_cache) — 페이지·sitemap·RSS·llms.txt가 같은 캐시를 공유한다.
// 빌드 시점에는 DB를 읽지 않는다(호출하는 라우트가 모두 force-dynamic).

import { unstable_cache } from "next/cache";
import type { GuideArticle } from "@/lib/guide/articles";
import { rowToNote } from "./noteRow";
import { prisma } from "@/lib/prisma";

export const NOTES_REVALIDATE_SECONDS = 300;
export const NOTES_CACHE_TAG = "research-notes";

async function queryPublishedNotes(): Promise<GuideArticle[]> {
  const rows = await prisma.researchNote.findMany({
    where: { status: "PUBLISHED" },
    orderBy: [{ published: "desc" }, { sortKey: "asc" }, { slug: "asc" }],
  });
  return rows.map(rowToNote);
}

/** 공개(PUBLISHED) 노트 전체 — 최신 게시일 순, 같은 날은 sortKey 순.
 *  캐시는 운영에서만 쓴다. unstable_cache는 만료 후 첫 요청에 옛 목록을 주고 뒤에서 갱신한다 — 며칠 켜 둔 dev 서버는
 *  그 사이 DB에 넣은 노트를 첫 화면에서 빠뜨려 "운영엔 있는데 로컬엔 없다"로 보인다(2026-11-05). */
export const listNotes =
  process.env.NODE_ENV === "production"
    ? unstable_cache(queryPublishedNotes, ["research-notes-list"], {
        revalidate: NOTES_REVALIDATE_SECONDS,
        tags: [NOTES_CACHE_TAG],
      })
    : queryPublishedNotes;

export async function findNote(slug: string): Promise<GuideArticle | undefined> {
  return (await listNotes()).find((note) => note.slug === slug);
}
