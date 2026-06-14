import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AutoTradingStrategyMissingModal from "@/components/virtual-account/AutoTradingStrategyMissingModal";

describe("AutoTradingStrategyMissingModal", () => {
  it("shows the empty strategy guidance and both actions", () => {
    const onClose = vi.fn();
    const onCreateStrategy = vi.fn();

    render(
      <AutoTradingStrategyMissingModal
        isOpen={true}
        onClose={onClose}
        onCreateStrategy={onCreateStrategy}
      />
    );

    expect(screen.queryByRole("button", { name: "모달 닫기" })).not.toBeInTheDocument();
    expect(screen.getByText("자동매매 설정").parentElement?.parentElement).toHaveClass(
      "text-center"
    );
    expect(
      screen.getByText("아직 저장된 전략이 없습니다. 전략을 만들어 보세요")
    ).toBeInTheDocument();
    expect(
      screen.getByText("아직 저장된 전략이 없습니다. 전략을 만들어 보세요").parentElement
    ).toHaveClass("text-center");
    expect(screen.getByRole("button", { name: "취소" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "전략 만들기" })).toHaveClass(
      "bg-[var(--main-blue)]",
      "text-white"
    );
  });

  it("triggers each action button", () => {
    const onClose = vi.fn();
    const onCreateStrategy = vi.fn();

    render(
      <AutoTradingStrategyMissingModal
        isOpen={true}
        onClose={onClose}
        onCreateStrategy={onCreateStrategy}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    fireEvent.click(screen.getByRole("button", { name: "전략 만들기" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onCreateStrategy).toHaveBeenCalledTimes(1);
  });

  it("shows a disabled pending state while navigating", () => {
    render(
      <AutoTradingStrategyMissingModal
        isOpen={true}
        isCreatingStrategy={true}
        onClose={vi.fn()}
        onCreateStrategy={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "이동 중..." })).toBeDisabled();
  });

  it("can render a strategy creation title", () => {
    render(
      <AutoTradingStrategyMissingModal
        isOpen={true}
        title="전략 만들기"
        description="계좌에 연결하려면 저장된 전략이 필요합니다."
        onClose={vi.fn()}
        onCreateStrategy={vi.fn()}
      />
    );

    expect(screen.getByRole("heading", { name: "전략 만들기" })).toBeInTheDocument();
    expect(
      screen.getByText("계좌에 연결하려면 저장된 전략이 필요합니다.")
    ).toBeInTheDocument();
  });
});
