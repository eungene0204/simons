/**
 * 백엔드 경로 가두기 소스 검사(2026-10-11 경로 이탈 사고의 재발 방지).
 *
 * 백엔드는 외부에 노출되지 않는다는 전제로 인증 없이 동작한다. 그런데 Next 라우트가 디코드된
 * 라우트 파라미터('../../admin?')를 백엔드 URL 경로에 그대로 끼워, 비로그인 요청이 백엔드의
 * 아무 GET 경로에 닿았다. 백엔드 URL 경로 부분에 들어가는 `${...}`는 backendPathSegment로
 * 가둔 값(이름이 *Segment이거나 호출 그 자체)만 허용한다.
 */
import { readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";
import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..");
// 경로를 바꿀 수 없는 것만 허용한다 —
//  · 리서치 프록시 pathStr: 여러 조각을 받으므로 최종 URL이 /research/ 아래인지 접두 검사로 가둔다.
//  · '?'로 시작하는 쿼리 문자열 변수: 경로 뒤에 붙어 경로를 바꾸지 못한다.
const ALLOWED = new Set([
  "app/api/research/proxy/[...path]/route.ts:pathStr",
  "app/api/research/proxy/[...path]/route.ts:req.nextUrl.search",
  "app/api/news/impact/[symbol]/route.ts:query",
]);
const BASE_VAR = /^\s*(BACKEND\w*|process\.env\.BACKEND_URL[^}]*|baseUrl|base)\s*$/;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (name === "node_modules" || name.startsWith(".")) return [];
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(name) && !/\.test\./.test(name) ? [full] : [];
  });
}

function unconfinedInterpolations(): string[] {
  const offenders: string[] = [];
  for (const file of [...sourceFiles(join(ROOT, "app")), ...sourceFiles(join(ROOT, "lib"))]) {
    const source = readFileSync(file, "utf8");
    if (!/BACKEND|fetchBackend/.test(source)) continue;
    const rel = file.slice(ROOT.length + 1);
    for (const match of source.matchAll(/`([^`]*)`/g)) {
      const text = match[1];
      const before = source.slice(Math.max(0, match.index! - 40), match.index!);
      const backendUrl = /^\$\{\s*(BACKEND\w*|process\.env\.BACKEND_URL[^}]*)\s*\}\//.test(text);
      const backendPath = text.startsWith("/") && /fetchBackend\(\s*$/.test(before);
      if (!backendUrl && !backendPath) continue;
      const pathPart = text.split("?")[0];
      for (const [, expr] of pathPart.matchAll(/\$\{([^}]*)\}/g)) {
        if (BASE_VAR.test(expr)) continue;
        if (/^\s*\w*Segment\s*$/.test(expr) || /^\s*backendPathSegment\(/.test(expr)) continue;
        if (ALLOWED.has(`${rel}:${expr.trim()}`)) continue;
        offenders.push(`${rel}: \${${expr}}`);
      }
    }
  }
  return offenders;
}

describe("backend URL path confinement", () => {
  it("every dynamic value in a backend URL path goes through backendPathSegment", () => {
    expect(unconfinedInterpolations()).toEqual([]);
  });
});
