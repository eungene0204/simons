/**
 * 전략 타입 추론 유틸리티
 *
 * DSL 조건 블록 (1차) + 전략명/설명 텍스트 (2차) 를 분석해
 * 가장 적합한 전략 타입을 반환한다.
 *
 * 타입 목록: AI전략 | 가치투자 | 모멘텀 | 기술분석 | 수급전략 | 기타
 */

export type StrategyType = "AI전략" | "가치투자" | "모멘텀" | "기술분석" | "수급전략" | "기타";

interface ConditionLike {
  type?: string;
  id?: string;
}

interface ConditionGroupLike {
  conditions?: ConditionLike[];
  filters?: Record<string, unknown>;
}

interface DslLike {
  entry?: ConditionGroupLike;
  exit?: ConditionGroupLike;
}

/** DSL의 entry/exit 조건 블록에서 사용된 모든 id/type 문자열 수집 */
function collectDslKeys(dsl: DslLike): string[] {
  const keys: string[] = [];
  const collect = (group?: ConditionGroupLike) => {
    if (!group) return;
    for (const c of group.conditions ?? []) {
      if (c.id) keys.push(c.id.toLowerCase());
      if (c.type) keys.push(c.type.toLowerCase());
    }
    for (const k of Object.keys(group.filters ?? {})) {
      keys.push(k.toLowerCase());
    }
  };
  collect(dsl?.entry);
  collect(dsl?.exit);
  return keys;
}

/** 텍스트(전략명 + 설명)에서 소문자 키워드 목록 추출 */
function textKeywords(name: string, description: string): string[] {
  return (name + " " + description).toLowerCase().split(/[\s,.\-_/|]+/).filter(Boolean);
}

/**
 * 전략 타입 추론
 * @param name        전략 이름
 * @param description 전략 설명
 * @param dsl         전략 DSL 객체 (JSON.parse 결과)
 */
export function inferStrategyType(
  name: string,
  description: string,
  dsl: unknown
): StrategyType {
  const dslKeys = collectDslKeys((dsl as DslLike) ?? {});
  const txtKw = textKeywords(name, description);
  const all = [...dslKeys, ...txtKw];

  // ── DSL 1차 판정 (텍스트보다 신뢰도 높음) ─────────────────────────
  const has = (patterns: string[]) =>
    dslKeys.some((k) => patterns.some((p) => k.includes(p)));

  if (has(["ai_model", "ai_drop"])) return "AI전략";
  if (has(["per", "pbr", "psr", "pcr", "roe", "roa", "debt_ratio", "market_cap",
    "current_ratio", "quick_ratio", "reserve_ratio", "margin", "growth",
    "cf_amount"])) return "가치투자";
  if (has(["investor_net_buy"])) return "수급전략";
  if (has(["breakout", "ma_crossover", "macd", "volume_spike"])) return "모멘텀";
  if (has(["rsi", "bollinger", "stochastic", "cci", "adx", "ema"])) return "기술분석";

  // ── 텍스트 2차 판정 ────────────────────────────────────────────────
  const hasText = (patterns: string[]) =>
    all.some((k) => patterns.some((p) => k.includes(p)));

  if (hasText(["ai", "머신러닝", "딥러닝", "인공지능", "예측모델", "xgboost", "transformer"])) return "AI전략";
  if (hasText(["가치", "저pbr", "저per", "배당", "value", "fundamental", "재무", "순자산", "영업이익"])) return "가치투자";
  if (hasText(["수급", "외국인", "기관", "개인순매수", "net_buy", "매수세"])) return "수급전략";
  if (hasText(["모멘텀", "momentum", "추세", "breakout", "돌파", "52주", "신고가", "macd", "이평선교차", "골든크로스"])) return "모멘텀";
  if (hasText(["rsi", "볼린저", "bollinger", "기술적", "technical", "stochastic", "cci", "adx", "ema", "이동평균"])) return "기술분석";

  return "기타";
}
