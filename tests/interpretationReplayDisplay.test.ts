import { readFileSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { attachFieldStates, buildBuilderTurnPresentation } from "@/app/analytics/new/builderProgressPresentation";
import { listStrategyItems } from "@/app/analytics/new/strategyItems";

function display(row: any, expected: any) {
  if (!row.final?.parsed || !(expected?.require?.length || expected?.rows?.length)) {
    return { status: "HARNESS_INVALID", reason: "Missing API result or human display expectations" };
  }
  const res = row.final;
  const presentation = buildBuilderTurnPresentation({
    state: {}, reply: res.clarification_question ?? "", parsed: res.parsed,
    explicitFields: res.explicit_fields ?? [], backtestRequest: res.backtest_request,
    declinedFields: res.declined_fields ?? [], pendingConditions: res.pending_conditions ?? [],
  });
  const rendered = {
    ...presentation,
    progressItems: attachFieldStates(presentation.progressItems ?? [], res.field_states),
    settings: listStrategyItems(res.parsed),
    notices: res.notices, question: res.clarification_question, chips: res.clarification_suggestions,
  };
  const summary = JSON.stringify({ summary: rendered.summaryItems, settings: rendered.settings });
  const failures = (expected.require ?? []).filter((text: string) => !summary.includes(text));
  for (const rule of expected.rows ?? []) {
    const item = rendered.summaryItems.find((item) => item.label === rule.label);
    if (!item || rule.require.some((text: string) => !item.value.includes(text))) failures.push(rule.label);
  }
  for (const text of expected.forbid ?? []) if (summary.includes(text)) failures.push(text);
  return { status: failures.length ? "FAIL" : "PASS", failures, rendered };
}

describe("Offline interpretation display replay", () => {
  it("requires an API response and independent display gold", () => {
    expect(display({}, { require: ["PER"] }).status).toBe("HARNESS_INVALID");
    expect(display({ final: { parsed: {} } }, {}).status).toBe("HARNESS_INVALID");
  });
  it("does not accept a requested position count found only in a stop-loss value", () => {
    const row = { final: { parsed: { universe: ["KOSPI"], max_positions: 3, stop_loss_pct: 8 },
      explicit_fields: ["max_positions", "stop_loss_pct"] } };
    expect(display(row, { rows: [{ label: "최대 보유", require: ["8종목"] }] }).status).toBe("FAIL");
  });
  it.skipIf(!process.env.QA_REPLAY_INPUT)("renders every recorded API result through production functions", () => {
    const data = JSON.parse(readFileSync(process.env.QA_REPLAY_INPUT!, "utf8"));
    expect(data.results.length).toBeGreaterThan(0);
    const results = data.results.map((row: any) => ({ case_id: row.case_id,
      ...display(row, data.cases.find((c: any) => c.case_id === row.case_id)?.expected?.display) }));
    writeFileSync(process.env.QA_REPLAY_OUTPUT!, JSON.stringify(results));
    // Product failures are evidence, while missing rendering coverage invalidates the harness.
    expect(results.filter((row: any) => row.status === "HARNESS_INVALID")).toEqual([]);
  });
});
