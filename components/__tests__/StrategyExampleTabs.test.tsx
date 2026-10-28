import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EXAMPLES, StrategyTemplatePreviewModal } from "@/components/strategy/StrategyExampleTabs";

const example = EXAMPLES.find((e) => e.title === "이평선 골든크로스 따라가기")!;

describe("StrategyTemplatePreviewModal", () => {
  it("안내가 포함된 편집 모달을 보여주고 시작 시 편집된 프롬프트를 보낸다", async () => {
    const onGenerateStrategy = vi.fn();
    const user = userEvent.setup();
    const editedPrompt = "KOSPI 대형주 중 PBR 1 이하만 골라서 5종목으로 전략을 만들어줘.";

    render(<StrategyTemplatePreviewModal example={example} onCancel={vi.fn()} onGenerateStrategy={onGenerateStrategy} />);

    const dialog = screen.getByRole("dialog", { name: "이평선 골든크로스 따라가기" });
    expect(dialog).toHaveClass(
      "max-h-[calc(100dvh-1.5rem)]",
      "overflow-y-auto",
      "rounded-2xl",
      "p-4",
      "lg:max-h-none",
      "lg:p-5"
    );
    expect(
      within(dialog).queryByText("백테스트 입력 예시에 쓰인 수치는 단순 예시값이며, 투자 추천이나 미래 성과를 의미하지 않습니다.")
    ).not.toBeInTheDocument();
    const promptInput = within(dialog).getByLabelText("백테스트 예시 내용");
    expect((promptInput as HTMLTextAreaElement).value).toContain("골든크로스");
    expect(onGenerateStrategy).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.change(promptInput, { target: { value: editedPrompt } });
    });
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "예시로 시작" }));
    });

    expect(screen.queryByRole("button", { name: "템플릿 사용" })).not.toBeInTheDocument();
    expect(onGenerateStrategy).toHaveBeenCalledWith(editedPrompt);
  });

  it("취소를 누르면 프롬프트를 보내지 않고 onCancel만 부른다", async () => {
    const onGenerateStrategy = vi.fn();
    const onCancel = vi.fn();
    const user = userEvent.setup();

    render(<StrategyTemplatePreviewModal example={example} onCancel={onCancel} onGenerateStrategy={onGenerateStrategy} />);
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "취소" }));
    });

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onGenerateStrategy).not.toHaveBeenCalled();
  });
});
