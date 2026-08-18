export interface MonthlyReturnCell {
  month: number;
  value: number | null;
}

export interface MonthlyReturnRow {
  year: string;
  months: MonthlyReturnCell[];
  annualReturn: number | null;
}

const MONTHS = Array.from({ length: 12 }, (_, index) => index + 1);

export function buildMonthlyReturnTableData(
  monthlyReturns: Record<string, Record<string, number>>,
  limitYears = 10
): MonthlyReturnRow[] {
  const years = Object.keys(monthlyReturns)
    .sort((a, b) => Number(b) - Number(a))
    .slice(0, limitYears);

  return years.map((year) => {
    const months = MONTHS.map((month) => {
      const raw = monthlyReturns[year]?.[String(month)];
      return {
        month,
        value: typeof raw === "number" ? raw : null,
      };
    });

    const annualReturn = months.reduce((acc, cell) => {
      if (cell.value == null) return acc;
      return acc * (1 + cell.value / 100);
    }, 1);

    return {
      year,
      months,
      annualReturn: annualReturn === 1 ? null : (annualReturn - 1) * 100,
    };
  });
}

/**
 * 표 위 막대 차트용 시계열 — 표에 보이는 행(최근 N년)만, 값이 있는 달만 오름차순으로 편다.
 * 각 달은 그 달 1일에 놓여 x축에서 한 연도가 막대 12개가 된다.
 */
export function buildMonthlyReturnSeries(
  rows: MonthlyReturnRow[]
): { time: string; value: number }[] {
  return [...rows]
    .sort((a, b) => Number(a.year) - Number(b.year))
    .flatMap((row) =>
      row.months
        .filter((cell) => cell.value != null)
        .map((cell) => ({
          time: `${row.year}-${String(cell.month).padStart(2, "0")}-01`,
          value: cell.value as number,
        }))
    );
}
