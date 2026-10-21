import Link from "next/link";
import type { GuideArticle } from "@/lib/guide/articles";
import {
  NOTES_BASE_PATH,
  NOTES_DESCRIPTION,
  NOTES_DISCLAIMER,
  NOTES_TITLE,
} from "@/lib/notes/notes";

// 연구노트 목록 — 한국어 전용 공개 페이지(서버 컴포넌트). 글이 아직 없으면 준비 중 안내를 보인다.
export function NotesIndexPage({ notes }: { notes: GuideArticle[] }) {
  return (
    <main className="min-h-[100dvh] bg-[var(--background)] text-white">
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
          {notes.length === 0 ? (
            <p className="border-y border-white/[0.08] py-10 text-center text-sm font-bold text-gray-400">
              연구노트를 준비하고 있습니다.
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
                    <p className="mt-2 text-sm font-medium leading-7 text-gray-400">{note.description}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-10 text-xs font-bold leading-relaxed text-[var(--text-label)]">{NOTES_DISCLAIMER}</p>
        </div>
      </section>
    </main>
  );
}
