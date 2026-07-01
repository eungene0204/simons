// 검증이 "백테스트를 진행하시겠습니까?"로 끝났을 때, 사용자의 "네"·"진행해줘" 같은 긍정
// 응답을 분류/재파싱으로 보내지 않고 곧바로 백테스트 실행으로 연결하기 위한 판별 헬퍼.

// "...현재 상태로도 백테스트를 실행할 수 있습니다. ... 백테스트를 시작할까요?" /
// "백테스트를 실행할 수 있습니다." / "백테스트는 계속 실행할 수 있습니다." 등 진행 확인 성격의 코치 안내인지.
export function isBacktestPrompt(coachText: string | null | undefined): boolean {
  if (!coachText) return false;
  return /백테스트.{0,8}(진행|실행|시작)/.test(coachText);
}

// "네", "예", "응", "좋아요" 같은 순수 긍정 응답(반복·구두점 허용).
const AFFIRMATIVE_RE =
  /^(?:(?:네|넹|넵|예|옙|응|웅|어|ㅇㅇ|ㅇ|그래요?|좋아요?|좋습니다|콜|확인|예스|오케이?|ok|okay|yes|yep|yeah|y|고|go)[\s,.!~]*)+$/iu;

// 백테스트 설정(기간 등)을 함께 지정한 메시지인지. "백테스트 1주일로 해줘",
// "백테스트 3년으로 해줘"처럼 숫자/기간 단위가 들어 있으면 단순 진행 확인이 아니라
// 파라미터 수정 요청이므로 재파싱 경로로 보내야 한다(기존엔 stale 기간으로 실행되던 버그).
const CARRIES_PARAMETER_RE = /\d|일주일|주일|개월|반\s*년|며칠|몇\s*(?:일|주|개월|달)/u;

// 진행 확인 안내에 대한 긍정/진행 응답인지. "네", "넵넵", "좋아요"는 물론
// "진행해줘", "백테스트 실행해줘", "네 돌려주세요" 같은 명시적 진행 요청도 포함한다.
export function isBacktestConfirmation(text: string): boolean {
  const normalized = text.trim();
  if (!normalized) return false;
  // 파라미터(기간 등)를 담은 메시지는 확인이 아니라 수정 요청 → 재파싱으로 넘긴다.
  if (CARRIES_PARAMETER_RE.test(normalized)) return false;
  if (AFFIRMATIVE_RE.test(normalized)) return true;
  if (
    /백테스트.{0,6}(진행|실행|시작|돌려|돌리|해)|(진행|실행|시작|돌려|돌리)\s*(해|해줘|줘|해주세요|주세요|하자|할게|할래요?|해주실래요?|주실래요?)/u.test(
      normalized,
    )
  ) {
    return true;
  }
  return false;
}

// 백테스트 유효 기간은 1y/3y/5y/full이라 최소가 1년이다. 1년 미만 기간을 요청하면
// 안내 메시지를 보여준다.
export const BACKTEST_MIN_PERIOD_MESSAGE =
  "백테스트 최소 기간은 1년입니다. 1년·3년·5년 또는 전체 기간 중에서 선택해 다시 말씀해 주세요.";

// "백테스트" 바로 뒤(조사·'기간'·'최근' 등만 사이에 둠)에 1년 미만 기간(주/일/개월<12 등)이
// 오면 true. 보유기간('20일 보유')·지표기간('20일선')처럼 백테스트와 무관한 N일은 백테스트에
// 인접하지 않아 매칭되지 않는다. 1년 이상(1년/12개월/3년 등)은 유효하므로 false.
const _BT_ANCHOR =
  "백테스트\\s*(?:기간)?\\s*(?:은|는|을|를|이|가|로|으로|동안)?\\s*(?:최근)?\\s*";

export function backtestPeriodTooShort(text: string): boolean {
  const c = text.toLowerCase();
  // 주 단위·일주일·반년·며칠·몇 주 → 항상 1년 미만
  if (new RegExp(_BT_ANCHOR + "(?:일주일|반\\s*년|며칠|몇\\s*주|\\d+\\s*주일?|(?:한|두|세|네|반)\\s*주)").test(c)) {
    return true;
  }
  // N일 → 1년 미만 (지표 기간 표현 '일선/일평균/일봉/일 이동평균'은 제외)
  if (new RegExp(_BT_ANCHOR + "\\d+\\s*일(?!\\s*(?:선|평균|봉|이동))").test(c)) {
    return true;
  }
  // N개월/N달 → 12 미만이면 1년 미만
  const months = c.match(new RegExp(_BT_ANCHOR + "(\\d+)\\s*(?:개월|달)"));
  if (months && Number.parseInt(months[1], 10) < 12) {
    return true;
  }
  // 한~열한 달/개월 (모두 12 미만)
  if (
    new RegExp(
      _BT_ANCHOR + "(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|열한)\\s*(?:개월|달)",
    ).test(c)
  ) {
    return true;
  }
  return false;
}
