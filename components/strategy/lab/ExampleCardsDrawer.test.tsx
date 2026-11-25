import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EXAMPLES } from "@/components/strategy/strategyExamples";
import { dailyExampleIndex } from "./dailyExample";
import ExampleCardsDrawer from "./ExampleCardsDrawer";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("ExampleCardsDrawer", () => {
  it("전체 분류에서는 예시 20장만 그리고 나머지는 전체 보기 링크로 잇는다", () => {
    render(<ExampleCardsDrawer onPick={vi.fn()} />);

    expect(screen.getAllByTestId("lab-example-card")).toHaveLength(20);
    expect(screen.getByRole("link", { name: "전체 보기" })).toHaveAttribute("href", "/analytics/templates");
  });

  it("분류 탭을 고르면 그 분류의 카드만 남는다", () => {
    render(<ExampleCardsDrawer onPick={vi.fn()} />);

    fireEvent.click(screen.getByRole("tab", { name: "기술분석" }));

    const cards = screen.getAllByTestId("lab-example-card");
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) expect(within(card).getByText("기술분석")).toBeInTheDocument();
  });

  it("카드를 누르면 예시 문장을 onPick으로 넘긴다(전송은 호출한 쪽 몫이다)", () => {
    const onPick = vi.fn();
    render(<ExampleCardsDrawer onPick={onPick} />);

    fireEvent.click(screen.getAllByTestId("lab-example-card")[0]);

    expect(onPick).toHaveBeenCalledTimes(1);
    expect(typeof onPick.mock.calls[0][0]).toBe("string");
    expect(onPick.mock.calls[0][0].length).toBeGreaterThan(0);
  });

  it("예시 목록 끝에 이용 안내 푸터를 두지 않고 추천 문구를 쓰지 않는다", () => {
    render(<ExampleCardsDrawer onPick={vi.fn()} />);

    expect(screen.queryByRole("contentinfo", { name: "전략연구소 이용 안내" })).toBeNull();
    expect(screen.getByText("전략 예시")).toBeInTheDocument();
    expect(screen.queryByText(/추천 전략/)).toBeNull();
  });

  describe("오늘 둘러볼 예시", () => {
    afterEach(() => vi.useRealTimers());

    function renderOn(date: Date) {
      vi.useFakeTimers({ toFake: ["Date"] });
      vi.setSystemTime(date);
      return render(<ExampleCardsDrawer onPick={vi.fn()} />);
    }

    it("날짜로 고른 예시를 맨 위에 두고 말풍선과 강조 테두리를 붙인다", () => {
      renderOn(new Date(2026, 10, 25, 12));
      const expected = EXAMPLES[dailyExampleIndex(EXAMPLES.length, "2026-11-25")];

      const cards = screen.getAllByTestId("lab-example-card");
      expect(cards).toHaveLength(20);
      expect(cards[0]).toHaveAttribute("data-daily", "true");
      expect(cards[0]).toHaveClass("lab-example-featured");
      expect(within(cards[0]).getByText(expected.title)).toBeInTheDocument();
      expect(screen.getByTestId("lab-example-daily-bubble")).toHaveTextContent("오늘 둘러볼 예시 전략");
      // 맨 위로 옮길 뿐 목록에 두 번 나오지 않는다
      expect(screen.getAllByText(expected.title)).toHaveLength(1);
      expect(cards.filter((c) => c.getAttribute("data-daily") === "true")).toHaveLength(1);
    });

    it("오늘의 예시가 속한 분류 탭에서도 맨 위에 오고, 다른 분류에서는 나오지 않는다", () => {
      renderOn(new Date(2026, 10, 25, 12));
      const expected = EXAMPLES[dailyExampleIndex(EXAMPLES.length, "2026-11-25")];

      fireEvent.click(screen.getByRole("tab", { name: expected.category }));
      expect(screen.getAllByTestId("lab-example-card")[0]).toHaveAttribute("data-daily", "true");

      const other = EXAMPLES.find((e) => e.category !== expected.category)!;
      fireEvent.click(screen.getByRole("tab", { name: other.category }));
      expect(screen.queryByTestId("lab-example-daily-bubble")).toBeNull();
    });

    it("말풍선은 추천 문구를 쓰지 않는다(성과로 고르지 않는 둘러보기다)", () => {
      renderOn(new Date(2026, 10, 25, 12));
      expect(screen.queryByText(/추천/)).toBeNull();
    });
  });
});
