import { describe, expect, it } from "vitest";
import {
  buildRollingReturnSeries,
  hasRollingWindowSpan,
  subtractMonths,
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
