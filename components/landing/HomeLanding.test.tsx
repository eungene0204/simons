import { existsSync } from "node:fs";
import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EXAMPLES } from "@/components/strategy/strategyExamples";
import { PLANS } from "@/lib/plans";
import { readStrategyPromptParam } from "@/lib/strategy/strategyOpenLink";
import { HomeLanding, LANDING_START_HREF } from "./HomeLanding";

describe("HomeLanding", () => {
  it("sends both start buttons to the strategy lab's fixed address", () => {
    render(<HomeLanding />);

    // Role queries walk the whole accessibility tree (about 160 example cards); plain selectors keep this fast.
    const buttons = Array.from(document.querySelectorAll<HTMLAnchorElement>("a")).filter((a) => a.textContent?.trim() === "무료로 시작하기");
    expect(buttons).toHaveLength(2);
    buttons.forEach((button) => expect(button).toHaveAttribute("href", LANDING_START_HREF));
    expect(LANDING_START_HREF).toBe("/analytics");
  });

  it("has no standalone video above the steps (the design video is step 01 only)", () => {
    const { container } = render(<HomeLanding />);
    const videos = Array.from(container.querySelectorAll("video"));
    expect(videos).toHaveLength(3);
    videos.forEach((video) => expect(video.closest("#how-it-works")).not.toBeNull());
  });

  it("puts the strategy examples below step 03", () => {
    const { container } = render(<HomeLanding />);
    const lastStep = container.querySelector("#how-it-works ol > li:last-child")!;
    const examples = container.querySelector('[data-testid="example-flow"]')!;
    expect(lastStep.compareDocumentPosition(examples) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector("#how-it-works")!.contains(examples)).toBe(true);
  });

  it("ships the video files the page points to", () => {
    for (const name of [
      "landing-hero.webm", "landing-hero.mp4", "landing-hero-poster.jpg",
      "landing-validate.webm", "landing-validate.mp4", "landing-validate-poster.jpg",
      "landing-paper.webm", "landing-paper.mp4", "landing-paper-poster.jpg",
    ]) {
      expect(existsSync(path.join(process.cwd(), "public/videos", name))).toBe(true);
    }
  });

  it("shows every strategy example as a card that opens the strategy lab with its sentence", () => {
    const { container } = render(<HomeLanding />);
    const cards = Array.from(container.querySelectorAll<HTMLAnchorElement>("[data-example-card]"));
    // The list is drawn twice for a seamless loop; both copies carry the same links.
    expect(cards).toHaveLength(EXAMPLES.length * 2);
    const prompts = new Set(
      cards.map((card) => readStrategyPromptParam(new URL(card.getAttribute("href") ?? "", "https://example.test").searchParams)),
    );
    expect(prompts).toEqual(new Set(EXAMPLES.map((example) => example.prompt)));
  });

  it("names the section 전략 예시들 and drops the old helper line", () => {
    const { container } = render(<HomeLanding />);
    expect(screen.getByText("전략 예시들")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/예시를 누르면 입력창에 채워 둔 채로 열립니다/);
  });

  it("keeps double quotes out of inline <style> text (the server escapes them, which breaks hydration)", () => {
    const { container } = render(<HomeLanding />);
    const styles = Array.from(container.querySelectorAll("style")).map((style) => style.textContent ?? "");
    expect(styles.length).toBeGreaterThan(0);
    styles.forEach((css) => expect(css).not.toContain('"'));
  });

  it("hides the duplicate copy from assistive tech and keyboard focus", () => {
    const { container } = render(<HomeLanding />);
    const copies = container.querySelectorAll('ul[aria-hidden="true"] [data-example-card]');
    expect(copies).toHaveLength(EXAMPLES.length);
    copies.forEach((card) => expect(card.getAttribute("tabindex")).toBe("-1"));
  });

  it("shows plan limits from the plan table, not copies", () => {
    render(<HomeLanding />);
    const plans = screen.getByRole("heading", { name: "요금제" }).closest("section")!;

    expect(within(plans).getByText(`월 백테스트 ${PLANS.PRO.monthlyBacktestLimit.toLocaleString("ko-KR")}회`)).toBeInTheDocument();
    expect(within(plans).getByText(`₩${PLANS.PRO.monthlyPrice.toLocaleString("ko-KR")}`)).toBeInTheDocument();
    expect(within(plans).getByText("무료")).toBeInTheDocument();
  });

  it("links the free board from the footer for visitors who are not signed in", () => {
    render(<HomeLanding />);
    const board = Array.from(document.querySelectorAll<HTMLAnchorElement>("a")).find((a) => a.textContent?.trim() === "자유게시판");
    expect(board).toHaveAttribute("href", "/board");
  });

  it("carries the not-advice disclosure and avoids recommendation wording", () => {
    const { container } = render(<HomeLanding />);
    const text = container.textContent ?? "";

    expect(text).toMatch(/투자 자문·투자 추천을 제공하지 않는/);
    expect(text).toMatch(/미래 수익은 보장되지 않습니다/);
    for (const banned of ["추천 전략", "유망", "최고의 전략", "수익률 보장", "AI 투자 코치", "지금 사야"]) {
      expect(text).not.toContain(banned);
    }
  });
});
