import { describe, expect, it } from "vitest";

import { formatExecutionTuningLabels } from "./strategy-summary";

describe("entry tranche ladder label (engine v16.36)", () => {
  it("never derives the first tranche from the remainder (2026-09-28: invented '65%')", () => {
    const labels = formatExecutionTuningLabels({
      entry_tranches: {
        count: null, step_pct: null, first_pct: null,
        levels: [{ drop_pct: 25, size_pct: 25 }, { drop_pct: 15, size_pct: 10 }],
      },
    });
    expect(labels).toContain("하락 시 추가 매수 -15%에 10%, -25%에 25%");
    expect(labels.join(" ")).not.toContain("65%");
  });

  it("shows the first tranche the user stated, steps in drop order", () => {
    const labels = formatExecutionTuningLabels({
      entry_tranches: { first_pct: 50, levels: [{ drop_pct: 25, size_pct: 25 }, { drop_pct: 15, size_pct: 10 }] },
    });
    expect(labels).toContain("분할 매수 첫 회차 50% · 추가 -15%에 10%, -25%에 25%");
  });

  it("marks a ladder with a missing share as not set instead of guessing", () => {
    const labels = formatExecutionTuningLabels({
      entry_tranches: { levels: [{ drop_pct: 15, size_pct: null }] },
    });
    expect(labels).toContain("분할 매수 사다리(단계 미정)");
  });

  it("keeps the uniform tranche label", () => {
    const labels = formatExecutionTuningLabels({ entry_tranches: { count: 3, step_pct: 5 } });
    expect(labels).toContain("분할 매수 3회(5% 간격)");
  });
});
