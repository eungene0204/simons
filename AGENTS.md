# AGENTS.md

## MUST FOLLOW

- Follow all rules in:
  - `docs/development/codex-rules.md`
  - `docs/architecture/boundaries.md`

## Boundary Rules (CRITICAL)

Before making any change:
- Select exactly ONE boundary from `boundaries.md`
- Only modify files inside that boundary

## Simons Codex Policy

Before making code changes, decide whether the user request is already a complete executable spec.

If the request is short, vague, broad, or missing boundary / file scope / validation steps,
use the `spec-writer` skill first.

Only begin implementation after the request has been converted into this format:

- Task
- Boundary
- Files allowed
- Do not
- Requirements
- Run
- Deliver

If the request is already structured in this format, use it directly.

Always keep work inside one boundary.
Never modify forbidden paths unless explicitly instructed.
When creating a new UI, always review and follow `docs/UI_GUIDELINES.md`.

Whenever a task is completed, update the work details in the relevant documentation before finishing the task. At minimum, review and update any applicable documents such as:
- `docs/PROJECT_PLAN.md`
- `docs/software_architecture.md`
- `docs/SRS.md`

## 규제 안전 원칙 (유사투자자문업 회피)

### 핵심 원칙

- 우리 서비스는 투자 연구 및 시뮬레이션 플랫폼이다.
- 본 서비스는 투자 자문, 투자 추천, 개인 맞춤형 금융 조언을 제공하지 않는다.
- 모든 투자 판단은 사용자가 직접 수행한다.
- 시스템은 계산, 백테스트, 시뮬레이션 및 객관적인 과거 데이터 표시만 수행한다.

### 허용되는 기능

#### 전략 연구

- 사용자가 직접 전략 생성
- 조건 블록 조합
- 전략 수정 및 저장
- 전략 비교

#### 백테스트

- 과거 데이터 시뮬레이션
- CAGR
- MDD
- 샤프 비율
- Profit Factor
- 거래 통계
- 수익곡선

#### 가상계좌

- 모의투자만 제공
- 가상 체결
- 포트폴리오 추적
- 거래 내역 조회

#### 데이터 제공

- 차트
- 기술적 지표
- 재무 지표
- 과거 통계 정보

### 절대 구현하면 안 되는 기능

#### 투자 추천

다음 기능은 절대 제공하지 않는다.

- 전략 추천
- 종목 추천
- 섹터 추천
- ETF 추천
- 포트폴리오 추천

금지 예시:

- ❌ “이 전략을 추천합니다.”
- ❌ “전략 A를 사용하는 것이 좋습니다.”
- ❌ “현재는 가치 전략이 유리합니다.”
- ❌ “반도체 업종이 유망합니다.”

#### 시장 전망

다음 기능은 절대 제공하지 않는다.

- 시장 예측
- 시장 전망
- 매수 시점 제안
- 매도 시점 제안

금지 예시:

- ❌ “지금 매수하기 좋은 시기입니다.”
- ❌ “시장이 상승할 가능성이 높습니다.”
- ❌ “계속 보유하는 것이 좋습니다.”

#### 개인 맞춤형 조언

다음 기능은 절대 제공하지 않는다.

- 나이 기반 추천
- 자산 규모 기반 추천
- 소득 기반 추천
- 위험 성향 기반 추천

금지 예시:

- ❌ “40대라면 배당 전략이 적합합니다.”
- ❌ “1억 원이라면 성장주 비중을 늘리는 것이 좋습니다.”

#### AI 코치 기능

다음 기능은 절대 제공하지 않는다.

- 전략 자동 추천
- 전략 자동 개선
- 전략 우열 판단
- 사용자 행동 제안

금지 예시:

- ❌ “이 전략이 더 우수합니다.”
- ❌ “전략 B로 변경하는 것을 추천합니다.”
- ❌ “현재 시장에서는 전략 A가 더 적합합니다.”

### 안전한 표현 원칙

허용:

- ✅ “과거 데이터 기준 CAGR은 12.4%였습니다.”
- ✅ “최대 낙폭은 -18%였습니다.”
- ✅ “총 53회의 거래가 발생했습니다.”
- ✅ “결과는 과거 데이터 기반 시뮬레이션 결과입니다.”
- ✅ “미래 수익은 보장되지 않습니다.”

금지:

- ❌ “이 전략은 앞으로도 잘 작동할 것입니다.”
- ❌ “높은 성과가 기대됩니다.”
- ❌ “좋은 투자 전략입니다.”
- ❌ “추천 전략입니다.”
- ❌ “사용을 권장합니다.”

### UI 및 마케팅에서 금지되는 표현

절대 사용하지 않는다.

- ❌ AI 투자 코치
- ❌ 추천 전략 TOP 10
- ❌ 최고의 전략
- ❌ 2026년 유망 전략
- ❌ 지금 사야 할 종목
- ❌ 지금 팔아야 할 종목
- ❌ 고객 맞춤 전략
- ❌ 수익률 보장

### 권장 표현

사용 가능:

- ✅ 전략 연구소
- ✅ 투자 연구 플랫폼
- ✅ 백테스트 플랫폼
- ✅ 시뮬레이션 플랫폼
- ✅ 사용자 생성 전략
- ✅ 공개 전략
- ✅ 과거 성과 분석
- ✅ 연구 도구

# Repository Guidelines

## Project Structure & Module Organization
`app/` contains the Next.js 14 App Router pages and API routes. Reusable UI lives in `components/`, shared utilities in `lib/`, and type definitions in `types/`. Database schema and migrations are under `prisma/`, and static assets live in `public/`.

The Python backtesting service is isolated in `backend/`. Use `backend/main.py` as the FastAPI entry point, `backend/engine/` and `backend/ai/` for backend logic, and `backend/tests/` for pytest coverage. Frontend tests live in `tests/` and `components/__tests__/`. Data files and scripts live in `data/` and `scripts/`.

## Build, Test, and Development Commands
Install JS dependencies with `npm install` and Python backend dependencies with `pip install -r backend/requirements.txt`.

- `npm run dev`: start the Next.js app on port 3000.
- `npm run dev:backend`: start the FastAPI backend on port 8000 with reload limited to `backend/`.
- `npm run dev:all`: run frontend, backend, and scheduler together.
- `npm run build`: generate Prisma client and build the production app.
- `npm run lint`: run Next.js ESLint checks.
- `npm run test:frontend`: run Vitest in jsdom mode.
- `pytest backend/tests`: run backend regression and engine tests.

## Coding Style & Naming Conventions
TypeScript uses 2-space indentation, double quotes, and PascalCase component names such as `TopMenuBar.tsx`. Hooks, helpers, and route utilities use camelCase. Keep new files aligned with existing conventions, for example `components/strategy/*` or `app/api/*/route.ts`.

Python follows PEP 8 with 4-space indentation, snake_case functions, and pytest fixtures in `conftest.py`. Linting currently relies on `next/core-web-vitals`; there is no separate Prettier or Ruff config in this repo, so match the surrounding file style closely.

## Testing Guidelines
Frontend tests use Vitest and Testing Library with `*.test.ts` or `*.test.tsx` names. Backend tests use pytest with `test_*.py` files. Add regression tests for API routes, strategy logic, and backtest engine changes, especially when fixing production bugs.

When fixing a bug, add or update a unit/regression test that reproduces the original failure so the issue is prevented from recurring. Prefer tests that cover the exact broken path, such as fallback behavior for corrupted files, Git LFS pointer files, or malformed inputs.

Any time frontend code changes, run the frontend unit tests before finishing the task. For this repository that means `npm run test:frontend`.

Any time backend code changes, run the backend unit tests before finishing the task. For this repository that means `pytest backend/tests`.

If a task changes both frontend and backend code, run both test suites. If only documentation or non-code project files change, tests are not required unless the user explicitly asks for them.

## Commit & Pull Request Guidelines
Recent history uses Conventional Commit prefixes such as `feat:` and `refactor:`. Keep commit messages short, imperative, and scoped to one change. For pull requests, include a clear summary, note schema or env changes, link the issue when applicable, and attach screenshots for UI updates. List the exact commands you ran, such as `npm run test:frontend` and `pytest backend/tests`.

## Security & Configuration Tips
Keep secrets in `.env.local` or `.env`, not in source control. Required local settings include `DATABASE_URL` and `JWT_SECRET`. When changing Prisma models, run `npm run db:migrate` and `npm run db:generate` before submitting.
