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

const baseStrategy = {
  entry: {
    conditions: [
      { id: "pbr_filter", type: "filter", params: { value: 1 } },
    ],
  },
  risk: {
    stop_loss_pct: 10,
    take_profit_pct: 20,
  },
};

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
          baseStrategy={baseStrategy}
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

    expect(screen.getByText("예상 구간 수")).toBeInTheDocument();
    expect(screen.queryByText("현재 설정")).not.toBeInTheDocument();
    expect(screen.queryByText("최적화 목표 지표")).not.toBeInTheDocument();
    expect(screen.queryByText("첫 구간 미리보기")).not.toBeInTheDocument();
    expect(screen.getByTestId("walk-forward-panel")).not.toHaveClass("h-full", "flex");
    expect(screen.getAllByText("2024.01.01 - 2024.03.24").length).toBeGreaterThan(0);
    expect(screen.getAllByText("최적화 대상 파라미터")[0]).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /베이지안 최적화 유망한 후보를 우선 탐색하며/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /베이지안 최적화 유망한 후보를 우선 탐색하며/ })).toHaveClass("bg-white/[0.03]");
    expect(screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.getAllByText("최적화 대상 파라미터")[0].compareDocumentPosition(screen.getAllByText("베이지안 최적화 시도 횟수")[0]) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "PBR" })).toHaveClass("rounded-md");
    expect(screen.getByRole("button", { name: "PBR" })).toHaveTextContent("PBR");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent("0.25");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent(/step/i);
    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "손절라인" })).not.toHaveTextContent("2.5%p");
    expect(screen.getByRole("button", { name: "손절라인" })).not.toHaveTextContent(/step/i);
    expect(screen.getByRole("button", { name: "익절라인" })).not.toHaveTextContent("5%p");
    expect(screen.getByRole("button", { name: "익절라인" })).not.toHaveTextContent(/step/i);
    expect(screen.queryByText("CAGR")).not.toBeInTheDocument();
    expect(screen.getByLabelText("베이지안 최적화 시도 횟수 도움말")).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "PBR" }));
    const pbrStepDialog = screen.getByRole("dialog", { name: "PBR 값 설정" });
    expect(pbrStepDialog).toBeInTheDocument();
    expect(pbrStepDialog.firstElementChild).toHaveClass("rounded-xl");
    expect(within(pbrStepDialog).getByRole("button", { name: "기본값" })).toHaveClass("rounded-md");
    expect(within(pbrStepDialog).getByRole("button", { name: "닫기" })).toHaveClass("rounded-md");
    expect(within(pbrStepDialog).getByRole("button", { name: "저장" })).toHaveClass("rounded-md");
    expect(screen.getByLabelText("PBR 하한값")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("PBR 하한값")).toHaveValue(0.2);
    expect(screen.getByLabelText("PBR 상한값")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("PBR 상한값")).toHaveValue(5);
    expect(within(pbrStepDialog).getAllByText("예: 0.2, 2.6, 5")).toHaveLength(2);
    expect(screen.getByLabelText("PBR step 값")).not.toHaveAttribute("type", "range");
    expect(within(screen.getByLabelText("PBR step 값")).getAllByRole("button")).toHaveLength(3);
    expect(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.1" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.25" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.5" })).toBeInTheDocument();
    expect(screen.getByLabelText("PBR 하한값")).toHaveDisplayValue("0.2");
    expect(screen.getByLabelText("PBR 상한값")).toHaveDisplayValue("5");
    expect(within(pbrStepDialog).getAllByText("0.25").length).toBeGreaterThanOrEqual(2);
    expect(within(pbrStepDialog).queryByText(/Optuna/)).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("PBR 상한값"));
    expect(screen.getByLabelText("PBR 상한값")).toHaveDisplayValue("");
    await user.type(screen.getByLabelText("PBR 상한값"), "10");
    expect(screen.getByLabelText("PBR 상한값")).toHaveDisplayValue("10");
    fireEvent.change(screen.getByLabelText("PBR 하한값"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("PBR 상한값"), { target: { value: "1" } });
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(screen.getByText("하한값은 상한값보다 클 수 없습니다.")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "PBR 값 설정" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("PBR 하한값"), { target: { value: "0.9" } });
    fireEvent.change(screen.getByLabelText("PBR 상한값"), { target: { value: "1.5" } });
    expect(within(pbrStepDialog).getAllByText("0.25").length).toBeGreaterThanOrEqual(2);
    await user.click(within(screen.getByLabelText("PBR step 값")).getByRole("button", { name: "0.5" }));
    expect(within(pbrStepDialog).getAllByText("0.5").length).toBeGreaterThanOrEqual(2);
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(screen.queryByRole("dialog", { name: "PBR 값 설정" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PBR" })).toHaveTextContent("PBR");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent("0.5");
    expect(screen.getByRole("button", { name: "PBR" })).not.toHaveTextContent(/step/i);
    await user.click(screen.getByRole("button", { name: "손절라인" }));
    const stopLossStepDialog = screen.getByRole("dialog", { name: "손절라인 값 설정" });
    expect(screen.getByLabelText("손절라인 하한값")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("손절라인 상한값")).toHaveAttribute("type", "number");
    expect(within(stopLossStepDialog).getAllByText("%p")).toHaveLength(2);
    expect(within(screen.getByLabelText("손절라인 step 값")).getAllByRole("button")).toHaveLength(3);
    expect(within(screen.getByLabelText("손절라인 step 값")).getByRole("button", { name: "1%p" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("손절라인 step 값")).getByRole("button", { name: "2.5%p" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByLabelText("손절라인 step 값")).getByRole("button", { name: "5%p" })).toBeInTheDocument();
    await user.click(within(stopLossStepDialog).getByRole("button", { name: "닫기" }));
    await user.click(screen.getByRole("button", { name: "익절라인" }));
    const takeProfitStepDialog = screen.getByRole("dialog", { name: "익절라인 값 설정" });
    expect(within(screen.getByLabelText("익절라인 step 값")).getAllByRole("button")).toHaveLength(3);
    expect(within(screen.getByLabelText("익절라인 step 값")).getByRole("button", { name: "2.5%p" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("익절라인 step 값")).getByRole("button", { name: "5%p" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByLabelText("익절라인 step 값")).getByRole("button", { name: "10%p" })).toBeInTheDocument();
    await user.click(within(takeProfitStepDialog).getByRole("button", { name: "닫기" }));

    await user.click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith({
        n_splits: 5,
        train_pct: 0.75,
        anchor: false,
        target_metric: "cagr",
        n_trials: 30,
        method: "bayesian",
        parameter_steps: {
          PBR: 0.5,
          손절라인: 2.5,
          익절라인: 5,
        },
        parameter_ranges: {
          PBR: {
            min: 0.9,
            max: 1.5,
            step: 0.5,
          },
        },
      });
    });
    expect(screen.queryByText(/Optuna/)).not.toBeInTheDocument();
  });

  it("그리드 탐색 선택 시 예상 조합 수를 보여주고 실행 버튼을 활성화한다", async () => {
    await act(async () => {
      render(
        <WalkForwardModal
          open
          onOpenChange={() => {}}
          onRun={vi.fn()}
          backtestDates={buildDates(240)}
          baseStrategy={baseStrategy}
          optimizationTargets={[
            { id: "summary-0", label: "PBR" },
            { id: "summary-1", label: "손절라인" },
          ]}
        />
      );
    });

    await userEvent.setup().click(
      screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })
    );

    expect(screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })).toHaveClass("bg-white/[0.03]");
    expect(screen.queryByText("베이지안 최적화 시도 횟수")).not.toBeInTheDocument();
    expect(screen.getByText("그리드 탐색 예상")).toBeInTheDocument();
    expect(screen.getByText(/조합을 확인할 수 있습니다/)).toBeInTheDocument();
    expect(screen.getByText("실행 가능")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "워크포워드 분석 시작" })).not.toBeDisabled();
  });

  it("그리드 탐색 실행 시 onRun에 method: grid를 전달한다", async () => {
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
          baseStrategy={baseStrategy}
          optimizationTargets={[]}
        />
      );
    });

    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: /그리드 탐색 설정한 범위를 기준으로 전체 조합 수를 먼저 확인합니다\./ })
    );
    await user.click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ method: "grid" }));
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
        method: "bayesian",
      });
    });
  });
});
