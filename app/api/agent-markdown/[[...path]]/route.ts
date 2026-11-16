import { agentMarkdownFor } from "@/lib/seo/agentMarkdown";
import { listNotes } from "@/lib/notes/notesStore";
import { siteUrl } from "@/lib/seo/site";

// AI 에이전트용 마크다운 판 — 미들웨어가 `Accept: text/markdown` 요청을 이리로 rewrite 한다
// (middleware.ts, lib/seo/markdownNegotiation.ts). 연구노트가 DB에 있으므로 요청 시 생성한다.
export const dynamic = "force-dynamic";

const NOTES_PATH = /^\/(?:$|notes(?:\/|$))/;

// 원래 경로는 이 라우트 뒤에 그대로 붙어 온다(`/guide/x` → `/api/agent-markdown/guide/x`).
// rewrite 대상의 쿼리는 라우트 핸들러에 전달되지 않아(2026-11-17 실측) 경로에 싣는다.
export async function GET(_request: Request, { params }: { params: { path?: string[] } }) {
  const path = `/${(params.path ?? []).join("/")}`;
  const notes = NOTES_PATH.test(path) ? await listNotes() : [];
  const markdown = agentMarkdownFor(path, siteUrl(), notes);
  if (markdown == null) {
    return new Response("# 404\n\n페이지를 찾을 수 없습니다.\n", {
      status: 404,
      headers: { "Content-Type": "text/markdown; charset=utf-8", Vary: "Accept" },
    });
  }
  return new Response(markdown, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      Vary: "Accept",
      "Cache-Control": "public, max-age=300",
    },
  });
}
