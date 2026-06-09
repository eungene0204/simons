export type CoachSegment =
  | { type: "text"; value: string }
  | { type: "link"; value: string; href: string };

// 코치 메시지 안의 마크다운 링크([라벨](https://...)) 토큰. 코치는 '뉴스'를
// 실제 출처 기사 링크로 변환해 내려보낼 수 있다.
const LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

/**
 * 코치 메시지를 텍스트/링크 세그먼트로 분해한다.
 * - `**굵게**` 마커는 평문으로 벗겨낸다(기존 렌더 동작 유지).
 * - `[라벨](url)` 토큰은 클릭 가능한 링크 세그먼트로 분리한다.
 */
export function parseCoachSegments(text: string): CoachSegment[] {
  const stripped = text.replace(/\*\*(.*?)\*\*/g, "$1");
  const segments: CoachSegment[] = [];
  const re = new RegExp(LINK_RE.source, "g");
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(stripped)) !== null) {
    const index = match.index;
    if (index > lastIndex) {
      segments.push({ type: "text", value: stripped.slice(lastIndex, index) });
    }
    segments.push({ type: "link", value: match[1], href: match[2] });
    lastIndex = index + match[0].length;
  }

  if (lastIndex < stripped.length) {
    segments.push({ type: "text", value: stripped.slice(lastIndex) });
  }

  return segments;
}
