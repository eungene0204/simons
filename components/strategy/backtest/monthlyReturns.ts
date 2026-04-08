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
