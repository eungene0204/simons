import { describe, expect, it } from "vitest";
import { deriveSplitCount } from "@/components/strategy/backtest/walkForwardRunLimits";
import {
  buildMonteCarloGraph,
  buildWalkForwardGraph,
  buildWindowSchedule,
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
    { label: "PBR", range: "0.5~1.5 · STEP 0.1", excluded: false },
    { label: "손절라인", range: "5%~15% · STEP 2.5%", excluded: false },
    { label: "보유기간", range: "10거래일~20거래일 · STEP 10거래일", excluded: true },
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

  it("창 배치가 없으면 다섯 단계만 그리고 창 분할에 아래 연결점을 달지 않는다", () => {
    const graph = buildWalkForwardGraph(design);
    expect(graph.nodes.some((n) => n.id === "wf-schedule")).toBe(false);
    expect(step(graph, "wf-split").data.hasDetail).toBe(false);
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
