# 팩터 회귀 해석 — 2026-09-28

- 원인: 계수 부호를 소형주·대형주 등 종목 유형으로 변환해, 수익률의 조건부 관계를 보유 종목 구성처럼 설명했다. 프로덕션의 대형주 전략 SMB β=+0.197952, t=5.389427 사례가 이를 드러냈다.
- 수정: `factorInterpretation.ts`에서 시장 수익률과 SMB·HML·MOM의 수익률 차이를 정본으로 사용한다. 음의 계수에서도 차이의 정의를 바꾸지 않고 전략 수익률의 추정 방향을 낮게 표시한다.
- 개별 행과 요약은 동일한 해석 함수를 사용하며, 숫자 예시도 동일한 팩터 정의를 참조한다. 계수는 다른 팩터를 통제한 1%p 변화당 전략 하루 수익률의 추정 차이(%p)로 설명한다. 종목 유형·인과관계·미래 움직임을 단정하지 않는다.
- `AdvancedAnalyticsSection.tsx`는 실제 보유 구성과 팩터 회귀를 구분하고, 계산 유니버스에 미보유 종목도 포함될 수 있음을 설명한다. 유의성 문구는 현재 t값 기준을 충족한다는 수준으로 제한한다.
- 백테스트·회귀 계산, API, 저장 결과의 수치는 변경하지 않는다. 저장 결과도 이 컴포넌트로 표시할 때 새 해석 규칙을 적용한다.
- 테스트: 프로덕션 수치 재현, 4개 팩터 × 계수 양수·음수 × 한국어·영어, 결측·비유한 값·0·미지원 팩터, |t|=1.95/1.96 경계, 불확실한 알파 해석을 검증한다.
- `npm run test:frontend`: 308개 파일·2,259개 테스트 통과, 기존 1개 건너뜀. 이어서 추가한 t값 경계·0·미지원 사례까지 `npm run test:frontend -- components/strategy/backtest/factorInterpretation.test.ts` 19개 통과.
- `npx next lint --file components/strategy/backtest/factorInterpretation.ts --file components/strategy/backtest/factorInterpretation.test.ts --file components/strategy/backtest/AdvancedAnalyticsSection.tsx`: 경고·오류 없음.
- 한계: 이번 변경은 확인된 설명 규칙의 오류를 수정한다. 회귀 입력 데이터의 전수 감사나 표준오차 추정 방식 변경은 포함하지 않는다.
