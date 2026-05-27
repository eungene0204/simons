# Software Architecture

> 한국/글로벌 주식 퀀트 투자 플랫폼 — Simons
> **최종 갱신일:** 2026-05-28

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

| 항목 | 기술 |
|------|------|
| 프론트엔드 | Next.js 14 (App Router) + TypeScript + Tailwind CSS |
| 백엔드 | FastAPI (Python) + Uvicorn |
| ORM / DB | Prisma + SQLite |
| 백테스팅 엔진 | VectorBT + Polars + Pandas |
| AI/ML | PyTorch Transformer + XGBoost + SHAP |
| 전략 조언 | RAG + Experience Memory + 백테스트 개선 전/후 평가 |
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
│   ├── layout/                      # 레이아웃 (Navbar, Sidebar, Header)
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
│   │   ├── simulator.py             # Simulator (VectorBT 시뮬레이션)
│   │   ├── result_handler.py        # ResultHandler (지표 계산 + 직렬화)
│   │   ├── nl_parser.py             # 자연어 → ParsedStrategy (LLM)
│   │   ├── strategy_converter.py    # ParsedStrategy → BacktestRequest
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
│   ├── api/
│   │   ├── coach_routes.py          # FastAPI AI 전략 코치 라우터 (단건 + SSE 스트리밍)
│   │   ├── advisor_routes.py        # RAG/Experience Memory 전략 리뷰 라우터
│   │   ├── news_routes.py           # 뉴스 FastAPI 라우터
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
└── contexts/DrawerContext.tsx       # Drawer 전역 상태
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
| `/watchlist` | 관심 종목 관리 | `Watchlist`, `WatchlistDrawer` |

`/stock-order`의 종목정보 탭은 실시간 시세와 분리된 비실시간 종목 프로필 레이어를 사용한다. 종목명, 상장일, 섹터, 회사 기본 정보, 재무 요약, PER/PBR 같은 저빈도 갱신 값은 DB에 저장하고, 현재가/등락률/거래량 등 실시간 값은 기존 실시간 시세 경로에서 조회한다.

### 3.2 전략 Lab 컴포넌트 구조 (`/analytics/new`)

```
StrategyLabPage (app/analytics/new/page.tsx)
├── StrategyExampleTabs          — 초보/중급/고급별 예시 프롬프트 제공
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

전략 Lab의 코치 UX는 오른쪽 고정 패널을 사용하지 않는다. 파싱 완료 후 `/api/advisor/review` 결과를 같은 대화 흐름의 말풍선으로 표시하며, 사용자에게 RAG/Experience Memory/유사 사례 출처를 설명하지 않고 성과 신호, 비교 후보, 리스크 조치만 노출한다. 조언은 우선순위 상위 3개만 표시하고 나머지는 백테스트 결과 확인 후 이어서 볼 수 있다는 짧은 안내로 접는다.

### 3.3 상태 관리

| 방식 | 용도 |
|------|------|
| React Query (`useQuery`) | 서버 데이터 캐싱 (백테스트 이력, 계좌 목록 등) |
| React Query (`useMutation`) | 서버 상태 변경 (전략 저장, 주문 체결 등) |
| React Context (`DrawerContext`) | Drawer 열기/닫기, 선택된 계좌 ID |
| `useState` | 채팅 메시지 히스토리, 파싱된 전략 상태, 백테스트 결과, 배치 실행 UI 상태 |

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

**뉴스 Impact Agent**
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/news/articles` | 전체 뉴스 목록 (페이징) |
| POST | `/news/collect` | 뉴스 수집 트리거 |
| GET | `/news/symbol/{symbol}` | 종목별 뉴스 (as_of 지원) |
| GET | `/news/impact/{symbol}` | 종목 Alpha 시그널 (latest_alpha) |
| GET | `/news/top` | 주요 뉴스 |
| GET | `/news/fetch-body` | 기사 본문 일부 추출 (SSRF 방어 적용) |

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
    ├── 기술 신호 → Condition dict 변환
    ├── 재무 필터 → filter condition 변환
    └── 리스크 관리 설정 병합
    │
    ▼
BacktestRequest → 백테스트 엔진 실행
```

### 4.3 백테스트 엔진 파이프라인

```
BacktestEngine.run_backtest(request)
│
├── Phase 1: 데이터 로드
│   └── DataLoader.load_symbol_data()
│       ├── data/ohlcv/{symbol}.parquet 읽기 (Polars)
│       ├── in-memory 캐싱 (_cache dict)
│       └── 재무 지표 enrichment (ROE, EPS, BPS 병합)
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
│       ├── VectorBT Portfolio.from_signals()
│       ├── 리스크 관리:
│       │   ├── StopLoss / TakeProfit: 당일 close 감지 → 당일 close 청산
│       │   ├── TrailingStop: peak_price[] 배열로 추적
│       │   └── MaxHoldingDays: 보유 기간 초과 시 청산
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
- 리스크 종료: 당일 close 감지 → `exits_values[i]`에 당일 close 주입 (현실적 일봉 시뮬레이션)
- 벡터화 Step 순서 고정: **Step1 퇴장처리 → Step2 리스크 평가/주입 → Step3 진입처리**

### 4.4 가상매매 엔진 (`engine/virtual_trader.py`)

```
VirtualTrader (비동기 루프, FastAPI 메인 스레드 분리)
│
├── 장 개장 (09:00 KST) — entry 신호 평가 → 매수 주문
├── 정시 새로고침 — exit 신호 확인 → 청산 주문
└── 장 마감 (15:30 KST) — 최종 포지션 계산 → VirtualMarketLog 저장

거래 비용: 수수료 0.15% / 세금 0.30% / 슬리피지 0.20%
```

---

## 5. 데이터 레이어

### 5.1 Prisma 스키마 (SQLite)

```
User            — 사용자 계정 (planTier: FREE/PREMIUM)
Strategy        — 저장된 전략 정의 (id = SHA-256 canonical DSL) → BacktestResult (1:N)
BacktestHistory — 백테스트 실행 이력 + cache metadata → Strategy (N:1 optional)
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
| `data/korea-stocks.json` | JSON | 종목명, 코드, 시장, 섹터 |
| `data/kospi200-cache.json` | JSON | KOSPI200 종목 목록 캐시 |

---

## 6. API 통신 구조

### 6.1 요청 흐름

```
Client Browser
    ↓
Next.js API Route (/api/*)
    ├── 요청 검증 + 인증 확인
    ├── Strategy canonicalization + strategy_id 계산
    ├── Cache 확인 (Strategy.id / BacktestHistory.cacheKey)
    │   ├── Cache Hit  → 즉시 응답 + hitCount++ + status=cache_hit
    │   └── Cache Miss → FastAPI 포워드
    ├── FastAPI (http://localhost:8000)
    ├── 결과 영구 저장 (Strategy / BacktestResult / BacktestHistory)
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
    ├── cache hit 시 기존 결과 재사용
    └── miss 시 backtest-stream 실행 후 저장
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
- `POST /api/strategy/parse/stream` — accepted/skeleton/parsed_final/dsl_ready 이벤트를 보내는 자연어 파싱 SSE 프록시
- `POST /api/strategy/backtest-stream` — 단일 전략 SSE 백테스트 + strategy_id 캐시 활용
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

**가상 계좌**
- `POST /api/virtual-account` — 계좌 생성
- `POST /api/virtual-account/[id]/orders` — 주문 생성
- `POST /api/virtual-account/[id]/strategy/start` — 자동매매 시작
- `POST /api/virtual-account/[id]/strategy/stop` — 자동매매 중지

---

## 7. AI/ML 파이프라인

### 7.1 자연어 파싱 LLM (`backend/engine/nl_parser.py`)

| 항목 | 내용 |
|------|------|
| 백엔드 | MLX (Apple Silicon) 또는 Ollama |
| 기본 모델 | `mlx-community/Qwen3.5-9B-OptiQ-4bit` |
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
| `<think>` 처리 | Qwen3 thinking-mode 아티팩트 자동 제거 (`re.sub`) |

### 7.1c RAG + Experience Memory 전략 Advisor (`backend/advisor/*`)

전략 Advisor는 현재 전략만 보고 조언하지 않고, 과거 유사 전략과 조언 결과를 검색한 뒤 재사용 가능한 lesson을 반영한다. 다만 이 근거 출처는 내부 판단에만 사용하며, 최종 사용자 문구는 "유사 사례" 설명이 아니라 바로 실행 가능한 비교 실험 조언으로 압축한다.

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
| `experiment_learning.py` | 10,000건 smoke sample 기반 learning artifact에서 조건별 성과 중앙값과 비교 후보를 산출 |
| `response_composer.py` | 내부 근거를 조합하되 사용자에게는 성과 신호, 비교 후보, 리스크 조치 중심의 짧은 조언 생성 |

**Advisor learning artifact**

- 기준 데이터셋은 KOSPI200 smoke sample 10,000건 백테스트 결과다.
- 저장 위치는 `data/advisor-learning/strategy_advisor_learning_dataset.jsonl`과 `data/advisor-learning/strategy_prompt_experiment_summary.json`이다.
- `advisor_smoke_0001`..`advisor_smoke_10000` sample_id를 정규화 키로 사용해 source/resume run 결과를 병합한다.
- flat evidence(CAGR/Sharpe/MDD 중앙값이 모두 0에 가까움)는 낮은 신뢰도와 "현재안 반복 금지" 조언으로 변환한다.
- 낮은 유사도 또는 범용 매칭은 confidence를 낮추고, `profit_factor`, `trade_count`를 함께 고려해 조언 품질을 보정한다.

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
    backtest_period: Literal["1y", "3y", "5y", "full"]
    initial_capital: float
```

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
| `test_engine_loader.py` | DataLoader: Parquet 로드, 캐싱 |
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
| `SidebarQuickSearch.test.tsx` | 검색 사이드바 |
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
