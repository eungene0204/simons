import { afterEach, describe, expect, it } from "vitest";
import { setLanguage } from "@/lib/i18n";

import { confirmedInput, executedInput, META } from "./fixtures";
import { buildStrategyGraph, isEmptyGraph } from "./transform";
import type { GraphNode, StrategyGraph } from "./types";

const build = (name: Parameters<typeof confirmedInput>[0], meta = META) => buildStrategyGraph(confirmedInput(name), meta);
const byLabel = (g: StrategyGraph, text: string) => g.nodes.filter((n) => n.label.includes(text));
const sectionOf = (g: StrategyGraph, key: string) => g.nodes.find((n) => n.id === `section:${key}`);
const childrenOf = (g: StrategyGraph, id: string) => g.edges.filter((e) => e.source === id).map((e) => g.nodes.find((n) => n.id === e.target) as GraphNode);
const row = (n: GraphNode, label: string) => n.details.rows.find((r) => r.label === label)?.value;

describe("1. golden cross + RSI AND entry", () => {
  const g = build("goldenCrossRsiAnd");
  it("groups both signals under an AND group inside the entry section", () => {
    const group = g.nodes.find((n) => n.id === "group:entry");
    expect(group?.label).toContain("AND");
    const kids = childrenOf(g, "group:entry");
    expect(kids.map((k) => k.kind)).toEqual(["condition", "condition"]);
    expect(kids[0].details.expression).toBe("20일선-60일선 골든크로스");
    expect(kids[1].details.expression).toBe("RSI(14) < 70");
  });
  it("marks crossovers as threshold-not-applicable and RSI value as present", () => {
    const [cross, rsi] = childrenOf(g, "group:entry");
    expect(cross.status).toBe("not_applicable");
    expect(row(cross, "기준값")).toBe("해당 없음");
    expect(rsi.status).toBe("ok");
    expect(row(rsi, "기준값")).toBe("70");
  });
  it("distinguishes a persistent state from a crossover event and from a simple comparison", () => {
    const gate = build("entryOrWithFilters").nodes.find((n) => n.id === "cond:filters/entry.3") as GraphNode;
    expect(gate.details.expression).toBe("종가가 EMA60 위 유지");
    expect(row(gate, "판정 방식")).toBe("지속 상태(교차 사건 아님)");
    const [cross, rsi] = childrenOf(g, "group:entry");
    expect(row(cross, "판정 방식")).toBe("교차 사건");
    expect(row(rsi, "연산자")).toBe("<");
  });
});

describe("2. entry_logic OR and its scope", () => {
  const g = build("entryOrWithFilters");
  it("applies OR only to the entry signals", () => {
    expect(g.nodes.find((n) => n.id === "group:entry")?.label).toContain("OR");
    expect(childrenOf(g, "group:entry")).toHaveLength(2);
  });
  it("keeps filters (fundamental + gate) in an always-AND filter group", () => {
    const group = g.nodes.find((n) => n.id === "group:filters");
    expect(group?.label).toContain("AND");
    expect(group?.details.statusNote).toContain("항상 AND");
    expect(childrenOf(g, "group:filters")).toHaveLength(2);
  });
  it("does not apply the entry logic to the exit group (engine default OR, labelled as such)", () => {
    const exit = g.nodes.find((n) => n.id === "group:exit");
    expect(exit?.label).toContain("OR");
    expect(exit?.details.valueSource).toBe("engine_default");
  });
});

describe("3/4. same indicator on both sides; different periods", () => {
  it("keeps separate condition nodes and shares one indicator node", () => {
    const g = build("sameIndicatorBothSides");
    const rsiConds = g.nodes.filter((n) => n.kind === "condition");
    expect(rsiConds).toHaveLength(2);
    const indicators = g.nodes.filter((n) => n.kind === "indicator");
    expect(indicators).toHaveLength(1);
    const uses = g.edges.filter((e) => e.kind === "uses_indicator");
    expect(uses.map((e) => e.target)).toEqual(["ind:technical.rsi", "ind:technical.rsi"]);
  });
  it("never merges conditions with different periods or positions", () => {
    const g = build("samePeriodDiffers");
    const conds = g.nodes.filter((n) => n.kind === "condition").map((n) => n.details.expression);
    expect(conds).toEqual(["RSI(14) < 30", "RSI(7) < 20", "RSI(21) > 70"]);
    expect(new Set(g.nodes.filter((n) => n.kind === "condition").map((n) => n.id)).size).toBe(3);
  });
});

describe("5. filter + ranking + entry together", () => {
  const g = build("filterRankingEntry");
  it("creates distinct sections in the strategy order", () => {
    const sections = g.nodes.filter((n) => n.kind === "section").map((n) => n.id);
    expect(sections).toEqual(["section:universe", "section:filters", "section:ranking", "section:entry", "section:allocation", "section:rebalance"]);
  });
  it("reads only supported ranking fields", () => {
    const metric = g.nodes.find((n) => n.id === "setting:ranking/metric") as GraphNode;
    expect(metric.label).toContain("높은 순");
    expect(row(metric, "산정 기간")).toBe("120일");
    expect(row(metric, "최근 제외 기간")).toBe("21거래일");
  });
  it("shows rebalancing period and method", () => {
    const p = g.nodes.find((n) => n.id === "setting:rebalance/period") as GraphNode;
    expect(row(p, "주기")).toBe("매월");
    expect(row(p, "방식")).toBe("종목 교체");
  });
});

describe("6. risk roles and basis", () => {
  const g = build("riskRoles");
  it("states reference price, trigger price and trading-day basis", () => {
    const sl = g.nodes.find((n) => n.id === "setting:risk/stop_loss") as GraphNode;
    expect(row(sl, "기준가")).toBe("매수가");
    expect(row(sl, "판정 가격")).toBe("장중 저가");
    const trail = g.nodes.find((n) => n.id === "setting:risk/trailing") as GraphNode;
    expect(row(trail, "기준가")).toBe("보유 중 장중 고점");
    expect(row(trail, "작동 조건")).toContain("+8%");
    const hold = g.nodes.find((n) => n.id === "setting:risk/max_holding") as GraphNode;
    expect(row(hold, "기준")).toBe("거래일");
  });
  it("keeps the evaluation priority instead of flattening risk into an OR", () => {
    const section = sectionOf(g, "risk") as GraphNode;
    expect(row(section, "청산 평가 순서")).toContain("최대 보유기간 → 손절 → 익절 → 트레일링");
    expect(g.nodes.some((n) => n.kind === "group" && n.section === "risk")).toBe(false);
  });
  it("explains a hold period that the request switches off under rebalancing", () => {
    const h = build("holdIgnoredByRebalance");
    const hold = h.nodes.find((n) => n.id === "setting:risk/max_holding") as GraphNode;
    expect(hold.status).toBe("not_applicable");
    expect(hold.details.statusNote).toContain("꺼집니다");
    expect(hold.details.valueSource).toBe("parsed");
  });
});

describe("7. pending, valueless, zero, empty", () => {
  it("marks a required-but-missing threshold as pending, not as 0", () => {
    const g = build("valuelessAndPending");
    const cond = g.nodes.find((n) => n.kind === "condition") as GraphNode;
    expect(cond.status).toBe("pending");
    expect(row(cond, "기준값")).toBe("미정");
  });
  it("keeps parsed-only pending settings visible (not sent to the request)", () => {
    const g = build("valuelessAndPending");
    const pending = g.nodes.filter((n) => n.status === "pending" && n.kind === "setting");
    expect(pending.map((n) => n.id).sort()).toEqual(["setting:allocation/cash_pool_pending", "setting:risk/market_regime_pending"]);
  });
  it("treats a 0 threshold as a valid value, not as pending", () => {
    const g = build("zeroThreshold");
    const cond = g.nodes.find((n) => n.kind === "condition") as GraphNode;
    expect(cond.details.expression).toBe("영업이익증가율 >= 0");
    expect(cond.status).toBe("ok");
    expect(row(cond, "기준값")).toBe("0");
  });
  it("shows a stored stop loss of 0 as a disabled value instead of hiding it", () => {
    const input = confirmedInput("riskRoles");
    const request = JSON.parse(JSON.stringify(input.request));
    request.risk.stop_loss_pct = 0;
    const g = buildStrategyGraph({ ...input, request }, META);
    const sl = g.nodes.find((n) => n.id === "setting:risk/stop_loss") as GraphNode;
    expect(sl.label).toContain("-0%");
    expect(row(sl, "상태")).toBe("0 (비활성)");
  });
  it("honours ranking_enabled=false (a boolean false is a real value)", () => {
    const input = confirmedInput("filterRankingEntry");
    const request = JSON.parse(JSON.stringify(input.request));
    request.risk.ranking_enabled = false;
    const g = buildStrategyGraph({ ...input, request }, META);
    expect(g.nodes.some((n) => n.id === "section:ranking")).toBe(false);
  });
  it("returns an empty graph for an empty strategy", () => {
    const g = build("emptyStrategy");
    expect(isEmptyGraph(g)).toBe(false);
    expect(g.nodes.filter((n) => n.kind === "condition")).toHaveLength(0);
  });
  it("returns no nodes when there is no snapshot", () => {
    const g = buildStrategyGraph({ origin: "none", schema: "none", sourceRef: "none:x" }, META);
    expect(g.nodes).toEqual([]);
    expect(isEmptyGraph(g)).toBe(true);
  });
});

describe("8/9. executed snapshot is what is shown", () => {
  it("renders the executed request A, independent of any later strategy B", () => {
    const a = buildStrategyGraph(executedInput("goldenCrossRsiAnd"), META);
    const b = buildStrategyGraph(executedInput("sameIndicatorBothSides"), META);
    expect(a.origin).toBe("executed");
    expect(a.nodes.filter((n) => n.kind === "condition").map((n) => n.details.expression)).toContain("RSI(14) < 70");
    expect(b.nodes.filter((n) => n.kind === "condition").map((n) => n.details.expression)).not.toContain("RSI(14) < 70");
  });
  it("says that pending states and quotes cannot be recovered from an executed request", () => {
    const a = buildStrategyGraph(executedInput("valuelessAndPending"), META);
    expect(a.notes.join(" ")).toContain("미정 항목과 조건별 원문 인용은 확인할 수 없습니다");
    expect(a.nodes.some((n) => n.id.endsWith("_pending"))).toBe(false);
  });
});

describe("10. complex KR strategy", () => {
  const g = build("krComplex");
  it("expresses the supported settings that are present", () => {
    const ids = g.nodes.map((n) => n.id);
    for (const id of [
      "section:universe", "section:filters", "section:ranking", "section:entry", "section:exit",
      "section:allocation", "section:rebalance", "section:risk",
      "setting:ranking/composite", "setting:allocation/entry_tranches", "setting:risk/partial_tp",
      "setting:risk/market_regime", "setting:filters/mcap_top", "setting:allocation/allocation_type",
    ]) expect(ids).toContain(id);
    expect(row(g.nodes.find((n) => n.id === "setting:universe/sector") as GraphNode, "업종")).toBe("반도체");
  });
  it("keeps composite components with their own direction, lookback and weight", () => {
    const comps = g.nodes.filter((n) => n.id.startsWith("cond:ranking/component."));
    expect(comps).toHaveLength(3);
    expect(row(comps[1], "가중치")).toBe("2");
    expect(row(comps[2], "산정 기간")).toBe("252일");
    expect(row(comps[2], "최근 제외 기간")).toBe("21거래일");
  });
  it("describes the bollinger band + touch lookback and the RSI rebound exit", () => {
    const entry = childrenOf(g, "group:entry").map((n) => n.details.expression);
    expect(entry.some((e) => e?.includes("중심선") && e.includes("5거래일"))).toBe(true);
    const exit = g.nodes.find((n) => n.id === "cond:exit/exit.0") as GraphNode;
    expect(exit.details.expression).toContain("재돌파");
  });
  it("states the position weight basis from the simulator", () => {
    const w = g.nodes.find((n) => n.id === "setting:allocation/position_size") as GraphNode;
    expect(row(w, "비중 기준")).toContain("총자산");
  });
});

describe("backtest period", () => {
  it("shows the backtest window as a setting in the capital allocation section", () => {
    const g = build("goldenCrossRsiAnd");
    const period = g.nodes.find((n) => n.id === "setting:allocation/period") as GraphNode;
    expect(period.label).toBe("백테스트 기간 5년");
    expect(row(period, "기간")).toBe("5년");
  });
  it("shows an explicit start/end range from the request", () => {
    const input = confirmedInput("goldenCrossRsiAnd");
    const request = JSON.parse(JSON.stringify(input.request));
    request.startDate = "2020-01-01";
    request.endDate = "2023-12-31";
    const g = buildStrategyGraph({ ...input, request }, META);
    const period = g.nodes.find((n) => n.id === "setting:allocation/period") as GraphNode;
    expect(period.details.rows[0].value).toContain("2020");
    expect(period.details.rows[0].value).toContain("2023");
  });
});

describe("draft: unstated defaults are not drawn as if the user said them", () => {
  const draft = (explicitFields: string[]) => buildStrategyGraph({ ...confirmedInput("filterRankingEntry"), origin: "draft", explicitFields }, META);
  const ids = (g: ReturnType<typeof draft>) => new Set(g.nodes.map((n) => n.id));

  it("hides period, capital and holdings the user has not stated", () => {
    const g = ids(draft(["universe"]));
    for (const id of ["setting:allocation/period", "setting:allocation/init_cash", "setting:allocation/max_positions", "setting:allocation/position_size"]) {
      expect(g.has(id)).toBe(false);
    }
    // a real monthly rebalancing can only come from the user, so it stays
    expect(g.has("setting:rebalance/period")).toBe(true);
  });

  it("draws them once the user has stated them", () => {
    const g = ids(draft(["universe", "max_positions", "backtest_period", "initial_capital", "rebalancing"]));
    for (const id of ["setting:allocation/period", "setting:allocation/init_cash", "setting:allocation/max_positions"]) {
      expect(g.has(id)).toBe(true);
    }
  });

  it("hides the compiler's default 'no rebalancing' until the user answered it", () => {
    const input = confirmedInput("goldenCrossRsiAnd");
    const none = (fields: string[]) => ids(buildStrategyGraph({ ...input, origin: "draft", explicitFields: fields }, META));
    expect(none(["universe"]).has("setting:rebalance/period")).toBe(false);
    expect(none(["universe", "rebalancing"]).has("setting:rebalance/period")).toBe(true);
  });

  it("confirmed snapshots still draw everything", () => {
    expect(ids(build("goldenCrossRsiAnd")).has("setting:allocation/period")).toBe(true);
  });
});

describe("11. immutability and determinism", () => {
  it("does not mutate the input and yields identical ids", () => {
    const input = confirmedInput("krComplex");
    const before = JSON.stringify(input);
    const metaBefore = JSON.stringify(META);
    const one = buildStrategyGraph(input, META);
    const two = buildStrategyGraph(input, META);
    expect(JSON.stringify(input)).toBe(before);
    expect(JSON.stringify(META)).toBe(metaBefore);
    expect(JSON.stringify(one)).toBe(JSON.stringify(two));
    expect(one.nodes.map((n) => n.id)).toEqual(two.nodes.map((n) => n.id));
  });
  it("gives every node and edge a unique id and valid endpoints", () => {
    const g = build("krComplex");
    const ids = new Set(g.nodes.map((n) => n.id));
    expect(ids.size).toBe(g.nodes.length);
    expect(new Set(g.edges.map((e) => e.id)).size).toBe(g.edges.length);
    for (const e of g.edges) {
      expect(ids.has(e.source)).toBe(true);
      expect(ids.has(e.target)).toBe(true);
    }
  });
});

describe("12. ontology relations stay separate from instances", () => {
  it("keeps every condition instance when classification nodes are filtered out", () => {
    const g = build("krComplex");
    const withoutClasses = g.nodes.filter((n) => n.kind !== "class");
    const conds = g.nodes.filter((n) => n.kind === "condition");
    expect(withoutClasses.filter((n) => n.kind === "condition")).toHaveLength(conds.length);
    expect(g.edges.filter((e) => e.kind === "is_a").every((e) => e.source.startsWith("ind:") || e.source.startsWith("class:"))).toBe(true);
  });
  it("shows a readable unit instead of the raw registry identifier", () => {
    const per = build("filterRankingEntry").nodes.find((n) => n.id === "ind:fundamental.per") as GraphNode;
    expect(row(per, "값의 단위")).toBe("배");
    const rsi = build("goldenCrossRsiAnd").nodes.find((n) => n.id === "ind:technical.rsi") as GraphNode;
    expect(JSON.stringify(rsi.details)).not.toMatch(/percent|ratio|point/);
  });
  it("shows the support state and classification path of an indicator", () => {
    const g = build("goldenCrossRsiAnd");
    const rsi = g.nodes.find((n) => n.id === "ind:technical.rsi") as GraphNode;
    expect(rsi.details.support).toBe("SUPPORTED");
    expect(rsi.details.classPath.length).toBeGreaterThan(0);
    const per = build("filterRankingEntry").nodes.find((n) => n.id === "ind:fundamental.per") as GraphNode;
    expect(per.status).toBe("partial");
  });
  it("falls back to structure only when metadata is unavailable", () => {
    const g = buildStrategyGraph(confirmedInput("goldenCrossRsiAnd"), null);
    expect(g.metaState).toBe("unavailable");
    expect(g.nodes.some((n) => n.kind === "indicator" || n.kind === "class")).toBe(false);
    expect(g.nodes.filter((n) => n.kind === "condition")).toHaveLength(3);
    expect(g.notes.join(" ")).toContain("지표 정보를 불러오지 못해");
  });
  it("never stores a per-condition quote because no snapshot schema has one", () => {
    const g = build("krComplex");
    expect(g.nodes.every((n) => n.details.quote === null)).toBe(true);
  });
});


describe("English UI", () => {
  afterEach(() => setLanguage("ko"));
  it("uses English names and templates for everything the graph owns (no Korean left in labels or rows)", () => {
    setLanguage("en");
    const g = buildStrategyGraph(confirmedInput("krComplex"), META);
    const text = g.nodes
      .filter((n) => n.kind !== "class") // classification names exist in Korean only
      .flatMap((n) => [n.label, n.details.expression ?? "", n.details.statusNote ?? "", ...n.details.rows.flatMap((r) => [r.label, r.value])]);
    // Data the user typed (a sector name) is allowed to stay as data.
    const hangul = text.filter((x) => /[가-힣]/.test(x) && x !== "반도체" && x !== "업종: 반도체" && !/Sector: 반도체/.test(x));
    expect(hangul).toEqual([]);
    expect(g.nodes.find((n) => n.id === "ind:technical.rsi")?.label).toBe("RSI");
    expect(g.nodes.find((n) => n.id === "section:entry")?.label).toBe("Buy rules");
  });
});
