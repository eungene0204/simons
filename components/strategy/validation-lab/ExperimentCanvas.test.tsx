import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import ExperimentCanvas from "./ExperimentCanvas";
import { buildWalkForwardGraph, type WalkForwardDesign } from "./experimentGraph";

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

const design: WalkForwardDesign = {
  periodLabel: "2020-01-02 ~ 2024-12-30",
  totalBars: 1000,
  trainBars: 300,
  validationBars: 100,
  anchor: false,
  windows: 7,
  methodLabel: "베이지안 30회",
  targetMetricLabel: "CAGR",
  parameters: [{ id: "risk.stop_loss", label: "손절라인", range: "5%~15%", excluded: false }],
  edit: { windowBarsMin: 100, windowBarsMax: 1000, trainRatioMin: 20, trainRatioMax: 80, method: "bayesian", trials: 30, trialOptions: [20, 30, 50] },
  blockedAt: null,
  running: false,
  result: null,
};

describe("ExperimentCanvas 노드 편집", () => {
  it("고칠 값이 있는 단계를 누르면 입력 칸이 열리고, 확정한 값을 key와 함께 알린다", () => {
    const onEdit = vi.fn();
    const onFocusSection = vi.fn();
    render(<ExperimentCanvas graph={buildWalkForwardGraph(design)} onFocusSection={onFocusSection} onEdit={onEdit} />);

    fireEvent.click(screen.getByTestId("experiment-node-wf-split"));
    expect(onFocusSection).not.toHaveBeenCalled();
    const windowInput = screen.getByLabelText("구간 길이");
    fireEvent.change(windowInput, { target: { value: "500" } });
    fireEvent.keyDown(windowInput, { key: "Enter" });
    expect(onEdit).toHaveBeenCalledWith("wf.windowBars", 500);

    fireEvent.change(screen.getByLabelText("방식"), { target: { value: "anchored" } });
    expect(onEdit).toHaveBeenCalledWith("wf.anchor", "anchored");
  });

  it("같은 값으로 확정하면 알리지 않고, Escape로 입력 칸을 닫는다", () => {
    const onEdit = vi.fn();
    render(<ExperimentCanvas graph={buildWalkForwardGraph(design)} onFocusSection={vi.fn()} onEdit={onEdit} />);
    fireEvent.click(screen.getByTestId("experiment-node-wf-split"));
    const ratio = screen.getByLabelText("학습 비중");
    fireEvent.blur(ratio);
    expect(onEdit).not.toHaveBeenCalled();
    fireEvent.keyDown(ratio, { key: "Escape" });
    expect(screen.queryByLabelText("학습 비중")).toBeNull();
  });

  it("파라미터 칸은 조정 칸의 설정 창을 열도록 알린다", () => {
    const onEdit = vi.fn();
    render(<ExperimentCanvas graph={buildWalkForwardGraph(design)} onFocusSection={vi.fn()} onEdit={onEdit} />);
    fireEvent.click(screen.getByTestId("experiment-node-wf-optimize"));
    fireEvent.click(screen.getByLabelText("손절라인"));
    expect(onEdit).toHaveBeenCalledWith("wf.param:risk.stop_loss", null);
  });

  it("고칠 값이 없는 단계를 누르면 예전처럼 그 값을 정하는 조정 칸으로 간다", () => {
    const onFocusSection = vi.fn();
    render(<ExperimentCanvas graph={buildWalkForwardGraph(design)} onFocusSection={onFocusSection} onEdit={vi.fn()} />);
    fireEvent.click(screen.getByTestId("experiment-node-wf-data"));
    expect(onFocusSection).toHaveBeenCalledWith("wf-data");
  });
});
