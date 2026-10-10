// "이 전략 그대로 열기" 링크 — 전략연구소 주소의 `prompt` 파라미터로 전략 문장을 넘겨받아 입력창에 채운다.
//
// 채우기만 하고 보내지 않는다. 링크를 여는 것만으로 해석·백테스트가 돌면 방문자 사용량이 의도 없이
// 소모되고, 남이 만든 링크가 방문자 이름으로 임의 문장을 실행하게 된다 — 보내기는 방문자가 누른다.
// 로그인 전 방문자가 보내면 기존 인증 게이트(문장 보관 → 로그인 → 이어서 처리)가 그대로 받는다.

export const STRATEGY_PROMPT_PARAM = "prompt";

// 예시 문장은 200자 안팎이다 — 이보다 긴 값은 링크 용도가 아니므로 채우지 않는다.
export const MAX_STRATEGY_PROMPT_LENGTH = 1000;

export function readStrategyPromptParam(params: Pick<URLSearchParams, "get">): string | null {
  const prompt = params.get(STRATEGY_PROMPT_PARAM)?.trim();
  if (!prompt || prompt.length > MAX_STRATEGY_PROMPT_LENGTH) return null;
  return prompt;
}

/** 채운 뒤 주소창에서 `prompt`만 걷어낸다(새로고침해도 다시 채우지 않게). 다른 파라미터(utm 등)는 남긴다. */
export function withoutStrategyPromptParam(pathname: string, search: string): string {
  const params = new URLSearchParams(search);
  params.delete(STRATEGY_PROMPT_PARAM);
  const rest = params.toString();
  return rest ? `${pathname}?${rest}` : pathname;
}
