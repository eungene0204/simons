import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { GuideArticlePage } from "@/components/guide/GuideArticlePage";
import { buildNotesCollection, notePath } from "@/lib/notes/notes";
import { findNote, listNotes } from "@/lib/notes/notesStore";
import { buildOpenGraph } from "@/lib/seo/site";

type NoteRouteProps = { params: { slug: string } };

// 노트는 DB에서 읽는다 — 배포 없이 새 글이 열려야 하므로 요청 시 렌더한다(목록은 notesStore가 캐시).
// DB에 없는 slug는 notFound()로 404를 돌려준다(빈 200 페이지 금지).
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: NoteRouteProps): Promise<Metadata> {
  const note = await findNote(params.slug);
  if (!note) return {};
  const path = notePath(note.slug);
  return {
    title: note.title,
    description: note.description,
    openGraph: {
      ...buildOpenGraph("ko", { title: note.title, description: note.description, url: path }),
      type: "article",
      publishedTime: note.published,
      modifiedTime: note.updated,
    },
    alternates: { canonical: path },
  };
}

export default async function NoteRoute({ params }: NoteRouteProps) {
  const notes = await listNotes();
  const note = notes.find((item) => item.slug === params.slug);
  if (!note) notFound();
  return <GuideArticlePage article={note} collection={buildNotesCollection(notes)} />;
}
