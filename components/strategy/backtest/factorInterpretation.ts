import type { AnalyticsResult } from "@/types/strategy";

type Exposure = AnalyticsResult["factorExposure"];
type Loading = NonNullable<Exposure["loadings"]>[number];

const FACTOR_RETURNS: Record<string, [string, string]> = {
  MKT: ["시장 수익률", "market return"],
  SMB: ["소형주−대형주 수익률 차이", "small-minus-large return spread"],
  HML: ["저PBR−고PBR 수익률 차이", "low-minus-high PBR return spread"],
  MOM: ["모멘텀 상위−하위 수익률 차이", "high-minus-low momentum return spread"],
};

const isFiniteNumber = (value: number | null | undefined): value is number =>
  value != null && Number.isFinite(value);

function factorReturn(loading: Loading, english: boolean): string | null {
  if (!isFiniteNumber(loading.beta) || loading.beta === 0) return null;
  const descriptions = FACTOR_RETURNS[loading.factor];
  if (!descriptions) return null;
  return descriptions[english ? 1 : 0];
}

function isClear(loading: Loading): boolean {
  return isFiniteNumber(loading.tStat) && Math.abs(loading.tStat) >= 1.96;
}

function signed(value: number, digits: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function interpretFactor(loading: Loading, english: boolean): string {
  const measure = factorReturn(loading, english);
  if (!measure || !isFiniteNumber(loading.beta) || !isFiniteNumber(loading.tStat)) {
    return english ? "Insufficient data to interpret this exposure." : "노출을 해석할 자료가 부족합니다.";
  }
  const amount = Math.abs(loading.beta).toFixed(2);
  const movement = english
    ? `After accounting for the other factors, when the ${measure} was 1 percentage point higher, the strategy's daily return was estimated to be ${amount} percentage points ${loading.beta > 0 ? "higher" : "lower"} on average.`
    : `다른 팩터의 영향을 통제한 결과, ${measure}${loading.factor === "MKT" ? "이" : "가"} 1%p 높을 때 전략의 하루 수익률은 평균 ${amount}%p ${loading.beta > 0 ? "높게" : "낮게"} 추정됐습니다.`;
  return english
    ? `${movement} ${isClear(loading) ? "This estimate meets the t-value threshold." : "The data is too uncertain to call this a clear relationship."}`
    : `${movement} ${isClear(loading) ? "이 추정치는 t값 기준을 충족합니다." : "다만 이번 자료만으로는 분명하다고 보기 어렵습니다."}`;
}

export function explainFactorEstimate(exposure: Exposure, english: boolean): string {
  const example = exposure.loadings?.find((loading) => loading.factor === "MKT" && isFiniteNumber(loading.beta) && loading.beta !== 0)
    ?? exposure.loadings?.find((loading) => factorReturn(loading, english));
  const introduction = english
    ? "Beta (β) shows how strongly the strategy moved with a factor after accounting for the others. The t-value shows how clear that pattern is in this historical data."
    : "베타(β)는 다른 팩터의 영향을 빼고 얼마나 함께 움직였는지 보여줍니다. t값은 그 관계가 이번 과거 자료에서 얼마나 뚜렷한지 보여줍니다.";
  if (!example || !isFiniteNumber(example.beta)) return introduction;
  const label = factorReturn(example, english);
  if (!label) return introduction;
  const direction = example.beta >= 0 ? (english ? "higher" : "높게") : (english ? "lower" : "낮게");
  const illustration = english
    ? `For example, ${label} β ${signed(example.beta, 2)} means that when the ${label} was 1 percentage point higher, the strategy's daily return was about ${Math.abs(example.beta).toFixed(2)} percentage points ${direction} on average, after accounting for the other factors.`
    : `예를 들어 ${label} β ${signed(example.beta, 2)}는 다른 팩터의 영향을 빼고 ${label}${example.factor === "MKT" ? "이" : "가"} 1%p 높을 때 전략의 하루 수익률이 평균 ${Math.abs(example.beta).toFixed(2)}%p ${direction} 추정됐다는 뜻입니다.`;
  return `${introduction} ${illustration}`;
}

export function summarizeFactorPattern(exposure: Exposure, english: boolean): string {
  const loadings = (exposure.loadings ?? [])
    .filter((loading) => factorReturn(loading, english) && isFiniteNumber(loading.tStat));
  return loadings.map((loading) => interpretFactor(loading, english)).join(" ")
    || (english ? "There is not enough data to describe the factor relationships." : "팩터 수익률과의 관계를 해석할 자료가 부족합니다.");
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
