// 결정론적 검증 agent가 내려주는 누락 필드(category "missing_field")를 사용자 친화적인
// 한국어 명사로 매핑한다. 검증 JSON은 field로 어떤 조건이 비었는지 알려주므로, 딱딱한
// "~ 조건이 정의되어 있지 않습니다" 나열 대신 한 문장으로 부드럽게 묶어 보여준다.
// 표시 순서(손절·익절 → 청산 → 나머지)와 한국어 명사를 함께 정의한다. 백엔드가 내려주는
// 이슈 순서와 무관하게 항상 이 순서로 묶어, 사용자에게 일관된 문구를 보여준다.
const MISSING_FIELD_LABELS: Array<[string, string]> = [
  ["stop_loss_pct", "손절"],
  ["take_profit_pct", "익절"],
  ["exit_rule", "청산"],
  ["universe", "유니버스"],
  ["entry_rule", "진입"],
  ["rebalance_rule", "리밸런싱"],
  ["position_sizing", "매수 수량"],
  ["max_positions", "최대 보유 종목 수"],
  ["data_frequency", "데이터 주기"],
  ["backtest_period", "백테스트 기간"],
];
const MISSING_FIELD_LABEL_BY_FIELD = new Map(MISSING_FIELD_LABELS);
const MISSING_FIELD_ORDER = MISSING_FIELD_LABELS.map(([field]) => field);

interface ValidationIssue {
  field?: unknown;
  category?: unknown;
  message?: unknown;
}

// 검증 이슈 목록을 친근한 안내 문구로 조립한다. 비어 있는(누락) 조건은 명사로 묶어
// "~ 조건이 비어 있지만 현재 상태로도 백테스트를 실행할 수 있습니다"로, 그 외 이슈는
// 사실 그대로 덧붙인다. 보여줄 내용이 없으면 ""를 반환해 호출부가 valid/fallback을 처리한다.
function buildValidationMessage(issues: unknown[]): string {
  const missingFields: string[] = [];
  const otherMessages: string[] = [];

  for (const issue of issues) {
    if (!issue || typeof issue !== "object") continue;
    const { field, category, message } = issue as ValidationIssue;
    const label = typeof field === "string" ? MISSING_FIELD_LABEL_BY_FIELD.get(field) : undefined;
    if (category === "missing_field" && typeof field === "string" && label) {
      if (!missingFields.includes(field)) missingFields.push(field);
      continue;
    }
    if (typeof message === "string" && message.trim()) {
      otherMessages.push(message.trim());
    }
  }

  const missingNouns = missingFields
    .sort((a, b) => MISSING_FIELD_ORDER.indexOf(a) - MISSING_FIELD_ORDER.indexOf(b))
    .map((field) => MISSING_FIELD_LABEL_BY_FIELD.get(field)!);

  const parts: string[] = [];
  if (missingNouns.length > 0) {
    parts.push(`${missingNouns.join(", ")} 조건이 비어 있지만 현재 상태로도 백테스트를 실행할 수 있습니다.`);
  }
  if (otherMessages.length > 0) {
    parts.push(otherMessages.join("\n"));
    if (missingNouns.length === 0) {
      parts.push("현재 상태로도 백테스트를 실행할 수 있습니다.");
    }
  }
  if (parts.length === 0) return "";

  return [
    "전략이 아직 완전히 구성되지는 않았습니다.",
    "",
    parts.join("\n\n"),
    "",
    "먼저 결과를 확인해 보고, 필요하면 나중에 조건을 추가해 보세요.",
    "",
    "백테스트를 시작할까요?",
  ].join("\n");
}

export function normalizeCoachMessage(value: unknown, fallback: string): string {
  if (typeof value !== "string") {
    return fallback;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return fallback;
  }

  const codeBlockMatch = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/);
  const candidate = codeBlockMatch ? codeBlockMatch[1].trim() : trimmed;

  if (candidate.startsWith("{") && candidate.endsWith("}")) {
    try {
      const parsed = JSON.parse(candidate);
      if (typeof parsed?.is_valid === "boolean" && Array.isArray(parsed?.issues)) {
        const built = buildValidationMessage(parsed.issues);
        if (built) {
          return built;
        }

        return parsed.is_valid
          ? "전략 정의가 완료되었습니다. 백테스트를 실행할 수 있습니다."
          : fallback;
      }
      if (typeof parsed?.message === "string" && parsed.message.trim()) {
        return parsed.message.trim();
      }
    } catch {
      return trimmed;
    }
  }

  return trimmed;
}
