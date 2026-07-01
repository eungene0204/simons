// @ts-nocheck
import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    expect(screen.getByText("2024.01.01 - 2024.03.24")).toBeInTheDocument();
    expect(screen.getByText("최적화 대상 파라미터")).toBeInTheDocument();
    expect(screen.getByText("PBR")).toBeInTheDocument();
    expect(screen.getByText("손절라인")).toBeInTheDocument();
    expect(screen.queryByText("CAGR")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Optuna 시도 횟수 도움말")).toBeInTheDocument();
    expect(screen.getByText(/파라미터 조합을 몇 번 탐색할지/)).toBeInTheDocument();
    expect(screen.getByLabelText("IS 창 방식 도움말")).toBeInTheDocument();
    expect(screen.getByText(/IS\(In-Sample\)는 파라미터를 맞추는 학습 구간/)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "워크포워드 분석 시작" }));

    await waitFor(() => {
      expect(onRun).toHaveBeenCalledWith({
        n_splits: 5,
        train_pct: 0.75,
        anchor: false,
        target_metric: "cagr",
        n_trials: 30,
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
