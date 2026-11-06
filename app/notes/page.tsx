import type { Metadata } from "next";
import { NotesIndexPage } from "@/components/notes/NotesIndexPage";
import { NOTES_DESCRIPTION, NOTES_TITLE, notesListHref } from "@/lib/notes/notes";
import { listNotes } from "@/lib/notes/notesStore";
import { buildOpenGraph } from "@/lib/seo/site";

// 노트는 DB에서 읽는다 — 빌드 시점에 DB를 건드리지 않도록 요청 시 렌더(목록은 notesStore가 캐시).
export const dynamic = "force-dynamic";

type NotesPageProps = { searchParams: { page?: string | string[]; q?: string | string[] } };

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

function listParams(searchParams: NotesPageProps["searchParams"]): { page: number; query: string } {
  return { page: Number(first(searchParams.page)) || 1, query: first(searchParams.q).trim().slice(0, 100) };
}

export async function generateMetadata({ searchParams }: NotesPageProps): Promise<Metadata> {
  const notes = await listNotes();
  const { page, query } = listParams(searchParams);
  // 쪽마다 canonical을 따로 둔다(1쪽=/notes). 검색 결과는 색인하지 않는다.
  const url = notesListHref(page);
  const title = page > 1 ? `${NOTES_TITLE} ${page}쪽` : NOTES_TITLE;
  return {
    title,
    description: NOTES_DESCRIPTION,
    openGraph: buildOpenGraph("ko", { title, description: NOTES_DESCRIPTION, url }),
    alternates: { canonical: url },
    // 글이 생기기 전의 빈 목록과 검색 결과는 색인하지 않는다.
    ...(notes.length === 0 || query ? { robots: { index: false, follow: true } } : {}),
  };
}

export default async function NotesPage({ searchParams }: NotesPageProps) {
  const { page, query } = listParams(searchParams);
  return <NotesIndexPage notes={await listNotes()} page={page} query={query} />;
}
