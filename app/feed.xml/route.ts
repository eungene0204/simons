import { buildGuideRss } from "@/lib/guide/feeds";
import { GUIDE_ARTICLES } from "@/lib/guide/articles";
import { listNotes } from "@/lib/notes/notesStore";
import { siteUrl } from "@/lib/seo/site";

// 연구노트가 DB에 있으므로 요청 시 생성한다(목록은 notesStore가 캐시).
export const dynamic = "force-dynamic";

export async function GET() {
  return new Response(buildGuideRss(GUIDE_ARTICLES, siteUrl(), await listNotes()), {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}
