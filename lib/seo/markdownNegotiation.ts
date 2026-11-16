// AI 에이전트용 마크다운 협상 — 미들웨어(엣지)가 쓰므로 의존성 없는 순수 함수만 둔다.
//
// 에이전트는 `Accept: text/markdown, text/html;q=0.9` 처럼 마크다운을 먼저 달라고 요청한다.
// 브라우저는 text/markdown을 보내지 않으므로 사람 방문자는 종전대로 HTML을 받는다.
// 이 판정은 HTTP 헤더의 형식 파싱이다(사용자 원문 해석 아님).

/** 마크다운 판을 제공하는 경로 — 공개 설명 글(홈·가이드·연구노트·방법론)만. */
const MARKDOWN_PATH = /^\/(?:guide(?:\/[^/]+)?|notes(?:\/[^/]+)?|methodology)?\/?$/;

export const AGENT_MARKDOWN_ROUTE = "/api/agent-markdown";

export function isAgentMarkdownPath(pathname: string): boolean {
  return MARKDOWN_PATH.test(pathname);
}

/** Accept 헤더에서 미디어 타입별 q값을 읽는다(없으면 1, 형식이 깨지면 0). */
function qualityOf(accept: string, mediaType: string): number {
  let best = 0;
  for (const part of accept.split(",")) {
    const [type, ...params] = part.trim().split(";").map((token) => token.trim().toLowerCase());
    if (type !== mediaType) continue;
    const qParam = params.find((param) => param.startsWith("q="));
    const q = qParam ? Number(qParam.slice(2)) : 1;
    if (Number.isFinite(q)) best = Math.max(best, q);
  }
  return best;
}

/** text/markdown을 명시했고 그 우선순위가 text/html 이상일 때만 마크다운을 준다. */
export function prefersMarkdown(accept: string | null | undefined): boolean {
  if (!accept) return false;
  const markdown = qualityOf(accept, "text/markdown");
  return markdown > 0 && markdown >= qualityOf(accept, "text/html");
}
