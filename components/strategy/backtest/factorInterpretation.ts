import type { AnalyticsResult } from "@/types/strategy";

type Exposure = AnalyticsResult["factorExposure"];
type Loading = NonNullable<Exposure["loadings"]>[number];

const FACTOR_STYLES: Record<string, { positive: [string, string]; negative: [string, string] }> = {
  MKT: { positive: ["시장과 같은 방향", "the same direction as the market"], negative: ["시장과 반대 방향", "the opposite direction from the market"] },
  SMB: { positive: ["소형주", "smaller companies"], negative: ["대형주", "larger companies"] },
  HML: { positive: ["PBR이 낮은 종목", "lower-PBR stocks"], negative: ["PBR이 높은 종목", "higher-PBR stocks"] },
  MOM: { positive: ["최근 상대적으로 오른 종목", "recent outperformers"], negative: ["최근 상대적으로 덜 오른 종목", "recent underperformers"] },
};

const isFiniteNumber = (value: number | null | undefined): value is number =>
  value != null && Number.isFinite(value);

function style(loading: Loading, english: boolean): string | null {
  if (!isFiniteNumber(loading.beta) || loading.beta === 0) return null;
  const descriptions = FACTOR_STYLES[loading.factor];
  if (!descriptions) return null;
  return (loading.beta > 0 ? descriptions.positive : descriptions.negative)[english ? 1 : 0];
}

function isClear(loading: Loading): boolean {
  return isFiniteNumber(loading.tStat) && Math.abs(loading.tStat) >= 1.96;
}

function signed(value: number, digits: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function interpretFactor(loading: Loading, english: boolean): string {
  const description = style(loading, english);
  if (!description || !isFiniteNumber(loading.tStat)) {
    return english ? "Insufficient data to interpret this exposure." : "노출을 해석할 자료가 부족합니다.";
  }
  const movement = loading.factor === "MKT"
    ? (english ? `The strategy tended to move in ${description}.` : `${description}으로 움직이는 편이었습니다.`)
    : (english ? `The strategy tended to move with ${description}.` : `${description}의 움직임을 따라간 편입니다.`);
  return english
    ? `${movement} ${isClear(loading) ? "This pattern is clear in the historical data." : "The data is too uncertain to call this a clear pattern."}`
    : `${movement} ${isClear(loading) ? "과거 자료에서 이 관계가 뚜렷합니다." : "다만 이번 자료만으로는 분명하다고 보기 어렵습니다."}`;
}

export function explainFactorEstimate(exposure: Exposure, english: boolean): string {
  const example = exposure.loadings?.find((loading) => loading.factor === "MKT" && isFiniteNumber(loading.beta) && loading.beta !== 0)
    ?? exposure.loadings?.find((loading) => FACTOR_STYLES[loading.factor] && isFiniteNumber(loading.beta) && loading.beta !== 0);
  const introduction = english
    ? "Beta (β) shows how strongly the strategy moved with a factor after accounting for the others. The t-value shows how clear that pattern is in this historical data."
    : "베타(β)는 다른 팩터의 영향을 빼고 얼마나 함께 움직였는지 보여줍니다. t값은 그 관계가 이번 과거 자료에서 얼마나 뚜렷한지 보여줍니다.";
  if (!example || !isFiniteNumber(example.beta)) return introduction;
  const labels: Record<string, [string, string]> = { MKT: ["시장", "market"], SMB: ["규모", "size"], HML: ["가치", "value"], MOM: ["모멘텀", "momentum"] };
  const label = labels[example.factor];
  if (!label) return introduction;
  const direction = example.beta >= 0 ? (english ? "higher" : "높게") : (english ? "lower" : "낮게");
  const illustration = english
    ? `For example, ${label[1]} β ${signed(example.beta, 2)} means that when the ${label[1]} factor return was 1 percentage point higher, the strategy's daily return was about ${Math.abs(example.beta).toFixed(2)} percentage points ${direction} on average, after accounting for the other factors.`
    : `예를 들어 ${label[0]} β ${signed(example.beta, 2)}는 다른 팩터의 영향을 빼고 ${label[0]} 수익률이 1%p 높을 때 전략의 하루 수익률이 평균 ${Math.abs(example.beta).toFixed(2)}%p ${direction} 추정됐다는 뜻입니다.`;
  return `${introduction} ${illustration}`;
}

export function summarizeFactorPattern(exposure: Exposure, english: boolean): string {
  const loadings = exposure.loadings ?? [];
  const parts: string[] = [];
  const clearStyles = loadings.filter((loading) => loading.factor !== "MKT" && isClear(loading))
    .map((loading) => style(loading, english)).filter((value): value is string => value != null);
  if (clearStyles.length) {
    parts.push(english
      ? `In the historical data, the strategy clearly moved with ${clearStyles.join(" and ")}.`
      : `과거에는 ${clearStyles.map((description) => `${description}의 움직임`).join("과 ")}을 따라가는 경향이 뚜렷했습니다.`);
  }
  const market = loadings.find((loading) => loading.factor === "MKT");
  if (market && isClear(market) && style(market, english)) {
    parts.push(english
      ? `It also clearly moved in ${style(market, english)}.`
      : `${style(market, english)}으로 움직이는 경향도 뚜렷했습니다.`);
  } else if (market && isFiniteNumber(market.tStat) && style(market, english)) {
    parts.push(english
      ? `The market pattern appears in the numbers, but is not clear enough to rely on.`
      : `시장과의 관계도 수치상 보이지만, 이번 자료만으로는 분명하다고 보기 어렵습니다.`);
  }
  const unclear = loadings.filter((loading) => loading.factor !== "MKT" && isFiniteNumber(loading.tStat) && !isClear(loading) && style(loading, english));
  for (const loading of unclear) {
    const description = style(loading, english);
    parts.push(english
      ? `A link with ${description} appears in the numbers, but the data is too uncertain to call it a clear pattern.`
      : `${description} 쪽 성향도 수치상 보이지만, 이번 자료만으로는 분명하다고 보기 어렵습니다.`);
  }
  return parts.join(" ") || (english ? "There is not enough data to describe the factor patterns." : "어떤 종목의 움직임을 따라갔는지 판단할 자료가 부족합니다.");
}

export function summarizeFactorStatistics(exposure: Exposure, english: boolean): string {
  const parts: string[] = [];
  if (isFiniteNumber(exposure.r2) && exposure.r2 >= 0 && exposure.r2 <= 1) {
    const percent = Math.round(exposure.r2 * 100);
    parts.push(english
      ? `These factors explain about ${percent}% of the strategy's day-to-day return changes in this sample (R²). The rest is not automatically alpha.`
      : `위 팩터들은 이 자료에서 하루 수익률의 오르내림을 약 ${percent}% 설명합니다(R²). 나머지가 모두 알파라는 뜻은 아닙니다.`);
  }
  if (isFiniteNumber(exposure.alphaAnnualPct)) {
    parts.push(english
      ? `Annualized alpha ${signed(exposure.alphaAnnualPct, 2)}% is an estimate of the return left after accounting for these factors, expressed as a yearly rate.`
      : `연환산 알파 ${signed(exposure.alphaAnnualPct, 2)}%는 이 팩터들로 설명되지 않는 수익을 1년 기준으로 바꾼 추정치입니다.`);
  }
  if (isFiniteNumber(exposure.alphaTStat)) {
    if (Math.abs(exposure.alphaTStat) < 1.96) {
      parts.push(english
        ? `Its t-value is ${signed(exposure.alphaTStat, 1)}, so this sample does not clearly show extra gains or losses after accounting for the factors.`
        : `하지만 알파의 t값이 ${signed(exposure.alphaTStat, 1)}이라, 이 자료만으로는 별도의 추가 수익이나 손실이 있었다고 말하기 어렵습니다.`);
    } else if (isFiniteNumber(exposure.alphaAnnualPct)) {
      parts.push(english
        ? `This sample shows a clear ${exposure.alphaAnnualPct > 0 ? "positive" : exposure.alphaAnnualPct < 0 ? "negative" : "near-zero"} alpha estimate.`
        : `이번 자료에서는 ${exposure.alphaAnnualPct > 0 ? "양수" : exposure.alphaAnnualPct < 0 ? "음수" : "0에 가까운"} 알파 추정치가 뚜렷하게 나타났습니다.`);
    }
  } else if (isFiniteNumber(exposure.alphaAnnualPct)) {
    parts.push(english ? "There is no alpha t-value, so this result alone cannot show whether that estimate is clear." : "알파의 t값이 없어 이 수치가 뚜렷한지는 판단할 수 없습니다.");
  }
  return parts.join(" ") || (english ? "There is not enough data to interpret R² or alpha." : "R²와 알파를 해석할 자료가 부족합니다.");
}
