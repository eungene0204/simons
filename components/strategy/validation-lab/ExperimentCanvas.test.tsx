import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import ExperimentCanvas from "./ExperimentCanvas";
import { EXPERIMENT_NODE_W, buildWalkForwardGraph, type WalkForwardDesign } from "./experimentGraph";

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

  it("모든 단계 노드에 크기 조절 손잡이가 붙는다", () => {
    render(<ExperimentCanvas graph={buildWalkForwardGraph(design)} onFocusSection={vi.fn()} onEdit={vi.fn()} />);
    for (const testId of ["experiment-node-wf-data", "experiment-node-wf-split", "experiment-node-wf-optimize"]) {
      expect(screen.getByTestId(testId).querySelector(".lab-resize-handle")).not.toBeNull();
    }
  });

  it("크기를 바꾸지 않은 노드는 기본 폭으로 그린다 — 잰 크기(첫 렌더 0)를 노드 폭으로 쓰면 노드가 쪼그라든다", () => {
    render(<ExperimentCanvas graph={buildWalkForwardGraph(design)} onFocusSection={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByTestId("experiment-node-wf-split").style.width).toBe(`${EXPERIMENT_NODE_W}px`);
  });

  // 내용 배율(CSS zoom)은 jsdom이 속성을 버려 여기서 볼 수 없다 — 폭이 사용자 폭을 따르는지만 본다.
  it("사용자가 정한 폭은 노드 폭으로 그린다", () => {
    const graph = buildWalkForwardGraph(design);
    const widened = { ...graph, nodes: graph.nodes.map((n) => (n.id === "wf-split" ? { ...n, width: EXPERIMENT_NODE_W * 1.5 } : n)) };
    render(<ExperimentCanvas graph={widened} onFocusSection={vi.fn()} onEdit={vi.fn()} />);
    const node = screen.getByTestId("experiment-node-wf-split");
    expect(node.style.width).toBe(`${EXPERIMENT_NODE_W * 1.5}px`);
  });

  it("확대·축소를 누르면 자동 맞춤을 멈추고, '화면에 맞춤'으로 돌아간다", () => {
    render(<ExperimentCanvas graph={buildWalkForwardGraph(design)} onFocusSection={vi.fn()} onEdit={vi.fn()} />);
    const fit = screen.getByRole("button", { name: "화면에 맞춤" });
    expect(fit).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "확대" }));
    expect(fit).toBeEnabled();
    fireEvent.click(fit);
    expect(fit).toBeDisabled();
  });
});
