# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

사용자가 자신만의 주식 투자 전략을 **설계 → 검증 → 최적화 → 실전 시뮬레이션**까지 원스톱으로 수행할 수 있는 종합 투자 시뮬레이션 플랫폼.


## 개발 명령어

### 테스트
```bash
# 백엔드 (test_backtest_engine, test_engine_ai, test_ai_sell, test_api_isolation 제외 — 서버/AI 모델 필요)
cd backend && pytest tests/ --ignore=tests/test_backtest_engine.py --ignore=tests/test_engine_ai.py --ignore=tests/test_ai_sell.py --ignore=tests/test_api_isolation.py

# 단일 백엔드 테스트 파일
cd backend && pytest tests/test_engine_signals.py -v

# 단일 테스트 함수
cd backend && pytest tests/test_engine_signals.py::test_function_name -v

# 프론트엔드 (Vitest + jsdom)
npm run test:frontend
```


## 아키텍처

아키텍처 상세 내용은 [`docs/software_architecture.md`](docs/software_architecture.md)를 참고한다.

## 코드 설계 원칙

코드를 작성하거나 수정할 때 반드시 [`docs/coding_rules.md`](docs/coding_rules.md)의 원칙들을 준수한다.
(SOLID, DRY, KISS, YAGNI, SoC, LoD, Composition Over Inheritance, Boy Scout Rule, Fail Fast)

## 필수 규칙

### 코드 수정 후 유닛 테스트 전체 실행
코드를 수정할 때마다 반드시 모든 유닛 테스트를 실행하여 기존 기능이 깨지지 않았는지 확인한다.
- 테스트 실패 시 반드시 원인 파악 후 수정할 것 — 기존 버그라도 그냥 넘기지 말 것
- 사용자가 별도로 요청하지 않아도 자동으로 실행할 것

### 버그 수정 시 유닛 테스트 자동 추가
버그나 문제를 발견하고 수정한 경우, 해당 버그를 재현하는 유닛 테스트를 자동으로 추가한다.
- 이미 동일한 케이스를 검증하는 테스트가 있으면 추가하지 않는다
- 백엔드: `backend/tests/` 내 적절한 파일에 추가
- 프론트엔드: `components/__tests__/` 또는 `tests/`에 추가
- 사용자가 별도로 요청하지 않아도 자동으로 실행할 것

### 계획서 완료 표시 자동 업데이트
작업 완료 시 `docs/PROJECT_PLAN.md`의 해당 항목을 자동으로 `✅ 완료`로 업데이트한다.

### UI 가이드라인 준수
새 페이지나 컴포넌트 작성 시 반드시 `docs/UI_GUIDELINES.md`를 참고한다.
 기존 페이지 수정 시도 가이드라인과 불일치하는 부분이 있으면 맞춰서 수정할 것

---

# Behavioral Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
