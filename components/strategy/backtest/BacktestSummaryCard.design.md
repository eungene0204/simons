# AI 리포트 점수 카드 — 2026-09-29

- 사용자 요청: 점수·등급과 성장성/안정성/일관성 영역을 애플 스타일로 재디자인.
- 큰 점수는 얇은 원형 링과 크림색 숫자로 표시한다. 등급은 중립 배지로 표시하고, 점수 상태 색상은 링에만 사용한다. 기존 UI 지침의 80/60/40 기준에 맞춰 초록/파랑/앰버/빨강을 적용한다.
- 기존 카드 배경 토큰과 16px 반경, 미세한 구분선을 사용한다. 데스크톱은 세부 지표 3열, 모바일은 작은 링과 설명을 나란히 놓은 세로 행이다.
- 점수 링은 이름·현재값·최솟값·최댓값을 가진 접근 가능한 meter다. 0점은 색상 선을 숨긴다. 설명 버튼의 포커스와 툴팁은 유지한다.
- 점수 계산식, 등급 기준, 리포트 요청/저장 및 설명 내용은 유지했다.
- 검증: `npm run test:frontend` — 309개 파일, 2,285개 테스트 통과; 기존 1개 건너뜀. 점수와 세부 지표 보존 테스트를 포함한다.
- 검증: `npx next lint --file components/strategy/backtest/BacktestSummaryCard.tsx --file components/strategy/backtest/BacktestSummaryCard.test.tsx`, `git diff --check`.
- 실제 컴포넌트와 기존 Tailwind/globals.css를 사용한 로컬 fixture로 데스크톱과 390px 모바일 표시를 확인했다. 모바일 가로 넘침 없음, 설명 버튼 클릭 시 툴팁 표시 확인. 로그인된 실제 리포트 페이지의 전체 동선은 검증하지 않았다.
- `docs/PROJECT_PLAN.md`, `docs/software_architecture.md`, `docs/SRS.md`의 관련 요구사항을 검토했다. 이번 작업은 Boundary A이며 작업 기록은 해당 경계 안의 이 문서에 남긴다.
