import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { GuideArticlePage } from "@/components/guide/GuideArticlePage";
import { BlogCopyButton } from "@/components/notes/BlogCopyButton";
import { buildBlogExport } from "@/lib/notes/blogExport";
import { buildNotesCollection, notePath } from "@/lib/notes/notes";
import { findNote, listNotes } from "@/lib/notes/notesStore";
import { classicNoteDataset } from "@/lib/notes/classicNotes";
import { mythNoteDataset, mythNoteOpenPrompt, mythNoteSeoTitle } from "@/lib/notes/mythNotes";
import { newsNoteDataset, newsNoteOpenPrompt } from "@/lib/notes/newsNotes";
import { buildOpenGraph } from "@/lib/seo/site";
import { strategyOpenHref } from "@/lib/strategy/strategyOpenLink";

type NoteRouteProps = { params: { slug: string } };

// 노트는 DB에서 읽는다 — 배포 없이 새 글이 열려야 하므로 요청 시 렌더한다(목록은 notesStore가 캐시).
// DB에 없는 slug는 notFound()로 404를 돌려준다(빈 200 페이지 금지).
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: NoteRouteProps): Promise<Metadata> {
  const note = await findNote(params.slug);
  if (!note) return {};
  const path = notePath(note.slug);
  const title = mythNoteSeoTitle(note.slug) ?? note.title;
  return {
    title,
    description: note.description,
    openGraph: {
      ...buildOpenGraph("ko", { title, description: note.description, url: path }),
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
  const prompt = mythNoteOpenPrompt(note.slug) ?? newsNoteOpenPrompt(note.slug);
  return (
    <GuideArticlePage
      article={note}
      collection={buildNotesCollection(notes)}
      dataset={mythNoteDataset(note.slug) ?? classicNoteDataset(note.slug) ?? newsNoteDataset(note.slug)}
      openHref={prompt ? strategyOpenHref(prompt, "notes", note.slug) : undefined}
      // 블로그 붙여 넣기용 복사는 로컬 개발 서버에서만 보인다(운영 화면에는 렌더하지 않는다).
      headerAction={
        process.env.NODE_ENV === "development" ? <BlogCopyButton content={buildBlogExport(note)} /> : undefined
      }
    />
  );
}
