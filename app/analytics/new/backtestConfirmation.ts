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

// 진행 확인 안내에 대한 긍정/진행 응답인지. "네", "넵넵", "좋아요"는 물론
// "진행해줘", "백테스트 실행해줘", "네 돌려주세요" 같은 명시적 진행 요청도 포함한다.
export function isBacktestConfirmation(text: string): boolean {
  const normalized = text.trim();
  if (!normalized) return false;
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
