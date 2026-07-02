// @ts-nocheck
import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import WalkForwardModal from "./WalkForwardModal";

function buildDates(length: number) {
  return Array.from({ length }, (_, index) => {
    const date = new Date(Date.UTC(2024, 0, 1 + index));
    return date.toISOString().slice(0, 10);
  });
}

describe("WalkForwardModal", () => {
  it("백테스트 기간 슬라이더를 기존 요청 설정으로 변환한다", async () => {
    const onRun = vi.fn().mockResolvedValue({
      status: "ok",
      n_splits: 5,
      anchor: false,
      target_metric: "cagr",
      windows: [],
      aggregate: {},
      combined_equity: [],
      combined_dates: [],
      walk_forward_efficiency: 0,
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
          optimizationTargets={[
            { id: "summary-0", label: "PBR" },
            { id: "summary-1", label: "손절라인" },
            { id: "summary-2", label: "익절라인" },
          ]}
        />
      );
    });

    act(() => {
      fireEvent.change(screen.getByLabelText("학습기간"), { target: { value: "84" } });
      fireEvent.change(screen.getByLabelText("검증기간"), { target: { value: "28" } });
    });

    expect(screen.queryByText("예상 구간 수")).not.toBeInTheDocument();
    expect(screen.queryByText("현재 설정")).not.toBeInTheDocument();
    expect(screen.queryByText("최적화 목표 지표")).not.toBeInTheDocument();
    expect(screen.queryByText("첫 구간 미리보기")).not.toBeInTheDocument();
    expect(screen.getByTestId("walk-forward-panel")).not.toHaveClass("h-full", "flex");
    expect(screen.getAllByText("2024.01.01 - 2024.03.24").length).toBeGreaterThan(0);
    expect(screen.getByText("최적화 대상 파라미터")).toBeInTheDocument();
    expect(
      screen.getByText("최적화 대상 파라미터").compareDocumentPosition(screen.getAllByText("Optuna 시도 횟수")[0]) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /PBR/ })).toHaveClass("rounded-md");
    expect(screen.getByRole("button", { name: /PBR/ })).toHaveTextContent("0.1");
    expect(screen.getByRole("button", { name: /PBR/ })).not.toHaveTextContent(/step/i);
    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /손절라인/ })).toHaveTextContent("1%p");
    expect(screen.getByRole("button", { name: /손절라인/ })).not.toHaveTextContent(/step/i);
    expect(screen.getByRole("button", { name: /익절라인/ })).toHaveTextContent("5%p");
    expect(screen.getByRole("button", { name: /익절라인/ })).not.toHaveTextContent(/step/i);
    expect(screen.queryByText("CAGR")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Optuna 시도 횟수 도움말")).toBeInTheDocument();
    expect(screen.getByText(/파라미터 조합을 몇 번 탐색할지/)).toBeInTheDocument();
    expect(screen.getByLabelText("IS 창 방식 도움말")).toBeInTheDocument();
    expect(screen.getByText(/IS\(In-Sample\)는 파라미터를 맞추는 학습 구간/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "30회" })).toHaveClass("rounded-md");
    expect(screen.getByRole("button", { name: "롤링" })).toHaveClass("rounded-md");
    const timeline = screen.getByTestId("walk-forward-period-timeline");
    expect(within(timeline).getAllByText("학습기간").length).toBeGreaterThan(0);
    expect(within(timeline).getAllByText("검증기간").length).toBeGreaterThan(0);
    expect(screen.getByTestId("walk-forward-timeline-train")).toHaveStyle({ width: "35%" });
    expect(screen.getByTestId("walk-forward-timeline-train")).toHaveClass("text-black");
    expect(screen.getByTestId("walk-forward-timeline-validation")).toHaveClass("text-black");
    expect(screen.getByTestId("walk-forward-timeline-validation")).toHaveStyle({
      width: "11.666666666666666%",
    });
    expect(screen.queryByTestId("walk-forward-timeline-train-dates")).not.toBeInTheDocument();
    expect(screen.queryByTestId("walk-forward-timeline-validation-dates")).not.toBeInTheDocument();
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).toHaveTextContent(
      "2024.01.01 - 2024.03.24"
    );
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).not.toHaveTextContent("학습기간");
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).toHaveClass("text-gray-500");
    expect(screen.getByTestId("walk-forward-timeline-axis-train-dates")).toHaveStyle({
      left: "17.364016736401673%",
    });
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveTextContent(
      "2024.03.25 - 2024.04.21"
    );
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).not.toHaveTextContent("검증기간");
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveClass("text-gray-500");
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveStyle({
      left: "40.79497907949791%",
    });
    expect(screen.queryByTestId("walk-forward-timeline-axis-train-range")).not.toBeInTheDocument();
    expect(screen.queryByTestId("walk-forward-timeline-axis-validation-range")).not.toBeInTheDocument();
    expect(screen.getByTestId("walk-forward-timeline-axis-validation-dates")).toHaveClass("top-0");
    expect(within(timeline).queryByText("2024.08.27")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /PBR/ }));
    const pbrStepDialog = screen.getByRole("dialog", { name: "PBR step 설정" });
    expect(pbrStepDialog).toBeInTheDocument();
    expect(pbrStepDialog.firstElementChild).toHaveClass("rounded-xl");
    expect(within(pbrStepDialog).getByRole("button", { name: "기본값" })).toHaveClass("rounded-md");
    expect(within(pbrStepDialog).getByRole("button", { name: "닫기" })).toHaveClass("rounded-md");
    expect(within(pbrStepDialog).getByRole("button", { name: "저장" })).toHaveClass("rounded-md");
    expect(screen.getByLabelText("PBR step 값")).toHaveAttribute("type", "range");
    expect(screen.getByLabelText("PBR step 값")).toHaveAttribute("min", "0.05");
    expect(screen.getByLabelText("PBR step 값")).toHaveAttribute("max", "1");
    expect(screen.getByLabelText("PBR step 값")).toHaveAttribute("step", "0.05");
    expect(within(pbrStepDialog).getByText("0.1")).toBeInTheDocument();
    expect(within(pbrStepDialog).queryByText(/Optuna/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("PBR step 값"), { target: { value: "0.2" } });
    expect(within(pbrStepDialog).getByText("0.2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(screen.queryByRole("dialog", { name: "PBR step 설정" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /PBR/ })).toHaveTextContent("0.2");
    expect(screen.getByRole("button", { name: /PBR/ })).not.toHaveTextContent(/step/i);
    await user.click(screen.getByRole("button", { name: /손절라인/ }));
    const stopLossStepDialog = screen.getByRole("dialog", { name: "손절라인 step 설정" });
    expect(screen.getByLabelText("손절라인 step 값")).toHaveAttribute("type", "range");
    expect(screen.getByLabelText("손절라인 step 값")).toHaveAttribute("max", "20");
    await user.click(within(stopLossStepDialog).getByRole("button", { name: "닫기" }));
    await user.click(screen.getByRole("button", { name: /익절라인/ }));
    const takeProfitStepDialog = screen.getByRole("dialog", { name: "익절라인 step 설정" });
    expect(screen.getByLabelText("익절라인 step 값")).toHaveAttribute("type", "range");
    expect(screen.getByLabelText("익절라인 step 값")).toHaveAttribute("max", "50");
    await user.click(within(takeProfitStepDialog).getByRole("button", { name: "닫기" }));

    await user.click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith({
        n_splits: 5,
        train_pct: 0.75,
        anchor: false,
        target_metric: "cagr",
        n_trials: 30,
        parameter_steps: {
          PBR: 0.2,
          손절라인: 1,
          익절라인: 5,
        },
      });
    });
  });

  it("확장 모드에서는 전체 백테스트 기간 대비 학습 비율을 사용한다", async () => {
    const onRun = vi.fn().mockResolvedValue({
      status: "ok",
      n_splits: 3,
      anchor: true,
      target_metric: "cagr",
      windows: [],
      aggregate: {},
      combined_equity: [],
      combined_dates: [],
      walk_forward_efficiency: 0,
    });

    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={onRun}
          backtestDates={buildDates(240)}
        />
      );
    });

    act(() => {
      fireEvent.change(screen.getByLabelText("학습기간"), { target: { value: "120" } });
      fireEvent.change(screen.getByLabelText("검증기간"), { target: { value: "40" } });
    });
    await userEvent.setup().click(screen.getByRole("button", { name: "확장" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith({
        n_splits: 3,
        train_pct: 0.5,
        anchor: true,
        target_metric: "cagr",
        n_trials: 30,
      });
    });
  });
});
