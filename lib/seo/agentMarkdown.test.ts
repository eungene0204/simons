// 2026-11-17 — 사이트 진단이 "에이전트가 요청해도 마크다운 판이 없다"고 지적. `Accept: text/markdown`
// 요청에 공개 설명 글의 마크다운을 주고, 브라우저 요청은 종전대로 HTML을 받는지 고정한다.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";
import { agentMarkdownFor } from "@/lib/seo/agentMarkdown";
import { isAgentMarkdownPath, prefersMarkdown } from "@/lib/seo/markdownNegotiation";
import { GUIDE_ARTICLES, GUIDE_DISCLAIMER } from "@/lib/guide/articles";
import { METHODOLOGY_ARTICLE } from "@/lib/methodology/methodology";
import { SEED_NOTES } from "@/lib/notes/notes";

const BASE = "https://www.nullstock.im";

describe("prefersMarkdown", () => {
  it("에이전트의 마크다운 우선 요청을 알아본다", () => {
    expect(prefersMarkdown("text/markdown")).toBe(true);
    expect(prefersMarkdown("text/markdown, text/html;q=0.9, */*;q=0.8")).toBe(true);
    expect(prefersMarkdown("text/html, text/markdown")).toBe(true);
  });

  it("브라우저·HTML 우선 요청에는 마크다운을 주지 않는다", () => {
    expect(prefersMarkdown(null)).toBe(false);
    expect(prefersMarkdown("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")).toBe(false);
    expect(prefersMarkdown("text/html, text/markdown;q=0.5")).toBe(false);
    expect(prefersMarkdown("text/markdown;q=0")).toBe(false);
  });
});

describe("isAgentMarkdownPath", () => {
  it("공개 설명 글 경로만 대상이다", () => {
    for (const path of ["/", "/guide", "/guide/what-is-backtest", "/notes", "/notes/x", "/methodology"]) {
      expect(isAgentMarkdownPath(path)).toBe(true);
    }
    for (const path of ["/analytics", "/pricing", "/guide/a/b", "/notes-x", "/login"]) {
      expect(isAgentMarkdownPath(path)).toBe(false);
    }
  });
});

describe("middleware 마크다운 협상", () => {
  it("마크다운을 요청한 에이전트는 마크다운 라우트로 rewrite 한다", () => {
    const res = middleware(new NextRequest(`${BASE}/guide/abc`, { headers: { accept: "text/markdown" } }));
    expect(res.headers.get("x-middleware-rewrite")).toBe(`${BASE}/api/agent-markdown/guide/abc`);
  });

  it("홈은 라우트 루트로 rewrite 한다", () => {
    const res = middleware(new NextRequest(`${BASE}/`, { headers: { accept: "text/markdown" } }));
    expect(res.headers.get("x-middleware-rewrite")).toBe(`${BASE}/api/agent-markdown`);
  });

  it("브라우저 요청은 rewrite 하지 않는다", () => {
    const res = middleware(new NextRequest(`${BASE}/`, { headers: { accept: "text/html,*/*;q=0.8" } }));
    expect(res.headers.get("x-middleware-rewrite")).toBeNull();
  });

  it("도구 화면은 마크다운 요청이어도 HTML 그대로다", () => {
    const res = middleware(new NextRequest(`${BASE}/analytics`, { headers: { accept: "text/markdown" } }));
    expect(res.headers.get("x-middleware-rewrite")).toBeNull();
  });
});

describe("agentMarkdownFor", () => {
  it("홈은 llms.txt와 같은 사이트 요약이다", () => {
    const md = agentMarkdownFor("/", BASE, SEED_NOTES)!;
    expect(md.startsWith("# 널스탁")).toBe(true);
    expect(md).toContain("투자 자문·투자 추천 서비스가 아닙니다");
  });

  it("가이드 글은 본문·면책·원문 주소를 싣는다", () => {
    const article = GUIDE_ARTICLES[0];
    const md = agentMarkdownFor(`/guide/${article.slug}/`, BASE, [])!;
    expect(md).toContain(`# ${article.title}`);
    expect(md).toContain(GUIDE_DISCLAIMER);
    expect(md).toContain(`${BASE}/guide/${article.slug}`);
    expect(md).toContain(`## ${article.sections[0].heading}`);
  });

  it("연구노트 표는 마크다운 표로 옮긴다", () => {
    const note = SEED_NOTES.find((item) => item.sections.some((section) => section.table))!;
    const md = agentMarkdownFor(`/notes/${note.slug}`, BASE, SEED_NOTES)!;
    expect(md).toContain(`# ${note.title}`);
    expect(md).toMatch(/\n\| --- \|/);
  });

  it("방법론·목록 페이지도 제공한다", () => {
    expect(agentMarkdownFor("/methodology", BASE, [])).toContain(`# ${METHODOLOGY_ARTICLE.title}`);
    expect(agentMarkdownFor("/guide", BASE, [])).toContain(GUIDE_ARTICLES[0].title);
    expect(agentMarkdownFor("/notes", BASE, SEED_NOTES)).toContain(SEED_NOTES[0].title);
  });

  it("없는 글은 null이다", () => {
    expect(agentMarkdownFor("/guide/no-such-article", BASE, [])).toBeNull();
    expect(agentMarkdownFor("/notes/no-such-note", BASE, SEED_NOTES)).toBeNull();
  });
});

// 2026-11-17 — 서버 컴포넌트였던 예시 흐름이 카드 82장을 HTML 본문과 RSC 페이로드에 두 번 실어
// 홈 HTML 33만 자 중 13만 자를 차지했다(크롤러 응답 시간 지적).
describe("홈 HTML 무게", () => {
  it("예시 흐름은 클라이언트 컴포넌트다(RSC 페이로드에 카드를 다시 싣지 않는다)", () => {
    const source = readFileSync("components/landing/ExampleFlow.tsx", "utf8");
    expect(source.startsWith('"use client";')).toBe(true);
  });
});
