# Simons System Boundaries (Codex Control Layer)

This document defines HARD boundaries for AI-assisted development.

Codex MUST operate within a single boundary.

---

## Boundary A: Strategy UI

### Purpose
User-facing strategy builder and prompt interface.

### Files
- app/analytics/**
- app/virtual-account/**
- components/strategy/**
- components/ui/CreateAccountModal.tsx
- lib/strategy-summary.ts
- lib/strategy-blocks.ts
- types/strategy.ts
- backend/tests/**

### Allowed Tasks
- UI improvements
- form validation
- parameter handling
- type fixes

### Forbidden
- API logic changes
- backend changes

---

## Boundary B: Backtest Transform

### Purpose
Convert parsed strategy → executable backtest request.

### Files
- backend/engine/nl_parser.py
- backend/engine/strategy_converter.py
- types/strategy.ts
- lib/strategy/**
- backend/tests/**

### Allowed Tasks
- mapping fixes
- null/optional handling
- schema alignment

### Forbidden
- simulation logic changes

---

## Boundary C: Backtest Core (HIGH RISK)

### Purpose
Core trading simulation engine.

### Files
- backend/engine/loader.py
- backend/engine/indicators.py
- backend/engine/signals.py
- backend/engine/simulator.py
- backend/engine/result_handler.py
- backend/stream_progress.py
- backend/tests/**

### Allowed Tasks
- small bug fixes ONLY
- backtest progress/status message fixes
- test additions

### Strict Rules
- ONE function at a time
- tests REQUIRED

### Forbidden
- architectural changes
- algorithm redesign

---

## Boundary D: AI / XAI Layer

### Purpose
AI predictions, summaries, explainability.

### Files
- backend/ai/**
- backend/advisor/**
- backend/api/advisor_routes.py
- backend/api/coach_routes.py
- app/api/backtest/summarize/**
- app/api/backtest/explain/**
- backend/tests/**

### Allowed Tasks
- output formatting
- prompt improvement
- response structure cleanup
- strategy advisor recommendation / explanation wording cleanup
- coach response caching / streaming cleanup

### Forbidden
- model architecture changes

---

## Boundary E: Dashboard / Read-only UI

### Purpose
Visualization only (NO business logic)

### Files
 - components/dashboard/**
 - components/layout/**
 - components/portfolio/**
 - app/backtest/**
 - app/kospi/**
 - app/stock-order/**
 - backend/tests/**

### Allowed Tasks
- UI improvements
- chart fixes
- performance optimization

### Forbidden
- trading logic changes

---

## Boundary K: AI Runtime Orchestration

### Purpose
Runtime coordination for local LLM inference, model preloading, and latency-sensitive AI request scheduling.

### Files
- backend/main.py
- backend/api/coach_routes.py
- app/api/ai/runtime/**
- backend/tests/**
- app/api/**/route.test.ts

### Allowed Tasks
- MLX inference lock coordination
- AI request priority / queue handling
- model preload wiring
- latency instrumentation for AI runtime paths
- Next.js proxy routes for AI runtime metrics

### Strict Rules
- Do not change model identifiers or model architecture
- Preserve public API response contracts
- Keep changes limited to AI runtime coordination

### Forbidden
- stock detail response schema changes
- backtest engine algorithm changes
- provider layer changes
- database schema changes

---

## Boundary L: Optimization Runtime

### Purpose
Strategy parameter optimization orchestration and deterministic optimizer behavior.

### Files
- backend/engine/optuna_optimizer.py
- backend/ai/local_optimization_agent.py
- backend/tests/test_optuna_optimizer.py
- backend/tests/**

### Allowed Tasks
- optimizer determinism fixes
- sampler / trial scheduling stability
- optimization result ranking and direction handling
- regression tests for optimizer behavior

### Strict Rules
- Preserve public optimizer input and output contracts
- Do not change backtest simulation algorithms
- Keep optimizer changes deterministic and testable

### Forbidden
- LLM model changes
- strategy parser changes
- provider layer changes
- database schema changes
- frontend/API route changes

---

## Boundary F: Stock Detail Pipeline

### Purpose
Live 주식 상세 데이터(가격·시가총액·PER/PBR 등) 조회 및 프론트엔드 전달.

### Files
- backend/main.py
- app/api/stock/[symbol]/detail/route.ts
- backend/tests/**

### Allowed Tasks
- KIS 시세/펀더멘털 파싱 추가 및 필드 매핑
- 응답 스키마 정합성 보완 및 캐싱 관련 경량 수정

### Forbidden
- 백테스트 엔진(`backend/engine/**`) 변경
- 데이터 파일, 스키마, 스크립트 수정

---

## Boundary H: Data Enrichment Pipeline

### Purpose
OHLCV parquet 수집 후처리 및 펀더멘털 보강(예: PER/PBR/ROE) 적재.

### Files
- backend/engine/data_fetcher.py
- backend/engine/fundamental_fetcher.py
- backend/tests/test_fundamental_fetcher.py
- data/ohlcv/**

### Allowed Tasks
- 외부 소스에서 펀더멘털 지표 조회 및 파싱
- parquet 컬럼 보강 및 재저장
- 공시 반영 시점 지연 로직 보완
- enrichment 전용 테스트 추가 및 수정

### Forbidden
- 백테스트 엔진(`backend/backtest_engine.py`, `backend/engine/loader.py`, `backend/engine/signals.py`, `backend/engine/simulator.py`) 변경
- API/프론트엔드 응답 스키마 변경
- provider 계층(`backend/engine/providers/**`) 변경
- 범용 스크립트(`scripts/**`, `backend/scripts/**`) 변경

---

## Boundary M: News Impact Pipeline

### Purpose
뉴스 수집, 정규화, 이벤트 추출, 영향도 산정 및 주식 상세 화면 전달 경로 유지보수.

### Files
- backend/news/**
- backend/tests/test_news_*.py
- app/api/news/**
- components/stock/NewsImpactPanel.tsx

### Allowed Tasks
- 뉴스 provider 응답 파싱 및 정규화 수정
- 이벤트 추출, look-ahead 방지, model/version 메타데이터 정합성 수정
- 뉴스 중복 제거, 심볼 매핑, 영향도 산정 로직 보완
- 뉴스 저장소와 API 응답 간 schema-compatible 필드 매핑 수정
- News Impact Panel 표시용 경량 응답 정합성 수정
- 뉴스 파이프라인 회귀 테스트 추가 및 수정

### Strict Rules
- Preserve public news API response contracts
- Keep changes isolated to news impact behavior
- Tests are required for event extraction, look-ahead, or impact scoring changes

### Forbidden
- 백테스트 엔진(`backend/engine/**`) 변경
- 전략 생성/Advisor 로직(`backend/advisor/**`) 변경
- AI runtime/model orchestration 변경
- database schema 변경
- 인증 로직 변경
- `components/stock/StockDetail.tsx` 구조 변경
- 범용 스크립트(`scripts/**`, `backend/scripts/**`) 변경

---

## Boundary G: Governance / Policy Docs

### Purpose
Codex 작업 규칙, boundary 정의, 운영 정책 문서 유지보수.

### Files
- AGENTS.md
- docs/architecture/**
- docs/development/**
- docs/PROJECT_PLAN.md
- docs/software_architecture.md
- docs/SRS.md

### Allowed Tasks
- boundary 정의 추가 및 수정
- Codex 작업 규칙 보완
- 정책 문서 간 정합성 수정
- 제품 범위/요구사항/아키텍처 문서 업데이트

### Forbidden
- 애플리케이션 코드 변경
- API/백엔드/프론트엔드 구현 변경
- 데이터/스키마/스크립트 수정

---

## Boundary I: Strategy Persistence / BatchRun Storage

### Purpose
전략 저장 구조, 백테스트 결과 영구 저장, BatchRun 이력 저장, strategy_id 기반 식별 체계 정합성 유지.

### Files
- prisma/**
- app/api/strategy/**
- app/api/dashboard/strategy-list/route.ts
- app/api/quick-search/route.ts
- lib/server/backtestCache.ts
- lib/strategy-tracked-symbols.ts
- lib/prisma.ts
- backend/tests/**

### Allowed Tasks
- `strategy_id`를 기준으로 한 PK/FK 정렬
- Strategy / BacktestResult / BacktestHistory / BatchRun 관련 schema 및 저장 로직 수정
- 캐시 저장/조회 키를 `strategy_id`와 일치시키는 수정
- BatchRun 이력 조회용 API 및 저장 정합성 보완
- persistence 회귀 테스트 추가 및 수정

### Forbidden
- 백테스트 엔진 알고리즘 변경
- Strategy UI 변경
- 인증 로직 변경
- 범용 스크립트 수정

---

## Boundary J: Stock Info Profile Persistence

### Purpose
`/stock-order` 종목정보 탭에서 사용하는 비실시간 종목 프로필/재무 정보의 저장 및 조회 정합성 유지.

### Files
- prisma/**
- app/api/stock/[symbol]/detail/route.ts
- app/api/stocks/**
- lib/prisma.ts
- backend/tests/**

### Allowed Tasks
- 종목정보 탭 전용 저장 구조 추가 및 수정
- 전체 종목 대상 종목정보 선적재/동기화 경로 추가
- 종목 상세 API의 DB-first 조회 전환
- 종목정보 탭 응답용 `companyBasic`, `summaryFinancials`, `pe`, `pbr`, `listingDate`, `sector`, `name` 정합성 보완
- persistence 회귀 테스트 추가 및 수정

### Forbidden
- 실시간 시세(`currentPrice`, `changePercent`, `change`, `open`, `high`, `low`, `volume`) 저장
- 종목정보 탭에서 사용하지 않는 필드 저장
- `backend/engine/**` 변경
- provider 계층(`backend/engine/providers/**`) 변경
- `app/stock-order/**` UI 구조 변경
- 범용 스크립트 수정

---

## Global Forbidden Paths

Codex must NEVER modify:

- backend/engine/providers/**
- app/api/login/**
- app/api/register/**
- app/api/user/**
- scripts/**

Exception:
- `prisma/**` is allowed only inside `Boundary I: Strategy Persistence / BatchRun Storage`
 - `prisma/**` is allowed inside `Boundary J: Stock Info Profile Persistence`

---

## Boundary Selection Rule

Before running Codex:

1. Choose ONE boundary
2. List allowed files
3. Confirm no cross-boundary edits

If violated → ABORT
