import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

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
});
