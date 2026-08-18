import { t } from "@/lib/i18n";
// 결정론적 검증 agent가 내려주는 누락 필드(category "missing_field")를 사용자 친화적인
// 한국어 명사로 매핑한다. 검증 JSON은 field로 어떤 조건이 비었는지 알려주므로, 딱딱한
// "~ 조건이 정의되어 있지 않습니다" 나열 대신 다음에 입력할 조건 하나만 보여준다.
// 표시 순서와 한국어 명사를 함께 정의해 백엔드 이슈 순서와 무관한 질문을 만든다.
const MISSING_FIELD_LABELS: Array<[string, string]> = [
  ["universe", "유니버스"],
  ["entry_rule", "진입"],
  ["exit_rule", "청산"],
  ["rebalance_rule", "리밸런싱"],
  ["stop_loss_pct", "손절"],
  ["take_profit_pct", "익절"],
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

// 누락 조건은 한 번에 하나만 입력하도록 안내하고, 그 외 이슈는 사실 그대로 덧붙인다.
// 보여줄 내용이 없으면 ""를 반환해 호출부가 valid/fallback을 처리한다.
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
      otherMessages.push(t(message.trim()));
    }
  }

  const firstMissingNoun = missingFields
    .sort((a, b) => MISSING_FIELD_ORDER.indexOf(a) - MISSING_FIELD_ORDER.indexOf(b))
    .map((field) => MISSING_FIELD_LABEL_BY_FIELD.get(field)!)
    .at(0);

  const parts: string[] = [];
  if (firstMissingNoun) {
    parts.push(t("{0} 조건을 입력해 주세요.", t(firstMissingNoun)));
  }
  if (otherMessages.length > 0) {
    parts.push(otherMessages.join("\n"));
  }
  if (parts.length === 0) return "";

  return parts.join("\n\n");
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
          ? t("전략 정의가 완료되었습니다. 백테스트를 실행할 수 있습니다.")
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
