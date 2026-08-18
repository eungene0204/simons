import { t } from "@/lib/i18n";
function isExperimentEvidenceCopy(body: string) {
  return (
    (body.includes("입력 하신 전략과 비슷한 전략으로 테스트 해본 결과") && body.includes("중앙값")) ||
    (body.includes("제안 주신 전략과 비슷한 전략") && body.includes("중앙값")) ||
    (body.includes("비슷한 ") && body.includes("실험에서") && body.includes("중앙값")) ||
    (body.includes("현재 조건과 가까운 실험군") && body.includes("중앙값"))
  );
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

function removeInternalCopy(body: string) {
  return body
    .replace(/confidence는\s+[a-z]+\s*입니다\./gi, "")
    .replace(/실험 데이터의 confidence가 낮아 이 근거만으로는 확신하기 어렵습니다\./gi, "")
    .replace(/근거 수준은\s+[^.。]+[.。]/gi, "")
    .replace(/근거 수준이 낮아\s+[^.。]+[.。]/gi, "")
    .replace(/확신하기 어렵습니다[.。]/gi, "")
    .replace(/이 내용은 투자 추천이 아니라 전략 검증\/리스크 관리 근거입니다\./gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

function preserveExperimentEvidence(body: string) {
  const cleaned = removeInternalCopy(body).replace(
    "제안 주신 전략과 비슷한 전략의 결과가 ",
    "입력 하신 전략과 비슷한 전략으로 테스트 해본 결과 "
  );

  if (cleaned.includes("비슷한 실험 데이터가 부족합니다")) {
    return cleaned.replace(
      "비슷한 실험 데이터가 부족합니다. 현재 전략은 추가 백테스트로 먼저 검증하세요.",
      "비슷한 실험 데이터가 부족하므로 현재 전략은 추가 백테스트로 먼저 검증하세요."
    );
  }

  if (cleaned.includes("실험 샘플이 부족해 확신하기 어렵습니다")) {
    return cleaned;
  }

  return cleaned;
}

function firstSentence(body: string) {
  const koreanMatch = body.match(/^.+?(?:입니다|합니다|됩니다|세요)\./);
  if (koreanMatch?.[0]) return koreanMatch[0].trim();
  const match = body.match(/^.+?[!?。]/);
  return match?.[0]?.trim() || body;
}

function extractCandidateSentence(body: string) {
  const match = body.match(/우선 비교할 후보는\s+.+?입니다\./);
  return match?.[0]?.trim() || "";
}

export function formatCoachAdviceBody(body: string) {
  const normalized = body.replace(/\s+/g, " ").trim();

  if (isExperienceMemoryCopy(normalized)) {
    return t("기본안을 그대로 돌린 뒤, 손절 8~10%, 최대 보유기간 20일, 종목 수 5~10개 분산안을 각각 비교해 어느 조건이 손실을 줄이는지 먼저 확인하세요.");
  }

  if (isExperimentEvidenceCopy(normalized)) {
    return preserveExperimentEvidence(normalized);
  }

  if (
    normalized.includes("비슷한 실험 데이터가 부족합니다") ||
    normalized.includes("실험 샘플이 부족해 확신하기 어렵습니다")
  ) {
    return t("지금 전략은 근거가 부족합니다. 기본안을 먼저 돌린 뒤 손절, 보유기간, 종목 수 조건을 하나씩만 바꿔 비교하세요.");
  }

  return removeInternalCopy(normalized);
}

export function formatPrimaryCoachAdviceBody(body: string) {
  const normalized = formatCoachAdviceBody(body);

  if (isExperimentEvidenceCopy(normalized)) {
    return normalized;
  }

  const sentences = normalized.match(/[^.!?。]+[.!?。]?/g) || [normalized];
  return sentences.slice(0, 2).join(" ").replace(/\s+/g, " ").trim();
}
