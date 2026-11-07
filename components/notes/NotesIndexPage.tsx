import Link from "next/link";
import { AdSideRails } from "@/components/ads/AdSideRails";
import { AdSlot } from "@/components/ads/AdSlot";
import { AD_SLOTS } from "@/lib/ads/adsense";
import type { GuideArticle } from "@/lib/guide/articles";
import {
  NOTES_BASE_PATH,
  NOTES_DESCRIPTION,
  NOTES_DISCLAIMER,
  NOTES_TITLE,
  notesListHref,
  paginateNotes,
  searchNotes,
} from "@/lib/notes/notes";
import { buildGuideIndexJsonLd } from "@/lib/guide/jsonLd";
import { serializeJsonLd } from "@/lib/seo/site";

// 연구노트 목록 — 한국어 전용 공개 페이지(서버 컴포넌트). 글이 아직 없으면 준비 중 안내를 보인다.
// 광고는 양옆과 목록 아래에만 두고(글 링크 사이에 끼우지 않는다), 글이 없는 빈 페이지에는 싣지 않는다.
// 한 쪽에 10편씩 싣고(?page=N), 검색(?q=)은 GET 폼이라 스크립트 없이도 동작한다. 구조화 데이터는 지금 쪽의 글만 싣는다.
export function NotesIndexPage({
  notes: allNotes,
  page: requestedPage = 1,
  query = "",
}: {
  notes: GuideArticle[];
  page?: number;
  query?: string;
}) {
  const matched = searchNotes(allNotes, query);
  const { notes, page, totalPages, total } = paginateNotes(matched, requestedPage);
  return (
    <main className="relative min-h-[100dvh] bg-[var(--background)] text-white">
      {allNotes.length > 0 && <AdSideRails pageKey="notes-index" />}
      {notes.length > 0 && (
        <script
          type="application/ld+json"
          data-testid="notes-structured-data"
          dangerouslySetInnerHTML={{
            __html: serializeJsonLd(
              buildGuideIndexJsonLd(notes, undefined, {
                basePath: NOTES_BASE_PATH,
                title: NOTES_TITLE,
                description: NOTES_DESCRIPTION,
              }),
            ),
          }}
        />
      )}
      <section className="border-b border-white/[0.08] px-4 pb-10 pt-24 sm:px-6 sm:pb-12 sm:pt-28">
        <div className="mx-auto max-w-3xl">
          <h1 className="font-serif text-4xl font-bold tracking-normal text-white sm:text-5xl">
            {NOTES_TITLE}
          </h1>
          <p className="mt-5 text-base font-medium leading-8 text-gray-300">{NOTES_DESCRIPTION}</p>
        </div>
      </section>

      <section className="px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-3xl">
          {allNotes.length > 0 && (
            <form action={NOTES_BASE_PATH} method="get" role="search" className="mb-6 flex gap-2">
              <input
                type="search"
                name="q"
                defaultValue={query}
                placeholder="제목·내용으로 찾기 (예: 반도체, RSI)"
                aria-label="퀀트 연구노트 검색"
                className="min-w-0 flex-1 rounded-xl border border-white/[0.12] bg-white/[0.03] px-4 py-2 text-sm font-bold text-white outline-none placeholder:text-[var(--text-placeholder)] focus-visible:border-[var(--chat-accent)]"
              />
              <button
                type="submit"
                className="shrink-0 rounded-xl bg-[var(--chat-accent)] px-4 py-2 text-sm font-bold text-[var(--chat-accent-ink)] transition-colors duration-200 hover:brightness-110 active:translate-y-[1px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50"
              >
                검색
              </button>
            </form>
          )}
          {query && (
            <p className="mb-4 text-sm font-bold text-gray-400">
              ‘{query}’ 검색 결과 {total}편 ·{" "}
              <Link href={NOTES_BASE_PATH} className="text-gray-200 underline underline-offset-4 hover:text-white">
                전체 보기
              </Link>
            </p>
          )}
          {allNotes.length === 0 ? (
            <p className="border-y border-white/[0.08] py-10 text-center text-sm font-bold text-gray-400">
              퀀트 연구노트를 준비하고 있습니다.
            </p>
          ) : notes.length === 0 ? (
            <p className="border-y border-white/[0.08] py-10 text-center text-sm font-bold text-gray-400">
              검색어가 들어간 노트가 없습니다.
            </p>
          ) : (
            <ul className="divide-y divide-white/[0.08] border-y border-white/[0.08]">
              {notes.map((note) => (
                <li key={note.slug}>
                  <Link
                    href={`${NOTES_BASE_PATH}/${note.slug}`}
                    className="block py-6 transition-colors duration-150 hover:bg-white/[0.02]"
                  >
                    <h2 className="text-xl font-black tracking-normal text-white">{note.title}</h2>
                    <p className="mt-1 text-xs font-bold text-[var(--text-label)]">
                      <time dateTime={note.published}>{note.published.replace(/-/g, ".")}</time>
                    </p>
                    <p className="mt-2 text-sm font-medium leading-7 text-gray-400">{note.description}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {totalPages > 1 && <NotesPagination page={page} totalPages={totalPages} query={query} />}
          {notes.length > 0 && <AdSlot key="notes-index-end" slot={AD_SLOTS.articleEnd} className="mt-10" />}
          <p className="mt-10 text-xs font-bold leading-relaxed text-[var(--text-label)]">{NOTES_DISCLAIMER}</p>
        </div>
      </section>
    </main>
  );
}

/** 쪽 번호 — 처음·끝 쪽과 지금 쪽 앞뒤 두 쪽을 보이고 사이는 말줄임으로 접는다. */
function pageWindow(page: number, totalPages: number): Array<number | "gap"> {
  const pages = Array.from({ length: totalPages }, (_, index) => index + 1).filter(
    (n) => n === 1 || n === totalPages || Math.abs(n - page) <= 2,
  );
  return pages.flatMap((n, index) => (index > 0 && n - pages[index - 1] > 1 ? ["gap" as const, n] : [n]));
}

function NotesPagination({ page, totalPages, query }: { page: number; totalPages: number; query: string }) {
  const item = "inline-flex min-w-9 items-center justify-center rounded-xl px-3 py-2 text-sm font-bold transition-colors duration-150";
  const idle = `${item} text-gray-400 hover:bg-white/[0.04] hover:text-white`;
  return (
    <nav aria-label="퀀트 연구노트 쪽" className="mt-8 flex flex-wrap items-center justify-center gap-1">
      {page > 1 && (
        <Link href={notesListHref(page - 1, query)} rel="prev" className={idle}>
          이전
        </Link>
      )}
      {pageWindow(page, totalPages).map((n, index) =>
        n === "gap" ? (
          <span key={`gap-${index}`} aria-hidden="true" className="px-1 text-sm font-bold text-gray-600">
            …
          </span>
        ) : n === page ? (
          <span key={n} aria-current="page" className={`${item} bg-white/[0.08] text-white`}>
            {n}
          </span>
        ) : (
          <Link key={n} href={notesListHref(n, query)} className={idle}>
            {n}
          </Link>
        ),
      )}
      {page < totalPages && (
        <Link href={notesListHref(page + 1, query)} rel="next" className={idle}>
          다음
        </Link>
      )}
    </nav>
  );
}
