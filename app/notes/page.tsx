import type { Metadata } from "next";
import { NotesIndexPage } from "@/components/notes/NotesIndexPage";
import { NOTES, NOTES_BASE_PATH, NOTES_DESCRIPTION, NOTES_TITLE } from "@/lib/notes/notes";
import { buildOpenGraph } from "@/lib/seo/site";

export function generateMetadata(): Metadata {
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
    ...(NOTES.length === 0 ? { robots: { index: false, follow: true } } : {}),
  };
}

export default function NotesPage() {
  return <NotesIndexPage />;
}
