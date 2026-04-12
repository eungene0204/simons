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
- backend/tests/**

### Allowed Tasks
- small bug fixes ONLY
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
- app/api/backtest/summarize/**
- app/api/backtest/explain/**
- backend/tests/**

### Allowed Tasks
- output formatting
- prompt improvement
- response structure cleanup

### Forbidden
- model architecture changes

---

## Boundary E: Dashboard / Read-only UI

### Purpose
Visualization only (NO business logic)

### Files
 - components/dashboard/**
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

## Boundary G: Governance / Policy Docs

### Purpose
Codex 작업 규칙, boundary 정의, 운영 정책 문서 유지보수.

### Files
- AGENTS.md
- docs/architecture/**
- docs/development/**

### Allowed Tasks
- boundary 정의 추가 및 수정
- Codex 작업 규칙 보완
- 정책 문서 간 정합성 수정

### Forbidden
- 애플리케이션 코드 변경
- API/백엔드/프론트엔드 구현 변경
- 데이터/스키마/스크립트 수정

---

## Global Forbidden Paths

Codex must NEVER modify:

- prisma/**
- backend/engine/providers/**
- app/api/login/**
- app/api/register/**
- app/api/user/**
- scripts/**

---

## Boundary Selection Rule

Before running Codex:

1. Choose ONE boundary
2. List allowed files
3. Confirm no cross-boundary edits

If violated → ABORT
