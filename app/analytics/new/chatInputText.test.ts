import { describe, expect, it } from "vitest";
import { readFileSync } from "fs";
import path from "path";

// JSX 속성값과 JSX 텍스트는 JS 문자열과 달리 \uXXXX 이스케이프를 해석하지 않는다.
// 소스에 리터럴 이스케이프가 들어가면 사용자에게 "어떤..." 그대로 노출된다
// (2026-07-24 채팅 입력창 placeholder 회귀).
describe("전략연구소 채팅 입력창 텍스트", () => {
  const source = readFileSync(
    path.join(process.cwd(), "app/analytics/new/page.tsx"),
    "utf-8",
  );

  it("placeholder와 버튼 라벨이 실제 한글로 들어있다", () => {
    expect(source).toContain('const FIRST_INPUT_PLACEHOLDER = "어떤 투자 아이디어를 테스트해볼까요?"');
    expect(source).toContain("대화 종료");
  });

  it("placeholder는 첫 입력(inline) 입력창에서만 노출된다", () => {
    expect(source).toContain(
      'placeholder={variant === "inline" ? FIRST_INPUT_PLACEHOLDER : undefined}',
    );
  });

  it("소스에 한글 리터럴 \\uXXXX 이스케이프가 없다", () => {
    // 한글 음절 범위(U+AC00~U+D7A3)의 리터럴 이스케이프만 검출 — 의도적으로 쓰는
    // " "(NBSP) 같은 비한글 이스케이프는 허용한다.
    const hangulEscape = /\\u(?:A[C-F][0-9A-F]{2}|[BC][0-9A-F]{3}|D[0-7][0-9A-F]{2})/i;
    const offenders = source
      .split("\n")
      .map((line, index) => ({ line: index + 1, text: line }))
      .filter(({ text }) => hangulEscape.test(text));
    expect(offenders).toEqual([]);
  });
});
