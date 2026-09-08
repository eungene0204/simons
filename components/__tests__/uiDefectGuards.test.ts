/**
 * 2026-09-08 UI 결함 수리 회귀 가드 — 소스 스캔.
 *
 * 1. `dark:` 조건부 색 금지: 앱은 다크 전용인데 tailwind에 darkMode 설정이 없어(media 전략)
 *    기기 색상 설정이 라이트인 사용자에게 `bg-white` 폴백이 그대로 나갔다(로그인 입력 글자 실종).
 * 2. 브라우저 기본 confirm/alert 금지(운영 콘솔 제외): 앱 내 ConfirmDialog·인라인 알림으로.
 * 3. 스피너·펄스 유틸리티는 감속 설정을 따른다(`motion-reduce:animate-none`).
 * 4. 상단 검색 힌트의 "/" 키 배지는 문구보다 큰 브레이크포인트에 숨지 않는다
 *    (1440px에서 "를 눌러 검색하세요"만 남던 결함).
 * 5. 포커스 링·감속 블록·하단 도킹 클래스가 globals.css에 남아 있다.
 */
import { describe, expect, it } from "vitest";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "../..");

function listSourceFiles(): string[] {
  const out = execSync("git ls-files app components lib", { cwd: ROOT, encoding: "utf8" });
  const untracked = execSync("git ls-files --others --exclude-standard app components lib", {
    cwd: ROOT,
    encoding: "utf8",
  });
  return [...out.split("\n"), ...untracked.split("\n")]
    .filter((f) => /\.(tsx|ts)$/.test(f))
    .filter((f) => !/\.test\.|__tests__|\.spec\./.test(f));
}

function grepFiles(pattern: RegExp, files: string[]): string[] {
  const hits: string[] = [];
  for (const file of files) {
    let src: string;
    try {
      src = readFileSync(path.join(ROOT, file), "utf8");
    } catch {
      continue;
    }
    src.split("\n").forEach((line, i) => {
      if (pattern.test(line)) hits.push(`${file}:${i + 1}: ${line.trim()}`);
    });
  }
  return hits;
}

describe("UI 결함 회귀 가드(2026-09-08)", () => {
  const files = listSourceFiles();
  const tsxFiles = files.filter((f) => f.endsWith(".tsx"));

  it("dark: 조건부 색을 쓰지 않는다(앱은 다크 전용)", () => {
    const hits = grepFiles(/\bdark:[a-z]/, tsxFiles);
    expect(hits, hits.join("\n")).toEqual([]);
  });

  it("브라우저 기본 confirm/alert를 쓰지 않는다(운영 콘솔 제외)", () => {
    const userFacing = tsxFiles.filter((f) => !f.startsWith("components/admin/"));
    const hits = grepFiles(/window\.confirm\(|(?<![\w.])confirm\((?!\{)|(?<![\w.])alert\(/, userFacing);
    expect(hits, hits.join("\n")).toEqual([]);
  });

  it("animate-spin/pulse/bounce에는 motion-reduce:animate-none을 함께 붙인다", () => {
    const hits = grepFiles(
      /animate-(spin|pulse|bounce)\b(?![^"'`]*motion-reduce:animate-none)/,
      tsxFiles,
    );
    expect(hits, hits.join("\n")).toEqual([]);
  });

  it("상단 검색 힌트: '/' 키 배지가 보이는 구간이 문구가 보이는 구간을 모두 덮는다", () => {
    const src = readFileSync(path.join(ROOT, "components/layout/TopNavigation.tsx"), "utf8");
    const hintIndex = src.indexOf('t("를 눌러 검색하세요")');
    expect(hintIndex).toBeGreaterThan(0);
    const before = src.slice(Math.max(0, hintIndex - 800), hintIndex);
    const kbdMatch = before.match(/className="[^"]*\bhidden\b[^"]*\b(\w+):flex\b[^"]*">\s*\/\s*<\/span>\s*<span className="[^"]*\bhidden\b[^"]*\b(\w+):block\b/);
    expect(kbdMatch, "kbd(/)와 문구 span 구조가 바뀌었다").not.toBeNull();
    const order = ["sm", "md", "lg", "xl", "2xl"];
    const kbdBp = order.indexOf(kbdMatch![1]);
    const textBp = order.indexOf(kbdMatch![2]);
    expect(kbdBp, `kbd=${kbdMatch![1]} text=${kbdMatch![2]}`).toBeLessThanOrEqual(textBp);
  });

  it("배경은 토큰 하나(bg-[var(--background)]) — 근검정 hex 직접 사용 금지", () => {
    const hits = grepFiles(/bg-\[#0[0-9a-f]0[0-9a-f]0[0-9a-f]\]/, tsxFiles);
    expect(hits, hits.join("\n")).toEqual([]);
  });

  it("100vh·min-h-screen·h-screen 대신 100dvh를 쓴다", () => {
    const hits = grepFiles(/\b100vh\b|(?<![\w-])(min-h|max-h)-screen\b|(?<![\w:-])h-screen\b/, tsxFiles);
    expect(hits, hits.join("\n")).toEqual([]);
  });

  it("반경 체계는 하나 — rounded-3xl·임의 rem 반경을 쓰지 않는다", () => {
    const hits = grepFiles(/rounded-3xl|rounded-\[\d+(\.\d+)?rem\]/, tsxFiles);
    expect(hits, hits.join("\n")).toEqual([]);
  });

  it("주요 버튼에 그라디언트·glow를 쓰지 않는다", () => {
    const hits = grepFiles(/bg-gradient-to-r from-(blue|indigo|red)-\d00 (via|to)-|hover:shadow-\[0_0_15px/, tsxFiles);
    expect(hits, hits.join("\n")).toEqual([]);
  });

  it("globals.css: 포커스 링 대비·감속 블록·하단 도킹 클래스", () => {
    const css = readFileSync(path.join(ROOT, "app/globals.css"), "utf8");
    expect(css).toMatch(/\*:focus-visible \{\s*outline: 2px solid #9ca3af;/);
    expect(css).not.toMatch(/outline: 2px solid #4b5563/);
    const reduce = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const cls of [".page-transition", ".animate-marquee", ".animate-fade-in", ".animate-slide-up"]) {
      expect(reduce, `${cls}가 감속 블록에 없다`).toContain(cls);
    }
    expect(css).toMatch(/\.dock-bottom \{\s*bottom: calc\(1rem \+ env\(safe-area-inset-bottom, 0px\) \+ var\(--kb-inset, 0px\)\);/);
  });

  it("대화 화면의 하단 고정 요소는 bottom-4 대신 dock-bottom을 쓴다", () => {
    const src = readFileSync(path.join(ROOT, "app/analytics/new/page.tsx"), "utf8");
    expect(src).not.toMatch(/fixed bottom-4/);
    expect((src.match(/fixed dock-bottom/g) ?? []).length).toBeGreaterThanOrEqual(3);
  });

  it("루트 레이아웃은 viewport-fit=cover와 키보드 인셋 추적기를 갖는다", () => {
    const src = readFileSync(path.join(ROOT, "app/layout.tsx"), "utf8");
    expect(src).toMatch(/viewportFit: "cover"/);
    expect(src).toContain("<VisualViewportInset />");
  });
});
