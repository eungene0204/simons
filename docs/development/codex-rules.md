# Codex Rules for Simons (Solo Developer Edition)

## Philosophy

Codex is not a co-architect.
Codex is a constrained executor.

The goal is:
- Small diffs
- Predictable behavior
- Zero-risk changes

---

## Core Rules

### 1. One Task = One Boundary

Codex must only modify files within ONE boundary.

Allowed:
- Strategy UI
- Backtest Transform
- Backtest Core (limited)
- AI Summary / Explain
- AI Runtime Orchestration
- Optimization Runtime
- Dashboard (read-only UI)
- Landing / Auth Entry Experience
- Strategy Persistence / BatchRun Storage
- User Personalization / Ownership Persistence
- News Impact Pipeline
- App Shell / Navigation
- Governance / Policy Docs

Never mix boundaries in one task.

---

### 2. Always Define Acceptance Criteria

Every task must include:

- What should change
- What must NOT change
- How success is validated

If acceptance criteria is unclear → DO NOT RUN Codex.

---

### 3. Mandatory Test Execution

Every Codex task must include:

- Exact test command
- Success condition: ALL PASS

If tests fail:
- Codex must retry OR explain blocker

---

### 4. Forbidden Modifications

Codex must NEVER modify:

- `prisma/**`
- `backend/engine/providers/**`
- `app/api/login/**`
- `app/api/register/**`
- `app/api/user/**`
- `scripts/**`
- authentication logic
- database schema

Unless explicitly instructed.

Exception:
- `app/api/login/**`, `app/api/user/**`, and authentication logic are allowed only when the task explicitly selects `Landing / Auth Entry Experience` or `User Personalization / Ownership Persistence`.
- `prisma/**` and database schema changes are allowed only when the task explicitly selects `Strategy Persistence / BatchRun Storage`.
- User-personalization-specific `prisma/**` and database schema changes are allowed only when the task explicitly selects `User Personalization / Ownership Persistence`.
- News-specific `prisma/**` and database schema changes are allowed only when the task explicitly selects `News Impact Pipeline`.
- `docs/PROJECT_PLAN.md`, `docs/software_architecture.md`, `docs/SRS.md` are allowed only when the task explicitly selects `Governance / Policy Docs`.

---

### 5. Diff Size Constraint

Rules:

- Max 3~5 files per task
- Prefer < 200 lines change

If diff is large:
→ REJECT and split task

---

### 6. No Silent Behavior Changes

Codex must:

- Preserve existing API contracts
- Preserve existing types unless required
- Never rename fields silently

---

### 7. Code Style Rules

- Comments must be in English
- Follow existing code style
- Prefer explicit over clever code

---

### 8. Always Output Summary

Every Codex result must include:

- Files changed
- Why changes were made
- Tests executed
- Test results
- Remaining risks

---

## Task Template (Required)

Use this format ALWAYS:

Task:
<short description>

Boundary:
<ONE boundary only>

Files allowed:
<explicit list>

Do not:
<explicit restrictions>

Requirements:
<clear bullet points>

Run:
<test commands>

Deliver:
- small diff
- summary
