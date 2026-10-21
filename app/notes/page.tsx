import type { Metadata } from "next";
import { NotesIndexPage } from "@/components/notes/NotesIndexPage";
import { NOTES_BASE_PATH, NOTES_DESCRIPTION, NOTES_TITLE } from "@/lib/notes/notes";
import { listNotes } from "@/lib/notes/notesStore";
import { buildOpenGraph } from "@/lib/seo/site";

// 노트는 DB에서 읽는다 — 빌드 시점에 DB를 건드리지 않도록 요청 시 렌더(목록은 notesStore가 캐시).
export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const notes = await listNotes();
  return {
    title: NOTES_TITLE,
    description: NOTES_DESCRIPTION,
    openGraph: buildOpenGraph("ko", {
      title: NOTES_TITLE,
      description: NOTES_DESCRIPTION,
      url: NOTES_BASE_PATH,
    }),
    alternates: { canonical: NOTES_BASE_PATH },
    // 글이 생기기 전의 빈 목록은 색인하지 않는다.
    ...(notes.length === 0 ? { robots: { index: false, follow: true } } : {}),
  };
}

export default async function NotesPage() {
  return <NotesIndexPage notes={await listNotes()} />;
}
