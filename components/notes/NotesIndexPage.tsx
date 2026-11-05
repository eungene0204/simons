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
} from "@/lib/notes/notes";
import { buildGuideIndexJsonLd } from "@/lib/guide/jsonLd";
import { serializeJsonLd } from "@/lib/seo/site";

// 연구노트 목록 — 한국어 전용 공개 페이지(서버 컴포넌트). 글이 아직 없으면 준비 중 안내를 보인다.
// 광고는 양옆과 목록 아래에만 두고(글 링크 사이에 끼우지 않는다), 글이 없는 빈 페이지에는 싣지 않는다.
export function NotesIndexPage({ notes }: { notes: GuideArticle[] }) {
  return (
    <main className="relative min-h-[100dvh] bg-[var(--background)] text-white">
      {notes.length > 0 && <AdSideRails pageKey="notes-index" />}
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
          {notes.length > 0 && <AdSlot key="notes-index-end" slot={AD_SLOTS.articleEnd} className="mt-10" />}
          <p className="mt-10 text-xs font-bold leading-relaxed text-[var(--text-label)]">{NOTES_DISCLAIMER}</p>
        </div>
      </section>
    </main>
  );
}
