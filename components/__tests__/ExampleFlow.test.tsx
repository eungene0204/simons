import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ExampleFlow } from "@/components/landing/ExampleFlow";
import { EXAMPLES } from "@/components/strategy/strategyExamples";

// 2026-11-04 — 끊김 없는 흐름용 복제 목록이 서버 HTML·RSC 페이로드에 카드를 두 번씩 실어 홈이 675KB였다.
describe("ExampleFlow", () => {
  it("server-renders each example card once", () => {
    const html = renderToString(<ExampleFlow />);
    expect(html.match(/data-example-card/g)).toHaveLength(EXAMPLES.length);
  });

  it("fills the decorative copy in the browser, hidden from reading and tab order", () => {
    render(<ExampleFlow />);
    const copy = screen.getByTestId("example-flow-copy");
    const links = copy.querySelectorAll("a");
    expect(links).toHaveLength(EXAMPLES.length);
    for (const link of links) {
      expect(link.tabIndex).toBe(-1);
      expect(link.getAttribute("aria-hidden")).toBe("true");
    }
    const readable = Array.from(document.querySelectorAll("a[data-example-card]")).filter((link) => !copy.contains(link));
    expect(readable).toHaveLength(EXAMPLES.length);
  });
});
