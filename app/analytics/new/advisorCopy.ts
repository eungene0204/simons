function parseMetric(body: string, label: "CAGR" | "Sharpe" | "MDD") {
  const match = body.match(new RegExp(`${label} 중앙값\\s*(-?\\d+(?:\\.\\d+)?)`));
  return match ? Number(match[1]) : null;
}

function parseSampleCount(body: string) {
  const match = body.match(/비슷한\s+(\d+)개\s+실험/);
  return match ? Number(match[1]) : null;
}

function isExperimentEvidenceCopy(body: string) {
  return body.includes("비슷한 ") && body.includes("실험에서") && body.includes("중앙값");
}

function isExperienceMemoryCopy(body: string) {
  return (
    body.includes("Experience Memory") ||
    body.includes("ChromaDB") ||
    body.includes("result_status=") ||
    body.includes("similarity=") ||
    body.includes("재사용 가능한 핵심 교훈")
  );
}

function buildEvidenceSummary(body: string) {
  const sampleCount = parseSampleCount(body);
  const cagr = parseMetric(body, "CAGR");
  const sharpe = parseMetric(body, "Sharpe");
  const mdd = parseMetric(body, "MDD");

  const hasWeakPerformanceSignal =
    (typeof cagr === "number" && cagr < 0) ||
    (typeof sharpe === "number" && sharpe < 0) ||
    (typeof mdd === "number" && mdd <= -20);

  const hasStrongPerformanceSignal =
    (typeof cagr === "number" && cagr > 8) &&
    (typeof sharpe === "number" && sharpe > 0.7) &&
    (typeof mdd === "number" && mdd > -15);

  const sampleText = typeof sampleCount === "number" ? `유사한 전략 실험 ${sampleCount}건` : "유사한 전략 실험";

  if (hasWeakPerformanceSignal) {
    return `${sampleText}을 보면 수익성은 낮고 손실 폭은 큰 편이었습니다.`;
  }

  if (hasStrongPerformanceSignal) {
    return `${sampleText}을 보면 기본 성과 흐름은 나쁘지 않았습니다.`;
  }

  return `${sampleText}을 보면 성과가 뚜렷하게 안정적이라고 보긴 어려웠습니다.`;
}

export function formatCoachAdviceTitle(title: string) {
  if (title.trim() === "유사 전략 경험 기반 점검") {
    return "비교 실험 제안";
  }

  return title;
}

export function formatCoachAdviceBody(body: string) {
  const normalized = body.replace(/\s+/g, " ").trim();

  if (isExperienceMemoryCopy(normalized)) {
    return "비슷한 과거 전략은 성과가 불안정했습니다. 기본안을 그대로 돌린 뒤, 손절 8~10%, 최대 보유기간 20일, 종목 수 5~10개 분산안을 각각 비교해 어느 조건이 손실을 줄이는지 먼저 확인하세요.";
  }

  if (isExperimentEvidenceCopy(normalized)) {
    const evidenceSummary = buildEvidenceSummary(normalized);
    return `${evidenceSummary} 지금 전략은 바로 사용하기보다 추가 백테스트로 먼저 검증하는 편이 안전합니다.`;
  }

  if (
    normalized.includes("비슷한 실험 데이터가 부족합니다") ||
    normalized.includes("실험 샘플이 부족해 확신하기 어렵습니다")
  ) {
    return "유사 사례가 충분하지 않아, 지금 전략은 바로 사용하기보다 추가 백테스트로 먼저 검증하는 편이 안전합니다.";
  }

  return normalized
    .replace(/confidence는\s+[a-z]+\s*입니다\./gi, "")
    .replace(/실험 데이터의 confidence가 낮아 이 근거만으로는 확신하기 어렵습니다\./gi, "")
    .replace(/이 내용은 투자 추천이 아니라 전략 검증\/리스크 관리 근거입니다\./gi, "")
    .replace(/\s+/g, " ")
    .trim();
}
