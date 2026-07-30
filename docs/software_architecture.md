# Software Architecture

> 한국/글로벌 주식 퀀트 투자 플랫폼 — Simons
> **최종 갱신일:** 2026-06-12

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [전체 디렉토리 구조](#2-전체-디렉토리-구조)
3. [프론트엔드 아키텍처](#3-프론트엔드-아키텍처)
4. [백엔드 아키텍처](#4-백엔드-아키텍처)
5. [데이터 레이어](#5-데이터-레이어)
6. [API 통신 구조](#6-api-통신-구조)
7. [AI/ML 파이프라인](#7-aiml-파이프라인)
8. [테스트 구조](#8-테스트-구조)
9. [외부 의존성](#9-외부-의존성)
10. [환경 설정](#10-환경-설정)
11. [데이터 흐름](#11-데이터-흐름)

---

## 1. 프로젝트 개요

사용자가 **LLM과 대화**하여 자연어로 투자 전략을 설계하고, 백테스트(과거 데이터)와 가상매매(모의 시장)로 검증하는 풀스택 퀀트 플랫폼.

### 서비스 규제 포지셔닝

- Simons는 투자 연구 및 시뮬레이션 플랫폼이며 투자 자문, 투자 추천, 개인 맞춤형 금융 조언을 제공하지 않는다.
- 시스템은 계산, 백테스트, 시뮬레이션, 객관적인 과거 데이터 표시만 수행하고 모든 투자 판단은 사용자가 직접 수행한다.
- 아키텍처 차원에서 전략 추천, 종목 추천, 섹터/ETF 추천, 포트폴리오 추천, 시장 전망, 매수/매도 시점 제안, 개인 맞춤형 조언 기능은 지원 대상이 아니다.
- AI 코치, Advisor, 리포트, 마케팅 카피는 미래 성과 보장, 우열 판단, 사용 권장, 맞춤 추천 표현을 생성하거나 노출해서는 안 된다.

| 항목 | 기술 |
|------|------|
| 프론트엔드 | Next.js 14 (App Router) + TypeScript + Tailwind CSS |
| 백엔드 | FastAPI (Python) + Uvicorn |
| ORM / DB | Prisma + SQLite |
| 백테스팅 엔진 | VectorBT + Polars + Pandas |
| AI/ML | PyTorch Transformer + XGBoost + SHAP |
| 전략 조언 | RAG (bge-m3 의미 임베딩 + ChromaDB 벡터 코퍼스) + Experience Memory + 백테스트 개선 전/후 평가 |
| 자연어 파싱 | Rule-first parser + LLM (MLX / Ollama) + JSON repair/fallback |
| 테스트 | Vitest (프론트) + Pytest (백엔드) |

### 전략 설계 방식

사용자는 UI 블록 조합 없이 **자연어 채팅**으로 전략을 설계한다:

```
사용자: "RSI 30 이하일 때 매수하고 20% 수익 나면 팔아줘. KOSPI200에서"
    ↓
LLM (MLX or Ollama) → ParsedStrategy (구조화된 JSON)
    ↓
strategy_converter → BacktestRequest
    ↓
백테스트 엔진 실행 → 결과 시각화
```

---

## 2. 전체 디렉토리 구조

```
simons/
├── app/                             # Next.js App Router (페이지 + API 라우트)
│   ├── api/                         # API 라우트 (Next.js → FastAPI 프록시)
│   │   └── strategy/
│   │       ├── batch-runs/route.ts  # 독립형 배치 백테스트 queue/worker + 이력 API
│   │       ├── backtest-stream/route.ts # 단일 전략 SSE 백테스트 + cache
│   │       ├── route.ts             # Strategy 저장/조회 (strategy_id 기반)
│   │       └── save-with-backtest/route.ts # 전략 저장 + 백테스트
│   ├── analytics/
│   │   ├── new/page.tsx             # 전략 Lab 메인 (LLM 채팅 + 백테스트)
│   │   └── [id]/page.tsx            # 저장된 전략 상세 조회
│   ├── backtest/[id]/               # 백테스트 결과 상세 페이지
│   ├── kospi/                       # KOSPI 시장 페이지
│   ├── login/, register/            # 인증 페이지
│   ├── stock/[symbol]/              # 개별 종목 상세 페이지
│   ├── stock-order/                 # 가상 주문 실행 페이지
│   ├── virtual-account/             # 가상 계좌 관리 페이지
│   ├── watchlist/                   # 관심 종목 페이지
│   └── layout.tsx, page.tsx         # 루트 레이아웃 + 대시보드 홈
│
├── components/
│   ├── dashboard/                   # 대시보드 위젯
│   ├── strategy/
│   │   ├── backtest/                # BacktestDashboard, BacktestConfig, BacktestStatsSummary 등
│   │   ├── RunAllTestsModal.tsx     # 독립형 Batch Backtest Results 모달
│   │   ├── StrategyExampleTabs.tsx  # 전략 예시 프롬프트 탭
│   │   └── legacyBreakout.ts        # 레거시 데이터 정규화 유틸
│   ├── stock/                       # 종목 관련 컴포넌트
│   │   └── NewsImpactPanel.tsx      # 뉴스·공시 + Alpha 시그널 패널 (stock-order 뉴스 탭)
│   ├── portfolio/                   # 포트폴리오 분석 컴포넌트
│   ├── order/                       # 주문서 및 호가 컴포넌트
│   ├── layout/                      # 전역 레이아웃 (TopMenuBar, TopNavigation)
│   ├── ui/                          # 기본 UI (Input, Button, Modal 등)
│   ├── virtual-account/             # 가상 계좌 컴포넌트
│   └── watchlist/                   # 관심 종목 컴포넌트
│
├── lib/
│   ├── strategy/
│   │   ├── BacktestService.ts       # 백테스트 실행 오케스트레이터
│   │   └── pipeline/UniverseResolver.ts  # 유니버스 종목 목록 캐싱
│   ├── server/
│   │   ├── backend.ts               # FastAPI 프록시 fetch wrapper
│   │   ├── backtestCache.ts         # strategy_id 기반 캐시/영구 저장 유틸
│   │   └── stock-prices.ts          # 서버 사이드 주식 가격 조회
│   ├── hooks/                       # React Hooks (useDelistingStatus 포함)
│   ├── stock-api/                   # 주식 데이터 API 공급자
│   ├── listing-status.ts            # 상장 상태 유틸 (isBuyAllowed, getStatusBadge 등)
│   ├── backtest-engine.ts           # 프론트엔드 백테스트 흐름 조율
│   └── prisma.ts                    # Prisma Client 싱글톤
│
├── types/
│   ├── strategy.ts                  # StrategyDSL, Condition, BacktestResult 등
│   ├── stock.ts                     # StockQuote, StockHistoricalData 등
│   ├── portfolio.ts                 # VirtualAccount, PortfolioHolding, Transaction
│   ├── market.ts                    # 시장 지표 타입
│   └── dashboard.ts                 # 대시보드 데이터 타입
│
├── backend/
│   ├── main.py                      # FastAPI 앱 진입점
│   ├── backtest_engine.py           # 백테스트 실행 오케스트레이터
│   ├── schemas.py                   # Pydantic 모델 (Request/Response)
│   ├── engine/
│   │   ├── loader.py                # DataLoader (OHLCV 로드 + 캐싱)
│   │   ├── indicators.py            # IndicatorEngine (지표 계산)
│   │   ├── signals.py               # SignalEngine (조건 평가, 벡터화)
│   │   ├── simulator.py             # Simulator (루프=의도 결정 + vbt from_orders 목표비중 체결 — NAV 사이징·정수주·장중 스탑·거래정지 이월·매도 거래세)
│   │   ├── rebalance.py             # 달력 기준 리밸런싱일 계산 (vbt 비의존)
│   │   ├── result_handler.py        # ResultHandler (지표 계산 + 직렬화)
│   │   ├── version.py               # 엔진 버전 SOT(ENGINE_VERSION·CHANGELOG). MAJOR=결과값 변경, MINOR=표시/버그. 결과에 기록됨(BacktestResponse.version)
│   │   ├── nl_parser.py             # 자연어 → ParsedStrategy (LLM)
│   │   ├── strategy_converter.py    # ParsedStrategy → BacktestRequest
│   │   ├── universe_pit.py          # PIT(생존편향 제거) 유니버스 + 섹터 유니버스(CANONICAL_SECTORS·normalize_sector·filter_by_sector) + ETF 유니버스(resolve_etf_symbols·filter_etf_by_theme·extract_etf_theme)
│   │   ├── universe_capabilities.py # 유니버스별 지원 팩터 레지스트리(ETF=기업 재무지표 불가, FR-STR-067)
│   │   ├── term_grounding.py        # 용어 그라운딩 — 어휘집→지식그래프→LLM→검색 체인으로 테마 용어를 정본 섹터에 매핑(FR-STR-069)
│   │   ├── knowledge_graph.py       # Investment Knowledge Graph — 개념·공급망·기업·ETF 노드/엣지 합성·탐색(FR-STR-070, docs/knowledge_graph.md)
│   │   ├── data_resolver.py         # 유니버스 필터링
│   │   ├── virtual_trader.py        # 가상매매 실시간 엔진 (상장 상태 체크 포함)
│   │   ├── listing_status.py        # 상장 상태 머신 (7단계) + DART 분류 + DB 동기화
│   │   ├── walk_forward.py          # 워크포워드 분석
│   │   ├── market_data.py           # 시장 데이터 조회
│   │   └── providers/               # 데이터 공급자 (KIS, pykrx, Naver, yfinance)
│   ├── ai/
│   │   ├── ai_engine.py             # Hybrid Transformer+XGBoost 추론 엔진
│   │   ├── models.py                # PyTorch 모델 정의
│   │   ├── xai_engine.py            # SHAP 기반 설명 가능 AI
│   │   └── summarize.py             # 백테스트 결과 AI 요약 (Claude API)
│   ├── advisor/                     # RAG + Experience Memory 전략 조언 Agent
│   │   ├── agent.py                 # 전략 진단/조언 오케스트레이터
│   │   ├── strategy_identity.py     # canonical DSL + SHA-256 strategy_id
│   │   ├── similarity.py            # 텍스트/구조 기반 유사도 계산
│   │   ├── memory_retriever.py      # 과거 유사 전략/경험 검색
│   │   ├── memory_repository.py     # AdviceExperience 저장/조회
│   │   ├── candidate_generator.py   # 개선 후보 전략 생성
│   │   ├── advice_evaluator.py      # 개선 전/후 성과 평가
│   │   └── response_composer.py     # 사용자 답변 섹션 구성
│   ├── vector_memory/               # ChromaDB 벡터 메모리(적재/쿼리 스키마·정규화·임베딩)
│   │   └── embedding.py             # bge-m3 의미 임베딩(1024차원) + 해싱 폴백
│   ├── corpus/                      # RAG 코퍼스 생성기(비-AI 전략 + NL 템플릿 설명)
│   │   ├── generator.py             # 다양한 비-AI 전략 DSL 샘플링(strategy_hash dedup)
│   │   └── nl_templates.py          # DSL→한국어 설명 결정적 렌더러
│   ├── scripts/build_strategy_corpus.py  # 생성→병렬 백테스트→bge-m3 임베딩→Chroma 적재
    │   ├── news/                        # 뉴스 Impact AI Agent
    │   │   ├── schemas.py               # NormalizedArticle, NewsImpact Pydantic 모델
    │   │   ├── dedup.py                 # 중복 제거 (Jaccard + body hash, 24h 윈도우)
    │   │   ├── collector.py             # 뉴스 수집 오케스트레이터
│   │   ├── analyzer.py              # 이벤트 분류 + alpha 계산
│   │   ├── storage.py               # DB 저장/조회
│   │   ├── news_routes.py           # FastAPI 라우터 (6개+ 엔드포인트)
    │   │   └── providers/
    │   │       ├── naver_news.py        # Naver Finance RSS (4피드, 무인증)
    │   │       └── rss_provider.py      # 한국경제·연합뉴스·매일경제 RSS
    │   ├── news_v2/                     # 종목 뉴스탭 캐시 파이프라인
    │   │   ├── models.py                # raw/analysis/cache/priority/queue 모델
    │   │   ├── repository.py            # 캐시 조회, dedup, mapping, priority 저장소
    │   │   ├── service.py               # collector→analysis→cache 오케스트레이션
    │   │   ├── priority.py              # 사용자 수요 기반 Priority Engine
    │   │   ├── tasks.py                 # Celery collect/analyze/maintenance tasks
    │   │   ├── scheduler.py             # Hot/Warm/Cold queue scheduler + worker autostart
    │   │   └── routes.py                # 캐시 전용 종목 뉴스 API
    │   ├── research/                    # Strategy Research Agent
│   │   ├── agent.py                 # StrategyResearchAgent 오케스트레이터 (상태머신)
│   │   ├── generator.py             # 후보 전략 생성기 (SHA256 dedup, seeded)
│   │   ├── search_space.py          # 템플릿별 파라미터 탐색 공간
│   │   ├── scoring.py               # 복합 스코어 (tanh-bounded, Deflated Sharpe)
│   │   ├── safeguards.py            # HoldoutGuard / CircuitBreaker / AIModelLeakGuard
│   │   ├── events.py                # SSE 이벤트 팬아웃 (DB + asyncio.Queue)
│   │   ├── prescreen.py             # 50종목 샘플 프리스크린
│   │   ├── robustness.py            # MC + WFA 견고성 검증
│   │   ├── promoter.py              # VirtualAccount 자동 승격
│   │   └── templates/               # 전략 템플릿 (momentum/mean_reversion/value/volume_breakout/ai_signal)
│   ├── intent/                      # 사용자 질문 의도 분류 (STRATEGY / STOCK_ANALYSIS / …)
│   │   ├── classifier.py            # 결정적 하이브리드 분류기 (규칙 + LLM 폴백)
│   │   └── schemas.py               # IntentResult Pydantic 모델
│   ├── stock_analysis/              # 종목 해석 유틸 (개별 종목 '분석' 파이프라인은 제거 — 종목 질문은 전략 설계 전환 안내로 응답)
│   │   ├── stock_master.py          # 종목 마스터 (Ground Truth) + 별칭/티커 해석
│   │   ├── symbol_resolver.py       # 자연어 → 종목코드 해석 (find_in_text)
│   │   ├── news_service.py          # news_v2 DB(감성) async 조회 (advisor 뉴스 보강에서 사용)
│   │   └── guardrails.py            # 금지 표현 필터 + 면책 문구 (/query/general에 적용)
│   ├── api/
│   │   ├── coach_routes.py          # FastAPI AI 전략 코치 라우터 (단건 + SSE 스트리밍)
│   │   ├── advisor_routes.py        # RAG/Experience Memory 전략 리뷰 라우터
│   │   ├── news_routes.py           # 뉴스 FastAPI 라우터
│   │   ├── intent_routes.py         # 질문 의도 분류·전략 빌더·일반 질문 API (/query/classify 등)
│   │   └── research_routes.py       # FastAPI 연구 에이전트 라우터 (9개 엔드포인트, SSE)
│   └── tests/                       # 백엔드 단위 테스트
│
├── data/
│   ├── ohlcv/                       # 4052개 한국 주식 OHLCV Parquet 파일
│   ├── fundamentals/                # 재무 지표 (ROE, EPS, BPS 등)
│   ├── korea-stocks.json            # 한국 주식 메타데이터
│   └── kospi200-cache.json          # KOSPI200 캐시
│
├── model/
│   ├── xgboost_head.json            # XGBoost 모델
│   ├── transformer_engine.pt        # PyTorch Transformer 체크포인트
│   ├── feature_scaler.joblib        # 입력 특성 스케일러
│   └── v2/                          # 모델 v2 (업/다운 분리 XGBoost)
│
├── prisma/schema.prisma             # DB 스키마
├── scripts/                         # 유틸 스크립트 (scheduler, sync, train)
└── contexts/OrderAccountContext.tsx # 주문 페이지 선택 계좌 상태
```

---

## 3. 프론트엔드 아키텍처

### 3.1 페이지 구조

| 경로 | 용도 | 핵심 컴포넌트 |
|------|------|-------------|
| `/` | 대시보드 홈 | `PortfolioSummaryBar`, `AccountProfitChart`, `VirtualTradingStatus`, `MarketSnapshot` |
| `/analytics/new` | **전략 Lab** — LLM 채팅으로 전략 설계 + 백테스트 + 독립형 배치 테스트 | `StrategyExampleTabs`, `RunAllTestsModal`, `BacktestDashboard` |
| `/analytics/[id]` | 저장된 전략 상세 조회 | `BacktestDashboard` |
| `/backtest/[id]` | 백테스트 결과 상세 | `BacktestDashboard` |
| `/kospi` | KOSPI 시장 현황 | `MarketSnapshot` |
| `/login`, `/register` | 사용자 인증 | `AuthCard` |
| `/stock/[symbol]` | 종목 상세 (차트, 호가, 뉴스) | `StockDetail`, `CandlestickChart`, `OrderBook` |
| `/stock-order` | 종목 거래 (5탭) | 차트·호가 / 종목정보 / 뉴스·공시(`NewsImpactPanel`) / 거래현황 / 커뮤니티 |
| `/virtual-account` | 가상 계좌 목록 | `VirtualAccountCard` |
| `/virtual-account/[id]` | 가상 계좌 상세 (포트폴리오) | `VirtualAccountMainView` |
| `/watchlist` | 관심 종목 관리 | `Watchlist` |
| `/console` | **관리자 콘솔** (운영자 전용, 단일 화면 탭 — Overview/Users/Backtests/Accounts/Strategies/Plans/Knowledge/Agents/Audit) | `AdminConsole` + `components/admin/*Tab` |

`/stock-order`의 종목정보 탭은 실시간 시세와 분리된 비실시간 종목 프로필 레이어를 사용한다. 종목명, 상장일, 섹터, 회사 기본 정보, 재무 요약, PER/PBR 같은 저빈도 갱신 값은 DB에 저장하고, 현재가/등락률/거래량 등 실시간 값은 기존 실시간 시세 경로에서 조회한다.

요금제 & 플랜 제한 시스템(`lib/plans.ts`, `lib/server/planLimits.ts`)이 가상계좌의 자금과 사용량 한도를 결정한다. 과거의 공유 "자산 지갑" 풀(`UserAsset.availableCash`에서 차감·반환) 모델은 폐기되었다. 각 가상계좌는 사용자의 현재 플랜(`User.planTier`, FREE/PRO/PREMIUM)에 정의된 **계좌당 초기 투자금**으로 독립 생성되며(`createFundedAccount`는 풀 차감 없이 계좌만 생성), 클라이언트가 보낸 금액은 무시하고 서버가 플랜 기준으로 결정한다. 플랜별 한도는 가상계좌 수(`assertCanCreateAccount`)·저장 전략 수(`assertCanSaveStrategy`)·월 백테스트 횟수(`consumeBacktestQuota`)로 enforce한다. 유료 플랜(PRO/PREMIUM) 구독이 결제 승인으로 시작되면 그 시점을 `User.planStartDate`로 기록하고(FREE 전환 시 null로 초기화), 월 백테스트 횟수는 `currentPlanCycle()`이 계산하는 **구독 시작일 기준 롤링 1개월 결제 주기**(`User.backtestUsageMonth`/`backtestCountThisMonth`로 주기 키 저장)로 리셋된다 — 구독 이력이 없는 사용자(FREE)는 KST 캘린더 월로 폴백한다. 가상계좌 수·저장 전략 수 한도는 주기 리셋 없이 상시 캡으로 유지된다(활성 계좌/저장된 전략 개수). 플랜 변경은 `planTier`만 변경하며 이미 생성된 계좌의 초기 투자금·잔고는 소급 변경하지 않는다. 플랜별 한도 기본값은 `lib/plans.ts`에 하드코딩되어 있고, 관리자 콘솔의 `PlanConfig` 오버라이드가 있으면 `getEffectivePlan()`이 병합해 적용한다(null 필드=기본값, `maxStrategies=-1`=무제한).

**토스페이먼츠 자동결제(빌링) 연동** (유료 플랜 구독 결제, FR-PLAN-011/011a): v2 SDK(`@tosspayments/tosspayments-sdk`)의 빌링 방식을 사용한다 — 카드를 한 번 등록해 빌링키를 발급받고, 이후 매월 서버가 자동 청구한다. 시작 흐름은 ① `/pricing`에서 유료 플랜 "구독 시작하기" → `/pricing/checkout?plan=` 이동 ② `PaymentCheckout`(클라이언트)이 `POST /api/payment/order`로 주문 생성 — 금액은 서버의 `lib/plans.ts`에서만 계산해 `PaymentOrder`(PENDING)에 기록, `customerKey`는 사용자당 1회 생성한 UUID(`User.tossCustomerKey`) — 하고 자동갱신 결제 조건(월 금액·자동 청구·해지 방법)을 화면에 고지 ③ `tossPayments.payment({customerKey}).requestBillingAuth({method:"CARD"})`로 카드 등록창 호출(successUrl=`/pricing/success?orderId=`, failUrl=`/pricing/fail`) ④ 성공 페이지가 `POST /api/payment/confirm` 호출 — successUrl로 돌아온 `customerKey`를 서버 저장 값과 대조한 뒤 `authKey`로 빌링키 발급(`/v1/billing/authorizations/issue`) → 첫 달 이용료를 서버 저장 주문 금액으로 즉시 청구(`/v1/billing/{billingKey}`, `lib/server/tossPayments.ts`, Basic 인증=`base64(시크릿키:)`, 멱등키=orderId)하고, 성공 시에만 트랜잭션으로 `PaymentOrder`를 DONE 처리하고 `planTier`/`planStartDate`/`tossBillingKey`/`subscriptionPlanId`/`nextBillingAt`(+1개월)을 갱신한다. 같은 주문의 재승인 요청(성공 페이지 새로고침)은 기존 결과를 반환한다(멱등).
**월 자동 갱신**: 인-프로세스 스케줄러(`lib/scheduler.ts`)가 매시 정각(주말 포함) `lib/server/billingRenewal.ts::processDueBillingRenewals()`를 실행한다 — `nextBillingAt`이 지난 구독을 빌링키로 청구(갱신 결제도 `PaymentOrder` 기록)하고 성공 시 `nextBillingAt`을 **예정 시각 기준** +1개월로 굴린다(재시도 지연으로 주기가 밀리지 않게). 실패 시 1일 후 재시도, 연속 3회(`BILLING_MAX_FAIL_COUNT`) 실패 시 FREE 전환 + 빌링 상태 해제. 사용자별 실패는 격리된다. **해지**: `POST /api/payment/billing/cancel`은 즉시 다운그레이드가 아니라 `subscriptionCanceledAt`만 기록(해지 예약, 멱등)하고, 다음 결제일에 갱신 잡이 청구 없이 FREE로 전환한다 — 요금제 페이지가 다음 결제일/해지 버튼(자동갱신 중) 또는 만료일(해지 예약)을 표시한다. `POST /api/user/plan`은 FREE 다운그레이드만 허용해 결제 없는 유료 전환을 차단하며, FREE 전환 시 빌링키·구독 상태를 함께 해제한다. 빌링키(`User.tossBillingKey`)와 시크릿 키는 서버 전용이다. 환경변수: `NEXT_PUBLIC_TOSS_CLIENT_KEY`(클라이언트), `TOSS_SECRET_KEY`(서버 전용) — 현재 문서 공용 테스트 키이며 프로덕션 배포 시 **자동결제(빌링) 계약이 완료된 상점의 라이브 키**로 교체(미계약 키는 `NOT_SUPPORTED_METHOD` 에러)하고 `prisma migrate deploy`(PaymentOrder + User 빌링 컬럼)를 실행해야 한다.

**관리자 콘솔** (`/console` — `app/console/page.tsx` + `components/admin/`): 운영자 전용 단일 화면. 서버 컴포넌트가 `lib/server/adminAuth.ts::requireAdmin()`(JWT 쿠키 + `User.role='ADMIN'` + `status='ACTIVE'`)으로 검증해 실패 시 `notFound()`(404)로 존재를 숨긴다. 기능별 API `/api/admin/{overview,users,backtests,accounts,strategies,plans,audit}` 7종도 각각 requireAdmin 게이트를 거치며, 모든 변경 작업은 `writeAuditLog()`가 `AdminAuditLog`(before/after JSON + IP)에 기록한다 — 감사 로그 삭제 API는 없다. ADMIN 부여는 DB 직접 변경으로만 가능하다. 사용자 정지/삭제는 `User.status`(SUSPENDED/DELETED) soft 처리로, 로그인(403)과 기존 세션(`getCurrentUser`가 null)을 모두 차단한다. 가상계좌 '일시 중지'는 `status='PAUSED'`로, 기존 `assetService`의 `status !== "ACTIVE"` 주문 가드가 거래를 자동 차단한다.
가상계좌 해지 요청(`DELETE /api/virtual-account/[id]`)은 보유 포지션을 현재가 기준으로 강제 매도하고 계좌를 `CLOSED`로 전환하되, 남은 현금·평가금액을 다른 계좌나 사용자 자산으로 **이전하지 않는다**. 정산값은 `ACCOUNT_LIQUIDATION_RETURN` 원장에만 기록되어 닫힌 계좌의 최종 평가금액/수익률 조회(`getAccountSettlementValues`)에 쓰인다.
가상계좌 목록 카드의 해지 버튼은 즉시 삭제하지 않고 해지 확인 모달("남은 현금과 보유 종목은 다른 계좌로 이전되지 않습니다")을 먼저 표시하며, 사용자가 확인해야만 위 해지 로직이 실행된다.

### 3.2 전략 Lab 컴포넌트 구조 (`/analytics/new`)

```
StrategyLabPage (app/analytics/new/page.tsx)
├── StrategyExampleTabs          — 초보/중급/고급별 예시 프롬프트 제공 (가치투자·기술분석·모멘텀·복합전략 4개 카테고리; AI 모델 예시·"AI 전략" 카테고리는 2026-06-09 제거)
├── Run All Tests CTA            — 독립형 배치 테스트 모달 오픈
├── 채팅 입력창
│   └── handleSend()             — POST SSE via /api/strategy/parse/stream
├── Strategy Skeleton UI         — accepted/skeleton 이벤트로 즉시 임시 전략 표시
├── Strategy Summary Card        — 노란 테두리 카드로 파싱 결과 요약 표시
├── AdvisorResultBubble          — /api/advisor/review 결과를 핵심 조언 말풍선으로 압축 표시
├── AI Runtime Metrics Panel     — parse/coach/summary latency 표시
├── RunAllTestsModal
│   ├── startBatchRun()          — POST /api/strategy/batch-runs
│   ├── fetchBatchRunDetail()    — GET /api/strategy/batch-runs?runId=...
│   ├── fetchBatchRunHistory()   — GET /api/strategy/batch-runs
│   └── cancelBatchRun()         — POST /api/strategy/batch-runs { action: "cancel" }
└── BacktestDashboard (dynamic import)
    ├── BacktestConfig
    ├── BacktestStatsSummary
    ├── BacktestChart
    ├── WalkForwardModal
    └── XAIModal                 — SHAP 설명
```

전략 Lab의 코치 UX는 오른쪽 고정 패널을 사용하지 않는다. 파싱 완료 후 `/api/advisor/review` 결과를 같은 대화 흐름의 말풍선으로 표시하며, 사용자에게 RAG/Experience Memory/유사 사례 출처를 설명하지 않고 성과 신호, 비교 후보, 리스크 조치만 노출한다. 조언은 우선순위 상위 3개만 표시하고 나머지는 백테스트 결과 확인 후 이어서 볼 수 있다는 짧은 안내로 접는다. advisor learning evidence는 내부 참고용이며, "백테스트 학습 사례 N건", 성과 중앙값, 복수 파라미터 후보를 나열하는 옛 템플릿 문장은 코치 입력 압축 단계와 최종 응답 파싱 단계에서 차단한다.

### 3.3 상태 관리

| 방식 | 용도 |
|------|------|
| React Query (`useQuery`) | 서버 데이터 캐싱 (백테스트 이력, 계좌 목록 등) |
| React Query (`useMutation`) | 서버 상태 변경 (전략 저장, 주문 체결 등) |
| React Context (`OrderAccountContext`) | 주문 페이지에서 공유하는 선택된 계좌 ID |
| `useState` | 채팅 메시지 히스토리, 파싱된 전략 상태, 백테스트 결과, 배치 실행 UI 상태 |

### 3.3.1 사용자 자산 API

| 메서드 | 경로 | 역할 |
|--------|------|------|
| GET | `/api/user/assets` | 사용 가능 자산, 활성 계좌 평가금액 합계, 계산된 총자산, 활성 계좌 목록 조회 |
| GET | `/api/user/assets/ledger` | `INITIAL_GRANT`, `ACCOUNT_ALLOCATION`, `ACCOUNT_LIQUIDATION_RETURN`, `FORCE_SELL` 등 자산 이동 내역 조회 |
| POST | `/api/virtual-account` | 사용 가능 자산 검증 후 계좌 초기 투자금 배정 |
| DELETE | `/api/virtual-account/[id]` | 포지션 강제청산, 자산 반환, 계좌 `CLOSED` 처리 |

프로필 메뉴의 `자산` 항목은 현재 위치에서 자산 요약 모달을 열고 `/api/user/assets` 계산값을 표시한다. `/assets` 화면도 저장된 총자산 값을 사용하지 않고 같은 자산 조회 로직을 서버에서 다시 계산해 상세 내역을 표시한다.

### 3.4 핵심 타입 (`types/`)

```typescript
// 전략 DSL — 백테스트 엔진이 받는 최상위 타입
interface StrategyDSL {
  name: string
  version: string
  universe: Universe
  entry: ConditionGroup[]
  exit: ConditionGroup[]
  risk: RiskManagement
}

// 리스크 관리
interface RiskManagement {
  stop_loss_pct?: number
  take_profit_pct?: number
  trailing_stop_pct?: number
  max_holding_days?: number
  max_positions?: number
}

// 백테스트 결과
interface BacktestResult {
  totalReturn: number
  cagr: number
  sharpe: number
  sortino: number
  maxDrawdown: number
  winRate: number
  profitFactor: number
  trades: number
  kelly: number
  dates: string[]
  equity: number[]
}
```

### 3.5 독립형 배치 백테스트 UI

- `RunAllTestsModal`은 기존 `backend/research/*`와 연동하지 않는다.
- 프롬프트 데이터셋은 빈 줄 단위로 분할해 서버 `BatchRun`으로 전달한다.
- 리더보드는 `CAGR` 기준 기본 내림차순 정렬이며, `Total Return`, `Sharpe`, `MDD`, `Profit Factor`, `Trades` 기준으로도 재정렬 가능하다.
- 각 후보 상태는 `waiting`, `running`, `computed`, `cache_hit`, `failed`, `skipped` 중 하나로 표시된다.
- 실행 중 이력 재조회 시 같은 `runId`를 폴링해 계속 진행 상태를 반영한다.
- Advisor learning용 export는 `format=advisor-learning-results`를 사용한다.
- 대형 learning run은 실패/중단 시 source run과 resume run을 `advisor_smoke_0001`..`advisor_smoke_10000` sample_id 기준으로 병합해 `data/advisor-learning` artifact를 재생성한다.

---

## 4. 백엔드 아키텍처

### 4.1 FastAPI 엔드포인트

**전략 설계 (LLM)**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/strategy/parse` | 자연어 → ParsedStrategy + BacktestRequest 변환 |
| POST | `/strategy/backtest-stream` | 백테스트 실행 (SSE 스트리밍) |
| POST | `/strategy/coach` | AI 전략 코치 응답 생성 (단건, Qwen MLX) |
| POST | `/strategy/coach/stream` | AI 전략 코치 SSE 스트리밍 (토큰 단위, Qwen MLX) |
| POST | `/advisor/review` | RAG + Experience Memory 기반 전략 진단/개선 조언 |

**백테스트**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/backtest` | 백테스트 실행 (VectorBT 시뮬레이션) |
| POST | `/optimize` | 전략 파라미터 최적화 (Optuna) |
| POST | `/walk-forward` | 워크포워드 분석 |

`/backtest`·`/strategy/backtest-stream`은 워치독(`engine/watchdog.py`)이 감싼다 — 엔진이
행(hang)에 빠져도 벽시계 제한 시간(`BACKTEST_TIMEOUT_S`, 기본 600초) 안에 504/SSE 에러로
반드시 끝난다. AI 신호(ai_model/ai_drop_model) 백테스트는 엔진 최종 관문에서 fail-fast:
운영 스위치 `AI_SIGNALS_ENABLED=0`이거나 AI 모델 로드 실패 시 0거래 침묵 진행 대신 즉시
명확한 에러를 반환한다.

**시장 데이터**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/stock/{symbol}/ohlcv` | OHLCV 캔들 데이터 |
| GET | `/market/price/{symbol}` | 현재가 조회 |
| GET | `/market/stock-detail/{symbol}` | 종목 상세 (호가, 거래량) |
| POST | `/market/prices` | 배치 현재가 조회 |
| GET | `/market/orderbook/{symbol}` | 호가창 |
| GET | `/market/orderbook-stream/{symbol}` | 호가창 스트리밍 |
| GET | `/market/indices` | 시장 지표 (KOSPI, KOSDAQ, 환율 등) |

**AI**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/model/status` | AI 모델 상태 확인 |
| GET | `/ai/runtime/metrics` | AI 런타임 latency 메트릭 조회 |
| POST | `/ai/runtime/metrics/reset` | AI 런타임 메트릭 초기화 |
| POST | `/summarize` | 백테스트 결과 AI 요약 (Claude API) |

**질문 의도 분류 / 일반 질문 (intent_routes)**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/query/classify` | 사용자 질문 의도 분류 (STRATEGY / STOCK_ANALYSIS / STOCK_PICK / GENERAL). [규제 안전] STOCK_ANALYSIS(특정 종목 매수·매도 질문)는 종목 분석 대신 '추천 불가 안내 + 그 종목에서 출발한 전략 설계 전환' 문구(suggested_reply)를 동반한다 — 개별 종목 분석 기능(/stock/analyze)은 제거됨. 요청 `history`(최근 대화 턴, `ChatTurn[]`)를 받아 LLM 폴백이 "다른 예는 없어?" 같은 후속 질문을 직전 주제의 연속으로 분류한다(FR-SA-002c-3, 결정적 규칙은 현재 입력만 봄). 라벨과 직교하는 **워크플로 제어 축**(`workflow_effect`: 멈춤·이어하기·취소·초기화·되돌리기)을 같은 LLM 호출로 함께 판정하고, 성립 여부는 결정론 코드가 정한다(규제 게이트 라벨은 제어 거부, 불성립은 NONE 강등). 상태(`workflow_status`)는 서버에 저장하지 않고 프론트가 매 요청에 에코한다 — FR-SA-007 |
| POST | `/query/general` | 분류·종목 비매칭 일반 질문 응답. `history`를 받아 후속 질문이면 직전 답변과 겹치지 않게 이어서 답한다 |
| POST | `/strategy/builder/step` | 전략 빌더 모드 한 턴 — 열린 추천(STOCK_PICK) 전환 직후 짧은 답변을 전략 필드로 누적하고, 완성 시 백테스트 프롬프트 합성. 결정적 상태 머신 `intent/strategy_builder.py`(무상태). 프론트 `builderModeRef`/`builderStateRef`가 상태 보관·재전송 |

**뉴스 Impact Agent**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/news/articles` | 전체 뉴스 목록 (페이징) |
| POST | `/news/collect` | 뉴스 수집 트리거 |
| GET | `/news/symbol/{symbol}` | 종목별 뉴스 (as_of 지원) |
| GET | `/news/impact/{symbol}` | 종목 Alpha 시그널 (latest_alpha) |
| GET | `/news/top` | 주요 뉴스 |
| GET | `/news/fetch-body` | 기사 본문 일부 추출 (SSRF 방어 적용) |

**종목 뉴스탭 캐시 API (news_v2)**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/v2/news/{symbol}` | FastAPI 캐시 전용 종목 뉴스 조회. `stock_news_cache`만 읽고 crawler/agent/LLM을 실행하지 않음 |
| POST | `/v2/news/events` | 종목 조회/검색/관심종목/보유종목 등 priority event 기록 |
| GET | `/v2/news/priority` | Priority score, Hot/Warm/Cold queue 상태 모니터링 |

**Strategy Research Agent (Premium)**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/research/templates` | 지원 전략 템플릿 목록 |
| POST | `/research/runs` | 리서치 런 시작 (BackgroundTask) |
| GET | `/research/runs` | 사용자 런 목록 |
| GET | `/research/runs/{id}` | 런 상태 조회 |
| DELETE | `/research/runs/{id}` | 런 취소 |
| GET | `/research/runs/{id}/candidates` | 후보 전략 목록 |
| GET | `/research/candidates/{id}` | 후보 상세 |
| POST | `/research/candidates/{id}/promote` | 페이퍼 트레이딩 승격 |
| GET | `/research/runs/{id}/audit` | 감사 로그 |
| GET | `/research/runs/{id}/stream` | SSE 실시간 이벤트 스트림 |

### 4.2 자연어 → 전략 파싱 파이프라인

```
사용자 입력: "RSI 30 이하 매수, KOSPI200, 손절 8%"
    │
    ▼
NLStrategyParser.parse() (backend/engine/nl_parser.py)
    ├── rule-first fast path: 명확한 정량 조건은 deterministic extractor로 즉시 파싱
    │   └── 커버리지 가드: 스키마가 표현할 수 없는 '미지원 개념'(_mentions_unsupported_concept
    │       — 변동성·현금흐름·섹터 분산·정배열·시장대비·배당·수급 등 유한 목록)을 언급하면
    │       규칙 기반은 부분 파싱을 내놓지 않고 None을 반환해 LLM 폴백에 위임(침묵 누락 방지).
    │   └── Rule Parse Guard(하이브리드): REGEX 매칭 ≠ 올바른 파싱.
    │       ① 결정론 red-flag(_rule_parse_red_flag) — 질문·비교·정정·추천처럼 실행 가능한
    │          전략이 아닌 발화면 슬롯 일부 매칭돼도 None(구어체 '말고'·트레일링 '대비'는
    │          정상이라 제외 → 오폴백 방지).
    │       ② LLM judge(opt-in NL_RULE_GUARD_LLM, _consult_rule_parse_guard) — red-flag는
    │          없지만 룰 파스가 원문을 다 설명 못 한 잔여가 남는 '애매한 경우에만' 호출해
    │          accept/fallback 판정. LLM 오류·비활성 시 보수적 수락(빠른 경로 보존).
    │   └── Parse Fidelity Validator(engine/parse_validator.py, validate_parse) — 룰 파스가
    │       수락되고 설명 못 한 잔여가 있으면 LLM이 원문↔파싱결과를 비교해 누락/모호/실행불가/
    │       과잉추론을 구조화 리포트(parse_validation: isValid·confidence·issues 등)로 낸다.
    │       출력 계약은 diff — 유효하면 {isValid, confidence}만, 교정은 correctedFields(바뀐
    │       필드만)로 출력하고 서버가 원본과 병합해 correctedStrategy(전체 객체)를 채운다.
    │       전체 전략 재출력 제거 + null 필드 생략 입력으로 검증 시간을 단축(생성 토큰이 지배 항).
    │       병합 교정본은 ParsedStrategy 스키마 검증 통과 시에만 적용(원문 description 보존,
    │       미지 필드 사전 필터). 교정본의 진입/청산 신호는 LLM 파싱 본경로와 동일하게
    │       _validate_signals로 재검증한다 — 스키마만 통과한 환각 신호(예: 원문에 없는 ai_model
    │       'AI 매수 예측') 주입을 차단하고 환각 신호만 떨군 채 나머지 교정은 유지.
    │       LLM 미도달(refused/cold)이면 짧은 probe로 즉시 graceful degrade해 빠른 경로를 막지
    │       않는다(투자 자문·성능 개선은 하지 않음, 검증·교정만). NL_VALIDATOR_MODEL(env)로
    │       검증 전용 경량 모델 opt-in 가능. 검증 발화 시 잔여 어휘를 로그로 남긴다
    │       ("parse validation triggered | residual=...") — 빈출 무해 토큰을
    │       _RULE_GUARD_KNOWN_VOCAB에 보강해 검증 호출 자체를 줄이는 운영 루프의 입력.
    │   └── 비차단(후행) 검증 — SSE 경로(/strategy/parse-stream)는 검증을 인라인으로 기다리지
    │       않는다: _run_nl_parse(defer_holder)가 룰 파스 결과(result)를 먼저 내보내고,
    │       _complete_deferred_validation이 후행 검증을 돌려 교정이 있을 때만 result_update
    │       이벤트로 후속 전송(캐시도 교정본으로 갱신). 프록시(app/api/strategy/parse/stream)는
    │       이를 parsed_updated로 변환하고, 프론트는 백테스트 실행 전이면 조용히 전략을 갱신,
    │       실행 후 도착하면 무시한다(실행 스냅샷 일관성). 'validating' stage는 후행 모드에서
    │       보내지 않는다(로딩 표시 회귀 방지). 비스트림 /strategy/parse는 기존 인라인 검증 유지.
    ├── 백엔드 선택: MLX (Mac) 또는 Ollama
    ├── compact prompt + JSON output → ParsedStrategy 스키마 정규화
    ├── tail-truncated JSON repair, 실패 시 fallback ParsedStrategy 생성
    └── 수정 모드: parse_modification() — 이전 전략 diff 기반 병합
    │
    ▼
ParsedStrategy (구조화된 JSON)
    {
      universe: ["KOSPI200"],
      entry_signals: [{ indicator: "rsi", operator: "<", value: 30 }],
      stop_loss_pct: 8.0,
      backtest_period: "5y",
      ...
    }
    │
    ├── validate_parsed_strategy()
    │   └── 부족한 정보는 안전한 기본값 또는 AI 코치 안내로 처리
    │
    ▼
strategy_converter.to_backtest_request() (backend/engine/strategy_converter.py)
    ├── parse 응답에서는 resolve_symbols=False로 유니버스 전체 로딩 회피
    ├── 백테스트 실행 시점에 필요한 유니버스 심볼 로딩
    ├── 단일/지정 종목 모드(FR-STR-068): ParsedStrategy.target_symbols가 있으면 유니버스
    │   해석 대신 그 종목만 사용 — universe_id=None(엔진 PIT 재해석·섹터 필터 미적용),
    │   position_size=100/n, ranking_enabled=False, backtest_mode/target_stocks(표시용).
    │   종목명→코드는 LLM이 아닌 결정적 추출(nl_parser._extract_target_symbols,
    │   stock_analysis/symbol_resolver 정본)이 채우고, 문맥 가드(업종·예시·제외 표현)가
    │   유니버스 전략의 오폭을 막는다. 청산 누락은 apply_single_asset_adjustments가
    │   반대 신호 청산 추천/안내(notices)로 보정한다.
    ├── 단일 종목 연구 프로파일(FR-STR-068b): engine/stock_profile.py의
    │   StockProfileService가 종목 지정 시 OHLCV·PIT 재무에서 결정론 프로파일
    │   (커버리지·설명 통계·신호 발생 빈도·지원/미지원 피처)을 생성·캐시
    │   (data/cache/stock_profiles/, fingerprint 무효화). LLM(코치/빌더)은 원시
    │   시계열이 아닌 직렬화 요약만 읽는다. engine/single_asset_review.py가 파싱
    │   결과를 프로파일과 대조해 희소/과다 신호·재무 미보유·PIT 안내를 비차단
    │   notices로 전달하고, engine/stock_question_templates.py가 데이터 가용성
    │   기반으로 질문 노출/제외(이유 포함)를 결정한다(횡단면 선별 질문 없음,
    │   재무는 advanced 시계열 신호로만). API: GET /stock/{symbol}/research-profile.
    │   빌더는 BuilderState.single_symbol로 유니버스·보유수·리밸런싱 질문을 건너뛰고
    │   모멘텀 랭킹·가치 스크리닝을 이유와 함께 차단한다. 사후 최적값(best value)은
    │   계산·저장·추천하지 않는다(과최적화 방지).
    ├── 기술 신호 → Condition dict 변환
    ├── 재무 필터 → filter condition 변환
    └── 리스크 관리 설정 병합
    │
    ▼
BacktestRequest → 백테스트 엔진 실행
```

### 4.2.1 LLM-first 전략 대화 아키텍처 (backend/strategy_conversation/, Phase 1: Shadow)

4.2의 rule-first 구조를 장기적으로 대체하기 위한 **LLM-first / Validation-heavy /
Registry-driven** 파이프라인. 자연어 의미 해석은 LLM(Qwen 3.5 9B,
`STRATEGY_INTERPRETER_MODEL` 전용 슬롯 — 2026-07-26 4B에서 승격)이 전담하고,
결정론 코드는 검증·컴파일·실행만 담당한다(Regex는 숫자/날짜/형식 정규화로 제한).

이 역할 분담의 규범 계약은 [`docs/nl_interpretation_contract.md`](nl_interpretation_contract.md)에
정의한다 — LLM/Regex/Schema/Domain 책임 경계, 출력 계약, 금지 사항 체크리스트,
그리고 현행 `engine/nl_parser.py`와의 격차 목록을 포함한다.

```
사용자 자연어
    ▼
LLM Strategy Interpreter (interpreter/llm_strategy_interpreter.py)
    ├── Ollama /api/chat, format=json, think=false, temperature 0 (기존 콜드스타트
    │   내성 재사용: _ollama_ensure_warm + _ollama_open_with_retry)
    ├── Registry 주입 프롬프트(prompts.py, PROMPT_VERSION) — 지원 지표 canonical ID 계약
    └── JSON 추출 → Pydantic 검증 실패 시 오류 첨부 1회 자동 수정 요청(output_repair.py)
    ▼
StrategyIntent (interpreter/models.py, schema_version 1.0)
    ├── intent Enum(CREATE/MODIFY/EXPLAIN/…/UNSUPPORTED/NON_STRATEGY)
    ├── 조건별 factor/operator/value/unit/source_text + value_source
    │   (USER_PROVIDED/…/SYSTEM_RECOMMENDED/MISSING — 추천값≠확정값 분리)
    └── unsupported_features / clarification_questions / confidence
        (status·missing_fields·assumptions는 LLM에 요구하지 않는다 — 검증 계층이
         재판정·재산출하는 죽은 채널이라 2026-07-30 프롬프트에서 제거)
    ▼
검증 계층 (validation/pipeline.py — confidence가 높아도 생략하지 않음)
    ├── Capability: IndicatorRegistry(registry/indicator_registry.py)가 지원 여부 최종
    │   판정(SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED). 미지원은 조용한 대체 금지,
    │   대체 지표는 suggested_fixes로 명시 제안만. factor를 canonical ID로 정규화.
    ├── Parameter: 임계값·파라미터 범위(Registry ParamSpec) 검증
    ├── Conflict: AND 구간 공집합(PER≤10 ∧ PER≥20), 단기≥장기, 보유기간<리밸런싱 등
    └── Completeness: 누락 필수값 → 되묻기 질문 생성(Registry 추천값 제시, 최대 3개/턴).
        사용자가 말하지 않은 값을 조용히 확정하지 않는다.
    ▼
Strategy Compiler (compiler/strategy_compiler.py) — 검증 READY만 컴파일(Fail Fast)
    └── StrategyIntent → ParsedStrategy(기존 내부 DSL, 결정론 매핑만) → 기존 파이프라인 합류
```

- **대화 상태**: conversation/strategy_draft.py(StrategyDraftState + DraftStore) —
  다중 턴 초안 유지, MODIFY는 JSON Patch(conversation/patch_applier.py, 경로·스키마 검증) 적용.
- **Shadow Mode**: `STRATEGY_INTERPRETER_MODE=shadow`면 main.py 초기 파스 경로에서
  신규 파이프라인을 백그라운드 스레드로 병행 실행(비차단), 기존 룰 파스와의 field diff를
  `backend/logs/strategy_interpreter_shadow.jsonl`(관측성 계약: llm_raw_output·
  validation_*·compiler_output·field_diff·latency_ms)에 기록. 사용자 응답은 기존 결과만.
- **Primary Mode (Phase 2)**: `STRATEGY_INTERPRETER_MODE=primary`면 초기 파스를
  인터프리터 파이프라인이 담당(strategy_conversation/primary.py::run_primary_parse):
  READY→전체 컴파일, NEEDS_CLARIFICATION→**미확정 조건 제외 부분 컴파일**(compile_partial —
  조용한 기본값 확정 금지)+되묻기 질문·추천값 칩을 기존 clarification 채널
  (clarification_question/suggestions)로 전달 — 칩("영업이익률 10% 이상")은 클릭 시 일반
  수정 메시지로 재전송돼 기존 modify 결정적 병합이 조건을 채운다(condition_builder와 동일한
  무상태 패턴). LLM/JSON 복구 실패·비전략 intent·컴파일 실패는 기존 규칙 파서 하이브리드로
  폴백. 대화 상태(프론트 previous_parsed 소유)는 기존 구조 유지.
  검증 리포트의 LLM 자체 질문은 결정론 missing_fields와 교차 확인된 것만 채택(4B 잉여 질문
  노이즈 차단), runtime.interpreter 메타(model/repairs/latency/status)로 관측.
- **Primary Modify (Phase 2 후속, 2026-07-17)**: primary 모드에서 수정 요청도 인터프리터가
  우선 처리(primary.py::run_primary_modification): Decompiler(compiler/strategy_decompiler.py)가
  ParsedStrategy→StrategySpec 역매핑으로 기존 전략을 draft로 주입 → LLM은 **patches(JSON
  Patch)만** 출력(전체 전략 재출력은 필드 소실 위험이라 불수락) → patch_applier 적용 →
  검증 READY일 때만 재컴파일. 안전장치(전부 결정론): ① **라운드트립 가드** — decompile→
  재compile(+이월)이 원본과 다르면 표현 불가 전략(rsi rebound 등)이므로 이관 거부,
  ② description·execution_timing·entry_filters는 StrategySpec 밖이라 원본 이월 보존,
  ③ 잘못된 patch(예: "/entry_conditions" 전체 remove — 과잉 삭제)는 스키마 검증이 거부.
  모든 거부는 기존 하이브리드 수정 경로 폴백. clarification_for_add 가드·coach 맥락 리스크
  귀속은 기존 위치 유지. LLM 연산자 토큰 드리프트('"operator":">="'→'"operator">="')는
  output_repair의 멱등 구문 복구가 처리.
  예외(2026-07-17): CLARIFY_STRATEGY(패치 없음)+clarification_questions가 있으면, 폴백해
  질문을 버리는 대신 전략을 그대로 유지한 채 질문을 clarification 채널로 전달한다
  (mode=primary_modify_clarify) — 폴백된 기존 수정 LLM이 무변경 전략을 정상 응답처럼
  반환해 질문이 사라지던 사고 방지(FR-SA-002c-4의 백엔드 2차 방어선).
  패치 없이 EXPLAIN_INDICATOR거나 unsupported_features만 보고된 경우도 침묵 폴백하지
  않는다 — EXPLAIN_INDICATOR(인터프리터 LLM 라벨)면 /query/general과 동일
  생성기(generate_general_answer)로 실제 설명을 notices로 답하고(primary_modify_explain,
  2026-07-19), 아니면 미반영 안내(primary_modify_unsupported). 같은 사고의 2차 —
  인터프리터가 질문 대신 unsupported_features=["PBR 개념 설명 요청"]로 보고한 실측 대응.
  프롬프트 1.2는 개념 설명 질문을 EXPLAIN_INDICATOR로 계약(unsupported_features 금지).
  질문 판정에 쓰던 원문 결정적 cue(is_definition_question 등)는 계약이 금지한 원문 의도
  분류라 제거했다(2026-07-26, nl_interpretation_contract § 11-4) — 라벨 드리프트는
  프롬프트 규칙 10 소관.
  **패치 환각 게이트(출처 대조)**: 인터프리터 패치는 `_patch_provenance_supported`가
  거른다 — ① LLM이 `PatchOp.source_text`로 인용한 원문 조각의 실재(표기 정규화 후 포함),
  ② 패치 수치와 입력 수치의 대조(단위 환산 포함), ③ 지정 종목의 해석 가능성(마스터 조회).
  셋 다 근거가 없으면 환각으로 거부하고 전략 유지+미해석 안내(QA 20-3). 과거의 필드별
  한국어 어휘 큐 스캔(_PATCH_FIELD_CUES)은 발화 어휘 스캔이라 폐기(§ 3-1 (b), 2026-07-26).
  **해석 권한 역전(2026-07-26, `STRATEGY_MODIFY_INTERPRETER_MODE`)**: 수정 경로의 최초
  해석자를 결정론에서 LLM으로 뒤집었다. 기본값 `llm_first`는 인터프리터만 호출하며
  결정론 fast-path(`_modify_rule_based`, 원문 정규식)를 **상담하지 않는다**(2026-07-26
  § 11-4 — LLM의 되묻기·설명이 그대로 전달되고, 미해석은 None 폴백으로 호출부 소관).
  `fast_path_first`로 두면 2026-07-17의 선제 게이트(fast-path가 인터프리터를 아예 건너뜀 —
  LLM 왕복 지연·수치/날짜 드리프트 회피)로 즉시 롤백된다.
  전환 근거: 얕은 결정론(문자열 cue 차감)이 최초 해석자이면서 동시에 **실패시킬 권한**을
  가진 구조가, 프론트 칩이 심은 `metric:"roe"`(정본 `roe_or_gpa`) 오염 하나로 이후 모든
  수정 요청을 HTTP 500으로 죽이는 영구 교착을 만들었다(2026-07-26 사고).
  **레이어 권한 계약**: 해석 파이프라인의 어떤 레이어도 요청을 실패시킬 수 없다. 반환값은
  "처리했음" 또는 "내 소관 아님(다음 레이어로)"뿐이며, **예외는 "내 소관 아님"으로 강등**
  한다(fast-path는 `parse_modification`·`fast_path_can_handle` 양쪽에서 예외 격리).
  모든 해석 레이어가 실패하면 500이 아니라 기존 clarification 채널로 되묻는다
  (`main._interpretation_failure_result` — 기존 전략 보존 + 예시 칩 +
  `clarification_priority="interpretation_failed"`). **500/503은 인프라 장애 전용**이다
  (LLM 연결 실패 → 503 유지).
  또한 primary 경로(초기 파스·수정 모두)는 컴파일 후
  `_override_explicit_dates`가 명시적 백테스트 날짜를 결정적으로 덮어쓴다(레거시
  `_apply_prompt_overrides`와 동형) — 오늘 날짜를 모르는 모델이 과거 연도를 미래로 오판해
  종료일을 누락하던 사고("2020년 1월~2025년 12월" → "2020~"만 표시) 방지. 인터프리터
  프롬프트도 오늘 날짜를 매 요청 주입하고 날짜 규칙을 계약한다(PROMPT_VERSION 1.1).
- **평가**: evaluation/(parse_cases.json 34케이스 — 동일의미 이표현·모호·누락·부정·수정·
  미지원·충돌·비정형) + `python -m strategy_conversation.evaluation.evaluator [--legacy]`.
  핵심 지표: false assumption rate, missing detection recall, 미지원 오판율.
- **마이그레이션 단계**: Phase 1 Shadow(현재) → Phase 2 LLM primary + 규칙 파서 폴백 →
  Phase 3 자연어 해석용 Regex/어휘집 제거(Registry·Validator·Compiler는 유지).

### 4.2.2 Tool 레이어 (backend/strategy_conversation/tools/ — Planner→Tool→Responder 전환 Phase 1)

전략 생성을 장기적으로 **Planner → Tool/Engine → Responder** 구조로 전환하기 위한
도구 경계. 기존 서비스를 타입드 입출력 계약(pydantic — 형식 검증만, 의미 판단 없음)을
가진 이름 있는 도구로 등록하고, 고정 파이프라인(primary.py)이 이 경계를 통해 호출한다
(동작 변화 0). 이후 Phase에서 mini-planner(테마/유니버스 해석 구간 한정, 스텝 상한+
고정 파이프라인 폴백+shadow 비교)가 같은 카탈로그를 소비한다.

| 도구 | 위임 대상 | deterministic |
|---|---|---|
| `kg_resolve_sector` | engine/knowledge_graph.resolve_sector_from_text | ✅ |
| `kg_theme_companies` | engine/knowledge_graph.theme_backtest_companies | ✅ |
| `ground_term` | engine/term_grounding.resolve_sector (검색·LLM, chat 주입 필수) | ❌ |
| `resolve_universe` | registry/universe_resolver (sectors+symbols) | ✅ |
| `lookup_capabilities` | registry/capability_registry 정본 상수 | ✅ |
| `validate_intent` | validation/pipeline.run_validation | ✅ |
| `compile_strategy` | compiler(compile_strategy/compile_partial, `partial` 플래그) | ✅ |

- 경계 규칙: 도메인 예외(StrategyCompileError 등)는 전파(폴백 판단은 호출부 소관),
  `ToolError`는 계약 위반(미등록 이름·입출력 형식)에만. 입출력 검증은 base.py::call 단일
  진입점이 수행한다.
- `run_backtest` 도구는 planner가 실제 소비할 Phase에서 추가한다(현재 소비자 없음 — YAGNI).

**Phase 2 — Responder 계약 + 출력 관문 (response/)**: Responder는 구조화된 결과
(StrategyIntent·ValidationReport·notices·되묻기)만 입력으로 받아 서술한다(원문 해석 금지 —
`response/__init__.py` 계약). 사용자에게 나가는 자유 텍스트(notices·되묻기 질문·칩)는
`response/output_guard.py::finalize_user_response`를 반드시 통과한다 — primary.py의 반환
6곳(초기 파스 1+수정 5)이 배선점이며, planner가 도입돼도 이 관문은 우회 불가가 계약이다.
관문은 결정론 정규식 문장 제거: 종목 행동 지시·확정 수익(stock_analysis/guardrails.py의
`_FORBIDDEN` 정본 공유)+전략 대화 고유 위반(전략 추천·우열 판단·시장 전망·성과 기대·보장).
'추천' 단어 자체는 금지가 아니다 — 시스템이 추천을 **하는** 문장만 제거하고 거절 안내
("'종목 추천' 조건은 지원되지 않아요")와 면책 문구('보장하지 않습니다')는 보존한다.
위반 없는 텍스트는 원문 그대로(무변형), 제거 발생 시 warning 로그로 관측한다.

**Phase 3 — Mini-Planner (planner/, 기본 off)**: 테마/유니버스 해석 구간 한정 동적 도구
계획. 지식그래프 조회 2종(kg_resolve_sector·kg_theme_companies)은 판단이 필요 없는 결정적
조회라 LLM 턴 없이 **사전 관찰**로 실행하고 관찰이 해석을 주면 LLM 0턴 종료, 검색 학습
성공 후 테마 재조회·종료도 결정론 절차다. LLM(인터프리터와 같은
`STRATEGY_INTERPRETER_MODEL` 슬롯)의 결정은 '검색(ground_term)할 가치가 있는 표현인가 vs
사용자에게 되물을 것인가'와 되묻기 질문 작성뿐이다. 도구명을 action 필드에 쓴 LLM 출력은
표기 정규화로 복구한다(원문 해석 아님 — 계약 § 판정 기준). 안전
계약은 전부 결정론: ① 화이트리스트 3종(kg_resolve_sector·kg_theme_companies·ground_term)만
② 스텝 예산(`STRATEGY_PLANNER_MAX_STEPS` 기본 6, 상한 8 클램프)·동일 호출 반복(루프) 즉시
실패 — 단 검색 학습(ground_term) 후 kg_theme_companies 재조회는 루프가 아니다(학습이 테마
앵커를 새로 만들 수 있어 고정 체인의 학습→재시도와 같은 계약) ③ **finish의
sector·companies는 LLM 주장값이 아니라 도구 관찰값에서만 채택**(근거
없는 finish는 거부 — 지어내기 구조 차단) ④ planner가 만든 되묻기 질문도 출력 관문 통과
⑤ 실패는 전부 None → 고정 파이프라인 폴백(planner는 단독 실패 지점이 될 수 없다).
운영: `STRATEGY_PLANNER_MODE=off(기본)/shadow/primary` — shadow는 `run_primary_parse`에서
고정 체인이 해석 못 한 업종 표현이 있을 때 백그라운드 스레드로만 실행, JSONL
(`logs/strategy_planner_shadow.jsonl`: outcome/steps/baseline_sector/latency) 기록.
primary(2026-07-26 배치 A/B 판정 근거 dev 승격)는 미해석 표현 구간을
`_resolve_sector_terms_planner_primary`가 담당 — planner 결과의 적용은 고정 체인과 같은
결정론 경로(apply_theme_companies→_merge_learned_sector→상장사 반영)를 재사용하고,
planner 실패(None)·예외는 표현 단위로 고정 체인 폴백. dev=primary(.env),
prod=미설정(off).

**Phase 4 — DAG Planner (planner/dag*.py, 기본 off)**: 대화 턴 전체를 Action DAG로
계획한다(계약 정본: `docs/planner_dag_contract.md`). Planner LLM의 **유일한 출력은
DAG(JSON)**이고 실행은 전부 결정론 러너다: `dag.py`가 구조 검증(비순환·id 고유·도구
화이트리스트 7종·노드 예산·done 노드 불변·finish→compile_strategy→validate_intent
의존 사슬 강제)과 ready 스케줄링을, `dag_planner.py`가 턴 루프(발행→검증→ready
실행 가능 도구 전이 실행→관찰 제시)를 담당한다. ask 노드는 새 관찰이 없는 턴에만
하나 표면화하며(관찰이 질문을 불필요하게 만들 수 있어 LLM에 수정 1턴), 질문은 출력
관문(output_guard)을 통과한다. 동일 도구+인자는 한 번만 실행(관찰 재사용),
ground_term 학습 후 테마 재조회는 결정론 에필로그, 확정값(sector·companies)은 도구
관찰값에서만 채택한다. validate_intent·compile_strategy는 DAG 구조상 허용하되 러너
보유 intent 상태가 필요해 shadow 단계에선 실행하지 않는다(primary 승격 시 배선).
모든 실패(JSON 파싱·계약 위반·도구 장애·턴 예산 `STRATEGY_DAG_PLANNER_MAX_TURNS`
소진·무진전 동일 발행)는 None → 기존 파이프라인이 그대로 담당. 9B 실측 교정:
done 노드 재발행 생략은 위반이 아니라 러너 보유 사본 병합(표기 정규화), 닫는 괄호
누락 JSON은 결정론 괄호 균형 보정, 공유 chat max_tokens=4096 명시. 운영:
`STRATEGY_DAG_PLANNER_MODE=off(기본)/shadow/primary` — shadow는 `run_primary_parse`
진입부에서 백그라운드 스레드로만 실행, JSONL(`logs/strategy_dag_planner_shadow.jsonl`)
기록. primary(2026-07-27 사용자 결정, dev)는 초기 파스의 되묻기 질문·칩을
`_dag_planner_clarification`이 대체(`_dag_state_summary`로 확정값 전달해 재질문 방지,
sector_unresolved 우선순위 질문은 불가침)하고 `clarification_priority="dag_planner"`
마커로 프론트 explicit 게이트의 고정 칩 삼킴을 막는다(프론트 수정 0 — 기존 우선순위
채널 재사용). planner 실패는 기존 고정 질문 유지 폴백. prod=off.

### 4.3 백테스트 엔진 파이프라인

```
BacktestEngine.run_backtest(request)
│
├── Phase 1: 데이터 로드
│   └── DataLoader.load_symbol_data()
│       ├── data/ohlcv/{symbol}.parquet 읽기 (Polars)
│       ├── in-memory 캐싱 (_cache dict)
│       ├── 재무 지표 enrichment (ROE, EPS, BPS 병합)
│       └── preprocess_data(): 수정주가/오류프린트 정규화
│           └── 배당 재투자 토탈리턴 보정 (engine/dividends.py) — **기본 ON**(options.total_return,
│               기본 True; False면 가격리턴 호환). 전략·벤치마크 양쪽 동일 적용(비교 일관성).
│               dividends 컬럼 없으면 no-op. 컬럼 백필: scripts/backfill_dividends.py
│               (KIS 예탁원 배당 API, face_val 액면분할 역조정)
│
├── Phase 2: 지표 계산
│   └── IndicatorEngine.calculate()
│       ├── MA (5/10/20/60/120일), RSI, MACD, Bollinger Bands
│       ├── Stochastic, CCI, ADX, Volume Spike, Breakout
│       └── StockDataFrame / pandas-ta 활용
│
├── Phase 3: AI 모델 프리로드 (필요 시)
│   └── entry/exit 조건에 ai_model / ai_drop_model 있을 때
│
├── Phase 4: 신호 생성
│   └── SignalEngine.generate_signals()
│       ├── _eval_vec(): 조건 하나 → boolean ndarray (전체 시계열)
│       ├── Signal 조건들: group.logic (OR/AND)으로 결합
│       ├── Filter 조건들: 항상 AND 결합
│       └── 최종: signal_result AND filter_result
│
├── Phase 5: 포트폴리오 시뮬레이션
│   └── Simulator.run()
│       ├── 달력 기준 리밸런싱 라우팅 (rebalance_mode 판정 — compute_rebalance_dates)
│       │   ├── 순수 리밸런싱(봉중간 리스크 없음) → _run_target_rebalance()
│       │   │   └── VectorBT Portfolio.from_orders(size_type='targetpercent') — 목표비중 reconstitution, 비중 리셋 O
│       │   └── 리밸런싱 + 봉중간 리스크 혼재 / 일반 전략 → 커스텀 루프 + Portfolio.from_signals()
│       ├── 리스크 관리 (커스텀 루프):
│       │   ├── StopLoss / TakeProfit: 당일 close 감지 → 당일 close 청산
│       │   ├── TrailingStop: peak_price[] 배열로 추적
│       │   ├── MaxHoldingDays: 보유 기간 초과 시 청산
│       │   └── Rebalance dropout: 리밸런싱일에 목표 집합 밖 보유 매도, 빈 슬롯 신규 편입
│       ├── Ranking: rank_df로 후보 재정렬 (PBR/ROE 복합 또는 모멘텀 ranking_metric="return")
│       ├── Position Limiting: 최대 동시 포지션 수 제한
│       └── Liquidity Check: 거래대금 기준 필터
│
└── Phase 6: 결과 계산 및 직렬화
    └── ResultHandler
        ├── 수익률: Total Return, CAGR, Buy&Hold Return
        ├── 위험: Max Drawdown, Volatility, Sharpe, Sortino, Kelly
        ├── 거래: Win Rate, Profit Factor, Trade Count
        ├── 월별/연도별 수익률 분해
        └── Per-Asset 통계 (종목별 수익률)
```

**Simulator 핵심 설계 원칙:**
- 체결 시점: 기본·권장은 `next_open`(신호 bar 다음날 시가 체결, 룩어헤드 없음). `same_close`는 당일 종가 신호를 당일 종가에 체결하는 비현실적 모드 — 엔진이 결과에 룩어헤드 경고를 자동 첨부(연구용). 독립 엔진(backtrader) 교차검증으로 `next_open` 체결 일치 확인됨
- 리스크 종료: 당일 close 감지 → `exits_values[i]`에 당일 close 주입 (현실적 일봉 시뮬레이션)
- 벡터화 Step 순서 고정: **Step1 퇴장처리 → Step2 리스크 평가/주입 → Rebalance(목표 집합 재구성/탈락 매도) → Step3 진입처리**
- 같은 날 매도+매수(리밸런싱 reconstitution)가 겹칠 때는 부기(active_mask/active_count/peak_price)도 즉시 갱신해야 한다 — 그렇지 않으면 빈 슬롯이 "아직 점유 중"으로 보여 신규 편입이 영구 차단되는 고스트 포지션 버그가 발생한다
- 달력 기준 리밸런싱: `compute_rebalance_dates()`로 주기별 첫 거래일 판정 → 봉중간 리스크 유무로 `from_orders(targetpercent)` / `from_signals` reconstitution 경로를 자동 분기 (하이브리드 라우팅)
- 리밸런싱 체결 타이밍 불변식: `next_open`이면 엔진(backtest_engine)이 신호·랭킹을 이미 1일 shift해 넘기므로(row i = 전일 종가 정보 = 체결일), 시뮬레이터는 추가 shift 없이 편입·편출 모두 **리밸런싱일 당일**(그 주기 첫 거래일 시가)에 체결한다. 두 경로(순수/루프)의 체결일이 같아야 하며, 리스크 청산(당일 intraday 정보 기반 → 다음 시가 체결)과는 타이밍 근거가 다르다 — 회귀: `test_simulator_ranking.py::test_next_open_rebalance_fills_on_rebalance_day_*`

### 4.4 가상매매 엔진 (`engine/virtual_trader.py`)

```
VirtualTrader (비동기 루프, FastAPI 메인 스레드 분리)
│
├── 장 개장 (09:00 KST) — entry 신호 평가 → 매수 주문
├── 정시 새로고침 — exit 신호 확인 → 청산 주문
└── 장 마감 (15:30 KST) — 최종 포지션 계산 → VirtualMarketLog 저장

거래 비용: 수수료 0.15% / 세금 0.30% / 슬리피지 0.20%
```

백엔드는 `backend/db.py`(공용 앱 DB 어댑터, Supabase Postgres)를 통해서만 앱 DB에 접근한다.
Prisma `Decimal` 컬럼(`currentCash`/`initialCash`/`avgPrice` 등 금액·수량 관련 전 컬럼)은
Postgres `NUMERIC`으로 매핑되는데, psycopg가 기본적으로 이를 `decimal.Decimal`로 반환해
SQLite 시절부터 float 연산을 가정해온 백엔드 코드(`current_cash * (pct / 100)` 등)가
`TypeError`를 낸다. `db.connect()`가 커넥션 단위로 `numeric → float` 로더(`FloatLoader`)를
등록해 모든 호출부에서 float로 통일되도록 한 곳에서 처리한다 — 개별 호출부에서 `float()` 캐스팅할
필요 없음.

---

## 5. 데이터 레이어

### 5.1 Prisma 스키마 (SQLite)

```
User            — 사용자 계정 (planTier: FREE/PREMIUM)
Strategy        — 저장된 전략 정의 (id = SHA-256 canonical DSL) → BacktestResult (1:N)
BacktestHistory — 백테스트 실행 이력 + cache metadata → Strategy (N:1 optional)
                  (prompt: 원문 프롬프트 스냅샷 — 표시용 SOT, conditions/metrics와 함께 기록에 보존)
BacktestResult  — 백테스트 결과 → Strategy (N:1), Stock (N:1)
BatchRun        — 독립형 배치 실행 단위 (run_id, ranking_snapshot, logs)
                → BatchRunCandidate (1:N)
BatchRunCandidate — 배치 후보 전략 (status, metrics, error, strategyId)
Stock           — 종목 메타데이터

VirtualAccount  → VirtualMarketState (1:1)
                → VirtualOrder (1:N)
                → VirtualPosition (1:N)
VirtualOrder    — 가상 주문 (PENDING / FILLED / CANCELLED)
VirtualPosition — 현재 보유 포지션 (avgPrice, peakPrice 포함)
VirtualMarketLog — 가상매매 신호 로그

WatchlistGroup  → WatchlistSymbol (1:N)

ResearchRun     — 리서치 에이전트 런 (status, config JSON, userId)
                → ResearchCandidate (1:N)
                → ResearchEvent (1:N)
ResearchCandidate — 후보 전략 (template, dsl_hash, scores, promoted)
ResearchEvent   — SSE 이벤트 로그 (type, payload JSON)

BacktestRun     — strategy_id 단위 백테스트 실행 캐시/메트릭 스냅샷
StrategyEmbedding — RAG 검색용 텍스트/구조 문서 및 임베딩 메타데이터
AdviceExperience — 조언 전/후 성과, 유사 사례, 평가, reusable lesson 저장
```

**Strategy 저장 규칙**
- `Strategy.id`는 surrogate key가 아니라 `strategy_id = SHA-256(canonical_strategy_dsl)` 이다.
- canonicalization은 stable JSON key ordering을 사용하고, 의미 없는 metadata를 제외한다.
- 동일 DSL이면 항상 동일 `strategy_id`가 생성되므로, 저장 중복 제거, 백테스트 캐시 키, 결과 조회 키를 하나의 식별자로 통합한다.
- Advisor memory는 `Strategy`를 insert-only로 참조한다. 같은 `strategy_id`가 이미 존재하면 사용자 저장 전략의 `name`, `description`, `settings`를 덮어쓰지 않는다.

### 5.2 데이터 파일

| 경로 | 형식 | 내용 |
|------|------|------|
| `data/ohlcv/{symbol}.parquet` | Parquet | 4052개 종목 OHLCV |
| `data/fundamentals/` | JSON/CSV | ROE, EPS, BPS, 부채비율 |
| `data/korea-stocks.json` | JSON | 종목명, 코드, 시장, 섹터 (현재 상장 — 섹터 SOT) |
| `data/stock-master.json` | JSON | PIT 종목 마스터(상장폐지 포함, 생존편향 제거) + 상폐 종목 industry/sector 백필(`backend/scripts/backfill_delisted_sectors.py`, 재빌드는 `build_stock_master.py`) |
| `data/etf-master.json` | JSON | ETF 유니버스 마스터(FDR ETF/KR ∩ 로컬 OHLCV + 상폐 백필 병합, `backend/scripts/build_etf_master.py`) — 상폐 미백필 상태에서만 엔진이 생존편향 경고 |
| `data/etf-delisted.json` | JSON | 상폐 ETF 멤버십(`backend/scripts/backfill_delisted_etf.py` — KRX Open API 승인 또는 KRX_ID/PW 필요, 일별 캐시=data/cache/krx-etf-daily/) |
| `data/kospi200-cache.json` | JSON | KOSPI200 종목 목록 캐시 |

---

## 6. API 통신 구조

### 6.1 요청 흐름

```
Client Browser
    ↓
Next.js API Route (/api/*)
    ├── 요청 검증 + 인증 확인
    ├── Strategy canonicalization + strategy_id/cacheKey 계산
    ├── FastAPI 항상 재실행 (동일 전략이라도 캐시로 실행을 건너뛰지 않음 — 엔진 버그 수정이 계속되는 동안
    │   과거(수정 전 버전) 결과를 그대로 반환하지 않기 위한 정책)
    ├── FastAPI (http://localhost:8000)
    ├── 결과 영구 저장 (Strategy / BacktestResult / BacktestHistory, cacheKey로 upsert — 기존 행은 최신 결과로 덮어씀)
    └── Client 응답

중복 요청 방지: x-trace-id 헤더, 2초 이내 동일 요청 차단
```

**배치 실행 흐름**

```
RunAllTestsModal
    ↓ POST /api/strategy/batch-runs
BatchRun row 생성 + BatchRunCandidate waiting 상태 저장
    ↓
In-process queue/worker (concurrency 제한)
    ├── running 상태 체크포인트
    ├── parse → canonical DSL → strategy_id 계산
    └── backtest-stream 실행(항상 재실행) 후 저장
    ↓
BatchRun ranking_snapshot / logs / counts 갱신
    ↓
Client polling으로 진행률/로그/리더보드 반영
```

**복구 동작**
- worker는 앱 프로세스 내부에 있지만, 상태는 `BatchRun`/`BatchRunCandidate`에 계속 저장된다.
- 서버 재시작 후 다음 `GET/POST /api/strategy/batch-runs` 요청이 들어오면 incomplete run을 재등록해 이어서 실행한다.
- 재시작 시 `running` 상태 후보는 `waiting`으로 되돌려 재시도하고, 취소 마커가 남은 run은 `skipped`로 정리한다.

### 6.2 주요 Next.js API 라우트

**전략**
- `POST /api/strategy/parse` — NL → DSL 파싱 프록시
- `POST /api/strategy/parse/stream` — accepted/skeleton/parsed_final/dsl_ready 이벤트를 보내는 자연어 파싱 SSE 프록시. `parsed_final`은 화이트리스트라 필드를 명시적으로 실어야 한다(`clarification_priority`·`pending_ask`·`explicit_fields`·`field_states`). `field_states`는 진행 골격 8칸의 상태 축(완료/미확인/해당 없음/확인 필요, FR-STR-019q)으로 진행률 카드 표시 전용이며 되묻기·실행 게이트는 쓰지 않는다
- `POST /api/strategy/rollback/resolve` — 되돌릴 지점 판정(FR-SA-008). 변경 이력을 요청에 실어 보내고(백엔드 무상태) 판정만 받는다 — 복원은 스냅샷을 보유한 클라이언트가 결정론으로 수행한다. 판정 실패는 전부 되묻기로 강등(임의 보정 금지)
- `POST /api/strategy/backtest-stream` — 단일 전략 SSE 백테스트. 동일 strategy_id/cacheKey라도 항상 엔진을 재실행하고, 결과는 cacheKey로 upsert 저장(재사용 목적 아닌 dedup 저장용)
- `POST /api/strategy/save-with-backtest` — 전략 저장 + 백테스트 동시 실행
- `GET/POST /api/strategy/batch-runs` — 배치 실행 시작/상세 조회/최근 이력/취소
- `POST /api/advisor/review` — RAG + Experience Memory 전략 리뷰/개선 조언
- `GET /api/ai/runtime/metrics` — AI 런타임 latency 메트릭 조회
- `POST /api/ai/runtime/metrics/reset` — AI 런타임 메트릭 초기화(production 비활성화)

**백테스트**
- `POST /api/backtest/run` — 실행 (캐싱 프록시)
- `POST /api/backtest/explain` — XAI 설명 생성
- `POST /api/backtest/summarize` — AI 요약 생성
- `POST /api/backtest/walk-forward` — 워크포워드 분석
- `GET /api/backtest/history` — 이력 조회

**주식 / 시장**
- `GET /api/stock/[symbol]/detail` — 종목 상세
- `GET /api/stock/[symbol]/ohlcv` — OHLCV 캔들
- `POST /api/stock/batch-quotes` — 배치 현재가
- `GET /api/market/indices` — KOSPI, KOSDAQ, 환율

**뉴스**
- `GET /api/news/symbol/[symbol]` — 종목별 뉴스 목록 (백엔드 미가동 시 seed 데이터 폴백)
- `GET /api/news/impact/[symbol]` — 종목 Alpha 시그널 (latest_alpha, risk_alert_level)
- `GET /api/news/top` — 주요 시장 뉴스 피드
- `GET /api/news/fetch-body` — 기사 본문 일부 추출 프록시. `http/https`만 허용하고 localhost/private/link-local/non-global IP와 userinfo URL을 차단한다.
- `GET /api/stocks/[symbol]/news?limit=30` — 종목 상세 뉴스탭용 캐시 전용 API. 캐시 미스 시 빈 배열을 즉시 반환하고 백그라운드 refresh job만 enqueue한다.

**가상 계좌**
- `POST /api/virtual-account` — 계좌 생성
- `POST /api/virtual-account/[id]/orders` — 주문 생성
- `POST /api/virtual-account/[id]/strategy/start` — 자동매매 시작
- `POST /api/virtual-account/[id]/strategy/stop` — 자동매매 중지

**관리자** (전부 `requireAdmin()` 게이트 — 비관리자에게는 404, 변경 작업은 `AdminAuditLog` 기록)
- `GET /api/admin/overview` — 사용자/가입/플랜별/백테스트/가상계좌/전략 통계 + 최근 관리자 작업
- `GET/PATCH /api/admin/users` — 사용자 목록(검색·필터·정렬·페이지네이션) / 플랜 변경·정지·활성화·삭제(soft)
- `GET/PATCH /api/admin/backtests` — 사용자별 월 사용량·잔여 횟수(+`?userId=` 최근 실행 기록) / 사용량 초기화·증가·감소
- `GET/PATCH /api/admin/accounts` — 가상계좌 목록(평가금·수익률) / 일시 중지·재개·초기화·삭제
- `GET/PATCH /api/admin/strategies` — 전략 목록(지표·연결 계좌·백테스트 수) / 비활성화·삭제(soft)
- `GET/PATCH /api/admin/plans` — 플랜 기본값+오버라이드 조회 / `PlanConfig` 한도 오버라이드 upsert
- `GET /api/admin/audit` — 감사 로그 조회 (삭제 API 없음)

---

## 7. AI/ML 파이프라인

### 7.0 종목 뉴스탭 백그라운드 파이프라인

종목 상세 뉴스탭은 조회 전용 UI다. 사용자가 뉴스탭을 클릭할 때 외부 뉴스 검색, 크롤링, scraper, LLM summarizer, news agent 분석을 실행하지 않는다. UI 요청 경로는 이미 생성된 `stock_news_cache`를 읽는 것으로 제한한다.

```
User Activity
    ↓
Priority Engine
    ↓
Stock Priority Ranking
    ↓
Hot Queue / Warm Queue / Cold Queue
    ↓
News Collector
    ↓
Raw News DB (news_raw)
    ↓
Deduplication
    ↓
Symbol Mapping
    ↓
News Agent Analysis (background only)
    ↓
StockNewsCache
    ↓
GET /api/stocks/[symbol]/news
    ↓
News Tab UI
```

**저장소 역할**

| 저장소 | 역할 |
|--------|------|
| `news_raw` | 원본 뉴스 저장: title, url, source, published_at, raw_content, created_at |
| `news_analysis` | news_id 기준 분석 결과: sentiment, impact_score, importance, summary, analyzed_at |
| `stock_news_cache` | 종목 뉴스탭에서 즉시 읽는 최종 캐시: symbol, news_id, published_at, rank_score, cached_at |

**수집 우선순위**

| Queue | 대상 | 기본 주기 |
|-------|------|----------|
| Hot Queue | 현재 조회 중 종목, 관심종목, 가상계좌 보유 종목, 최근 조회 급증 종목 | 1~5분 |
| Warm Queue | 거래대금 상위, 시가총액 상위, KOSPI200/KOSDAQ150 등 주요 지수 편입 종목 | 10~30분 |
| Cold Queue | 나머지 전체 종목 순회 수집 | 1~6시간 |

Priority score는 현재 조회, 관심종목, 보유종목, 최근 조회/검색, 거래대금, 뉴스 velocity, 지수 편입, 시가총액을 합산하되 사용자 행동 데이터가 시장 데이터보다 우선한다. 현재 보고 있는 종목이 가장 높은 우선순위를 갖고, 관심종목/보유종목은 시가총액보다 우선한다.

**Worker lifecycle**

FastAPI startup에서 news scheduler가 시작되면 Celery worker를 자동 기동할 수 있다. 중복 worker 방지를 위해 autostart 전 pid lock file을 획득하고, broker에 이미 동일 queue를 구독하는 worker가 있으면 새 worker를 시작하지 않는다. 운영 환경에서 별도 process manager를 사용하는 경우 `NEWSV2_WORKER_AUTOSTART_ENABLED=false`로 내장 autostart를 비활성화한다.

### 7.1 자연어 파싱 LLM (`backend/engine/nl_parser.py`)

| 항목 | 내용 |
|------|------|
| 백엔드 | MLX (Apple Silicon) 또는 Ollama |
| 기본 모델 | `mlx-community/Qwen3.5-4B-4bit` (MLX) / `hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M` (Ollama) |
| 출력 형식 | Deterministic extractor 우선, 필요 시 compact JSON LLM output |
| 신규 전략 | `parse(user_input)` → ParsedStrategy |
| 전략 수정 | `parse_modification(user_input, previous)` → diff 기반 병합 |
| JSON 복구 | tail-truncated JSON은 닫는 따옴표/중괄호 보정 후 재파싱 |
| Fallback | LLM JSON 복구 실패 시 extractor 기반 안전 ParsedStrategy 반환 |
| 자유 생성 | `chat(system_prompt, user_message)` → str (비구조화, MLX 전용) |
| 스트리밍 | `stream_chat(system_prompt, user_message)` → Generator[str] (토큰 단위 delta yield) |

### 7.1a AI 런타임 오케스트레이션

로컬 Qwen MLX 모델은 단일 디바이스 리소스를 공유하므로 parse, coach, summary를 동시에 실행하면 대기열 지연이 커진다. FastAPI 런타임은 priority inference lock을 사용해 사용자 입력에 가까운 작업을 먼저 처리한다.

| 항목 | 내용 |
|------|------|
| Priority 0 | `/strategy/parse` 자연어 파싱 |
| Priority 1 | `/strategy/coach`, `/strategy/coach/stream` |
| Priority 2 | `/summarize`, preload/background AI 작업 |
| 계측 | `phase`, `elapsed_ms`, `queue_wait_ms`, `status`를 in-memory metrics store에 기록 |
| FastAPI API | `GET /ai/runtime/metrics`, `POST /ai/runtime/metrics/reset` |
| Next.js 프록시 | `app/api/ai/runtime/metrics/**` |
| UI | `/analytics/new` AI Runtime 패널에서 최근 parse/coach/summary latency 확인 |

### 7.1b AI 전략 코치 (`backend/api/coach_routes.py`)

| 항목 | 내용 |
|------|------|
| 단건 엔드포인트 | `POST /strategy/coach` — 전체 JSON 응답 |
| 스트리밍 엔드포인트 | `POST /strategy/coach/stream` — SSE, `{"type":"delta"|"done"|"error"}` |
| 모델 | NLStrategyParser와 동일 Qwen 9B 모델 공유 (`set_parser()` 주입) |
| 스트리밍 프록시 | `app/api/strategy/coach/stream/route.ts` — SSE 본문 패스스루 |
| 입력 | `user_prompt`, `parsed_strategy`, `advisor_insight`, `news_agent_insight` |
| 출력 | `{"message": "코칭 메시지 (300자 이내)", "suggestions": ["제안1", ...]}` |
| 캐시 | JSON 응답 cache/in-flight dedupe, SSE 응답 replay cache |
| 우선순위 | MLX priority lock에서 parse보다 낮고 summary보다 높은 priority |
| 뉴스 우선순위 | news_agent_insight 존재 시 최우선 반영, risk_alert_level high → 리스크 조언 강제 |
| learning evidence 가드 | advisor_result의 표본 수/중앙값/복수 후보 나열형 옛 템플릿 문장을 LLM 컨텍스트에서 제거하고, LLM 최종 출력에서도 동일 패턴을 대체 |
| AI 모델 추천 가드 (2026-06-09) | `ai_model_recommendation`을 코치 LLM 컨텍스트에 넣지 않고, `COACH_SYSTEM_PROMPT`에 "AI 모델 추천 금지" 지시를 추가해 사용자가 먼저 언급해도 AI 모델 사용을 권하지 않음 |
| `<think>` 처리 | Qwen3 thinking-mode 아티팩트 자동 제거 (`re.sub`) |

### 7.1c RAG + Experience Memory 전략 Advisor (`backend/advisor/*`)

전략 Advisor는 현재 전략만 보고 조언하지 않고, 과거 유사 전략과 조언 결과를 검색한 뒤 재사용 가능한 lesson을 반영한다. 다만 이 근거 출처는 내부 판단에만 사용하며, 최종 사용자 문구는 "유사 사례" 설명이 아니라 바로 실행 가능한 비교 실험 조언으로 압축한다. 10,000건 learning artifact의 집계 지표는 confidence와 위험 판단에만 쓰고, 사용자에게 표본 수, `CAGR/Sharpe/MDD/Profit Factor` 중앙값, 거래 수 중앙값을 나열하지 않는다.

```
user_prompt + parsed_strategy + backtest_result
    ↓
canonical DSL → SHA-256 strategy_id
    ↓
백테스트 캐시/저장 결과 재사용
    ↓
텍스트 유사도 검색 + DSL 구조 유사도 검색
    ↓
Experience Memory(AdviceExperience)에서 성공/실패 사례 검색
    ↓
현재 성과 진단 + 개선 후보 DSL 생성
    ↓
후보 재백테스트 결과와 OOS/WFA 컨텍스트 비교
    ↓
advisor learning evidence 반영 + 사용자용 조언 문구 압축
    ↓
advice_evaluation 저장 + 대화창 말풍선 응답 생성
```

| 모듈 | 역할 |
|------|------|
| `strategy_identity.py` | Strategy DSL canonical string과 SHA-256 `strategy_id` 생성 |
| `similarity.py` | user prompt/advice text 기반 텍스트 검색과 DSL 구조 검색 결합 |
| `memory_retriever.py` | 유사 전략, 과거 조언, before/after metrics, lesson 선별 |
| `candidate_generator.py` | 현재 전략에 적용 가능한 개선 후보 DSL 생성 |
| `advice_evaluator.py` | CAGR, MDD, Sharpe, Profit Factor, trade count, OOS/WFA 기반 성공/실패 판단 |
| `memory_repository.py` | `AdviceExperience` 저장/조회. 기존 사용자 `Strategy` row는 덮어쓰지 않음 |
| `experiment_learning.py` | 10,000건 smoke sample 기반 learning artifact에서 내부 confidence와 위험 판단을 산출하되, 사용자 문구에는 표본 수/중앙값 나열을 노출하지 않음 |
| `response_composer.py` | 내부 근거를 조합하되 사용자에게는 성과 신호, 비교 후보, 리스크 조치 중심의 짧은 조언 생성 |

**AI 모델 추천 비활성화 (2026-06-09):** 검증 결과 AI 예측 모델이 알파를 내지 못하므로(7.2 참고) Advisor는 AI 모델 사용을 절대 추천하지 않는다. `suggestion_engine.py::_build_ai_recommendation`은 항상 `recommended=False`를 반환하고, `_build_experiments`는 "AI 예측 신호 추가" 실험을 제안하지 않는다.

**Advisor learning artifact**

- 기준 데이터셋은 KOSPI200 smoke sample 10,000건 백테스트 결과다.
- 저장 위치는 `data/advisor-learning/strategy_advisor_learning_dataset.jsonl`과 `data/advisor-learning/strategy_prompt_experiment_summary.json`이다.
- `advisor_smoke_0001`..`advisor_smoke_10000` sample_id를 정규화 키로 사용해 source/resume run 결과를 병합한다.
- flat evidence(CAGR/Sharpe/MDD 중앙값이 모두 0에 가까움)는 낮은 신뢰도와 "현재안 반복 금지" 조언으로 변환한다.
- 낮은 유사도 또는 범용 매칭은 confidence를 낮추고, `profit_factor`, `trade_count`를 함께 고려해 조언 품질을 보정한다.
- 사용자 응답 정책상 learning artifact의 표본 수와 중앙값은 직접 노출하지 않는다. 변경 제안은 여러 값을 동시에 던지는 방식이 아니라 "같은 기간과 비용 조건에서 변경은 한 번에 하나씩 비교"하는 안내로 제한한다.

**ParsedStrategy 주요 필드:**
```python
class ParsedStrategy(BaseModel):
    universe: List[Literal["KOSPI", "KOSDAQ", "KOSPI200"]]
    entry_signals: List[TechnicalSignal]
    exit_signals: List[TechnicalSignal]
    fundamental_filters: List[FundamentalFilter]
    stop_loss_pct: Optional[float]
    take_profit_pct: Optional[float]
    trailing_stop_pct: Optional[float]
    max_positions: int
    hold_period_days: Optional[int]
    ranking_metric: Optional[Literal["return"]]       # 모멘텀 랭킹 — "최근 N일 수익률 상위" 선정
    ranking_lookback_days: Optional[int]              # 모멘텀 계산 기간 (기본 60일)
    rebalancing_period: Literal["none", "daily", "monthly", "quarterly", "yearly"]
    backtest_period: Literal["1y", "3y", "5y", "full"]
    initial_capital: float
```

**관용적 입력 수용(2026-07-26, FR-STR-019i)**: `previous_parsed`는 프론트가 만들어
되돌려주는 신뢰할 수 없는 입력이다. 별칭 흡수는 경로별 새니타이저가 아니라 **스키마 진입
지점 한 곳**에서 한다 — `FundamentalFilter.metric`의 `BeforeValidator`(`roe`→`roe_or_gpa`
등 별칭 표 + 대소문자·공백·하이픈·슬래시 정규화)가 `model_validate`가 불리는 모든 지점을
덮는다. 표에도 없는 값은 그 필터만 드롭하고(`coerce_fundamental_filters`) 비차단 notice로
알린다 — 전체 실패(500)도, 조용한 드롭도 금지. 드롭 라벨은 직렬화 제외 필드
(`dropped_filter_notices`)로 전달돼 DSL·캐시키·라운드트립 비교에 영향을 주지 않는다.

### 7.2 예측 AI 엔진 (`backend/ai/ai_engine.py`)

**모델 아키텍처**: Hybrid Transformer + XGBoost

```
입력 피처 (45개)
    ├── 기술적 지표: RSI, ROC, Williams %R, MFI, TSI, Aroon, TRIX, ATR
    ├── 가격: 로그 수익률, 이동평균 (5/10/20/60일)
    └── 재무: ROE, EPS, BPS
    ↓
Feature Scaler
    ↓
PyTorch Transformer (Conv1D + RoPE + CLS Token)
    → CLS 임베딩 추출
    ↓
XGBoost Head (v1: 단일 모델 / v2: up/down 분리 모델)
    → 상승/하락 확률 (0~1)
```

조건 블록 ID: `ai_model` (매수 신호), `ai_drop_model` (매도 신호)

> ⚠️ **전략 도구 활용 비권장 (2026-06-09 검증):** 예측 모델은 추론은 정상 동작하나, 백테스트 검증에서 전략 도구로서의 가치가 확인되지 않았다.
> - **점수 분포:** 보정 안 된 좁은 분포(상승 0.20~0.30, 하락 0.33~0.40)라 UI/파서 기본 threshold=70은 신호 0건. 사용 시 분포 퍼센타일 기반 threshold가 필요하다.
> - **검증 결과:** per-stock 진입/청산(워크포워드 2018~2025), 포트폴리오 breadth 위험 오버레이 모두 바이앤홀드(+15.2%/년) 대비 알파 없음. 재현 스크립트: `backend/experiment_ai_auxiliary.py`, `experiment_ai_walkforward.py`, `experiment_ai_breadth_overlay.py`.
> - **정책:** 조언/코치 에이전트(7.1b, 7.1c)와 전략연구소 예시(3.2)는 AI 모델을 추천·노출하지 않는다. 사용자가 직접 명시하면 엔진/파서는 여전히 인식·실행한다.
> - **실행 주의:** AI 조건이 포함된 in-process 백테스트는 polars rayon 스레드풀 데드락을 피하기 위해 `POLARS_MAX_THREADS=1`로 실행해야 한다(+ XGBoost segfault 회피 `KMP_DUPLICATE_LIB_OK=TRUE`/`OMP_NUM_THREADS=1`).

### 7.3 설명 가능 AI (`backend/ai/xai_engine.py`)

SHAP 기반 — 각 예측에 영향을 준 피처와 기여도 반환, 프론트엔드 `XAIModal`에서 시각화

### 7.4 AI 요약 (`backend/ai/summarize.py`, `app/api/backtest/summarize/route.ts`)

백테스트 수치를 자연어 요약으로 변환한다. Next.js 프록시 계층은 `metrics + strategySummary` stable hash 기반 LRU cache와 in-flight dedupe를 적용해 동일 결과에 대한 중복 LLM 호출을 제거한다. 요약 생성은 전략 파싱 응답의 critical path에서 제외하고, 백테스트 결과 이후 비동기/지연 실행한다.

---

## 8. 테스트 구조

### 8.1 백엔드 (`backend/tests/`)

| 파일 | 테스트 대상 |
|------|-----------|
| `test_engine_signals.py` | SignalEngine: MA 교차, RSI, MACD, BB, Breakout 신호 평가 |
| `test_engine_indicators.py` | IndicatorEngine: 지표 계산 정확성 |
| `test_simulator.py` | Simulator: SL/TP/TS/MaxHold 리스크 관리 |
| `test_simulator_ranking.py` | Simulator: 모멘텀 랭킹(상위 K 선정) + 달력 기준 리밸런싱 회전 — 순수 리밸런싱(`from_orders`)/리스크 혼재(`from_signals`) 두 라우팅 경로 검증 |
| `test_rebalance_dates.py` | `compute_rebalance_dates()`: 일/월/분기/년 주기별 리밸런싱일 계산 (vbt 비의존, pandas만) |
| `test_engine_loader.py` | DataLoader: Parquet 로드, 캐싱 |
| `test_simulator_validation.py` | 검증 회귀: 핸드칼크·비용 양방향·결정론·next_open 체결·현금 음수 없음·중복 포지션 없음 |
| `test_reference_engine_crosscheck.py` | 레퍼런스 엔진 교차검증(#13): Simulator vs **backtrader** 진입/청산일·체결가·수량·최종자산 일치(무비용/비용) |
| `test_lookahead_no_prelisting_trades.py` | bfill 룩어헤드 가드(상장 전 미체결) + same_close 경고 발생 검증 |
| `test_random_strategy_stress.py` | 랜덤 전략 스트레스(#14): 예외/현금음수/비정상 NAV 없음 (N_STRESS env로 수천 건 확장) |
| `test_dividends.py` / `test_backfill_dividends.py` | 배당 토탈리턴 보정 + parquet 백필(스텁 provider 라운드트립) |
| `test_strategy_converter.py` | ParsedStrategy → BacktestRequest 변환 |
| `test_ai_code_fixes.py` | AI 관련 버그 픽스 회귀 테스트 |
| `test_news_dedup.py` | 뉴스 중복 제거: Jaccard 유사도·body hash·시간윈도우·intra-batch (22개) |
| `test_advisor_*` | RAG memory retrieval, candidate evaluation, response composer, advice evaluation |
| `test_news_fetch_body_security.py` | 뉴스 본문 fetch SSRF 방어: private URL 직접 요청/redirect 차단 |
| `test_listing_status.py` | 상장 상태 머신: 거래 허용 규칙, 0원 평가, 차단 사유, DART 공시 분류, 우선순위 (21개) |

제외 (서버/모델 필요): `test_backtest_engine`, `test_engine_ai`, `test_ai_sell`, `test_api_isolation`

```bash
cd backend && pytest tests/ \
  --ignore=tests/test_backtest_engine.py \
  --ignore=tests/test_engine_ai.py \
  --ignore=tests/test_ai_sell.py \
  --ignore=tests/test_api_isolation.py
```

### 8.2 프론트엔드 (`components/__tests__/`, `tests/`)

| 파일 | 테스트 대상 |
|------|-----------|
| `StrategyExampleTabs.test.tsx` | 전략 예시 탭 렌더링 및 클릭 |
| `AnalyticsStrategySummary.test.tsx` | 전략 요약 컴포넌트 |
| `backtestHistoryRoute.test.ts` | 백테스트 이력 API 라우트 |
| `backtestSummarizeRoute.test.ts` | 백테스트 요약 API 라우트 |
| `monthlyReturns.test.ts` | 월별 수익률 계산 로직 |
| `TopNavigationQuickSearch.test.tsx` | 상단 내비게이션 및 빠른 검색 |
| `OrderBook.test.tsx` | 호가창 컴포넌트 |
| `StrategyAdvisorPanel.request.test.tsx` | 후보 백테스트 결과와 evaluation context가 advisor 요청에 포함되는지 검증 |
| `app/api/news/fetch-body/route.test.ts` | Next.js 뉴스 본문 fetch 프록시 SSRF 입력 차단 |
| `tests/listing-status.test.ts` | 상장 상태 프론트엔드 유틸: 거래 허용 규칙, 배지, 위험 레벨, 카운트다운 (35개) |
| `app/api/market/delisting-status/route.test.ts` | 상장 상태 API: backend 통합 + prisma mock (2개) |

```bash
npm run test:frontend
```

---

## 9. 외부 의존성

### 9.1 프론트엔드 (`package.json`)

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `next` | 14.0.4 | 프레임워크 |
| `react`, `react-dom` | 18.2.0 | UI |
| `@tanstack/react-query` | 5.96.2 | 서버 상태 캐싱 |
| `@visx/*` | 3.12.0 | D3 기반 고성능 차트 |
| `recharts` | 2.10.3 | React 차트 |
| `lightweight-charts` | 5.0.9 | TradingView 캔들차트 |
| `prisma` | 5.7.1 | ORM (SQLite) |
| `tailwindcss` | 3.4.0 | CSS 유틸리티 |
| `framer-motion` | 12.27.0 | 애니메이션 |
| `jsonwebtoken` | 9.0.2 | JWT 인증 |

### 9.2 백엔드 (`backend/requirements.txt`)

| 패키지 | 용도 |
|--------|------|
| `fastapi==0.104.1` | API 프레임워크 |
| `polars==0.19.12` | 고속 데이터프레임 |
| `pandas==2.1.3` | 데이터 분석 |
| `vectorbt` | 포트폴리오 시뮬레이션 |
| `optuna` | 하이퍼파라미터 최적화 |
| `torch` | Transformer 모델 |
| `xgboost` | XGBoost 모델 |
| `shap` | 설명 가능 AI |
| `pydantic==2.5.2` | 데이터 검증 |

---

## 10. 환경 설정

### 10.1 환경 변수 (`.env`)

| 변수 | 필수 | 용도 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API (AI 요약) |
| `DATABASE_URL` | ✅ | `file:./dev.db` |
| `BACKEND_URL` | ✅ | `http://localhost:8000` |
| `KRX_API_KEY` | ✅ | KRX Open API (실시간 시세) |
| `PERPLEXITY_API_KEY` | 선택 | 뉴스 검색 |

### 10.2 주요 설정 파일

| 파일 | 용도 |
|------|------|
| `tsconfig.json` | TypeScript (path alias: `@/`) |
| `next.config.js` | Next.js 설정 |
| `tailwind.config.js` | 커스텀 테마 + CSS 변수 |
| `vitest.config.ts` | 프론트엔드 테스트 설정 |
| `prisma/schema.prisma` | DB 스키마 정의 |

---

## 11. 데이터 흐름

### 11.1 전략 설계 → 백테스트 전체 흐름

```
┌─────────────────────────────────────────────────┐
│  사용자: 자연어로 전략 입력                      │
│  예) "RSI 30 이하 매수, 20% 익절, KOSPI200"     │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  /analytics/new (Next.js)                        │
│  handleSend() → POST /api/strategy/parse/stream  │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  Next.js SSE: accepted → skeleton                │
│  UI: Strategy Skeleton 즉시 표시                 │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  FastAPI: /strategy/parse                        │
│  rule-first parser 또는 NLStrategyParser(LLM)    │
│  JSON repair/fallback → ParsedStrategy           │
│  strategy_converter(resolve_symbols=False)       │
└──────────────────┬──────────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
    Coach/Summary        사용자 버튼
    지연 실행             백테스트 실행
    SSE/cache            (자동 실행 없음)
          │
          └──────┐
                 ▼
┌─────────────────────────────────────────────────┐
│  POST /api/strategy/backtest-stream (SSE)         │
│  BacktestEngine.run_backtest()                   │
│  DataLoader → IndicatorEngine → SignalEngine     │
│  → Simulator (VectorBT) → ResultHandler          │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  BacktestDashboard                               │
│  수익률/지표 카드, 누적 수익률 차트, 거래 목록   │
│  + AI 요약, XAI 설명 (선택)                      │
└─────────────────────────────────────────────────┘
```

### 11.2 가상매매 실시간 흐름

```
┌─────────────────────────────────────────────────┐
│  POST /api/virtual-account/[id]/strategy/start   │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│  VirtualTrader (비동기 루프)                     │
│  09:00 — entry 신호 평가 → 매수                 │
│  매 시간 — exit 신호 확인 → 청산                │
│  15:30 — 포지션 최종 계산 → 로그 저장            │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│  /virtual-account/[id]                           │
│  VirtualMarketPanel: 신호 로그                   │
│  VirtualTradingStatus: 포지션/손익 현황           │
└─────────────────────────────────────────────────┘
```

### 11.3 상장폐지 리스크 대응 흐름

```
┌───────────────────────────────────────────────────┐
│  DART 공시 / 상폐 데이터 수집                       │
│  GET /market/dart/notices + GET /market/delist     │
└────────────────┬──────────────────────────────────┘
                 ▼
┌───────────────────────────────────────────────────┐
│  listing_status.py                                  │
│  classify_dart_notice() → ListingStatus            │
│  sync_from_dart_notices() → Stock 테이블 업데이트   │
│  sync_from_delisted_store() → DELISTED 동기화       │
└───────┬────────────────────┬───────────────────────┘
        ▼                    ▼
┌──────────────┐    ┌──────────────────────────────┐
│ 백테스트 엔진 │    │  VirtualTrader 루프            │
│ _process_    │    │  get_stock_listing_status()   │
│ symbol():    │    │  → 매수 차단 / 강제청산 주입   │
│ DELISTED →   │    │  → write_audit_log()          │
│ 종목 제외    │    └──────────────┬───────────────┘
└──────────────┘                   ▼
                        ┌──────────────────────┐
                        │  Next.js API 레이어   │
                        │  orders/route.ts:     │
                        │  getTradeBlockReason  │
                        │  → 403 거래 차단      │
                        │  positions/route.ts:  │
                        │  DELISTED → 0원 평가  │
                        └──────────┬───────────┘
                                   ▼
                        ┌──────────────────────┐
                        │  /virtual-account/id  │
                        │  DelistingRiskBanner  │
                        │  (D-N 카운트다운)     │
                        │  TrackedSymbolRow     │
                        │  (상태 배지)          │
                        └──────────────────────┘
```

**상장 상태 머신 (7단계):**

| 상태 | 매수 | 매도 | 평가 |
|------|------|------|------|
| `NORMAL` | ✅ | ✅ | 시장가 |
| `WARNING` | ✅ | ✅ | 시장가 |
| `RISK` | ✅ | ✅ | 시장가 |
| `TRADING_SUSPENDED` | ❌ | ❌ | 시장가 |
| `DELISTING_REVIEW` | ❌ | ✅ | 시장가 |
| `DELISTING_SCHEDULED` | ❌ | ✅ (정리매매) | 시장가 |
| `DELISTED` | ❌ | ❌ | 0원 |

**핵심 모듈:**
- `backend/engine/listing_status.py` — 상태 머신, DART 키워드 분류, SQLite 동기화, 감사 로그
- `lib/listing-status.ts` — 프론트엔드 상태 유틸 (`isBuyAllowed`, `getStatusBadge`, `getRiskLevel`, `daysUntil`)
- `lib/hooks/useDelistingStatus.ts` — 상장 상태 React 훅 (`resolveListingStatus`)
- `components/virtual-account/DelistingRiskBanner.tsx` — 리스크 배너 (D-N 카운트다운, 강제청산 버튼)
- `app/api/virtual-account/[id]/liquidate/route.ts` — 강제청산 엔드포인트
- `app/api/market/delisting-status/route.ts` — 통합 상장 상태 조회 (backend + DB)
