import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyExampleTabs } from "@/components/strategy/StrategyExampleTabs";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("StrategyExampleTabs", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("전략 템플릿과 내 전략 2개 탭을 보여주고 기본으로 예시 20개를 노출한다", () => {
    const onSelectExample = vi.fn();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    expect(screen.getByRole("button", { name: "전략 템플릿" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내 전략" })).toBeInTheDocument();
    expect(screen.getAllByTestId("strategy-example-card")).toHaveLength(20);

    const categoryBadge = within(screen.getAllByTestId("strategy-example-card")[0]).getByText("가치투자");
    expect(categoryBadge.className).toContain("bg-black");
    expect(categoryBadge.className).toContain("text-emerald-300");
    expect(categoryBadge.className).not.toContain("border");
  });

  it("전체 보기 링크를 제공하고 메인 탭은 예시 20개만 유지한다", () => {
    const onSelectExample = vi.fn();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    expect(screen.getByText("저PBR 대형주 장기보유")).toBeInTheDocument();
    expect(screen.getByText("수익률 상위 종목 주간 교체")).toBeInTheDocument();
    expect(screen.getAllByTestId("strategy-example-card")).toHaveLength(20);

    const allTemplatesLink = screen.getByRole("link", { name: "전체 보기" });
    expect(allTemplatesLink).toHaveAttribute("href", "/analytics/templates");
  });

  it("전체 보기로 이동하기 전까지 모든 예시를 한 번에 노출하지 않는다", () => {
    const onSelectExample = vi.fn();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    expect(screen.getAllByTestId("strategy-example-card")).toHaveLength(20);
    expect(screen.queryByText("밸류 트랩 회피형 분산 보유")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "전체 보기" })).toBeInTheDocument();
  });

  it("선택된 탭 버튼은 main-blue 배경을 사용한다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ strategies: [] }),
    }));

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    const examplesTab = screen.getByRole("button", { name: "전략 템플릿" });
    expect(examplesTab.className).toContain("bg-[var(--main-blue)]");
    expect(examplesTab.className).toContain("text-white");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "내 전략" }));
    });

    const myStrategiesTab = screen.getByRole("button", { name: "내 전략" });
    expect(myStrategiesTab.className).toContain("bg-[var(--main-blue)]");
    expect(myStrategiesTab.className).toContain("text-white");
  });

  it("내 전략 탭을 누르면 저장된 전략 빈 상태를 보여준다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ strategies: [] }),
    }));

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "내 전략" }));
    });

    expect(await screen.findByText("아직 저장된 전략이 없습니다")).toBeInTheDocument();
  });

  it("예시 카드를 누르면 편집 가능한 모달을 보여주고 전략 생성 시 편집된 프롬프트를 보낸다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();
    const editedPrompt = "KOSPI 대형주 중 PBR 1 이하만 골라서 5종목으로 전략을 만들어줘.";

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /이평선 골든크로스 따라가기/i }));
    });

    expect(onSelectExample).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog", { name: "이평선 골든크로스 따라가기" });
    expect(dialog).toBeInTheDocument();
    const promptInput = within(dialog).getByLabelText("전략 내용");
    expect((promptInput as HTMLTextAreaElement).value).toContain("골든크로스");

    await act(async () => {
      fireEvent.change(promptInput, { target: { value: editedPrompt } });
    });

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "전략 생성" }));
    });

    expect(screen.queryByRole("button", { name: "템플릿 사용" })).not.toBeInTheDocument();
    expect(onSelectExample).toHaveBeenCalledWith(editedPrompt);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("예시 카드 미리보기 모달에서 취소를 누르면 프롬프트를 보내지 않는다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /이평선 골든크로스 따라가기/i }));
    });
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "취소" }));
    });

    expect(onSelectExample).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
