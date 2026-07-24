import {
  formatMarketCapValue,
  getRankingLabel,
  getSignalLabel,
  METRIC_LABELS,
  UNIVERSE_LABELS,
  type ParsedSummary,
} from "./strategySummary";
import { hasExplicitUniverse } from "./backtestReadiness";

const KO_NUMBER_FORMAT = new Intl.NumberFormat("ko-KR");

const OPERATOR_CLAUSES: Record<string, string> = {
  "<": "미만",
  "<=": "이하",
  ">": "초과",
  ">=": "이상",
};

// 한국어로 읽었을 때 받침으로 끝나는 라틴 문자(엘·엠·엔·알)와 숫자(영·일·삼·육·칠·팔).
const CONSONANT_ENDING_CHARS = new Set(["l", "m", "n", "r", "0", "1", "3", "6", "7", "8"]);

// 주격 조사(이/가) 선택 — 마지막 글자의 받침 유무로 판정한다.
function subjectParticle(word: string): "이" | "가" {
  const last = word.trim().slice(-1).toLowerCase();
  const code = last.charCodeAt(0);
  if (code >= 0xac00 && code <= 0xd7a3) {
    return (code - 0xac00) % 28 > 0 ? "이" : "가";
  }
  return CONSONANT_ENDING_CHARS.has(last) ? "이" : "가";
}

// 재무 필터를 서술절로 만든다: "PER이 10 이하", "순이익이 흑자".
function filterClause(filter: { metric: string; operator: string; value: number }): string {
  // EPS·영업이익 부호 필터는 '흑자/적자' 키워드의 표현형 — 사용자 어휘로 되돌려준다.
  if (filter.metric === "eps" && filter.value === 0) {
    if (filter.operator === ">") return "순이익이 흑자";
    if (filter.operator === "<") return "순이익이 적자";
  }
  if (filter.metric === "ebit" && filter.value === 0) {
    if (filter.operator === ">") return "영업이익이 흑자";
    if (filter.operator === "<") return "영업이익이 적자";
  }
  const label = METRIC_LABELS[filter.metric] ?? filter.metric;
  let value: string;
  if (filter.metric === "market_cap") {
    value = formatMarketCapValue(filter.value);
  } else if (filter.metric === "trading_value") {
    value = `${KO_NUMBER_FORMAT.format(filter.value)}억`;
  } else {
    value = String(filter.value);
  }
  const operator = OPERATOR_CLAUSES[filter.operator] ?? filter.operator;
  return `${label}${subjectParticle(label)} ${value} ${operator}`;
}

// 진입 신호를 매수 트리거절로 만든다: "MA 골든크로스가 발생하면" / "RSI 30 이하일 때".
function signalTriggerClause(labels: string[]): string {
  const joined = labels.join(" · ");
  if (/(?:이하|이상|미만|초과)$/.test(joined)) return `${joined}일 때`;
  if (/예측$/.test(joined)) return `${joined} 신호가 발생하면`;
  return `${joined}${subjectParticle(joined)} 발생하면`;
}

// 대상 범위 접두어: "반도체 업종에서" / "KOSDAQ에서". 시장을 명시하지 않았으면 생략한다
// (기본값 양시장을 굳이 되풀이하지 않는다).
function buildScope(parsed: ParsedSummary, prompt: string): string | null {
  const universeLabels = hasExplicitUniverse(prompt, parsed)
    ? parsed.universe.map((u) => UNIVERSE_LABELS[u.toLowerCase()] ?? UNIVERSE_LABELS[u] ?? u)
    : [];
  const sectors = Array.isArray(parsed.sector)
    ? parsed.sector
    : parsed.sector
      ? [parsed.sector]
      : [];
  if (sectors.length > 0) {
    const prefix = universeLabels.length > 0 ? `${universeLabels.join("·")} ` : "";
    return `${prefix}${sectors.join("·")} 업종에서`;
  }
  if (universeLabels.length > 0) return `${universeLabels.join("·")}에서`;
  return null;
}

/**
 * 파싱된 전략을 자연어 한 문장으로 재정리한다 — 첫 응답을 "…전략이군요."로 시작해
 * 사용자의 자연어가 백테스트 가능한 전략 개념으로 어떻게 이해됐는지 되돌려주는 용도.
 * 매수(종목 선정) 기준이 없으면 재정리할 내용이 없으므로 null을 반환한다.
 * 지정 종목 백테스트는 별도 흐름(빌더·되묻기)으로 안내되므로 제외한다.
 */
export function buildStrategyRestatement(
  parsed: ParsedSummary | null | undefined,
  prompt = "",
): string | null {
  if (!parsed) return null;
  if (parsed.target_symbols && parsed.target_symbols.length > 0) return null;

  const clauses = (parsed.fundamental_filters ?? []).map(filterClause);
  const signalLabels = (parsed.entry_signals ?? []).map((signal) =>
    getSignalLabel(signal, "entry"),
  );
  const rankingLabel = getRankingLabel(parsed);

  let core: string;
  if (signalLabels.length > 0) {
    const leadParts: string[] = [];
    if (clauses.length > 0) leadParts.push(`${clauses.join("이고 ")}인`);
    if (rankingLabel) leadParts.push(rankingLabel);
    const lead = leadParts.length > 0 ? `${leadParts.join(" ")} 종목 중에서 ` : "";
    core = `${lead}${signalTriggerClause(signalLabels)} 매수하는`;
  } else if (rankingLabel) {
    const lead = clauses.length > 0 ? `${clauses.join("이고 ")}인 종목 중에서 ` : "";
    core = `${lead}${rankingLabel} 종목을 매수하는`;
  } else if (clauses.length > 0) {
    // "A인 종목 중에서 B인 종목을" — 첫 조건으로 모집단을 좁히고 나머지로 선별하는 어순.
    const chain =
      clauses.length === 1
        ? clauses[0]
        : `${clauses[0]}인 종목 중에서 ${clauses.slice(1).join("이고 ")}`;
    core = `${chain}인 종목을 매수하는`;
  } else {
    return null;
  }

  const scope = buildScope(parsed, prompt);
  return `${scope ? `${scope} ` : ""}${core} 전략이군요.`;
}
