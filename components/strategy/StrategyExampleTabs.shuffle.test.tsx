import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EXAMPLES, StrategyExampleTabs, shuffleExamples } from "./StrategyExampleTabs";

describe("예시 카드 무작위 노출", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("원소를 잃거나 더하지 않고 원본도 건드리지 않는다", () => {
    const originalOrder = EXAMPLES.map((example) => example.title);
    const shuffled = shuffleExamples(EXAMPLES);

    expect(shuffled).toHaveLength(EXAMPLES.length);
    expect(shuffled.map((example) => example.title).sort()).toEqual([...originalOrder].sort());
    expect(EXAMPLES.map((example) => example.title)).toEqual(originalOrder);
  });

  // Math.random()이 1에 수렴하면 Fisher-Yates의 j가 항상 i라 순서가 그대로다.
  // 순서에 의존하는 다른 테스트들이 이 성질로 목록을 고정한다.
  it("난수가 1에 수렴하면 정의 순서를 유지한다", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.999999);

    expect(shuffleExamples(EXAMPLES)).toEqual(EXAMPLES);
  });

  it("전략연구소 첫 화면 카드도 마운트 후 섞인 순서로 보여준다", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const visible = shuffleExamples(EXAMPLES).slice(0, 20);
    const dropped = EXAMPLES.slice(0, 20).find((example) => !visible.includes(example));

    render(<StrategyExampleTabs onSelectExample={vi.fn()} />);

    const cards = screen.getAllByTestId("strategy-example-card");
    expect(cards).toHaveLength(20);
    expect(cards[0]).toHaveTextContent(visible[0].title);
    expect(dropped).toBeDefined();
    expect(screen.queryByText(dropped!.title)).not.toBeInTheDocument();
  });

  it("첫 줄 카드 중 무작위 하나에만 시작 말풍선을 붙인다", () => {
    // 섞기와 말풍선 위치가 같은 난수를 쓴다 — 0.5면 후보 5장 중 index 2
    vi.spyOn(Math, "random").mockReturnValue(0.5);

    render(<StrategyExampleTabs onSelectExample={vi.fn()} />);

    const bubbles = screen.getAllByTestId("strategy-example-start-bubble");
    expect(bubbles).toHaveLength(1);
    expect(bubbles[0]).toHaveTextContent("예시로 시작해 보세요!");
    const cards = screen.getAllByTestId("strategy-example-card");
    expect(cards[2]).toContainElement(bubbles[0]);
    // 말풍선 카드만 테두리가 강조색으로 은은하게 빛난다
    expect(cards[2].className).toContain("shadow-[0_0_20px_var(--chat-accent-soft)]");
    expect(cards.filter((card) => card.className.includes("chat-accent"))).toHaveLength(1);
  });
});
