import { describe, expect, it } from "vitest";

import {
  applyRunWindow,
  backtestConfigOptions,
  toPanelPeriodId,
} from "./backtestOptions";

// 2026-08-01 정리: 설정 패널의 기간 표현과 엔진 요청의 기간 표현이 어긋나
// ① 명시 창으로 파싱된 전략이 패널에서 아무 버튼도 선택되지 않았고
// ② 패널에서 기간을 바꿔도 남아 있던 명시 창이 그 선택을 삼켰다.

describe("toPanelPeriodId", () => {
  it("엔진 요청의 소문자 표기를 패널 id로 맞춘다", () => {
    expect(toPanelPeriodId("5y")).toBe("5Y");
    expect(toPanelPeriodId("3y")).toBe("3Y");
    expect(toPanelPeriodId("full")).toBe("full");
  });

  it("대응 버튼이 없으면 null이다 — 없는 기간을 임의로 고르지 않는다", () => {
    expect(toPanelPeriodId("7y")).toBeNull();
    expect(toPanelPeriodId(null)).toBeNull();
  });
});

describe("backtestConfigOptions", () => {
  it("명시 창이 있으면 '직접 입력'으로 그 창을 그대로 보여준다", () => {
    const options = backtestConfigOptions({
      period: "5y",
      startDate: "2016-08-01",
      endDate: "2026-08-01",
      risk: { init_cash: 30000000 },
    });
    // period="5y"를 그대로 넘기면 실행되는 창(2016~2026)이 화면 어디에도 없다.
    expect(options.period).toBe("custom");
    expect(options.startDate).toBe("2016-08-01");
    expect(options.endDate).toBe("2026-08-01");
    expect(options.initialCapital).toBe(30000000);
  });

  it("명시 창이 없으면 상대 기간을 패널 id로 맞춰 보여준다", () => {
    const options = backtestConfigOptions({ period: "3y", risk: { init_cash: 10000000 } });
    expect(options.period).toBe("3Y");
    expect(options.startDate).toBeUndefined();
  });

  it("요청이 없으면 기본값으로 연다", () => {
    expect(backtestConfigOptions(null)).toMatchObject({ period: "5Y", initialCapital: 10000000 });
  });
});

describe("applyRunWindow", () => {
  it("상대 기간을 고르면 이전 명시 창을 떼어낸다", () => {
    const next = applyRunWindow(
      { period: "5y", startDate: "2016-08-01", endDate: "2026-08-01", symbols: ["005930"] },
      { period: "1Y" },
    );
    // 창이 남으면 엔진이 startDate를 우선해 사용자가 고른 1년이 무시된다.
    expect(next.period).toBe("1Y");
    expect("startDate" in next).toBe(false);
    expect("endDate" in next).toBe(false);
    expect(next.symbols).toEqual(["005930"]);
  });

  it("'직접 입력'이면 패널에서 고른 창을 싣는다", () => {
    const next = applyRunWindow(
      { period: "5y", startDate: "2016-08-01", endDate: "2026-08-01" },
      { period: "custom", startDate: "2020-01-01", endDate: "2024-12-31" },
    );
    expect(next.startDate).toBe("2020-01-01");
    expect(next.endDate).toBe("2024-12-31");
  });

  it("'전체'를 고르면 창 없이 period만 남는다", () => {
    const next = applyRunWindow({ period: "5y", startDate: "2016-08-01" }, { period: "full" });
    expect(next.period).toBe("full");
    expect("startDate" in next).toBe(false);
  });
});
