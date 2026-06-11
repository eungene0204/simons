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
