# Simons System Boundaries (Codex Control Layer)

## Boundary Y: Anonymous Community Board

사용자 승인(2026-10-19). 전용 범위와 실행 명세는
`docs/development/community-board.md`에 정의한다. 해당 문서에 명시된 게시판
UI/API/Prisma/테스트/공개 진입점/문서만 변경한다. 신규 게시판 스키마와
관리자 검수 연결을 허용하며 기존 인증 계약은 보존한다.

This document defines HARD boundaries for AI-assisted development.

Codex MUST operate within a single boundary.

---

## Boundary A: Strategy UI

### Purpose
User-facing strategy builder and prompt interface.

### Files
- app/analytics/**
- app/virtual-account/**
- components/virtual-account/**
- components/stock/StockSearchModal.tsx
- components/strategy/**
- components/ui/CreateAccountModal.tsx
- lib/strategy-summary.ts
- lib/strategy-blocks.ts
- types/strategy.ts
- backend/tests/**

- app/api/strategy/parse/stream/route.ts (KR request revision and structured progress only)
- app/api/strategy/parse/route.ts (KR request revision pass-through only)

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
- backend/engine/modify_rag.py
- backend/engine/data/modify_examples.json
- backend/engine/data/modify_knowledge.json
- backend/engine/strategy_converter.py
- types/strategy.ts
- lib/strategy/**
- backend/tests/**

### Allowed Tasks
- mapping fixes
- null/optional handling
- schema alignment
- strategy modification knowledge retrieval and validated corpus maintenance

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
- data/advisor-learning/**
- backend/tests/**

### Allowed Tasks
- output formatting
- prompt improvement
- response structure cleanup
- strategy advisor recommendation / explanation wording cleanup
- coach response caching / streaming cleanup
- advisor learning artifact generation and refresh

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
- backend/nl_cache.py
- backend/strategy_conversation/primary.py
- backend/strategy_conversation/config.py
- backend/strategy_conversation/interpreter/**
- backend/strategy_conversation/runtime/**
- docs/development/strategy-call-reduction.md
- app/api/ai/runtime/**
- backend/tests/**
- app/api/**/route.test.ts

### Allowed Tasks
- MLX inference lock coordination
- AI request priority / queue handling
- model preload wiring
- latency instrumentation for AI runtime paths
- Next.js proxy routes for AI runtime metrics
- Strategy parse request coalescing, context-safe caching, and batching auxiliary LLM extraction/checks
- Conditional planner scheduling based on independently extracted, validated universe evidence

### Strict Rules
- Do not change model identifiers or model architecture
- Preserve public API response contracts
- Keep changes limited to AI runtime coordination
- Preserve independent omission detection, existing validation/apply rules, and fallback for ambiguous or invalid evidence
- Do not replace natural-language interpretation with regular expressions or change compiler/engine semantics
- Split call-reduction work into request sharing, extraction, check batching, and planner scheduling steps; validate each before proceeding

### Forbidden
- stock detail response schema changes
- backtest engine algorithm changes
- provider layer changes
- database schema changes

---

## Boundary W: Strategy Interpretation Stabilization

### Purpose
Preserve user-stated strategy meaning across primary interpretation, provenance checks, and modification patches.

### Files
- backend/strategy_conversation/primary.py
- backend/strategy_conversation/config.py
- backend/strategy_conversation/conversation/versioning.py (KR request revision CAS only)
- backend/strategy_conversation/response/notice_evidence.py (structured final-state notice evidence only)
- backend/strategy_conversation/response/** (KR notice evidence handoff only)
- backend/intent/interpreter.py (structured KR turn axes only)
- backend/intent/schemas.py (additive KR turn axes only)
- backend/intent/classifier.py (KR semantic routing and turn-axis handoff only)
- backend/intent/strategy_builder.py (retire KR raw-text semantic paths only)
- backend/intent/builder_interpreter.py (existing structured builder path wiring only)
- backend/api/intent_routes.py (existing LLM builder wiring only)
- backend/strategy_conversation/interpreter/**
- backend/strategy_conversation/conversation/patch_applier.py
- backend/strategy_conversation/conversation/patch_approval.py (internal patch groups, identity, and atomic selection only)
- backend/strategy_conversation/validation/capability_validator.py (operator wording and KR sector notice findings only)
- backend/strategy_conversation/registry/indicator_registry.py (existing breakout buy-high/sell-low operator contract only)
- backend/strategy_conversation/compiler/strategy_compiler.py (existing breakout role/direction guard only)
- backend/strategy_conversation/validation/conflict_validator.py (localized parameter conflict labels only)
- backend/strategy_conversation/validation/pipeline.py (KR sector notice evidence handoff only)
- backend/strategy_conversation/response/notice_assembly.py (KR create/modify/fill/ETF final-state notice assembly only)
- backend/main.py
- backend/tests/**
- components/admin/AgentsTab.tsx
- scripts/qa_free_input.py
- scripts/qa_template_detect.py
- scripts/qa_template_expectations.json
- backend/observability/tracing.py (complete local replay snapshots only)
- backend/observability/agent_trace.py (replay dependency and API response evidence only)
- scripts/qa_kr_display_sweep.test.ts (coverage and replay display checks only)
- tests/interpretationReplayDisplay.test.ts

### Allowed Tasks
- fix interpretation provenance and numeric evidence handoff
- keep dependent modification patches atomic and preserve unrelated conditions
- repair narrowly scoped auxiliary LLM checks and their runtime wiring
- update the existing agent-flow diagram to match changed guards
- add regression tests for these paths
- localize user-facing invalid-operator notices without changing validation decisions
- keep the existing free-input QA fixture and semantic assertions consistent with the draft supplied to the interpreter
- retire raw-text modification fast-path routing across the primary entry point and its rollback setting
- replace regex-derived QA expectations with human-authored example expectations without reducing checked meaning
- record complete local interpretation replay evidence without changing execution or external telemetry payloads
- replay API postprocessing and existing frontend display functions using fixed external observations
- assemble create-turn KR sector/theme notices from final state and structured resolution evidence
- normalize existing auxiliary verdicts into internal decisions and consume them in modification group approval
- preserve independent changes when a rejected or ambiguous condition replacement is held, without changing auxiliary fail-open policy
- apply the approved stage-five required-verdict hold policy within existing checker targets, preserving original conditions and independent changes
- finish user-approved remaining KR domain-validation group holds, final-state notices, and primary semantic reconciliation; US-specific implementation is excluded
- repair all user-authorized remaining KR example failures using existing engine bindings, including breakout role directions and verified EMA recovery

### Strict Rules
- Do not infer meaning from raw `user_input` with regexes, keywords, or vocabulary lists
- Do not invent parameter values or silently remove conditions
- Use LLM verdicts for semantic judgments; validate only output format and quoted provenance deterministically
- Preserve public response contracts. Invalid auxiliary verdicts keep their existing policy except for the explicitly approved stage-five required checks, which hold only the affected new or replacement group.
- Keep each implementation task narrow and verify the original failure before changing code
- Keep raw replay evidence inside the existing three-day local Trace retention; never persist credentials

### Forbidden
- new Agent, parser, State model, or DSL
- compiler changes outside the registered breakout role/direction guard; engine, provider, database, or data-file changes
- strategy recommendation or market prediction

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
- backend/news_v2/**
- backend/api/news_routes.py
- backend/tests/test_news_*.py
- app/api/news/**
- app/api/stocks/[symbol]/news/route.ts
- lib/hooks/useStockNews.ts
- types/news-v2.ts
- components/stock/NewsImpactPanel.tsx
- components/stock/StockDetail.tsx
- prisma/**

### Allowed Tasks
- 뉴스 provider 응답 파싱 및 정규화 수정
- 이벤트 추출, look-ahead 방지, model/version 메타데이터 정합성 수정
- 뉴스 중복 제거, 심볼 매핑, 영향도 산정 로직 보완
- 뉴스 저장소와 API 응답 간 schema-compatible 필드 매핑 수정
- News Impact Panel 표시용 경량 응답 정합성 수정
- 뉴스 파이프라인 회귀 테스트 추가 및 수정
- 뉴스 v2 캐시 조회 API, 백그라운드 수집/분석 worker, queue/scheduler wiring 정합성 수정
- 뉴스탭 전용 React Query/SWR hook, proxy route, response type 정합성 수정
- 종목 상세 페이지의 뉴스탭 prefetch wiring 추가 및 수정
- 뉴스 전용 Prisma model/migration/index 추가 및 수정
- 뉴스 전용 raw news, analysis, symbol mapping, stock news cache 저장 구조 추가 및 수정

### Strict Rules
- Preserve public news API response contracts unless the task explicitly defines the replacement contract.
- Keep changes isolated to news impact behavior
- Tests are required for event extraction, look-ahead, or impact scoring changes
- News tab read APIs must not run crawlers, scrapers, external news search, or LLM/news agent analysis inline.
- News agent and crawler execution must stay in scheduler, queue worker, or explicit admin refresh paths.
- `prisma/**` changes inside this boundary are limited to news-only models, migrations, and indexes.
- Required news cache indexes must be declared in the schema or migration when adding news cache storage.

### Forbidden
- 백테스트 엔진(`backend/engine/**`) 변경
- 전략 생성/Advisor 로직(`backend/advisor/**`) 변경
- AI runtime/model orchestration 변경
- non-news database schema 변경
- 인증 로직 변경
- `components/stock/StockDetail.tsx`의 뉴스 prefetch wiring 외 구조 변경
- 범용 스크립트(`scripts/**`, `backend/scripts/**`) 변경

---

## Boundary G: Governance / Policy Docs

### Purpose
Codex 작업 규칙, boundary 정의, 운영 정책 문서 유지보수.

### Files
- AGENTS.md
- CLAUDE.md
- .agents/skills/strategy-interpretation/SKILL.md
- docs/architecture/**
- docs/development/**
- docs/nl_interpretation_contract.md
- docs/PROJECT_PLAN.md
- docs/software_architecture.md
- docs/SRS.md

### Allowed Tasks
- boundary 정의 추가 및 수정
- Codex 작업 규칙 보완
- 전략 해석 실패 대응용 개발 skill 문서 유지보수 (애플리케이션 런타임 변경 제외)
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

## Boundary N: Vector Memory Infrastructure

### Purpose
Backtest result Experience Memory를 semantic retrieval 용도로 저장하고 검색하는 vector memory infrastructure.

### Files
- backend/vector_memory/**
- backend/tests/test_vector_memory_*.py
- backend/tests/test_advisor_vector_memory.py

### Allowed Tasks
- normalized backtest memory document 생성 로직 추가 및 수정
- strategy DSL hash 기반 vector memory key 생성
- embedding client protocol 및 deterministic/local embedding adapter 추가
- ChromaDB repository adapter 추가 및 수정
- vector memory upsert/query service 추가 및 수정
- metadata filtering, duplicate prevention, strategy version metadata 보완
- vector memory infrastructure unit test 추가 및 수정

### Strict Rules
- Vector DB는 semantic retrieval memory로만 사용하고 source of truth로 취급하지 않는다.
- 백테스트 완료 즉시 upsert wiring은 별도 boundary에서 수행한다.
- embedding 대상은 압축된 strategy/backtest summary여야 하며 raw trade logs, 개인정보, 긴 report 원문은 저장하지 않는다.
- ChromaDB, embedding provider, repository 구현은 protocol 뒤에 숨긴다.

### Forbidden
- 백테스트 엔진(`backend/engine/**`) 변경
- Prisma schema 또는 DB persistence 변경
- Advisor 응답 문구/추천 로직(`backend/advisor/**`) 변경
- API/프론트엔드 route 변경
- provider 계층(`backend/engine/providers/**`) 변경
- 범용 스크립트 수정

---

## Boundary O: Landing / Auth Entry Experience

### Purpose
Public landing page, sign-in entry flow, and session bootstrap into the existing dashboard.

### Files
- app/layout.tsx
- app/page.tsx
- app/login/page.tsx
- app/dashboard/page.tsx
- app/api/auth/**
- app/api/login/route.ts
- app/api/logout/route.ts
- app/api/user/route.ts
- app/api/user/info/route.ts
- components/landing/**
- components/ui/AuthCard.tsx
- components/providers/**
- lib/auth.ts
- lib/firebase.ts
- lib/get-user.ts
- .env.local
- package.json
- backend/tests/**

### Allowed Tasks
- 랜딩페이지 UI/카피/레이아웃 개선
- 로그인 페이지를 랜딩 진입점과 통합하는 수정
- OAuth provider client bootstrap 추가 및 수정
- 로그인 성공 후 dashboard 진입 redirect/wiring 수정
- auth session bootstrap, cookie/session token wiring, logout 흐름 정합성 보완
- landing/auth entry 전용 SEO, metadata, accessibility 개선
- landing/auth entry 회귀 테스트 추가 및 수정

### Strict Rules
- Preserve existing dashboard business logic and data contracts.
- Keep auth changes limited to entry/session bootstrap needed for landing and login.
- Do not introduce signup, billing, or profile-management flows in this boundary.
- Do not change Prisma schema or backend provider logic.
- If a task introduces a new auth dependency, keep the diff limited to the dependency manifest and files in this boundary.
- Secret or credential updates in `.env.local` are allowed only for local development setup explicitly requested by the user and must never be moved into tracked source files.

### Forbidden
- `prisma/**` 변경
- backend Python 코드 변경
- 전략/백테스트/뉴스/종목 상세 기능 변경
- dashboard 내부 시각화/비즈니스 로직 변경
- 범용 스크립트(`scripts/**`, `backend/scripts/**`) 변경

---

## Boundary P: User Personalization / Ownership Persistence

### Purpose
로그인 직후 사용자 bootstrap, 사용자별 기본 설정 생성, 그리고 전략/관심종목/가상계좌/대시보드 데이터의 `user_id` 소유권 분리 정합성 유지.

### Files
- prisma/**
- app/assets/**
- app/api/login/route.ts
- app/api/logout/route.ts
- app/api/user/**
- app/api/strategy/**
- app/api/watchlist/**
- app/api/virtual-account/**
- app/api/virtual-market/**
- app/virtual-account/**
- app/api/dashboard/**
- app/api/quick-search/route.ts
- lib/auth.ts
- lib/dashboard-data.ts
- lib/get-user.ts
- lib/order-engine.ts
- lib/prisma.ts
- lib/server/assetService.ts
- lib/server/backtestCache.ts
- lib/server/virtual-market-refresh.ts
- lib/server/strategy-start.ts
- lib/server/scheduler-actions.ts
- lib/scheduler.ts
- lib/strategy-tracked-symbols.ts
- components/layout/TopNavigation.tsx
- components/__tests__/TopNavigationQuickSearch.test.tsx
- components/virtual-account/**
- components/__tests__/VirtualAccountOverviewCache.test.tsx
- app/virtual-account/*.test.tsx
- backend/tests/**

### Allowed Tasks
- 로그인 성공 시 사용자 프로필/bootstrap row 생성 또는 upsert
- 사용자별 기본 설정, onboarding 상태, 기본 watchlist/기본 데이터 초기화
- 전략/백테스트/관심종목/가상계좌/대시보드 조회를 현재 사용자 기준으로 제한
- 기존 shared/guest 가정 로직을 `user_id` ownership 기반으로 정리
- personalization/ownership 회귀 테스트 추가 및 수정
- user-owned entity에 필요한 Prisma model/field/index/FK 추가 및 수정
- 사용자 자산 지갑, 자산 원장, 가상계좌 배정/정산에 필요한 금액 타입 및 계산 정합성 수정
- 사용자 소유 가상계좌의 주문/가상시장 체결 경로에서 `Decimal`/`Numeric` 기반 금액 저장 정합성 수정
- 사용자 자산 지갑 조회 화면/모달 및 기존 사용자 메뉴 진입점 연결
- 사용자 소유 가상계좌 목록 조회 실패가 빈 목록으로 오인되지 않도록 UI/cache 오류 처리 보강

### Strict Rules
- Preserve public API response contracts unless the task explicitly defines the replacement contract.
- Authentication provider selection itself is not the focus; keep auth changes limited to user bootstrap and ownership enforcement.
- Any schema change must be directly tied to user personalization or ownership isolation.
- Bootstrap must be idempotent and safe on repeated login.
- Ownership checks must deny cross-user reads and writes by default.
- User asset, account cash, order amount, and position valuation persistence must avoid Float fields when tied to user-owned assets.
- Keep changes away from backtest engine algorithms and provider implementations.

### Forbidden
- 백테스트 엔진(`backend/engine/**`) 변경
- provider 계층(`backend/engine/providers/**`) 변경
- 랜딩페이지 UI/카피 변경
- 뉴스/종목 상세 전용 파이프라인 변경
- 범용 스크립트(`scripts/**`, `backend/scripts/**`) 변경

---

## Boundary Q: App Shell / Navigation

### Purpose
전역 앱 셸, 상단 내비게이션, 그리고 앱 셸에서 공유되는 주문 계좌 선택 상태의 구조 정합성 유지.

### Files
- app/layout.tsx
- app/stock-order/**
- components/layout/**
- components/portfolio/**
- components/__tests__/TopNavigationQuickSearch.test.tsx
- contexts/OrderAccountContext.tsx

### Allowed Tasks
- 전역 상단 내비게이션 중복 렌더링 제거
- `TopNavigation`과 `TopMenuBar` 역할 및 명칭 정합성 유지
- 레거시 drawer query parameter가 다시 전파되지 않도록 내비게이션 정리
- 주문 계좌 선택 상태의 전용 context 유지
- 앱 셸 레이아웃, 높이, 오프셋, 전환 동작 정리
- 관련 회귀 테스트 추가 및 수정

### Strict Rules
- 주문 페이지의 선택 계좌 동작과 공개 컴포넌트 계약을 보존한다.
- 전역 내비게이션은 한 번만 렌더링한다.
- 제거된 drawer UI와 context API를 다시 도입하지 않는다.
- 한 작업의 diff가 5개 파일 또는 200줄을 넘으면 이름/레이아웃 정리와 drawer/context 제거를 별도 작업으로 분리한다.

### Forbidden
- API route 변경
- 인증 또는 사용자 소유권 로직 변경
- 주문 체결, 자산 계산, 백테스트 알고리즘 변경
- 데이터베이스 스키마 변경
- backend 코드 변경

---

## Boundary R: Pricing / Plan UI

### Purpose
요금제 페이지와 플랜 카드 UI의 표시, 레이아웃, 상호작용 정합성 유지.

### Files
- app/pricing/**
- components/pricing/**

### Allowed Tasks
- 요금제 페이지 UI/카피/레이아웃 개선
- 플랜 카드 표시, hover/focus 상태, CTA 스타일 정리
- 플랜 한도와 가격 표시 문구 정합성 보완
- pricing UI 회귀 테스트 추가 및 수정

### Strict Rules
- 실제 결제, 구독 생성, 플랜 변경 API 계약은 변경하지 않는다.
- 플랜 한도 계산과 사용자 소유권 로직은 변경하지 않는다.
- 투자 추천, 수익 보장, 개인 맞춤 조언으로 해석될 수 있는 문구를 추가하지 않는다.

### Forbidden
- API route 변경
- 인증 또는 사용자 소유권 로직 변경
- 플랜 한도 계산 로직 변경
- 데이터베이스 스키마 변경
- backend 코드 변경

---

## Boundary S: Virtual Trading Runtime

### Purpose
백테스트에서 확정된 전략 DSL의 신호·랭킹·리스크 의미를 가상계좌 자동매매 런타임에 동일하게 적용하고, 전략 시작 시 평가할 후보 유니버스를 구성한다.

### Files
- backend/engine/virtual_trader.py
- backend/engine/live_signal_utils.py
- backend/engine/virtual_trading/**
- backend/tests/test_virtual_trader.py
- backend/tests/test_virtual_trader_*.py
- lib/server/strategy-start.ts
- lib/strategy-tracked-symbols.ts
- app/api/virtual-account/[id]/strategy/start/route.ts
- app/api/virtual-account/tracked-symbol-filter.test.ts
- app/api/virtual-account/strategy-start.test.ts
- app/api/virtual-market/[accountId]/route.ts
- app/api/virtual-market/[accountId]/route.test.ts
- lib/server/virtual-market-refresh.ts
- lib/server/virtual-market-refresh.test.ts
- lib/server/scheduler-actions.ts (startAutoAccounts only)
- tests/scheduler-actions.test.ts

### Allowed Tasks
- 저장된 전략 DSL의 진입·청산 조건을 자동 트레이더 평가 입력으로 변환
- 기술·재무·AI 신호용 live dataframe 준비 로직 정합성 보완
- 수익률 횡단면 랭킹, 최대 보유 종목 수, 리밸런싱 편입·편출 처리
- 전략 유니버스와 필터를 기준으로 자동매매 후보 종목 구성
- 모니터링 후보의 상장폐지/거래정지 제외와 저장 목록 조회·재개·표시 갱신·장 시작 자동 재개 시 재검증
- 손절·익절·트레일링스톱·최대보유기간·체결시점 의미 정합성 보완
- 자동매매 신호 평가와 주문 실행 회귀 테스트 추가 및 수정

### Strict Rules
- FastAPI `VirtualTrader`를 가상계좌 자동매매 체결의 단일 실행 경로로 유지한다.
- 백테스트의 `SignalEngine`과 전략 요청 의미를 재사용하며 지표 공식을 별도로 재구현하지 않는다.
- 횡단면 랭킹과 체결 판단은 해당 시점까지 확인 가능한 데이터만 사용하고 미래 데이터를 참조하지 않는다.
- 공개 API 응답, Strategy DSL, 주문·포지션 저장 계약을 보존한다.
- 모니터링 필터는 실제 상장폐지 원장·종목 마스터와 DB 상장 상태를 사용하고 조회 실패를 정상으로 간주하지 않는다. 기존 목록 정리는 비교 후 갱신해 동시 사용자 변경을 덮어쓰지 않는다.
- 신호 계열별 회귀 테스트와 look-ahead 방지 테스트를 추가한다.
- 한 작업이 5개 파일 또는 200줄을 넘으면 신호 평가, 랭킹, 리밸런싱·체결 정합화를 별도 작업으로 분리한다.

### Forbidden
- 백테스트 엔진(`backend/backtest_engine.py`, `backend/engine/simulator.py`, `backend/engine/result_handler.py`) 변경
- 공용 신호 공식(`backend/engine/signals.py`, `backend/engine/indicators.py`) 변경
- provider 계층(`backend/engine/providers/**`) 변경
- 데이터베이스 스키마 또는 Prisma 변경
- 인증·사용자 소유권 로직 변경
- 범용 스크립트(`scripts/**`, `backend/scripts/**`) 변경

---

## Boundary T: Delisted Stock Names

### Purpose
상장폐지 원장에 종목명을 보존하고 가상계좌가 사용하는 종목명 조회에 전달한다.

### Files
- backend/engine/market_data.py (DelistedSymbolStore only)
- backend/main.py (mark_delisted only)
- scripts/sync_data.py (_mark_delisted and its call site only, explicitly requested delisting persistence)
- data/delisted-stocks.json
- lib/krx-stocks.ts
- app/api/stocks/names/route.ts
- backend/tests/test_delisted_stock_names.py
- backend/tests/test_sync_data_status.py
- components/__tests__/stockNamesRoute.test.ts
- lib/krx-stocks.test.ts

### Allowed Tasks
- 상장폐지 코드와 이름을 함께 저장하고 기존 코드 목록을 호환해서 읽기
- 현재/과거 종목 마스터로 이름 복원, 이름 누락 등록 거부
- 이름 맵에 원장/마스터 이름 병합과 파일 변경 시 캐시 갱신
- 저장·조회 경로 회귀 테스트

### Strict Rules
- 기존 symbols 배열과 상장폐지 판정·시세 차단 의미를 보존한다.
- scripts/sync_data.py 수정은 사용자가 상장폐지 목록 저장을 명시적으로 요청한 경우에만 허용한다.
- 5개 파일 또는 200줄을 넘으면 원장 저장, 이름 조회, 기존 데이터 보정을 별도 작업으로 나눈다.

### Forbidden
- provider 구현, 백테스트 알고리즘, 주문·청산·소유권 로직 변경
- Prisma schema 변경, 다른 수집 스크립트 변경
- 가상계좌 UI 변경(별도 Boundary A 작업)

---

## Boundary U: Strategy Interpretation Notices

### Purpose
Keep strategy interpretation notices accurate when a validated condition is represented by a supported factor.

### Files
- backend/strategy_conversation/primary.py (`_substituted_factor` and its notice path only)
- backend/tests/test_strategy_conversation.py

### Allowed Tasks
- Correct false or missing approximation notices using the structured condition and registry evidence
- Add regression coverage for the exact condition and a genuine substitution

### Strict Rules
- Do not infer new strategy semantics from the user's natural-language input
- Preserve supported factor selection, validation, compilation, and API response contracts
- Keep true substitutions visible to the user

### Forbidden
- Interpreter prompts or model changes
- Registry, compiler, converter, and backtest engine changes
- Frontend changes

---

## Boundary V: Quarterly Operating Income Comparison

### Purpose
Represent and execute a user's strict comparison of the latest reported quarter's operating income with the same quarter one year earlier, including loss reduction and turnaround.

### Files
- backend/engine/quarterly_earnings.py (comparison events/series only)
- backend/engine/data_resolver.py (comparison metric resolution only)
- backend/engine/version.py (comparison metric version entry only)
- backend/engine/nl_parser.py (comparison metric schema/labels only)
- backend/engine/signals.py (comparison metric label only)
- backend/strategy_conversation/registry/indicator_registry.py (comparison metric only)
- backend/strategy_conversation/registry/display_labels.py (comparison metric label only)
- data/indicator-ontology.json (comparison metric membership and polarity only)
- backend/strategy_conversation/interpreter/prompts.py (comparison metric instruction only)
- backend/strategy_conversation/primary.py (comparison metric notice only)
- backend/tests/test_ncav_and_quarterly_growth.py
- backend/tests/test_strategy_conversation.py
- lib/strategy-summary.ts (comparison metric label only)
- lib/i18n/en.ts (comparison metric translation only)
- lib/strategy-summary.labels.test.ts
- app/analytics/new/parsedStrategyMerge.ts (comparison metric label only)

### Allowed Tasks
- Add a strict YoY quarter comparison distinct from percentage growth
- Carry the comparison metric through interpretation, compilation, execution, and summary
- Test negative, zero, positive, missing-quarter, and filing-date cases

### Strict Rules
- Preserve the existing YoY growth-rate metric and public strategy schema
- Use only data available by each simulated date; fail closed on missing comparisons
- Do not infer strategy meaning from natural-language regular expressions
- Split engine, interpretation, and display changes into small reviewable tasks

### Forbidden
- Provider, database schema, authentication, and unrelated backtest changes

---

## Boundary X: Strategy Ontology Graph

### Purpose
사용자의 확정·실행 전략 스냅샷을 읽기 전용 온톨로지 그래프로 보여 주는 기능 전용 boundary. 공개 지표 메타데이터 전달,
스냅샷→그래프 순수 변환, 그래프 UI, 세 진입점(확정 카드·결과 화면·저장된 결과 상세) 연결만 다룬다.
계약·작업 명세: `docs/development/strategy-ontology-graph.md`. 상태: 구현 완료(2026-10-15, X-1~X-7).

### Files
수정(기존 파일):
- backend/main.py (`include_router` 한 줄만)
- app/analytics/new/page.tsx (확정 성공 가지의 스냅샷 보존·그래프 카드 렌더, 실행 시점 스냅샷 사본 전달, 되묻기 중 초안 요약 카드를 초안 그래프로 대체하는 DraftStrategyView만)
- components/strategy/backtest/BacktestDashboard.tsx (전략 설명 영역의 그래프 진입점만)
- app/backtest/[id]/page.tsx (저장된 실행 스냅샷 전달만)
- lib/i18n/en.ts (그래프 신규 문구 번역만)
- app/analytics/new/page.confirm.test.tsx (확정 자동 표시 사례 추가만)
- app/backtest/[id]/page.test.tsx (그래프 스냅샷 전달 사례 추가만)
- app/analytics/new/page.back-after-parse.test.tsx, page.scroll.test.tsx, page.unknown-intent.test.tsx (초안 그래프 미리보기용 compile 호출을 시나리오 mock에서 구분하는 가드만)

신규(새로 만들 파일):
- backend/strategy_conversation/registry/public_metadata.py
- backend/api/strategy_graph_meta_routes.py
- backend/tests/test_strategy_graph_meta.py
- app/api/strategy/graph-meta/route.ts
- app/api/strategy/graph-meta/route.test.ts
- lib/strategy-graph/** (types, snapshot, meta, useGraphMeta, conditions, graphBuilder, transform*, concepts, textOutline, layout, fixtures, __fixtures__/*.json 및 각 *.test.ts)
- components/strategy/graph/** (StrategyGraphView, StrategyGraphDetail, StrategyGraphText, StrategyGraphCard, graphLabels 및 *.test.tsx)
- components/strategy/backtest/BacktestDashboard.strategyGraph.test.tsx
- docs/development/strategy-ontology-graph.md

### Allowed Tasks
- IndicatorSpec/REGISTRY·온톨로지에서 공개 가능한 이름·단위·지원 상태·파라미터 범위·분류·개념 관계를 결정론적으로 추출해 읽기 전용 응답으로 제공
- 출처가 명시된 스냅샷 입력 래퍼와 순수 그래프 변환(React·네트워크 의존 없음)
- 자체 SVG 그래프·상세 패널·텍스트 보기·크게 보기 UI (신규 의존성 없음)
- 확정 성공 시점과 백테스트 결과·저장 결과의 스냅샷을 그래프에 연결
- 위 경로의 회귀 테스트 추가

### Strict Rules
- 한 작업은 이 boundary 안에서 3~5개 파일, 가능하면 200줄 미만으로 나눈다. 코드 작업과 Governance 문서 갱신은 별도 작업이다.
- 기존 공개 응답·`types/strategy.ts`·전략 공개 계약을 변경하지 않는다. 그래프 전용 입력 래퍼만 새로 둔다.
- 스냅샷은 확정 응답(`/strategy/compile`의 parsed·backtest_request·notices) 또는 실행 시점 요청(`executedReq`, 저장된 `result.executedRequest`)만 쓴다. `latestParsed`·`backtestReq`·`item.settings`를 실행/확정 스냅샷 대용으로 쓰지 않는다.
- 표시용 요약 문자열을 역파싱하지 않는다. 사용자 원문에 정규식·키워드로 의미를 판정하지 않는다. LLM·검색을 호출하지 않는다.
- 지표별 이름·단위·기본값·매매 의미 사전을 프론트엔드에 복제하지 않는다. `default`·`recommended_value`로 미정 사용자 값을 채우지 않는다.
- 공개 메타데이터에는 사용자 전략·원문·다른 사용자 데이터, 관리자 진단(issues)을 싣지 않는다. 관리자 엔드포인트(`/api/admin/ontology/graph`)를 사용자 화면에서 호출하지 않는다.
- 새 의존성이나 파일이 필요하면 구현 전에 이 목록과 `strategy-ontology-graph.md`를 먼저 갱신한다.

### Forbidden
- 전략 해석·검증·컴파일·백테스트 실행 코드(`backend/engine/**`, `backend/strategy_conversation/{interpreter,compiler,validation}/**`, `backend/engine/nl_parser.py`) 변경
- 인증·세션·소유권 로직, `/api/backtest/history/**`의 소유권 검사 변경
- DB 스키마(`prisma/**`) 변경
- 그래프 DB, 그래프 편집으로 전략 변경, 추천·전망·성과 비교 기능
- 범용 스크립트(`scripts/**`) 변경

---

## Boundary Z: Public Strategy Simulation

### Purpose
공개(`Strategy.isPublic`) 저장 전략의 최근 3년 과거 데이터 시뮬레이션 결과를 로그인 없이 열람하고, 방문자가
지표 파라미터만 바꾼 임시 사본으로 같은 조건의 결과 차이를 확인하는 '전략 시뮬레이션' 기능 전용 boundary.
계약·작업 명세: `docs/development/strategy-simulation.md`. 상태: 구현 완료(2026-10-27) — Z-1~Z-10.

### Files
신규(새로 만들 파일):
- backend/public_simulation/** (`__init__.py`, `window.py`, `summary.py`, `params.py`)
- backend/api/public_simulation_routes.py
- backend/tests/test_public_simulation_*.py
- lib/server/publicSimulation/** (access, originals, modified 및 *.test.ts)
- app/api/strategy-simulation/** (route.ts, [publicId]/route.ts, [publicId]/run/route.ts 및 *.test.ts)
- app/strategy-simulation/page.tsx
- components/strategy-simulation/** (카드 그리드·미니 차트·상세 모달·수익률 차트·요약·파라미터 폼·재계산 훅 및 *.test.tsx)

수정(기존 파일, 범위 한정):
- backend/main.py (`include_router` 두 줄만)
- lib/i18n/en.ts (이 기능의 신규 문구 번역만)
- prisma/schema.prisma (`PublicSimulationResult` 모델과 `Strategy` 역관계 한 줄만) — 사용자 승인(명세 D1, 2026-10-27)으로 수정 완료
- prisma/migrations/20261027000000_public_strategy_simulation/** — 위와 같은 조건(운영 DB 적용 완료)

### Allowed Tasks
- 공개 조건(`isPublic && isSaved && deletedAt null`) 재검증, 불투명 `publicId`, 허용 목록 기반 공개 응답
- Asia/Seoul 기준 3년 창·데이터 기준일 계산과 기존 엔진 실행 경로(`backtest_executor.run` + 워치독) 재사용
- 엔진 결과의 공개 요약 축약(초기자금·최종 평가자산·총 손익·누적 수익률·MDD·CAGR·샤프·승률·거래 수, 누적 수익률 곡선, 손익 기여 상·하위 3종목)
- REGISTRY 기반 수정 가능 파라미터 설명자·서버 검증·깊은 복사본 적용
- 원본 결과 영속 캐시(D1 승인 시)·지연 갱신, 수정 결과 메모리 캐시·중복 합치기·요청 제한·동시 실행 제한
- 카드 목록·상세 모달·누적 수익률 차트 하나·파라미터 폼 UI와 회귀 테스트

### Strict Rules
- 한 작업은 이 boundary 안에서 3~5개 파일, 가능하면 200줄 미만. 내비게이션 연결은 Boundary Q, 문서 갱신은 Boundary G의 별도 작업이다.
- 모든 조회·실행·캐시 응답·저장 직전에 공개 조건을 DB로 다시 확인한다. 공개 철회·삭제된 전략의 결과는 어떤 경로로도 응답하지 않는다.
- 응답에 소유자 정보·`Strategy.id`·`symbols` 전체 목록·가상계좌·`BacktestHistory`·엔진 원본 결과를 싣지 않는다. 응답은 `Cache-Control: no-store`.
- 지표·준비 기간·비용·체결 계산은 엔진 값만 쓰고 재계산·보간하지 않는다. 실패를 0%·거래 없음으로 바꾸지 않는다.
- 스냅샷에 없는 설정을 기본값·recommended_value로 채우지 않는다(실행 불가로 표시). 프론트엔드에 지표 이름·단위·범위 사전을 두지 않는다.
- 방문자 수정은 원본의 깊은 복사본에만 적용하며 `Strategy`·원본 결과·사용자 기록 테이블에 쓰지 않는다. 월 백테스트 한도를 소비하지 않는다.
- 사용자 원문 해석·LLM·검색 호출을 하지 않는다. 추천·순위·우열·전망 표현을 쓰지 않는다.
- 새 파일이나 의존성이 필요하면 구현 전에 이 목록과 명세를 먼저 갱신한다.

### Forbidden
- 백테스트 엔진·지표·시뮬레이터·결과 처리(`backend/backtest_engine.py`, `backend/backtest_executor.py`, `backend/engine/**`) 변경
- provider 계층, 데이터 파일, 범용 스크립트(`scripts/**`, `backend/scripts/**`) 변경
- 기존 백테스트·전략·공유 라우트(`app/api/backtest/**`, `app/api/strategy/**`, `app/api/shared/**`)와 `lib/server/backtestCache.ts` 변경
- 인증·세션·소유권 로직 변경, 공개 플래그 토글 UI 변경
- `PublicSimulationResult` 외 Prisma 모델·컬럼 변경
- 조건 추가·삭제·지표 교체·자동 최적화·파라미터 탐색

---

## Global Forbidden Paths

Codex must NEVER modify:

- backend/engine/providers/**
- app/api/login/**
- app/api/register/**
- app/api/user/**
- scripts/**

Exception:
- `app/api/login/**`, `app/api/user/**`, and authentication logic are allowed only inside `Boundary O: Landing / Auth Entry Experience`, limited to sign-in/session bootstrap work explicitly requested by the task.
- `app/api/login/**`, `app/api/user/**`, and authentication logic are allowed inside `Boundary P: User Personalization / Ownership Persistence` only for user bootstrap, ownership enforcement, and idempotent personalization setup.
- `prisma/**` is allowed only inside `Boundary I: Strategy Persistence / BatchRun Storage`
- `prisma/**` is allowed inside `Boundary P: User Personalization / Ownership Persistence` only for user personalization models, ownership fields/FKs, and indexes required for per-user isolation.
- `prisma/**` is allowed inside `Boundary J: Stock Info Profile Persistence`
- `prisma/**` is allowed inside `Boundary M: News Impact Pipeline` only for news-specific models, migrations, and indexes
- `prisma/**` is allowed inside `Boundary Z: Public Strategy Simulation` only for the `PublicSimulationResult` model, the `Strategy` back-relation line, and its single migration — user decision D1 in `docs/development/strategy-simulation.md` was approved on 2026-10-27 and the migration is applied

---

## Boundary Selection Rule

Before running Codex:

1. Choose ONE boundary
2. List allowed files
3. Confirm no cross-boundary edits

If violated → ABORT
