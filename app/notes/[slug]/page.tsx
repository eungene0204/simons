import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { GuideArticlePage } from "@/components/guide/GuideArticlePage";
import { NOTES, NOTES_COLLECTION, getNote, notePath } from "@/lib/notes/notes";
import { buildOpenGraph } from "@/lib/seo/site";

type NoteRouteProps = { params: { slug: string } };

// 목록에 없는 slug는 렌더하지 않고 404 — 빌드 시점에 글 전체를 정적 생성한다.
export const dynamicParams = false;

export function generateStaticParams() {
  return NOTES.map((note) => ({ slug: note.slug }));
}

export function generateMetadata({ params }: NoteRouteProps): Metadata {
  const note = getNote(params.slug);
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

export default function NoteRoute({ params }: NoteRouteProps) {
  const note = getNote(params.slug);
  if (!note) notFound();
  return <GuideArticlePage article={note} collection={NOTES_COLLECTION} />;
}
