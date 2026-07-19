import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RunProgressModal from "./RunProgressModal";

describe("RunProgressModal responsive layout", () => {
  it("keeps running progress and detail inside the mobile viewport", () => {
    render(
      <RunProgressModal
        open
        title="워크포워드 분석"
        isRunning
        progressRatio={0.42}
        progressLabel="42/100회 완료"
        detail={<span>very-long-detail-value-without-natural-breaks</span>}
        onCancel={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByRole("dialog")).toHaveClass("p-2", "lg:px-4", "lg:py-0");
    expect(screen.getByTestId("run-progress-modal-panel")).toHaveClass(
      "max-h-[calc(100dvh-1rem)]",
      "overflow-y-auto",
      "p-4",
      "lg:max-h-none",
      "lg:overflow-visible",
      "lg:p-6"
    );
    expect(screen.getByRole("progressbar", { name: "워크포워드 분석" })).toHaveAttribute(
      "aria-valuenow",
      "42"
    );
    expect(screen.getByText("very-long-detail-value-without-natural-breaks").parentElement).toHaveClass(
      "break-words"
    );
    expect(screen.getByRole("button", { name: "취소" })).toBeInTheDocument();
  });

  it("wraps long errors and keeps the close action available", () => {
    render(
      <RunProgressModal
        open
        title="몬테카를로 시뮬레이션"
        isRunning={false}
        error="very-long-error-value-without-natural-breaks"
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText("very-long-error-value-without-natural-breaks")).toHaveClass("break-words");
    expect(screen.getByRole("button", { name: "닫기" })).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});
