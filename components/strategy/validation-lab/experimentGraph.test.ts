import { describe, expect, it } from "vitest";
import { deriveSplitCount } from "@/components/strategy/backtest/walkForwardRunLimits";
import {
  attachContextNodes,
  buildMonteCarloGraph,
  buildWalkForwardGraph,
  buildWindowSchedule,
  EXPERIMENT_GAP_X,
  parseWalkForwardEdit,
  scheduleFromPeriods,
  stackNodes,
  STACK_GAP_Y,
  type ExperimentGraph,
  type ExperimentNode,
  type ScheduleNode,
  type WalkForwardDesign,
} from "./experimentGraph";

const design: WalkForwardDesign = {
  periodLabel: "2020-01-02 ~ 2024-12-30",
  totalBars: 1000,
  trainBars: 300,
  validationBars: 100,
  anchor: false,
  windows: 7,
  methodLabel: "베이지안 30회",
  targetMetricLabel: "CAGR",
  parameters: [
    { id: "filters.pbr", label: "PBR", range: "0.5~1.5 · STEP 0.1", excluded: false },
    { id: "risk.stop_loss", label: "손절라인", range: "5%~15% · STEP 2.5%", excluded: false },
    { id: "hold_days", label: "보유기간", range: "10거래일~20거래일 · STEP 10거래일", excluded: true },
  ],
  blockedAt: null,
  running: false,
  result: null,
};

const step = (graph: ExperimentGraph, id: string) => graph.nodes.find((n) => n.id === id) as ExperimentNode;

describe("buildWindowSchedule", () => {
  it("롤링: 학습 창이 검증 길이만큼 함께 밀리고 창 수는 화면 예상 구간 수와 같다", () => {
    const schedule = buildWindowSchedule(1000, 300, 100, false);
    expect(schedule).toHaveLength(deriveSplitCount(1000, 300, 100));
    expect(schedule[0]).toEqual({ window: 1, isStart: 0, isEnd: 300, oosStart: 300, oosEnd: 400 });
    expect(schedule[1]).toEqual({ window: 2, isStart: 100, isEnd: 400, oosStart: 400, oosEnd: 500 });
    expect(schedule[schedule.length - 1].oosEnd).toBeLessThanOrEqual(1000);
  });

  it("확장: 학습 시작은 첫날에 고정되고 검증 길이를 못 채우는 조각 창은 만들지 않는다", () => {
    const schedule = buildWindowSchedule(1050, 300, 100, true);
    expect(schedule).toHaveLength(7);
    expect(schedule.every((span) => span.isStart === 0)).toBe(true);
    expect(schedule[6]).toEqual({ window: 7, isStart: 0, isEnd: 900, oosStart: 900, oosEnd: 1000 });
  });

  it("학습+검증이 기간보다 길면 창이 없다", () => {
    expect(buildWindowSchedule(300, 250, 100, false)).toEqual([]);
  });
});

describe("buildWalkForwardGraph", () => {
  it("실행 순서대로 다섯 단계를 잇고, 막힌 단계만 blocked로 표시한다", () => {
    const graph = buildWalkForwardGraph({ ...design, blockedAt: "optimize" });
    expect(graph.nodes.map((n) => n.id)).toEqual(["wf-data", "wf-split", "wf-optimize", "wf-test", "wf-result"]);
    expect(graph.edges.map((e) => `${e.source}->${e.target}`)).toEqual([
      "wf-data->wf-split",
      "wf-split->wf-optimize",
      "wf-optimize->wf-test",
      "wf-test->wf-result",
    ]);
    expect(step(graph, "wf-optimize").data.status).toBe("blocked");
    expect(step(graph, "wf-split").data.status).toBe("ready");
  });

  it("결과가 있으면 WFE 값을 싣고, 학습 CAGR ≤ 0이면 해석 불가로 적는다", () => {
    const done = buildWalkForwardGraph({ ...design, result: { wfe: 0.72, wfeTierText: "일부 감소", avgOosCagr: 8.4, windowsDone: 7 } });
    const wfeNode = step(done, "wf-result");
    expect(wfeNode.data.status).toBe("done");
    expect(wfeNode.data.rows).toContainEqual({ label: "WFE", value: "72.0%" });
    const invalid = buildWalkForwardGraph({ ...design, result: { wfe: null, wfeTierText: null, avgOosCagr: null, windowsDone: 7 } });
    expect(step(invalid, "wf-result").data.rows).toContainEqual({ label: "WFE", value: "해석 불가" });
  });
});

describe("buildWalkForwardGraph 창 배치 노드", () => {
  it("창 배치를 주면 창 분할 단계 밑에 노드를 붙여 점선으로 잇고, 누르면 창 분할 설정으로 간다", () => {
    const spans = buildWindowSchedule(1000, 300, 100, false);
    const graph = buildWalkForwardGraph({ ...design, schedule: { spans, dates: [] } });
    const schedule = graph.nodes.find((n) => n.id === "wf-schedule") as ScheduleNode;
    const split = step(graph, "wf-split");
    expect(schedule.type).toBe("schedule");
    expect(schedule.data.section).toBe("wf-split");
    expect(schedule.position.x).toBe(split.position.x);
    expect(graph.stack["wf-schedule"]).toEqual(["wf-data", "wf-split", "wf-optimize", "wf-test", "wf-result"]);
    expect(split.data.hasDetail).toBe(true);
    expect(graph.edges.find((e) => e.target === "wf-schedule")).toMatchObject({ source: "wf-split", sourceHandle: "detail", className: "lab-edge-aux" });
  });

  it("검증 단계에 첫 검증 시작일 ~ 마지막 검증 종료일을 싣는다", () => {
    const dates = Array.from({ length: 1000 }, (_, i) => `d${String(i).padStart(4, "0")}`);
    const spans = buildWindowSchedule(1000, 300, 100, false);
    const graph = buildWalkForwardGraph({ ...design, schedule: { spans, dates } });
    expect(step(graph, "wf-test").data.rows[0]).toEqual({ label: "기간", value: "d0300 ~ d0999" });
    const noDates = buildWalkForwardGraph({ ...design, schedule: { spans, dates: [] } });
    expect(step(noDates, "wf-test").data.rows.some((r) => r.label === "기간")).toBe(false);
  });

  it("창 배치가 없으면 다섯 단계만 그리고 창 분할에 아래 연결점을 달지 않는다", () => {
    const graph = buildWalkForwardGraph(design);
    expect(graph.nodes.some((n) => n.id === "wf-schedule")).toBe(false);
    expect(step(graph, "wf-split").data.hasDetail).toBe(false);
  });
});

describe("노드에서 고치는 칸", () => {
  const edit = { windowBarsMin: 100, windowBarsMax: 1000, trainRatioMin: 20, trainRatioMax: 80, method: "bayesian" as const, trials: 30, trialOptions: [20, 30, 50] };
  const editOf = (graph: ExperimentGraph, id: string, label: string) => step(graph, id).data.rows.find((row) => row.label === label)?.edit;

  it("조정 칸에 컨트롤이 있는 값에만 입력 칸을 달고, 파생값·결과는 읽기 전용으로 둔다", () => {
    const graph = buildWalkForwardGraph({ ...design, edit });
    expect(editOf(graph, "wf-split", "방식")).toMatchObject({ kind: "select", key: "wf.anchor", value: "rolling" });
    expect(editOf(graph, "wf-split", "구간 길이")).toEqual({ kind: "number", key: "wf.windowBars", value: 400, min: 100, max: 1000, suffix: "거래일" });
    expect(editOf(graph, "wf-split", "학습 비중")).toMatchObject({ kind: "number", key: "wf.trainRatioPct", value: 75, min: 20, max: 80 });
    expect(editOf(graph, "wf-split", "창 수")).toBeUndefined();
    expect(editOf(graph, "wf-optimize", "방법")).toMatchObject({ kind: "select", key: "wf.method", value: "bayesian:30" });
    expect(editOf(graph, "wf-optimize", "목표")).toBeUndefined();
    expect(editOf(graph, "wf-optimize", "PBR")).toEqual({ kind: "open", key: "wf.param:filters.pbr" });
    expect(step(graph, "wf-data").data.rows.some((row) => row.edit)).toBe(false);
  });

  it("결과가 있거나 실행 중이라 edit이 null이면 어떤 칸도 고칠 수 없다", () => {
    const graph = buildWalkForwardGraph({ ...design, edit: null });
    expect(graph.nodes.some((n) => n.type === "experiment" && n.data.rows.some((row) => row.edit))).toBe(false);
  });

  it("노드에서 고친 값을 조정 칸의 설정 변경으로 되돌린다", () => {
    expect(parseWalkForwardEdit("wf.anchor", "anchored")).toEqual({ field: "anchor", value: true });
    expect(parseWalkForwardEdit("wf.windowBars", 500)).toEqual({ field: "windowBars", value: 500 });
    expect(parseWalkForwardEdit("wf.trainRatioPct", 60)).toEqual({ field: "trainRatioPct", value: 60 });
    expect(parseWalkForwardEdit("wf.method", "grid")).toEqual({ field: "method", method: "grid" });
    expect(parseWalkForwardEdit("wf.method", "bayesian:50")).toEqual({ field: "method", method: "bayesian", trials: 50 });
    expect(parseWalkForwardEdit("wf.param:risk.stop_loss", null)).toEqual({ field: "parameter", id: "risk.stop_loss" });
    expect(parseWalkForwardEdit("mc.iterations", "500")).toBeNull();
  });

  it("몬테카를로는 방식·반복 횟수를 조정 칸의 선택지로 고친다", () => {
    const base = { sourceLabel: "일별 수익률", sourceDetail: "1,200개", methodLabel: "21일 블록", iterations: 1000, seed: 42, running: false, result: null };
    const options = [{ value: "block21", label: "21일 블록" }];
    const graph = buildMonteCarloGraph({ ...base, edit: { methodValue: "block21", methodOptions: options, iterationOptions: [500, 1000] } });
    expect(editOf(graph, "mc-resample", "방식")).toEqual({ kind: "select", key: "mc.method", value: "block21", options });
    expect(editOf(graph, "mc-paths", "반복")).toMatchObject({ kind: "select", key: "mc.iterations", value: "1000" });
    expect(editOf(graph, "mc-paths", "seed")).toBeUndefined();
  });
});

describe("attachContextNodes", () => {
  it("참고 노드를 첫 단계 왼쪽 열에 위에서부터 쌓고, 첫 노드만 첫 단계로 잇는다", () => {
    const graph = attachContextNodes(buildWalkForwardGraph(design), [
      { id: "lab-strategy", testId: "s", content: null },
      { id: "lab-method", testId: "m", content: null },
    ]);
    expect(graph.nodes.slice(0, 2).map((n) => n.id)).toEqual(["lab-strategy", "lab-method"]);
    expect(graph.nodes[0].position.x).toBeLessThan(0);
    expect(graph.nodes[1].position.x).toBe(graph.nodes[0].position.x);
    expect(graph.stack["lab-method"]).toEqual(["lab-strategy"]);
    expect(graph.edges[0]).toMatchObject({ source: "lab-strategy", target: "wf-data", className: "lab-edge-aux" });
    expect(graph.edges.filter((e) => e.source === "lab-method")).toEqual([]);
    expect(step(graph, "wf-data").position).toEqual({ x: 0, y: 0 });
  });
});

describe("buildMonteCarloGraph", () => {
  it("실행 중이면 처리 단계로 들어가는 선을 움직이고, 결과가 있으면 분포 요약을 싣는다", () => {
    const base = { sourceLabel: "일별 수익률", sourceDetail: "1,200개", methodLabel: "21일 블록", iterations: 1000, seed: 42 };
    const running = buildMonteCarloGraph({ ...base, running: true, result: null });
    expect(running.edges.some((e) => e.animated)).toBe(true);
    const done = buildMonteCarloGraph({
      ...base,
      running: false,
      result: { cagrMedian: 0.1, cagrP05: -0.02, mddMedian: 0.25, probPositive: 0.9 },
    });
    expect(step(done, "mc-result").data.rows).toContainEqual({ label: "양수 CAGR 확률", value: "90.0%" });
  });
});

describe("scheduleFromPeriods", () => {
  const dates = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09"];

  it("결과 창의 기간 문자열을 거래일 인덱스로 되돌린다(끝은 포함하지 않는다)", () => {
    expect(
      scheduleFromPeriods(dates, [{ window: 1, isPeriod: "2020-01-02 ~ 2020-01-06", oosPeriod: "2020-01-07 ~ 2020-01-08" }]),
    ).toEqual([{ window: 1, isStart: 0, isEnd: 3, oosStart: 3, oosEnd: 5 }]);
  });

  it("기간을 읽을 수 없으면 null — 폼 설정 배치로 되돌아간다", () => {
    expect(scheduleFromPeriods(dates, [{ window: 1, isPeriod: "", oosPeriod: "" }])).toBeNull();
    expect(scheduleFromPeriods([], [{ window: 1, isPeriod: "2020-01-02 ~ 2020-01-06", oosPeriod: "2020-01-07 ~ 2020-01-08" }])).toBeNull();
  });
});

describe("buildWalkForwardGraph 모니터 값", () => {
  it("파라미터 탐색 단계에 파라미터별 범위·STEP을 조정 칸 표기 그대로 비추고, 제외한 파라미터는 제외됨으로 적는다", () => {
    const rows = step(buildWalkForwardGraph(design), "wf-optimize").data.rows;
    expect(rows).toContainEqual({ label: "손절라인", value: "5%~15% · STEP 2.5%" });
    expect(rows).toContainEqual({ label: "보유기간", value: "제외됨" });
  });

  it("실행 계획 노드는 실행 전에만 그리고, 막혔으면 사유와 실행 가능한 설정을 적는다", () => {
    const plan = { totalBacktests: 93, estimateLabel: "실행 불가", blockedReason: "충족되지 않은 조건: 구간이 너무 짧습니다", suggestions: ["구간 길이 300거래일 이상"], note: null };
    const blocked = step(buildWalkForwardGraph({ ...design, plan }), "wf-plan");
    expect(blocked.data.status).toBe("blocked");
    expect(blocked.data.index).toBeUndefined();
    // 결과 단계 오른쪽, 파이프라인의 맨 끝에 이어 붙는다(아래로 쌓지 않는다).
    expect(blocked.position).toEqual({ x: 5 * EXPERIMENT_GAP_X, y: 0 });
    expect(buildWalkForwardGraph({ ...design, plan }).edges).toContainEqual(
      expect.objectContaining({ source: "wf-result", target: "wf-plan", sourceHandle: "out", targetHandle: "in" }),
    );
    expect(buildWalkForwardGraph({ ...design, plan }).stack["wf-plan"]).toBeUndefined();
    expect(blocked.data.footnote).toEqual({ tone: "warn", lines: [plan.blockedReason, "구간 길이 300거래일 이상"] });
    const done = buildWalkForwardGraph({ ...design, plan, result: { wfe: 0.7, wfeTierText: null, avgOosCagr: 1, windowsDone: 7 } });
    expect(done.nodes.some((n) => n.id === "wf-plan")).toBe(false);
  });

  it("결과가 있고 결과 판 자리를 주면 결과 단계 밑에 결과 판을 붙이고 위 노드들 아래로 쌓는다", () => {
    const slot = () => {};
    const before = buildWalkForwardGraph({ ...design, reportSlot: slot });
    expect(before.nodes.some((n) => n.id === "wf-report")).toBe(false);
    const done = buildWalkForwardGraph({
      ...design,
      reportSlot: slot,
      schedule: { spans: [], dates: [] },
      result: { wfe: 0.7, wfeTierText: null, avgOosCagr: 1, windowsDone: 7 },
    });
    expect(done.nodes.find((n) => n.id === "wf-report")?.type).toBe("report");
    expect(step(done, "wf-result").data.hasDetail).toBe(true);
    expect(done.edges.find((e) => e.target === "wf-report")).toMatchObject({ source: "wf-result", sourceHandle: "detail" });
    expect(done.stack["wf-report"]).toContain("wf-schedule");
  });
});

describe("stackNodes", () => {
  const node = (id: string, y: number, height?: number) => ({ id, position: { x: 0, y }, data: {}, ...(height != null ? { measured: { width: 100, height } } : {}) });

  it("기준 노드들 중 가장 아래 끝에서 간격만큼 밑으로 내린다", () => {
    const out = stackNodes([node("a", 0, 120), node("b", 0, 180), node("c", 0, 50)], { c: ["a", "b"] });
    expect(out[2].position.y).toBe(180 + STACK_GAP_Y);
  });

  it("기준 노드가 아직 측정 전이면 그대로 두고, 위치가 같으면 같은 객체를 돌려준다", () => {
    const pending = [node("a", 0), node("c", 7)];
    expect(stackNodes(pending, { c: ["a"] })[1]).toBe(pending[1]);
    const settled = [node("a", 0, 100), node("c", 100 + STACK_GAP_Y)];
    expect(stackNodes(settled, { c: ["a"] })[1]).toBe(settled[1]);
  });
});
