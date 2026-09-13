import { describe, expect, it } from "vitest";
import {
  buildRollingReturnSeries,
  buildRollingWindowPoints,
  buildRollingWindowStatsTable,
  hasRollingWindowSpan,
  isAnnualizedWindow,
  quantile,
  subtractMonths,
  summarizeRollingWindows,
  toDisplayReturn,
} from "@/components/strategy/backtest/rollingReturns";

describe("subtractMonths", () => {
  it("N개월 전 날짜를 반환해야 함", () => {
    expect(subtractMonths("2024-05-15", 1)).toBe("2024-04-15");
    expect(subtractMonths("2024-05-15", 12)).toBe("2023-05-15");
  });

  it("연도 경계를 넘어가야 함", () => {
    expect(subtractMonths("2024-02-10", 3)).toBe("2023-11-10");
  });

  it("말일은 대상 월의 말일로 클램프해야 함", () => {
    expect(subtractMonths("2024-03-31", 1)).toBe("2024-02-29"); // 윤년
    expect(subtractMonths("2023-03-31", 1)).toBe("2023-02-28");
    expect(subtractMonths("2024-07-31", 1)).toBe("2024-06-30");
  });
});

describe("buildRollingReturnSeries", () => {
  const dates = [
    "2024-01-02",
    "2024-02-01",
    "2024-03-04",
    "2024-04-01",
  ];
  const equity = [100, 110, 121, 133.1];

  it("기준 시점(창 시작) 이하 마지막 equity 대비 수익률을 계산해야 함", () => {
    const series = buildRollingReturnSeries(dates, equity, 1);
    // 2024-02-01의 1개월 전=2024-01-01 → 그 이하 거래일 없음(01-02가 첫날) → 제외
    // 2024-03-04의 1개월 전=2024-02-04 → 기준=02-01(110) → 121/110-1=10%
    // 2024-04-01의 1개월 전=2024-03-01 → 기준=02-01(110) → 133.1/110-1=21%
    expect(series).toHaveLength(2);
    expect(series[0].time).toBe("2024-03-04");
    expect(series[0].value).toBeCloseTo(10, 6);
    expect(series[1].time).toBe("2024-04-01");
    expect(series[1].value).toBeCloseTo(21, 6);
  });

  it("창이 백테스트 시작 이전으로 나가는 날짜는 제외해야 함", () => {
    const series = buildRollingReturnSeries(dates, equity, 3);
    // 3개월 창이 완전히 들어오는 날짜는 2024-04-01뿐 (04-01 - 3개월 = 01-01 < 01-02?)
    // 01-01 < 01-02 → 제외. 즉 전부 제외
    expect(series).toHaveLength(0);
  });

  it("빈 입력이면 빈 배열을 반환해야 함", () => {
    expect(buildRollingReturnSeries([], [], 12)).toHaveLength(0);
  });

  it("기준 equity가 0 이하이면 해당 지점을 건너뛰어야 함", () => {
    const series = buildRollingReturnSeries(
      ["2024-01-02", "2024-02-05"],
      [0, 110],
      1
    );
    expect(series).toHaveLength(0);
  });
});

describe("buildRollingWindowPoints", () => {
  // 1개월 창 안에서 고점 대비 낙폭이 생기는 자산곡선
  const dates = ["2024-01-02", "2024-01-15", "2024-01-25", "2024-02-05", "2024-02-20"];
  const equity = [100, 120, 90, 110, 100];

  it("창 시작·종료 거래일과 창 안 MDD를 함께 돌려줘야 함", () => {
    const points = buildRollingWindowPoints(dates, equity, 1);
    // 02-05: 1개월 전=01-05 → 기준=01-02(100). 창 [100,120,90,110]: 고점 120→90 = -25%
    // 02-20: 1개월 전=01-20 → 기준=01-15(120). 창 [120,90,110,100]: 고점 120→90 = -25%
    expect(points).toHaveLength(2);
    expect(points[0]).toMatchObject({ start: "2024-01-02", end: "2024-02-05" });
    expect(points[0].value).toBeCloseTo(10, 6);
    expect(points[0].mdd).toBeCloseTo(-25, 6);
    expect(points[1]).toMatchObject({ start: "2024-01-15", end: "2024-02-20" });
    expect(points[1].value).toBeCloseTo(-16.666666, 4);
    expect(points[1].mdd).toBeCloseTo(-25, 6);
  });

  it("MDD의 고점은 창 시작에서 다시 세야 함(창 밖 고점 무시)", () => {
    // 첫날 고점 200 이후 계속 100 근처 → 02-20 창(기준 01-15=100)의 MDD는 창 밖 200을 보지 않음
    const points = buildRollingWindowPoints(
      ["2024-01-02", "2024-01-15", "2024-02-05", "2024-02-20"],
      [200, 100, 105, 102],
      1
    );
    const last = points[points.length - 1];
    expect(last.start).toBe("2024-01-15");
    expect(last.mdd).toBeCloseTo((102 / 105 - 1) * 100, 6);
  });

  it("buildRollingReturnSeries는 창 종료일·수익률에 창 시작일을 동반한 투영이어야 함", () => {
    const points = buildRollingWindowPoints(dates, equity, 1);
    const series = buildRollingReturnSeries(dates, equity, 1);
    expect(series).toEqual(
      points.map((p) => ({ time: p.end, value: p.value, start: p.start, benchmark: null }))
    );
    // 툴팁 "시작 ~ 종료" 근거: 첫 지점은 01-02 ~ 02-05
    expect(series[0]).toMatchObject({ start: "2024-01-02", time: "2024-02-05" });
  });
});

describe("summarizeRollingWindows / buildRollingWindowStatsTable", () => {
  const points = [
    { start: "2024-01-02", end: "2024-02-01", value: 10, mdd: -5, benchmarkValue: 8 },
    { start: "2024-01-03", end: "2024-02-02", value: -20, mdd: -30, benchmarkValue: -10 },
    { start: "2024-01-04", end: "2024-02-05", value: 4, mdd: -1, benchmarkValue: null },
  ];

  it("평균·중앙값·최저·최고·손실 비율·MDD 평균·최악과 해당 창을 요약해야 함", () => {
    const s = summarizeRollingWindows(1, points);
    expect(s).not.toBeNull();
    expect(s!.count).toBe(3);
    expect(s!.meanReturn).toBeCloseTo(-2, 6);
    expect(s!.medianReturn).toBe(4);
    expect(s!.minReturn).toBe(-20);
    expect(s!.minReturnWindow).toEqual({ start: "2024-01-03", end: "2024-02-02" });
    expect(s!.maxReturn).toBe(10);
    expect(s!.maxReturnWindow).toEqual({ start: "2024-01-02", end: "2024-02-01" });
    expect(s!.lossRatio).toBeCloseTo(33.3333, 3);
    expect(s!.meanMdd).toBeCloseTo(-12, 6);
    expect(s!.worstMdd).toBe(-30);
    expect(s!.worstMddWindow).toEqual({ start: "2024-01-03", end: "2024-02-02" });
    expect(s!.annualized).toBe(false);
    // 하위/상위 5% — 선형 보간 분위(정렬 [-20, 4, 10])
    expect(s!.p5Return).toBeCloseTo(-20 + (4 - -20) * 0.1, 6);
    expect(s!.p95Return).toBeCloseTo(4 + (10 - 4) * 0.9, 6);
  });

  it("벤치마크 초과 비율·벤치마크 평균은 벤치마크가 있는 창만으로 계산한다", () => {
    const s = summarizeRollingWindows(1, points);
    // 벤치마크 있는 창 2개: (10 > 8) 초과, (-20 > -10) 미달 → 50%
    expect(s!.benchmarkWindowCount).toBe(2);
    expect(s!.beatBenchmarkRatio).toBeCloseTo(50, 6);
    expect(s!.benchmarkMeanReturn).toBeCloseTo(-1, 6);
  });

  it("벤치마크가 전혀 없으면 초과 비율·벤치마크 평균은 null", () => {
    const s = summarizeRollingWindows(
      1,
      points.map((p) => ({ ...p, benchmarkValue: null }))
    );
    expect(s!.benchmarkWindowCount).toBe(0);
    expect(s!.beatBenchmarkRatio).toBeNull();
    expect(s!.benchmarkMeanReturn).toBeNull();
  });

  it("창이 없으면 null", () => {
    expect(summarizeRollingWindows(1, [])).toBeNull();
  });

  it("표는 창을 담을 수 있는 투자 기간만 행으로 만들어야 함", () => {
    const dates = ["2024-01-02", "2024-02-01", "2024-03-04", "2024-04-01"];
    const equity = [100, 110, 121, 133.1];
    const rows = buildRollingWindowStatsTable(dates, equity, [1, 3, 12]);
    // 1개월: 2개 창, 3개월: 04-01-3개월=01-01 < 01-02 → 창 없음, 12개월: 구간 부족
    expect(rows.map((r) => r.windowMonths)).toEqual([1]);
    expect(rows[0].count).toBe(2);
  });
});

describe("hasRollingWindowSpan", () => {
  it("구간이 창보다 길면 true", () => {
    expect(
      hasRollingWindowSpan(["2023-01-02", "2024-06-28"], 12)
    ).toBe(true);
  });

  it("구간이 창보다 짧으면 false", () => {
    expect(
      hasRollingWindowSpan(["2024-01-02", "2024-06-28"], 12)
    ).toBe(false);
  });

  it("데이터가 1개 이하이면 false", () => {
    expect(hasRollingWindowSpan(["2024-01-02"], 1)).toBe(false);
    expect(hasRollingWindowSpan([], 1)).toBe(false);
  });
});

describe("연환산(12개월 초과 창)", () => {
  it("12개월 이하 창은 누적, 초과 창은 연환산", () => {
    expect(isAnnualizedWindow(12)).toBe(false);
    expect(isAnnualizedWindow(24)).toBe(true);
    expect(toDisplayReturn(50, 12)).toBe(50);
    // 2년에 +100% → 연 41.42%
    expect(toDisplayReturn(100, 24)).toBeCloseTo((Math.SQRT2 - 1) * 100, 6);
    // 3년에 +33.1% → 연 10%
    expect(toDisplayReturn(33.1, 36)).toBeCloseTo(10, 6);
    // 전액 손실은 -100%로 고정(음수 밑의 거듭제곱 방지)
    expect(toDisplayReturn(-100, 24)).toBe(-100);
  });

  it("2년 창의 지점 수익률·통계는 연환산 값이고 최저·최고 창은 누적과 같은 창이다", () => {
    // 2022-01-03 ~ 2024-01-03 매월 초 — 마지막 지점만 2년 창을 담는다
    const dates: string[] = [];
    const equity: number[] = [];
    for (let i = 0; i <= 24; i++) {
      const y = 2022 + Math.floor(i / 12);
      const m = (i % 12) + 1;
      dates.push(`${y}-${String(m).padStart(2, "0")}-03`);
      equity.push(100 * Math.pow(1.21, i / 24)); // 2년 동안 +21% → 연 10%
    }
    const points = buildRollingWindowPoints(dates, equity, 24);
    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({ start: "2022-01-03", end: "2024-01-03" });
    expect(points[0].value).toBeCloseTo(10, 6);
    const rows = buildRollingWindowStatsTable(dates, equity, [12, 24]);
    expect(rows.map((r) => [r.windowMonths, r.annualized])).toEqual([[12, false], [24, true]]);
    expect(rows[1].meanReturn).toBeCloseTo(10, 6);
    expect(rows[1].minReturnWindow).toEqual({ start: "2022-01-03", end: "2024-01-03" });
  });
});

describe("벤치마크 롤링 수익률", () => {
  const dates = ["2024-01-02", "2024-01-15", "2024-02-05", "2024-02-20"];
  const equity = [100, 110, 121, 120];

  it("같은 창의 벤치마크 수익률을 함께 계산하고 결측 끝점은 null로 둔다", () => {
    const benchmark = [200, 210, 220, null];
    const points = buildRollingWindowPoints(dates, equity, 1, benchmark);
    // 02-05 창(01-02→02-05): 전략 21%, 벤치마크 220/200-1=10%
    // 02-20 창(01-15→02-20): 벤치마크 종료 결측 → null
    expect(points).toHaveLength(2);
    expect(points[0].benchmarkValue).toBeCloseTo(10, 6);
    expect(points[1].benchmarkValue).toBeNull();
    const series = buildRollingReturnSeries(dates, equity, 1, benchmark);
    expect(series[0].benchmark).toBeCloseTo(10, 6);
    expect(series[1].benchmark).toBeNull();
  });

  it("벤치마크를 넘기지 않으면 모두 null", () => {
    const points = buildRollingWindowPoints(dates, equity, 1);
    expect(points.every((p) => p.benchmarkValue === null)).toBe(true);
  });

  it("벤치마크 기준값이 0 이하이면 그 창의 벤치마크는 null(전략 수익률은 유지)", () => {
    const points = buildRollingWindowPoints(dates, equity, 1, [0, 210, 220, 230]);
    expect(points[0].value).toBeCloseTo(21, 6);
    expect(points[0].benchmarkValue).toBeNull();
  });
});

describe("quantile", () => {
  it("선형 보간 분위", () => {
    expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3);
    expect(quantile([1, 2, 3, 4], 0.5)).toBe(2.5);
    expect(quantile([10], 0.05)).toBe(10);
    expect(quantile([0, 100], 0.95)).toBeCloseTo(95, 6);
    expect(Number.isNaN(quantile([], 0.5))).toBe(true);
  });
});
