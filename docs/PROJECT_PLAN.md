# Simons — 종합 투자 시뮬레이션 플랫폼 프로젝트 계획서

> **문서 버전:** v2.3
> **최종 갱신일:** 2026-06-28
> **프로젝트명:** Simons (시몬스)

---

## 1. 프로젝트 개요

### 1.1 비전
사용자가 자신만의 주식 투자 전략을 **설계 → 검증 → 최적화 → 실전 시뮬레이션**까지 원스톱으로 수행할 수 있는 종합 투자 시뮬레이션 플랫폼.

### 1.2 핵심 가치 제안
| 가치 | 설명 |
|------|------|
| **AI 대화형 전략 설계** | 자연어 프롬프트로 투자 전략을 설명하면 AI가 자동으로 퀀트 전략으로 변환 |
| **RAG 전략 조언** | 과거 유사 전략, 백테스트 결과, 조언 성공/실패 경험을 검색해 검증 가능한 개선안 제시 |
| **AI 융합** | 자체 개발 Transformer+XGBoost 예측 모델을 전략 신호로 결합 (검증 결과 보조 도구로만, 3.3.1 참고) |
| **과학적 검증** | 과거 데이터 기반 백테스트 + SHAP 기반 설명 가능 AI |
| **가상 실전 매매** | 실시간 시장 데이터 기반 페이퍼 트레이딩으로 전략 실전 검증 |
| **자동 최적화** | Optuna 기반 하이퍼파라미터 튜닝으로 전략 고도화 |

### 1.3 타겟 사용자
- **초급:** 투자에 관심 있지만 체계적 방법론이 없는 개인 투자자
- **중급:** 기술적 분석을 활용하는 트레이더 (전략 검증 니즈)
- **고급:** 퀀트 투자자, 알고리즘 트레이딩 연구자 (AI 모델 결합, 최적화)

### 1.4 종목정보 프로필 DB화 원칙

- `/stock-order` 종목정보 탭에서 사용하는 비실시간 종목정보는 전체 종목 기준으로 선적재 후 DB에서 조회한다.
- 저장 범위는 종목정보 탭 렌더링에 실제로 사용되는 필드로 제한한다.
- 실시간 시세(`currentPrice`, `changePercent`, `change`, `open`, `high`, `low`, `volume`)는 DB 저장 대상에서 제외한다.
- `52주 고저`, 차트 시계열, 캔들 데이터 등 종목정보 탭에서 사용하지 않는 필드는 저장하지 않는다.
- 종목 상세 API는 종목정보 필드에 대해 DB-first 로 동작하고, 실시간 시세는 기존 실시간 경로를 유지한다.

---

## 2. 시스템 아키텍처

### 2.1 기술 스택

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 14)                 │
│  React 18 · TypeScript · Tailwind CSS · Recharts        │
│  TradingView Charts · TanStack Table · Framer Motion    │
├─────────────────────────────────────────────────────────┤
│                    API Layer                             │
│  Next.js API Routes (60+개) ←→ FastAPI Backend (15+개)  │
├─────────────────────────────────────────────────────────┤
│                    Backend (Python FastAPI)              │
│  Polars/Pandas · vectorbt · stockstats · Optuna         │
│  PyTorch · XGBoost · SHAP · MLX (Apple Silicon)        │
├─────────────────────────────────────────────────────────┤
│                    Data Layer                            │
│  SQLite + Prisma ORM · Content-addressed Strategy IDs   │
│  Parquet Files (4,052 종목) · BatchRun Checkpoints      │
│  AI Model Artifacts (Transformer + XGBoost v2)          │
└─────────────────────────────────────────────────────────┘
```

### 2.2 모듈 구조

```
simons/
├── app/                    # Next.js 페이지 & API 라우트
│   ├── api/               # 70+ REST API 엔드포인트 (18개 도메인)
│   ├── analytics/         # 전략연구소 (프롬프트 기반 전략 생성)
│   ├── backtest/          # 백테스트 이력 & 상세
│   ├── kospi/             # 시장 대시보드
│   ├── stock/             # 종목 상세 (차트, 호가, 시그널)
│   ├── stock-order/       # 종목 거래/주문 (차트·호가·뉴스·거래현황 5탭)
│   ├── watchlist/         # 관심종목
│   ├── virtual-account/   # 가상계좌 & 가상매매
│   ├── login/             # 로그인
│   └── register/          # 회원가입
├── backend/               # Python FastAPI 서버
│   ├── engine/            # 백테스트 엔진 핵심 모듈 (19개 파일)
│   │   ├── loader.py      #   데이터 로딩 (Parquet → Polars)
│   │   ├── indicators.py  #   기술적 지표 계산 (20+종)
│   │   ├── signals.py     #   시그널 생성 엔진 (벡터화)
│   │   ├── nl_parser.py   #   자연어 → 전략 파서 (MLX/Ollama LLM)
│   │   ├── strategy_converter.py  # ParsedStrategy → BacktestRequest
│   │   ├── simulator.py   #   매매 시뮬레이션 (vectorbt)
│   │   ├── result_handler.py  # 결과 집계·메트릭
│   │   ├── optuna_optimizer.py # 하이퍼파라미터 최적화
│   │   ├── walk_forward.py #   워크포워드 분석
│   │   ├── grid_optimizer.py # 그리드 서치 최적화
│   │   ├── virtual_trader.py # 가상매매 자동 실행기
│   │   ├── live_signal_utils.py # 실시간 시그널 유틸
│   │   ├── market_data.py #   멀티 Provider 시세 데이터 (CircuitBreaker)
│   │   ├── data_fetcher.py #  외부 OHLCV 수집 + 재무 데이터(EPS/BPS/PER/PBR) enrichment
│   │   ├── fundamental_fetcher.py # Naver Finance 기반 재무 데이터 스크래핑 (EPS/BPS → PER/PBR)
│   │   ├── vectorbt_native.py # VectorBT 네이티브 엔진
│   │   ├── krx_client.py  #   KRX API 클라이언트
│   │   ├── vi_utils.py    #   VI(변동성 완화) 유틸
│   │   ├── sector_mapper.py # 섹터 분류 매핑
│   │   └── providers/     #   시세 데이터 Provider (6개)
│   │       ├── kis.py     #     한국투자증권 REST API
│   │       ├── kis_ws.py  #     한국투자증권 WebSocket
│   │       ├── naver.py   #     네이버 금융
│   │       ├── yfinance_kr.py # Yahoo Finance (KRX)
│   │       ├── pykrx_provider.py # PyKRX
│   │       ├── krx_api_provider.py # KRX 직접 API
│   │       └── base.py    #     Provider 베이스 클래스
│   ├── ai/                # AI/ML 모듈
│   │   ├── ai_engine.py   #   Transformer + XGBoost 하이브리드 v2
│   │   ├── xai_engine.py  #   SHAP 설명 가능 AI
│   │   ├── summarize.py   #   AI 요약 생성 (Qwen 7B MLX)
│   │   ├── models.py      #   HybridAIModel (PyTorch)
│   │   ├── local_optimization_agent.py  # Optuna 최적화 에이전트
│   │   └── optimization_agent.py        # 원격 최적화 조율
│   ├── advisor/           # RAG + Experience Memory 기반 전략 조언 Agent
│   │   ├── agent.py       #   전략 진단 오케스트레이터
│   │   ├── strategy_identity.py # canonical DSL + SHA-256 strategy_id
│   │   ├── similarity.py  #   텍스트/구조 기반 유사 전략 검색
│   │   ├── memory_retriever.py # Experience Memory 검색/선별
│   │   ├── memory_repository.py # AdviceExperience 저장/조회
│   │   ├── candidate_generator.py # 개선 후보 전략 생성
│   │   ├── advice_evaluator.py # 개선 전/후 성과 평가
│   │   └── response_composer.py # 사용자 답변 섹션 구성
│   ├── news/              # 뉴스 Impact AI Agent 모듈
│   │   ├── schemas.py     #   NormalizedArticle, NewsImpact Pydantic 모델
│   │   ├── dedup.py       #   중복 제거 (Jaccard 유사도 + body hash)
│   │   ├── collector.py   #   뉴스 수집 오케스트레이터
│   │   ├── analyzer.py    #   뉴스 임팩트 분석 (이벤트 분류, alpha 계산)
│   │   ├── storage.py     #   NewsArticle DB 저장/조회
│   │   ├── news_routes.py #   FastAPI 라우터 (10개 엔드포인트)
│   │   └── providers/     #   뉴스 데이터 수집 공급자
│   │       ├── naver_news.py  # Naver Finance RSS (4개 피드, 키 불요)
│   │       └── rss_provider.py # 한국경제·연합뉴스·매일경제 RSS
│   ├── news_v2/           # 종목 뉴스탭 캐시·백그라운드 수집 파이프라인
│   │   ├── models.py      #   news_raw/news_analysis/stock_news_cache 등 저장 모델
│   │   ├── repository.py  #   캐시 조회, dedup, symbol mapping, priority 저장소
│   │   ├── service.py     #   수집→분석→캐시 갱신 오케스트레이션
│   │   ├── priority.py    #   사용자 수요 기반 Priority Engine
│   │   ├── tasks.py       #   Celery background task
│   │   ├── scheduler.py   #   Hot/Warm/Cold queue scheduler + worker autostart
│   │   └── routes.py      #   캐시 전용 종목 뉴스 API
│   └── tests/             # 40+개 테스트 파일 (pytest)
├── components/            # React 컴포넌트
│   ├── strategy/          # 전략 설계 UI (자연어 채팅 기반)
│   │   ├── StrategyExampleTabs.tsx  # 전략 예시 프롬프트 탭
│   │   └── RunAllTestsModal.tsx  # 독립형 Batch Backtest UI
│   ├── dashboard/         # 홈 대시보드
│   ├── stock/             # 종목 차트/상세
│   │   ├── NewsImpactPanel.tsx   # 뉴스·공시 + Alpha 시그널 패널
│   ├── order/             # 호가/주문
│   ├── portfolio/         # 포트폴리오 분석
│   ├── virtual-account/   # 가상계좌
│   ├── virtual-market/    # 가상매매 패널
│   ├── layout/            # 전역 상단 내비게이션
│   ├── watchlist/         # 관심종목
│   ├── ui/                # 공통 UI
│   ├── providers/         # React 프로바이더
│   └── __tests__/         # 주요 프론트엔드 컴포넌트/API 테스트
├── lib/                   # 프론트엔드 유틸리티
│   ├── strategy/          # BacktestService, UniverseResolver, SignalEvaluator
│   ├── scheduler.ts       # 장 스케줄러 (사전/개시/갱신/마감)
│   └── mock-stock-data.ts # GBM 기반 모의 데이터 생성기
├── model/                 # AI 모델 아티팩트 (v1 + v2)
├── data/                  # 데이터
│   ├── ohlcv/             #   4,052개 종목 OHLCV Parquet
│   ├── korea-stocks.json  #   한국 종목 마스터 (1,500+개)
│   ├── kospi200-cache.json #  KOSPI200 구성종목 캐시
│   └── universe-history.json # 유니버스 동기화 이력
├── prisma/                # DB 스키마 & 마이그레이션
│   └── schema.prisma      #   13개 모델 (DelistingAuditLog 추가)
├── types/                 # TypeScript 타입 정의
│   └── strategy.ts        #   핵심 전략 DSL 타입
├── scripts/               # 유틸리티 스크립트
│   └── scheduler.py       #   일일 데이터 동기화 (00:00 KST)
└── docs/                  # 프로젝트 문서
```

### 2.3 데이터 흐름도

```
[사용자]
    │  자연어 프롬프트 입력
    │  (예: "PBR 1 이하, PER 7 이하 종목 10개를 1년간 보유")
    ▼
┌──────────────────┐     ┌──────────────────┐
│  전략연구소 Chat  │────▶│  NLStrategyParser│
│  (프롬프트 UI)    │     │  (로컬 LLM 파싱)  │
└──────────────────┘     └────────┬─────────┘
                                  │ POST /strategy/parse
                                  ▼
                         ┌──────────────────┐
                         │ StrategyConverter│
                         │ (ParsedStrategy  │
                         │  → BacktestReq)  │
                         └────────┬─────────┘
                                  │ POST /strategy/backtest-stream (SSE)
                                  ▼
                         ┌──────────────────┐
                         │   FastAPI Server  │
                         └────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
      ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
      │  DataLoader   │  │ SignalEngine │  │   AIEngine   │
      │ (Parquet→DF)  │  │ (벡터화 평가) │  │ (예측 모델)  │
      └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
              │                 │                  │
              └─────────────────┼──────────────────┘
                                ▼
                       ┌──────────────────┐
                       │    Simulator     │
                       │  (매매 시뮬레이션) │
                       └────────┬─────────┘
                                ▼
                       ┌──────────────────┐
                       │  ResultHandler   │
                       │  (메트릭·리포트)   │
                       └────────┬─────────┘
                                ▼
                       ┌──────────────────┐
                       │ BacktestDashboard│
                       │ (시각화·분석)     │
                       └──────────────────┘
```

---

## 3. 핵심 기능 명세

### 3.1 전략 설계 시스템

#### 3.1.1 전략연구소 (프롬프트 기반 전략 생성) ✅ 완료

> 사용자가 한국어로 투자 전략을 설명하면, 로컬 LLM이 이를 구조화된 퀀트 전략으로 자동 변환.

**UX 흐름:**

| 단계 | 기능 | 구현 상태 |
|------|------|-----------|
| 1. 프롬프트 입력 | 자연어로 전략 설명 (채팅 인터페이스) | ✅ 완료 |
| 2. 즉시 접수 | `/api/strategy/parse/stream` 이 `accepted`/`skeleton` SSE 이벤트를 먼저 반환 | ✅ 완료 |
| 3. AI 파싱 | 로컬 LLM 또는 rule-first fast path가 자연어 → ParsedStrategy 구조 변환 | ✅ 완료 |
| 4. 전략 요약 확인 | 파싱된 유니버스, 필터, 시그널, 포트폴리오 설정 표시 | ✅ 완료 |
| 5. 전략 수정 | 대화형으로 파라미터 점진적 수정 가능 | ✅ 완료 |
| 6. AI 전략 코치 | 파싱 완료 후 지연 실행하며 전략 어드바이저 + 뉴스 시그널 기반 코칭 (SSE 스트리밍) | ✅ 완료 |
| 7. 백테스트 실행 | SSE 스트림으로 진행률 + 결과 실시간 전달 | ✅ 완료 |
| 8. 결과 분석 | BacktestDashboard (수익률, 샤프, MDD, 거래내역, 차트) | ✅ 완료 |

**자연어 파서 (NLStrategyParser):**

| 항목 | 내용 |
|------|------|
| 위치 | `backend/engine/nl_parser.py` |
| 지원 백엔드 | MLX (Apple Silicon 최적, 기본값), Ollama (범용) |
| 기본 모델 | `mlx-community/Qwen3.5-4B-4bit` (MLX) / `hf.co/unsloth/Qwen3.5-4B-GGUF:Q4_K_M` (Ollama) |
| 입력 | 한국어 자연어 전략 설명 |
| 출력 | `ParsedStrategy` (유니버스, 펀더멘탈 필터, 진입/청산 시그널, 리스크 설정) |
| 수정 모드 | `previous_parsed` 전달 시 기존 전략 기반 점진적 수정 |
| 캐시 | 200-item LRU (중복 방지) |
| Fast path | 명확한 정량 조건은 deterministic extractor로 우선 파싱하여 LLM 호출 회피 |
| 복구 | LLM 출력이 tail-truncated JSON인 경우 보정 후 파싱, 실패 시 안전한 fallback strategy 생성 |
| 자유 생성 | `chat()` — 코칭 응답 생성 (비구조화 텍스트, MLX 전용) |
| 스트리밍 | `stream_chat()` — 토큰 단위 SSE 스트리밍 (`mlx_lm.stream_generate`) |

#### 3.1.1a 자연어 전략 생성 성능 최적화 ✅ 완료

> 모델은 `mlx-community/Qwen3.5-4B-4bit`(경량)를 사용하고, 프롬프트/파이프라인/런타임 계층만 변경해 사용자 체감 지연을 줄인다.

| 항목 | 구현 내용 |
|------|-----------|
| 파이프라인 분리 | parse → '분석 중...' 로딩 표시 → 파싱 완료 시 전략 요약 → summary/coach 지연 실행 |
| SSE parse 프록시 | `app/api/strategy/parse/stream/route.ts` 가 `accepted`, `skeleton`, `parsed_final`, `dsl_ready`, `done` 이벤트를 순차 전달 (`skeleton`은 클라이언트에서 표시하지 않음) |
| UX | `/analytics/new` 에서 파싱 완료 전까지 '분석 중...' 로딩만 표시하고(구조 스켈레톤 박스 미표시), 백테스트는 사용자가 버튼을 누를 때만 실행 |
| DSL 변환 | `to_backtest_request(resolve_symbols=False)`로 파싱 직후 불필요한 전체 유니버스 로딩을 회피 |
| 코치 캐싱 | Next.js 프록시와 FastAPI 코치 라우터 양쪽에서 동일 요청 cache/in-flight dedupe 적용 |
| 요약 캐싱 | `/api/backtest/summarize` 에 payload hash 기반 LRU cache와 in-flight dedupe 적용 |
| AI 런타임 조율 | MLX inference priority lock으로 parse(0) → coach(1) → summary/preload(2) 순서 보장 |
| 관측성 | `/ai/runtime/metrics`, `/api/ai/runtime/metrics` 로 parse/coach/summary latency 기록 및 UI 패널 표시 |

**측정 결과(동일 모델 유지, 로컬 개발 환경):**

| 구간 | 목표 | 측정값 |
|------|------|--------|
| Parse first response | 100~300ms | 약 155ms |
| Parse full response | 300ms 내외(rule-first fast path) | 약 159ms |
| Backend parse runtime | 300ms 내외 | 약 2.6ms |
| Coach first token | 5초 이내 | 약 4.3초 |
| Coach done | 8초 이내 | 약 6.9초 |
| Summary done | 비동기 지연 실행 | 약 15.2초 |

#### 3.1.1b AI 전략 코치 ✅ 완료

> 전략 파싱 완료 후 StrategyAdvisor(rule-based) + RAG/Experience Memory + Qwen MLX(LLM) 를 조합하여 맞춤형 코칭 메시지를 비동기 스트리밍으로 표시.

| 항목 | 내용 |
|------|------|
| 백엔드 라우터 | `backend/api/coach_routes.py` |
| 동기 엔드포인트 | `POST /strategy/coach` — 전체 응답 반환 |
| 스트리밍 엔드포인트 | `POST /strategy/coach/stream` — SSE 토큰 스트리밍 |
| Next.js 프록시 | `app/api/strategy/coach/route.ts`, `app/api/strategy/coach/stream/route.ts` |
| 모델 공유 | `set_parser()` 주입으로 NLParser와 동일 Qwen 9B 모델 재사용 (메모리 절약) |
| 캐시 | 동일 전략/프롬프트에 대해 JSON 응답과 SSE replay 캐시 적용 |
| 런타임 우선순위 | parse보다 낮고 summary보다 높은 priority로 MLX 추론 락 획득 |
| 뉴스 통합 | `news_agent_insight` 우선 반영 — risk_alert_level high 시 리스크 조언 최우선 |
| advisor 통합 | `advisor_insight` (rule-based 전략 진단) → 코치 컨텍스트로 활용 |
| RAG 통합 | 현재 전략의 텍스트/DSL 구조 유사 사례와 과거 조언 성공/실패 경험을 검색 |
| 개선 검증 | 후보 전략 생성 후 가능하면 개선 전/후 백테스트와 WFA/OOS 컨텍스트를 비교 |
| UX | 전략 요약 카드 → 대화창 내 코치 분석 말풍선 → 핵심 조언 최대 3개 → 완료 시 백테스트 버튼 표시 |
| 응답 형식 | `{"message": "...(300자 이내)", "suggestions": ["제안1", "제안2", "제안3"]}` |
| 옛 조언 템플릿 차단 | `백테스트 학습 사례 N건`, `CAGR/Sharpe/MDD 중앙값`, `각각 바꿔 테스트` 같은 내부 learning 템플릿 문구는 LLM 입력/최종 응답 양쪽에서 필터링 |

**코치 표시 흐름:**
```
전략 파싱 완료
  ├── 전략 요약: 노란 테두리 카드로 표시
  ├── /api/advisor/review 호출
  └── 전략 코치 말풍선
      ├── 사용자에게 과거 사례/RAG 출처를 직접 노출하지 않음
      ├── 성과 신호 + 비교 후보 중심으로 조언 압축
      └── 조언은 최대 3개만 우선 표시
```

**코치 응답 가드레일:** 코치는 advisor learning evidence를 내부 판단 근거로만 사용한다. 사용자 응답에는 학습 표본 수, 성과 중앙값, Profit Factor 중앙값, 거래 수 중앙값, 여러 파라미터 후보를 한꺼번에 나열하는 옛 템플릿을 노출하지 않는다. 동일 패턴이 advisor_result에 포함되거나 LLM이 그대로 출력하더라도 최종 응답에서는 제거하고, "같은 기간과 비용 조건으로 먼저 백테스트한 뒤 변경은 한 번에 하나씩 비교"하는 실행 가능한 안내로 대체한다.

**전략 변환기 (StrategyConverter):**

| 항목 | 내용 |
|------|------|
| 위치 | `backend/engine/strategy_converter.py` |
| 기능 | `ParsedStrategy` → `BacktestRequest` 변환 + canonical DSL 기반 `strategy_id` 생성 |
| 종목 로딩 | `/data/korea-stocks.json` 기반 유니버스별 심볼 매핑 (KOSPI, KOSDAQ, KOSPI200) |
| 필터 변환 | 펀더멘탈 필터 → `type="filter"` 조건 블록 |
| 시그널 변환 | 기술적 시그널 → `type="indicator"` 조건 블록 + 파라미터 |
| Canonicalization | stable JSON key ordering, 의미 없는 metadata 제외, 의미 있는 배열 순서 유지 |
| Strategy ID | `strategy_id = SHA-256(canonical_strategy_dsl)` |

#### 3.1.1c RAG + Experience Memory 전략 조언 Agent ✅ 완료

> 전략 조언 Agent는 단순 rule-based 문구 생성이 아니라 현재 전략 → 과거 유사 사례 검색 → 경험 데이터 참고 → 개선안 생성 → 재백테스트 비교 → 경험 저장 루프를 수행한다.

| 단계 | 구현 내용 | 상태 |
|------|-----------|------|
| Strategy ID | Strategy DSL canonical string 생성 후 SHA-256 hash를 `strategy_id`로 사용 | ✅ 완료 |
| 백테스트 재실행 정책 | 동일 `strategy_id`/cache key라도 실행을 건너뛰지 않고 항상 엔진을 새로 실행(엔진 버그 수정 중 과거 결과 노출 방지). cacheKey는 결과 upsert 저장/조회 용도로만 사용 | ✅ 완료 |
| 텍스트 유사도 검색 | prompt, summary, indicator, entry/exit/risk 설명, advice text 기반 검색 | ✅ 완료 |
| 구조 유사도 검색 | DSL indicators, entry/exit rules, filters, risk, universe, timeframe, parameter 값 비교 | ✅ 완료 |
| Experience Memory | `AdviceExperience`에 조언 전/후 성과, 유사 사례, 평가, lesson 저장 | ✅ 완료 |
| 개선 후보 생성 | 현재 전략 문제점과 과거 lesson 기반 후보 DSL 생성 | ✅ 완료 |
| 개선 효과 평가 | CAGR, MDD, Sharpe, Sortino, Calmar, Profit Factor, trade count, OOS/WFA 컨텍스트 종합 평가 | ✅ 완료 |
| UI 반영 | 오른쪽 advisor panel 제거, `/analytics/new` 대화창 말풍선에서 핵심 조언만 표시 | ✅ 완료 |
| Advisor 학습 데이터 | KOSPI200 smoke sample 10,000건 백테스트 결과로 learning dataset/summary artifact 갱신 | ✅ 완료 |
| 조언 표현 정책 | RAG/Experience Memory/유사 사례 출처는 내부 근거로만 사용하고 사용자에게는 행동 가능한 조언만 표시 | ✅ 완료 |
| 옛 learning 문구 제거 | 표본 수/중앙값/복수 파라미터 후보를 그대로 나열하는 과거 조언 패턴 제거 | ✅ 완료 |

**조언 답변 정책:** 전략 요약은 별도 카드로 분리하고, 코치 말풍선은 성과 신호 → 비교 후보 → 리스크 관리 조치 중심으로 압축한다. "유사 전략", "과거 사례", "Experience Memory" 같은 내부 근거 출처는 사용자 문구에 직접 노출하지 않는다. 또한 "백테스트 학습 사례 N건 기준", "CAGR 중앙값", "Sharpe 중앙값", "MDD 중앙값", "Profit Factor 중앙값", "거래 수 중앙값", "각각 바꿔 테스트", "MDD와 Sharpe가 동시에 좋아지는 설정" 같은 옛 템플릿 문구는 사용자 문구로 생성하거나 전달하지 않는다.

#### 3.1.2 모두 테스트 (독립형 배치 백테스트) ✅ 완료

> 전략 만들기 채팅 페이지 상단 CTA에서 수십 개의 프롬프트를 한 번에 실행하는 독립형 배치 기능. 기존 Strategy Research Agent와 연동하지 않고 별도 `BatchRun` 저장 구조와 API로 동작한다.

| 단계 | 기능 | 구현 상태 |
|------|------|-----------|
| 1. 데이터셋 입력 | 빈 줄 기준 다중 프롬프트 입력 | ✅ 완료 |
| 2. 배치 실행 시작 | `POST /api/strategy/batch-runs`로 run 생성 | ✅ 완료 |
| 3. 서버 Queue 처리 | concurrency 제한이 있는 in-process worker 실행 | ✅ 완료 |
| 4. 진행률 표시 | 전체 진행률, 현재 전략명, 완료/실패/스킵/대기 수 표시 | ✅ 완료 |
| 5. 실시간 상태 반영 | 폴링 기반 로그/리더보드/실패 목록 스트리밍 | ✅ 완료 |
| 6. 결과 랭킹 | CAGR 기준 내림차순 정렬, 최고 성과 전략 강조 | ✅ 완료 |
| 7. 영구 저장 | `BatchRun`, `BatchRunCandidate`, `Strategy`, `BacktestResult`, `BacktestHistory` 저장 | ✅ 완료 |
| 8. 취소 & 복구 | 취소 요청, 체크포인트 저장, 서버 재시작 후 다음 요청 시 복구 | ✅ 완료 |
| 9. Advisor learning export | `format=advisor-learning-results` export와 merged resume 결과 기반 artifact 생성 | ✅ 완료 |

**현재 제약:**
- worker는 별도 프로세스가 아닌 앱 프로세스 내부 큐로 실행된다.
- 서버 재시작 후 자동 재개는 아니며, 다음 `batch-runs` API 요청 시 DB 상태를 보고 이어서 복구한다.
- 대형 run은 중단/실패 시 completed 구간과 resume run을 sample_id 기준으로 병합해 하나의 learning artifact로 재생성한다.

#### 3.1.3 지원 시그널·지표 (29종) ✅ 전체 구현

> 전략 설계는 UI 블록 조합 없이 자연어 채팅으로만 이뤄진다(블록 조합 5단계 위자드 빌더는 제거됨). 아래 조건들은 NL 파서가 출력하고 엔진·DSL이 평가하는 시그널/필터로, `ParsedStrategy`의 진입/청산/필터 항목에 그대로 매핑된다.

**기술적 지표 (15개)**
| 조건 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `ma_crossover` | 이동평균 골든/데드크로스 | shortMA, longMA, crossType | ✅ |
| `rsi` | RSI 과매수/과매도 | period, operator, value | ✅ |
| `macd` | MACD 크로스오버 | fastPeriod, slowPeriod, signalPeriod | ✅ |
| `bollinger_bands` | 볼린저밴드 이탈/반등 | period, stdDev, signalType | ✅ |
| `volume_spike` | OBV 기반 거래량 급증 | period, signalType | ✅ |
| `breakout` | 52주 신고가/신저가 돌파 (NL: "박스권 돌파", "N일 고점 돌파" 등 서술형 표현도 인식) | lookbackPeriod, signalType | ✅ |
| `ema` | 지수이동평균 | period | ✅ |
| `stochastic` | 스토캐스틱 | kPeriod, dPeriod | ✅ |
| `cci` | 상품채널지수 | period | ✅ |
| `adx` | 추세 강도 | period, threshold | ✅ |
| `dividend_yield` | 배당수익률 | operator, value | ✅ (hidden) |
| `revenue_growth` | 매출 성장률 | operator, value | ✅ (hidden) |
| `operating_margin` | 영업이익률 | operator, value | ✅ (hidden) |
| `beta` | 시장 베타 | operator, value | ✅ (hidden) |
| `ev_ebitda` | EV/EBITDA | operator, value | ✅ (hidden) |

**필터 (7개)**
| 조건 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `trading_value` | 거래대금 필터 | operator, value (억원) | ✅ |
| `market_cap` | 시가총액 필터 | operator, value | ✅ |
| `per` | PER 필터 | operator, value | ✅ (Naver Finance EPS 기반 일별 PER 계산) |
| `pbr` | PBR 필터 | operator, value | ✅ (Naver Finance BPS 기반 일별 PBR 계산) |
| `roe_or_gpa` | ROE/GPA 필터 | metric, operator, value | ✅ |
| `debt_ratio` | 부채비율 필터 | operator, value | ✅ |
| `trading_suspension` | 거래정지 제외 | exclude | ✅ |

**수급 (1개)**
| 조건 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `investor_net_buy` | 기관/외인 순매수 | investorType, period, minAmount | ✅ |

**리스크 (4개)**
| 조건 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `price_limit_exit` | 손절/익절 | stopLossPct, takeProfitPct | ✅ |
| `max_holding_days` | 최대 보유기간 | value | ✅ |
| `trailing_stop` | 트레일링 스탑 | percentage | ✅ |

**AI/ML (2개)** — ⚠️ 검증 결과 비권장 (Phase 3.10 참고)
| 조건 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `ai_model` | AI 상승 예측 | threshold, direction | ⚠️ 동작하나 비권장 |
| `ai_drop_model` | AI 하락 예측 | threshold | ⚠️ 동작하나 비권장 |

> 블록 자체는 엔진/DSL에 그대로 남아 사용자가 직접 명시하면 동작한다. 다만 워크포워드·breadth 오버레이 검증에서 알파가 확인되지 않아(Phase 3.10), **조언/코치 에이전트와 전략연구소 예시는 AI 모델을 더 이상 추천·노출하지 않는다.**

#### 3.1.4 리스크 관리 설정

```typescript
RiskManagement {
  position_size_pct: number     // 종목당 투자 비중 (기본 10%)
  max_positions: number         // 최대 동시 보유 종목 수
  stop_loss_pct?: number        // 손절선 (%)
  take_profit_pct?: number      // 익절선 (%)
  trailing_stop_pct?: number    // 트레일링 스탑 (%)
  max_holding_days?: number     // 최대 보유 기간 (일)
  max_mdd_limit_pct?: number    // 전략 MDD 한도 (%)
  execution_timing: "next_open" | "current_close"  // 체결 시점
  allocation_type: "equal" | "fixed_pct"            // 배분 방식
  init_cash: number             // 초기 투자금 (기본 1,000만원)
}
```

---

### 3.2 백테스트 엔진 ✅ 완료

#### 3.2.1 엔진 파이프라인

```
입력: BacktestRequest (종목, 조건, 리스크, 기간)
  │
  ├─ 1. DataLoader: Parquet → Polars DataFrame
  ├─ 2. IndicatorEngine: 기술적 지표 계산 (20+종)
  ├─ 3. SignalEngine: 벡터화 시그널 평가 (OR/AND)
  ├─ 4. AIEngine (선택): Transformer+XGBoost 예측
  ├─ 5. Simulator: vectorbt 기반 매매 시뮬레이션
  │     ├─ Step 1: 퇴장 처리 (이전 리스크 트리거)
  │     ├─ Step 2: 리스크 평가 (SL/TP/TS/MaxHold)
  │     └─ Step 3: 진입 처리 (랭킹 기반 선택)
  └─ 6. ResultHandler: 메트릭 계산 & 리포트
  │
출력: BacktestResponse (CAGR, Sharpe, MDD, 거래내역, 에퀴티커브)
```

#### 3.2.2 성능 메트릭

| 메트릭 | 설명 |
|--------|------|
| Total Return | 총 수익률 (%) |
| CAGR | 연평균 복리 수익률 |
| Buy & Hold Return | 단순 매수 후 보유 수익률 (벤치마크) |
| Max Drawdown | 최대 낙폭 (%) |
| Sharpe Ratio | 위험 조정 수익률 |
| Sortino Ratio | 하방 위험 조정 수익률 |
| Win Rate | 승률 (%) |
| Profit Factor | 총이익 / 총손실 |
| Kelly Criterion | 켈리 기준 최적 베팅 비율 |
| Volatility | 연 환산 변동성 |
| 월별/연도별 수익률 | 기간별 수익 분해 |
| 종목별 통계 | 개별 종목 성과 분석 |

#### 3.2.3 시뮬레이터 핵심 규칙

- **리스크 종료:** 당일 close 감지 → 당일 close 체결 (일봉 기반 현실적 시뮬레이션)
- **트레일링 스탑:** peak_price 배열로 추적, 진입 시 초기화
- **처리 순서:** Exit → Risk → Entry (벡터화, 순서 고정)
- **랭킹:** 다중 종목 동시 시그널 시 스코어 기반 우선순위 배정 (PBR/ROE 또는 모멘텀 `ranking_metric="return"` — N일 수익률 상위 K종목 선정)
- **달력 기준 리밸런싱:** `rebalancing_period`(daily/monthly/quarterly/yearly) 지정 시 리밸런싱일마다 목표 집합(상위 K) 재구성(reconstitution). 순수 리밸런싱은 vbt 네이티브 `from_orders(targetpercent)`, 봉중간 리스크(SL/TP/TS) 혼재 시 커스텀 `from_signals` 루프로 하이브리드 라우팅

#### 3.2.4 SSE 스트리밍 ✅ 완료

- `POST /strategy/backtest-stream` — 진행률 실시간 전달
- 단계: data loading → filter applying → simulation → aggregation → final metrics

---

### 3.3 AI/ML 시스템

#### 3.3.1 하이브리드 예측 모델 v2 ✅ 완료

```
입력: 45개 피처 (멀티타임프레임 모멘텀, 변동성, 거래패턴, 캔들)
    │
    ├─ Conv1D Stem (3일/7일 멀티스케일 로컬 패턴)
    │
    ├─ Advanced Transformer Encoder
    │   ├─ 128~256차원 임베딩 (Optuna 최적화)
    │   ├─ Rotary Positional Encoding (RoPE)
    │   ├─ Pre-LayerNorm + Stochastic Depth
    │   ├─ 4~8 Head Attention, 4~8 Encoder Layers
    │   ├─ Learnable [CLS] Token (전역 집계)
    │   └─ 256~1024차원 FFN
    │
    ├─ XGBoost UP Model (상승 예측 전용)
    │   └─ Embedding + 통계 피처 → P(7%+ 상승)
    │
    ├─ XGBoost DOWN Model (하락 예측 전용)
    │   └─ Embedding + 통계 피처 → P(7%+ 하락)
    │
    └─ 출력: 10일 내 상승/하락 확률 (0~1) 분리 예측
```

> ⚠️ **전략 도구 활용 비권장 (2026-06-09 검증):** 모델 추론 자체는 동작하나, 백테스트 검증(Phase 3.10)에서 진입/청산/위험 오버레이 어느 방식으로도 바이앤홀드 대비 알파가 확인되지 않았다. 조언/코치/전략연구소 예시는 AI 모델을 추천하지 않는다. 전략 도구로 되살리려면 사용법 튜닝이 아니라 라벨링/캘리브레이션부터의 모델 재설계가 필요하다.

#### 3.3.2 설명 가능 AI (XAI) ✅ 완료

- **프레임워크:** SHAP (SHapley Additive exPlanations)
- **방법:** TreeExplainer (XGBoost 전용)
- **제공 정보:**
  - 매매별 피처 기여도 (어떤 지표가 매수/매도 판단에 기여했는지)
  - Force Plot (개별 예측 분해)
  - Bar Plot (전체 피처 중요도)

#### 3.3.3 AI 요약 생성 ✅ 완료

- **위치:** `backend/ai/summarize.py`
- **모델:** Qwen 7B MLX (macOS) 또는 추론 서비스
- **기능:** 백테스트 결과를 자연어 리포트로 변환 (점수, 요약, 추천)
- **advisor 하이브리드 ✅ 완료:** `parsed_strategy`가 전달되면 `StrategyAdvisorAgent`가 개선안(improvements)·점수·과적합 위험을 결정론적으로 산출하고, LLM은 그 진단을 근거로 총평·강점·단점만 서술한다(환각 차단). `parsed_strategy` 미전달·advisor 실패 시 기존 LLM 단독 경로로 폴백.
- **정확성/신뢰성 점검(2026-07-08) ✅ 완료:**
  - 캐시 히트·DB 저장에 advisor 진단 필드(advisorScore/riskScore/overfitRisk) 포함 — 재조회 시 "전략 리스크 진단" 카드 유실 수정 (`app/api/backtest/summarize/route.ts`)
  - 같은 화면에서 백테스트 재실행 시 이전 전략의 리포트가 새 결과에 남던 stale 캐시 수정 (`BacktestDashboard` executionId 감지 리셋 + 카드 key)
  - '다시 생성' 버튼에 `force` 재생성 지원(기존엔 캐시 반환으로 no-op), 리포트 탭을 열어둔 채 백그라운드 생성 완료 시 화면 자동 갱신
  - 프롬프트에 백테스트 기간·초기/최종 자본 명시 + "제시된 수치만 인용, 미래 예측 금지" 규칙 추가(기간 환각 방지, 규제 안전), advisor 진단이 3개 미만이면 단점을 그 수만큼만 쓰도록 모순 해소
  - `summarize_ollama`에 Modal 콜드스타트 내성(warmup GET + 재시도) 적용, 프록시 타임아웃 상향(120s→360s) — 프로덕션 콜드 상태 리포트 생성 실패 수정
  - 대시보드/카드 metrics 페이로드 통일(`aiReportMetrics.ts`) — 캐시 키 불일치로 인한 중복 LLM 호출 제거, 리포트 하단 규제 안전 고지 문구 추가
- **총평 지시문/내부추론 누출 사고 수정(2026-07-08) ✅ 완료:** 총평에 프롬프트 지시문·`<think>` 추론이 그대로 노출되던 문제의 4중 수정 — ① `summarize_ollama`를 `/api/generate`→`/api/chat`+`think:false`로 전환(GGUF 임포트 모델은 generate 경로에서 think:false가 무시됨, 실측 확인) ② grounded 프롬프트를 base에 덧붙이는 이중 규칙(모순)에서 단일 규칙 세트로 재구성(모델이 규칙 충돌을 추론하다 지시문을 복창하던 원인) ③ `parse_llm_output`에 미닫힘 `<think>` 절단 + 지시문 에코 시그니처 감지 → 폴백(누출 텍스트를 총평으로 절대 반환하지 않음) ④ 파싱 실패 폴백은 `degraded` 플래그로 표시해 프록시 메모리 캐시·DB 저장·클라이언트 PATCH를 모두 차단(실패 문구 캐시 고착 방지). 기존 오염 레코드는 `hasReportFormattingArtifact`/`hasAiReportArtifact` 시그니처 확장으로 서빙·표시를 막고 재생성한다. 금액은 억/만 단위로 결정론 변환해 프롬프트에 제공(LLM이 1,000만원을 1억으로 오환산하던 문제). 로컬 Ollama(Qwen3.5-4B) 라이브 검증: 진단 0건/2건 케이스 모두 정상 총평, 누출 0.
- **코퍼스 비교 총평(2026-07-08) ✅ 완료:** 총평이 "결과 읽기"에 그치지 않도록, 동일 엔진으로 실행된 과거 전략 시뮬레이션 코퍼스(2,000개, `advisor/corpus_insights_data.jsonl.gz` — Chroma 코퍼스에서 `scripts/export_corpus_insights.py`로 내보낸 커밋 아티팩트)와의 결정론적 비교를 리포트에 주입한다(`advisor/corpus_insights.py`). ① 구조 유사 전략 코호트(`structural_similarity`≥0.5, 30개 미만이면 전체 코퍼스) 내 CAGR/MDD 방어/샤프/승률 백분위 ② 사용자 전략에 없는 구조 장치(손절·익절·정기 리밸런싱·5종목 분산)의 유무별 코호트 중앙값 대조(과거 통계 서술만, 추천 표현 금지). 문장은 Python이 완성해 프롬프트에 주입하고 LLM은 그대로 옮긴다(수치 환각 방지). **함정: "상위 79%" 표기를 LLM이 상위권으로 오독(실측)** → 중앙값 아래는 "하위 X% (중앙값 대비 낮음)"으로 오독 불가능하게 서술 + 프롬프트에 하위 긍정 서술 금지 규칙. 응답에 `corpusComparison` 포함. 코퍼스 파일 없으면 기존 리포트로 무해 폴백. 라이브 검증: 승률 하위 21%→"진입 신호 정제 필요", 손절 부재→유무별 MDD 중앙값(-21.91% vs -14.26%) 대조가 총평·단점에 정확 반영.
- **프로/프리미엄 전용 게이트(2026-07-08) ✅ 완료:** AI 리포트는 프로·프리미엄 전용 기능. 무료 플랜이 "AI 리포트" 탭을 누르면 리포트 대신 안내 문구("AI 리포트는 프로/프리미엄 플랜 전용 기능입니다") + "플랜 변경" 버튼(→ `/pricing`)을 노출한다. 무료 플랜은 백그라운드/저장 시 유료 LLM 생성을 트리거하지 않는다(`isAiReportEnabled = planId !== "FREE"`, `BacktestDashboard`). 요금제 페이지 기능표에 "AI 리포트" 행 추가(`PricingPlans`). 회귀 테스트 `BacktestDashboard.aiReportPlanGate.test.tsx`

#### 3.3.3.1 백테스트 결과 다운로드 (CSV/JSON) ✅ 완료 (2026-07-08)

- **기능:** 백테스트 결과 페이지 상단 "결과 다운로드" 버튼 → 모달에서 CSV 또는 JSON 선택 후 다운로드. 개별 CSV/JSON 버튼을 직접 노출하지 않고 반드시 버튼 → 모달 → 형식 선택 흐름을 거친다.
- **대상 데이터:** 종목 분석(현재 정렬 반영, 매매 0건 제외) + 매매 기록을 하나의 파일에 함께 포함. 화면과 동일 소스(`sortedSymbols`/`result.tradesList`, `resolveTradeReason`) 사용. 전략명은 metadata/제목에 한 번만 포함하고 각 행에는 넣지 않는다. CSV는 UTF-8 BOM(Excel 한글 보호), JSON은 pretty print(비율=소수).
- **파일명:** `{strategy_slug}_backtest_result_{yyyyMMdd}.{csv|json}`
- **프로/프리미엄 전용 게이트:** 무료·비로그인 사용자는 "결과 다운로드" 클릭 시 업그레이드 안내 모달("결과 다운로드는 Pro 이상에서 사용할 수 있어요" + "요금제 보기"/"닫기")만 노출, CSV/JSON 선택 버튼과 export API 호출이 발생하지 않는다. **서버(`app/api/backtest/export`)에서도 `getUserPlan`으로 플랜을 재검증** — Free/비로그인/차단 사용자가 직접 API를 호출해도 403/401로 파일을 만들지 않는다.
- **확장성:** 순수 빌더 `lib/backtest-export.ts`(`ExportFormat`/`buildExportFile` 포맷 분기)로 향후 Excel/PDF 추가 용이. 회귀 테스트 `backtestExport.test.ts`(빌더), `backtestExportRoute.test.ts`(서버 게이트), `BacktestDashboard.downloadGate.test.tsx`(UI 게이트)

#### 3.3.4 전략 최적화 (Optuna) ✅ 완료

- **방식:** TPE (Tree-structured Parzen Estimator) 기반 베이지안 최적화
- **파라미터:** 이산형 리스트 또는 연속형 범위 (min, max, step)
- **제약조건:** 의미적 순서 보장 (예: shortMA < longMA)
- **타겟 메트릭:** CAGR, Sharpe, Profit Factor, Win Rate, Total Return
- **결과물:** 최적 파라미터, Top-N 결과, 파라미터 중요도, 마크다운 리포트

---

### 3.4 가상 매매 시스템 (페이퍼 트레이딩) ✅ 전체 구현

#### 3.4.1 기능 명세

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| 가상 계좌 생성 | 초기 자금 설정, 복수 계좌 관리 | ✅ 완료 |
| 실시간 호가 조회 | 종목별 10단계 매수/매도 호가 (KIS API + WebSocket) | ✅ 완료 |
| 시장가/지정가 주문 | 매수·매도 주문, 취소 | ✅ 완료 |
| 포지션 관리 | 보유 종목, 평균 단가, 평가 손익 | ✅ 완료 |
| 전략 연동 매매 | 백테스트 전략 기반 자동 주문 (자동매매/신호알림 모드) | ✅ 완료 |
| 가상 주식시장 엔진 | VirtualTrader 백그라운드 루프, 30초 간격 시그널 평가 (휴장일/스테일 시세 가드) | ✅ 완료 |
| 리스크 관리 | SL/TP/TS/MaxHold 자동 적용, 중복매매 방지, PENDING 자동체결 | ✅ 완료 |
| 거래 내역 & 정산 | 수수료·세금 포함 실현 손익, 체결 이력 | ✅ 완료 |
| 실시간 PnL | 다중 Provider 시세 기반 실시간 손익 추적 | ✅ 완료 |
| 매매 로그 | 진입/청산/오류 사유별 로그 기록 (VirtualMarketLog) | ✅ 완료 |
| 가상 매매 대시보드 | 종합 성과, 포지션, 주문 이력, 로그 | ✅ 완료 |

#### 3.4.2 가상 매매 아키텍처

```
[사용자 전략]
    │
    ▼
┌──────────────────┐     ┌──────────────────┐
│  VirtualTrader   │────▶│  Order Manager   │
│  (30초 루프)      │     │  (주문 처리/체결)  │
└──────────────────┘     └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
           ┌─────────────┐ ┌──────────┐ ┌──────────────┐
           │ Position Mgr │ │ Risk Mgr │ │ Market Logger│
           │ (포지션 관리) │ │ (리스크)  │ │ (매매 로그)   │
           └─────────────┘ └──────────┘ └──────────────┘
                    │
                    ▼
           ┌──────────────────┐
           │  MarketDataProv  │
           │  (KIS→Naver→     │
           │   yfinance→pykrx)│
           └──────────────────┘
```

#### 3.4.3 스케줄러 ✅ 완료

**TypeScript 스케줄러 (`lib/scheduler.ts`):**
| 시간 (KST) | 작업 |
|-------------|------|
| 08:50 | 장전 캐시 워밍 (추적 종목 시세 선행 로드) |
| 09:00 | 장 개시 (자동매매 계좌 시작) |
| 09:00~15:30 | 시그널 평가·체결은 백엔드 VirtualTrader(30초 루프)가 담당 |
| 15:30 | 장 마감 (자동매매 일시정지) |

**Python 스케줄러 (`scripts/scheduler.py`):**
| 시간 (KST) | 작업 |
|-------------|------|
| 00:00 | 일일 OHLCV 데이터 동기화 |

#### 3.4.4 상장폐지 리스크 대응 시스템 ✅ 완료

> 상장폐지·거래정지 등 비정상 종목을 자동 감지하고 가상계좌와 백테스트 엔진 전반에 걸쳐 일관된 리스크 처리를 수행한다.

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| 상장 상태 머신 | 7단계 상태 (NORMAL → DELISTED), 거래 허용/차단 규칙 정의 | ✅ 완료 |
| DB 스키마 확장 | Stock 테이블에 listingStatus 외 6개 필드, DelistingAuditLog 모델, VirtualAccount delistingPolicy | ✅ 완료 |
| DART 공시 분류 | report_nm 키워드 → ListingStatus 자동 매핑 (5개 키워드 그룹) | ✅ 완료 |
| Stock 테이블 동기화 | DART 공시 수신 시 sync_from_dart_notices(), DelistedSymbolStore → sync_from_delisted_store() | ✅ 완료 |
| 거래 제한 | orders/route.ts에서 listingStatus 확인 후 차단 + DelistingAuditLog 기록 | ✅ 완료 |
| 0원 평가 | DELISTED 포지션은 currentPrice=0, totalValue=0 반환 | ✅ 완료 |
| 강제청산 | DELISTED/DELISTING_SCHEDULED + AUTO_LIQUIDATE 정책: 마지막 시세로 청산 또는 0원 제거 | ✅ 완료 |
| VirtualTrader 연동 | 매매 사이클마다 상태 체크 → 매수 차단 / 강제청산 신호 주입 | ✅ 완료 |
| 백테스트 생존자 편향 방지 | _process_symbol() 상단에서 delisted_store 확인 후 종목 제외 | ✅ 완료 |
| UI 배지 | TrackedSymbolRow에 상태 배지 표시 (red/orange/yellow) | ✅ 완료 |
| DelistingRiskBanner | 가상계좌 상단 리스크 배너 (D-N 카운트다운, 강제청산 버튼) | ✅ 완료 |
| 감사 로그 | DelistingAuditLog: AUTO_LIQUIDATE / TRADE_BLOCKED / STATUS_CHANGE 이벤트 기록 | ✅ 완료 |
| 테스트 | backend 21개 (test_listing_status.py), frontend 35개 (listing-status.test.ts), API 2개 | ✅ 완료 |

**새 API 엔드포인트:**
- `GET /market/listing-status` — 전체 상장 상태 조회 (backend + DB 통합)
- `POST /market/listing-status/sync` — 수동 동기화 트리거
- `POST /virtual-account/{id}/force-liquidate/{symbol}` — 강제청산
- `GET /api/market/delisting-status` — Next.js 통합 상태 조회 (5개 배열 + details)

---

### 3.5 시장 데이터 시스템 ✅ 완료

#### 3.5.1 멀티 Provider 시세 데이터

| Provider | 역할 | 데이터 |
|----------|------|--------|
| KIS (한국투자증권) | Primary — REST + WebSocket | 현재가, 호가, VI 상태, 종목 상세 |
| Naver Finance | Fallback #1 | 현재가, 시가총액 |
| yfinance | Fallback #2 | 현재가, 과거 OHLCV |
| pykrx | Fallback #3 | 현재가, 과거 OHLCV |
| KRX API | Fallback #4 | 종목 목록, 실시간 시세 |

- **CircuitBreaker 패턴:** Provider 장애 시 자동 차단/복구
- **WebSocket 실시간:** KIS WebSocket 구독 (종목별 실시간 호가)
- **SSE 스트리밍:** 호가 스트림, 시세 스트림, 인기종목 스트림

#### 3.5.2 시장 데이터 기능

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| 글로벌 지수 | KOSPI, KOSDAQ, Nasdaq, DOW, S&P500, VIX, Nikkei, Shanghai, FX, 원자재 | ✅ 완료 |
| 종목 상세 | 차트, 시세, 시가총액, 거래량, KIS 상세 데이터 | ✅ 완료 |
| 10단계 호가 | KIS API 실시간 호가창 | ✅ 완료 |
| 호가 스트리밍 | SSE 기반 실시간 호가 업데이트 | ✅ 완료 |
| 종목 검색 | 이름/코드 기반 검색 | ✅ 완료 |
| 퀵 서치 | 종목+전략 통합 검색 | ✅ 완료 |
| 인기 종목 | 실시간 인기 종목 랭킹 (캐시) | ✅ 완료 |
| 유니버스 동기화 | KRX KIND → korea-stocks.json (추가/상폐 추적) | ✅ 완료 |
| VI 표시 | 변동성 완화장치 상태 식별 + 호가 단위 계산 | ✅ 완료 |
| 뉴스 피드 | 주요 시장 뉴스 | ✅ 완료 |

---

### 3.6 포트폴리오 & 대시보드

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| 홈 대시보드 | 전략/백테스트/가상계좌 허브 (WelcomeSection, 시장 스냅샷, 관심종목, 전략/백테스트 이력, 가상매매 현황) | ✅ 완료 |
| 포트폴리오 대시보드 | 전체 자산 현황, 수익률 추이, 포지션 분포, 품질 게이지 | ✅ 완료 |
| 요금제 & 플랜 제한 | Free/Pro/Premium 플랜별 계좌당 초기 투자금·가상계좌 수·저장 전략 수·월 백테스트 한도. 계좌는 플랜의 초기 투자금으로 독립 생성(공유 풀 폐기), 계좌 해지 시 금액 미이전. 요금제 페이지(무료 플랜 변경), 내 플랜/사용량 모달·페이지 | ✅ 완료 |
| 구독 시작/종료일 & 롤링 결제 주기 | "구독 시작하기" 결제 완료 시 `User.planStartDate` 기록, "내 플랜" 모달의 종료 날짜는 시작일 기준 롤링 1개월 후로 계산(`currentPlanCycle`). 월 백테스트 사용량 리셋도 이 롤링 주기를 따름(미구독자는 캘린더 월 폴백). 가상계좌·전략 저장 한도는 주기 리셋 없는 상시 캡 유지. FR-PLAN-010 | ✅ 완료 |
| 토스페이먼츠 자동결제(빌링) 연동 | 유료 플랜(PRO/PREMIUM) 정기 구독 결제 — v2 SDK `requestBillingAuth`(카드 등록창) 기반. 흐름: `/pricing` "구독 시작하기" → `/pricing/checkout?plan=`(자동갱신 조건 고지, `PaymentCheckout`) → 카드 등록창 → `/pricing/success`에서 서버 승인(`POST /api/payment/confirm`: customerKey 대조 → 빌링키 발급 `/v1/billing/authorizations/issue` → 첫 달 청구 `/v1/billing/{billingKey}`) → `planTier`+`planStartDate`+`tossBillingKey`+`nextBillingAt`(+1개월) 갱신. 주문은 `POST /api/payment/order`가 서버 금액(lib/plans.ts)으로 `PaymentOrder`에 기록, 멱등키(orderId)·재승인 멱등 처리. `POST /api/user/plan`은 FREE 다운그레이드만 허용(무결제 유료 전환 차단, 빌링 상태 함께 해제). FR-PLAN-011 | ✅ 완료 |
| 구독 월 자동갱신·해지 | 인-프로세스 스케줄러가 매시 정각 `processDueBillingRenewals`(lib/server/billingRenewal.ts) 실행 — `nextBillingAt` 도래 구독을 빌링키로 자동 청구(갱신도 `PaymentOrder` 기록), 성공 시 예정 시각 기준 +1개월. 실패 시 1일 후 재시도, 연속 3회 실패 시 FREE 전환. 해지는 `POST /api/payment/billing/cancel`이 해지 예약(`subscriptionCanceledAt`)만 기록하고 다음 결제일에 청구 없이 FREE 전환(결제된 기간은 이용 유지). 요금제 페이지에 다음 결제일/자동갱신 해지/만료일 표시. 라이브 전환 시 토스 자동결제(빌링) 계약 필요. FR-PLAN-011a | ✅ 완료 |
| 관심종목 | 종목 추가/삭제, 그룹 관리 (색상), DB 영구 저장, 드로어 UI | ✅ 완료 |
| 월별 수익률 | 히트맵 시각화 | ✅ 완료 |
| 종목별 비중 | 파이차트, 섹터별 분산도 | ✅ 완료 |
| 리밸런싱 추천 | 목표 비중 대비 조정 제안 | 🔲 미구현 |
| 성과 귀인 분석 | 종목·전략·타이밍별 기여도 | 🔲 미구현 |

---

### 3.7 고급 분석 도구

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| 워크포워드 분석 | 롤링/앵커 윈도우 분할 최적화 + 효율성 평가 | ✅ 완료 |
| 워크포워드 정합성 개선 | 엔진이 실제 읽는 파라미터만 화이트리스트 추출, 사용자 범위 무클램프 적용, 파라미터 제외 토글, is/oos_bars 명시 분할(표시=실행), wfe_valid, Calmar·expectancy 집계, 취소 지원 (FR-BT-049) | ✅ 완료 |
| 워크포워드 SSE 진행률 | `/walk-forward/stream` 창 단위 진행률 스트리밍 + 연결 종료 시 창 경계 협조적 취소 (FR-BT-049) | ✅ 완료 |
| 워크포워드 예상 소요 시간 | 실행 전 총 백테스트 수(구간×(조합/시도+1))를 기준 백테스트 실측 속도(`executionTime`)로 보정해 예상 소요 시간 범위를 미리 표시 + 실행 중 실측 timing으로 남은 시간(라이브 ETA) 갱신. 사전 추정의 구간 길이 비율 스케일은 제거(1회 비용은 기간과 거의 무관한 고정비 지배 — 스케일 시 수 배 과소추정돼 라이브 ETA와 괴리) (FR-BT-049) | ✅ 완료 |
| 지표 기간 파라미터화 | MACD fast/slow/signal, 스토캐스틱 period, 볼린저 period/stdDev를 DSL 값으로 계산 — 기본값은 기존 컬럼 유지로 과거 결과 보존 (FR-BT-049b, engine/indicator_columns.py) | ✅ 완료 |
| 몬테카를로 시뮬레이션 | 수익률 분포 확률적 분석 | ✅ 완료 |
| 몬테카를로 분포 리포트 | Worst/Best·사분위(5/25/75/95%)·CAGR/MDD 히스토그램·진행률/취소·블록 1/5/10/21일 방식 선택 (FR-BT-050) | ✅ 완료 |
| 몬테카를로 거래 재표본 | 체결 기록 FIFO 매칭 → 거래별 수익률 복원추출(trade bootstrap), 완결 거래 20건 미만 시 에러 (FR-BT-050) | ✅ 완료 |
| 검증 결과 쉬운 설명 섹션 | 워크포워드·몬테카를로 결과에 수치를 일상 언어 문장으로 풀어 주는 "쉽게 이해하기" 섹션 결정적 생성 (FR-BT-051b, `ResultPlainSummary.tsx`) | ✅ 완료 |
| 저장 결과 워크포워드 422 수정 | 저장 DSL에 symbols 부재로 워크포워드/재실행이 pydantic 422 → `buildWalkForwardRequest` 단일 통로에서 `symbols: []` 폴백 + detail 객체 배열 "[object Object]"를 읽을 수 있는 메시지로 변환 + 전략 기록 상세(`/backtest/[id]`)를 비스트림에서 SSE 스트림 클라이언트로 전환 (FR-STR-042b) | ✅ 완료 |
| 워크포워드 취소 반응성 수정 | 취소가 창 경계에서만 확인되어 진행 중 창의 최적화(그리드 최대 500조합)가 계속 실행되던 버그 — should_cancel을 그리드 조합 루프·베이지안 trial 콜백(study.stop)·OOS 직전까지 배선해 백테스트 1회 단위로 중단 (FR-BT-049) | ✅ 완료 |
| Optuna 최적화 | TPE 베이지안 파라미터 최적화 | ✅ 완료 |
| 그리드 서치 | 순열 기반 파라미터 탐색 (단기<장기 의미 제약 공유) | ✅ 완료 |
| 팩터 분석 | Fama-French, 모멘텀, 밸류 팩터 분해 | 🔲 미구현 |
| 상관관계 분석 | 종목 간 상관계수 히트맵 | 🔲 미구현 |
| 섹터 로테이션 | 업종별 동향, 순환 패턴 | 🔲 미구현 |
| 벤치마크 비교 | KOSPI/S&P500 대비 알파/베타 | 🔲 미구현 |

---

## 4. 데이터베이스 설계

### 4.1 현재 스키마 (SQLite + Prisma)

```sql
-- 사용자
User {
  id, email (unique), name, password, createdAt, updatedAt
}

-- 종목 마스터
Stock {
  id, symbol (unique), name, market, updatedAt
  → BacktestResult[]
}

-- 전략 정의
Strategy {
  id (SHA-256 strategy_id), name, description, settings (JSON), strategyType, createdAt, updatedAt
  → BacktestResult[], BacktestHistory[], BatchRunCandidate[]
}

-- 백테스트 결과
BacktestResult {
  id (cuid), strategyId→Strategy, stockId→Stock, summary (JSON), trades (JSON), createdAt
}

-- 전략 단위 백테스트 실행 캐시
BacktestRun {
  id, strategyId→Strategy, strategyHash, canonicalDsl, request (JSON), result (JSON),
  metrics (JSON), market, universe, initialCapital, timeframe, costModel (JSON),
  createdAt, updatedAt
}

-- RAG 검색용 전략 임베딩/검색 메타데이터
StrategyEmbedding {
  id, strategyId→Strategy, embeddingModel, embeddingVector (JSON/Text),
  textDocument, structureDocument, createdAt
}

-- 조언 경험 메모리
AdviceExperience {
  id, strategyId→Strategy, userPrompt, strategySummary, strategyDsl, canonicalDsl,
  strategyHash, similarStrategyIds (JSON), retrievedCases (JSON), agentAdvice (JSON),
  beforeBacktest (JSON), afterBacktest (JSON), evaluation (JSON),
  lesson, confidence, market, universe, initialCapital, timeframe, dataCoverage, createdAt
}

-- 백테스트 이력 (캐싱 포함)
BacktestHistory {
  id (cuid), strategyId→Strategy?, strategyName, universe, conditions (JSON), metrics (JSON),
  result (JSON), cacheKey (unique), isVisible, hitCount, createdAt
}

-- 배치 실행
BatchRun {
  id (run_id), createdAt, totalPrompts, completedCount, failedCount, skippedCount,
  rankingSnapshot (JSON), logs (JSON)
  → BatchRunCandidate[]
}

-- 배치 실행 후보
BatchRunCandidate {
  id (cuid), runId→BatchRun, strategyId→Strategy?, prompt, strategyName, status,
  errorMessage, metrics (JSON), rank, createdAt
}

-- 가상 계좌
VirtualAccount {
  id, userId, name, initialCash, currentCash, status ("ACTIVE"/"CLOSED"),
  strategyId, strategyName, tradingMode ("manual"/"auto"), closedAt,
  createdAt, updatedAt
  → VirtualMarketState, VirtualOrder[], VirtualPosition[]
}

-- 사용자 플랜 / 월 백테스트 사용량 (User 모델 필드)
--   planTier ("FREE"/"PRO"/"PREMIUM"), planStartDate (유료 플랜 구독 시작일, FREE면 null),
--   backtestUsageMonth (사용량 리셋 주기 키), backtestCountThisMonth (Int)
--   — planStartDate 있으면 그 기준 롤링 1개월 주기, 없으면 캘린더 월로 초기화.
--   플랜 정의는 lib/plans.ts, 주기 계산은 lib/server/planLimits.ts의 currentPlanCycle().

-- (레거시) UserAsset / AssetLedger: 공유 자산 풀 모델은 폐기됨.
--   풀 펀딩/정산-반환 로직은 제거(계좌는 플랜별 초기 투자금으로 독립 생성).
--   AssetLedger는 계좌 정산값 기록(ACCOUNT_LIQUIDATION_RETURN, 닫힌 계좌 수익률 조회용)
--   및 매수/매도 거래 기록 용도로만 보존. UserAsset은 미사용(테이블 유지).
UserAsset {
  userId→User, availableCash (Decimal), initialGrantAmount (Decimal),
  createdAt, updatedAt
}
AssetLedger {
  id, userId→User, accountId→VirtualAccount?, type, amount (Decimal),
  balanceAfter (Decimal), createdAt
}

-- 가상 시장 상태
VirtualMarketState {
  id, accountId (unique)→VirtualAccount, startDate, status ("stopped"/"running"/"paused"),
  symbols (JSON), lastRefreshed, createdAt, updatedAt
}

-- 가상 주문
VirtualOrder {
  id, accountId→VirtualAccount, symbol, name, side ("BUY"/"SELL"),
  type ("MARKET"/"LIMIT"), quantity, price, filledPrice, status ("PENDING"/"FILLED"/"CANCELLED"),
  filledAt, avgBuyPrice, fee, realizedPnl, tax, createdAt
}

-- 가상 포지션
VirtualPosition {
  id, accountId→VirtualAccount, symbol (unique per account), name,
  quantity, avgPrice, currentPrice, peakPrice, openedAt, updatedAt
}

-- 가상매매 로그
VirtualMarketLog {
  id, accountId, date, symbol, signalType, reason, price, action, orderId, createdAt
}

-- 관심종목 그룹
WatchlistGroup {
  id, name, color (default blue), createdAt
  → WatchlistSymbol[]
}

-- 관심종목
WatchlistSymbol {
  id, symbol (unique), name, addedAt, groupId→WatchlistGroup
}
```

---

## 5. API 설계

### 5.1 Next.js API Routes (60+ 엔드포인트)

#### 인증 & 사용자 (5개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| POST | `/api/login` | 로그인 |
| POST | `/api/logout` | 로그아웃 |
| POST | `/api/register` | 회원가입 |
| GET/POST | `/api/user` | 사용자 정보 조회/수정 |
| GET | `/api/user/info` | 상세 사용자 정보 |

#### 종목 데이터 (12개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET | `/api/stock/quote` | 실시간 시세 |
| GET | `/api/stock/prices` | 배치 시세 |
| GET | `/api/stock/batch-quotes` | 복수 종목 시세 |
| GET | `/api/stock/search` | 종목 검색 |
| GET | `/api/stock/popular` | 인기 종목 |
| GET | `/api/stock/popular-stream` | 인기 종목 스트림 (SSE) |
| GET | `/api/stock/historical` | 과거 가격 |
| GET | `/api/stock/overview` | 시장 개요 |
| GET | `/api/stock/[symbol]/ohlcv` | OHLCV 캔들 (1260일) |
| GET | `/api/stock/[symbol]/detail` | 종목 상세 (시가총액, KIS) |
| GET | `/api/stock/[symbol]/orderbook` | 10단계 호가 |
| GET | `/api/stock/[symbol]/orderbook-stream` | 호가 실시간 스트림 (SSE) |

#### 시장 데이터 (11개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET | `/api/market/health` | Provider 헬스 체크 |
| GET | `/api/market/price/{symbol}` | 단일 종목 시세 (폴백 체인) |
| POST | `/api/market/prices` | 배치 시세 |
| POST | `/api/market/subscribe` | WebSocket 구독 |
| GET | `/api/market/realtime` | WebSocket 캐시 스냅샷 |
| GET | `/api/market/indices` | 글로벌 지수 (30s 캐시) |
| POST | `/api/market/signals` | 실시간 시그널 평가 |
| GET | `/api/market/orderbook/{symbol}` | 호가 (KIS) |
| GET | `/api/market/orderbook-stream/{symbol}` | 호가 스트림 |
| POST | `/api/market/prices-stream` | 멀티 종목 시세 스트림 (500ms) |

#### 백테스트 (7개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| POST | `/api/backtest/run` | 백테스트 실행 (프록시) |
| GET | `/api/backtest/history` | 이력 조회 (페이징) |
| GET | `/api/backtest/history/[id]` | 개별 결과 상세 |
| POST | `/api/backtest/walk-forward` | 워크포워드 분석 |
| POST | `/api/backtest/summarize` | AI 요약 생성 |
| GET | `/api/backtest/explain` | XAI 설명 (SHAP) |
| POST | `/api/backtest/ai-report` | AI 분석 리포트 |

#### 전략 / AI 런타임 (12개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET/POST | `/api/strategy` | 전략 목록/생성 |
| GET/PUT/DELETE | `/api/strategy/[id]` | 전략 상세/수정/삭제 |
| POST | `/api/strategy/parse` | 자연어 파싱 (MLX/Ollama) |
| POST | `/api/strategy/backtest-stream` | SSE 백테스트 스트림 |
| POST | `/api/strategy/save-with-backtest` | 전략 저장 + 백테스트 원자적 실행 |
| GET/POST | `/api/strategy/batch-runs` | 배치 실행 시작/이력 조회/상세 조회/취소 |
| POST | `/api/strategy/coach` | AI 전략 코치 (단건 응답) |
| POST | `/api/strategy/coach/stream` | AI 전략 코치 SSE 스트리밍 |
| POST | `/api/advisor/review` | RAG + Experience Memory 전략 리뷰/개선 조언 |
| GET | `/api/ai/runtime/metrics` | AI 런타임 latency 메트릭 조회 |
| POST | `/api/ai/runtime/metrics/reset` | AI 런타임 메트릭 초기화 (production 비활성화) |

#### 가상 계좌 & 매매 (11개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET/POST | `/api/virtual-account` | 계좌 목록/생성 |
| GET/PUT | `/api/virtual-account/[id]` | 계좌 상세/수정 |
| GET | `/api/virtual-account/[id]/positions` | 포지션 조회 |
| GET | `/api/virtual-account/[id]/orders` | 주문 이력 |
| POST | `/api/virtual-account/[id]/orders/fill` | PENDING 주문 수동 체결 |
| GET/DELETE | `/api/virtual-account/[id]/orders/[orderId]` | 주문 상세/취소 |
| GET | `/api/virtual-account/[id]/dashboard` | 대시보드 메트릭 |
| POST | `/api/virtual-account/[id]/strategy/start` | 자동매매 시작 |
| POST | `/api/virtual-account/[id]/strategy/stop` | 자동매매 중지 |

#### 가상 시장 (3개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET | `/api/virtual-market/[accountId]` | 시장 상태 |
| POST | `/api/virtual-market/[accountId]/refresh` | 시그널 갱신 (5분 주기) |
| GET | `/api/virtual-market/[accountId]/logs` | 매매 로그 |

#### 대시보드 (4개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET | `/api/dashboard/watchlist-snapshot` | 관심종목 시세 스냅샷 |
| GET | `/api/dashboard/account-monthly` | 월별 PnL |
| GET | `/api/dashboard/trading-status` | 가상계좌 현황 요약 |
| GET | `/api/dashboard/strategy-list` | 전략 목록 |

#### 관심종목 (6개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET/POST | `/api/watchlist` | 관심종목 조회/추가 |
| GET/POST | `/api/watchlist/groups` | 그룹 목록/생성 |
| PUT/DELETE | `/api/watchlist/groups/[id]` | 그룹 수정/삭제 |
| GET/POST | `/api/watchlist/symbols` | 종목 목록 |
| DELETE/PATCH | `/api/watchlist/symbols/[symbol]` | 종목 삭제/그룹 변경 |

#### 뉴스 & Impact (5개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET | `/api/news/top` | 주요 시장 뉴스 피드 |
| GET | `/api/news/symbol/[symbol]` | 종목별 뉴스 목록 (페이징, 백엔드 미가동 시 seed 데이터) |
| GET | `/api/news/impact/[symbol]` | 종목 뉴스 Alpha 시그널 (latest_alpha, risk_alert_level) |
| GET | `/api/news/fetch-body` | 기사 본문 요약 추출 프록시 (SSRF 방어 적용) |
| GET | `/api/stocks/[symbol]/news` | 종목 상세 뉴스탭 캐시 전용 API (`stock_news_cache` 조회 only) |

#### 기타 (5개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET/POST | `/api/stocks/names` | 종목 마스터 |
| POST | `/api/stocks/sync` | 종목 동기화 (KRX) |
| GET | `/api/universe/data` | 유니버스 필터 데이터 |
| GET | `/api/universe/history` | 유니버스 동기화 이력 |
| GET | `/api/model/status` | NL 파서 모델 상태 |
| GET | `/api/quick-search` | 통합 퀵 서치 |
| POST | `/api/scheduler` | 스케줄러 배치 (장전/개시/갱신/마감) |

### 5.2 FastAPI Backend 엔드포인트 (25+개)

| Method | Endpoint | 기능 |
|--------|----------|------|
| POST | `/backtest` | 백테스트 실행 (중복 방지 2초) |
| POST | `/optimize` | Optuna 최적화 |
| POST | `/walk-forward` | 워크포워드 분석 |
| GET | `/stock/{symbol}/ohlcv` | OHLCV (Parquet, 1260일) |
| GET | `/market/health` | Provider 헬스 |
| GET | `/market/price/{symbol}` | 단일 시세 (폴백) |
| GET | `/market/stock-detail/{symbol}` | KIS 상세 |
| POST | `/market/prices` | 배치 시세 |
| GET | `/market/indices` | 글로벌 지수 |
| POST | `/market/subscribe` | WebSocket 구독 |
| GET | `/market/realtime` | WebSocket 캐시 |
| GET | `/market/orderbook/{symbol}` | 10단계 호가 |
| GET | `/market/orderbook-stream/{symbol}` | 호가 SSE |
| POST | `/market/prices-stream` | 멀티 시세 SSE |
| POST | `/market/signals` | 실시간 시그널 평가 |
| POST | `/strategy/parse` | 자연어 파싱 (LRU 캐시) |
| POST | `/strategy/backtest-stream` | SSE 백테스트 스트림 |
| POST | `/strategy/coach` | AI 전략 코치 (단건 응답) |
| POST | `/strategy/coach/stream` | AI 전략 코치 SSE 스트리밍 (토큰 단위) |
| POST | `/advisor/review` | 전략 진단, RAG 검색, Experience Memory 저장 |
| GET | `/model/status` | NL 파서 상태 |
| GET | `/ai/runtime/metrics` | AI 런타임 latency 메트릭 조회 |
| POST | `/ai/runtime/metrics/reset` | AI 런타임 메트릭 초기화 |
| POST | `/summarize` | AI 요약 생성 |
| POST | `/sync-stocks` | 유니버스 동기화 |
| GET | `/news/articles` | 전체 뉴스 목록 (페이징) |
| POST | `/news/collect` | 뉴스 수집 트리거 |
| GET | `/news/symbol/{symbol}` | 종목별 뉴스 (페이징, as_of 지원) |
| GET | `/news/impact/{symbol}` | 종목 뉴스 Alpha 시그널 (latest_alpha) |
| GET | `/news/top` | 주요 뉴스 (섹터/전체) |
| GET | `/v2/news/{symbol}` | 종목 뉴스탭 캐시 조회 (crawler/agent/LLM 실행 없음) |
| POST | `/v2/news/events` | 뉴스 priority 사용자 행동 이벤트 기록 |
| GET | `/v2/news/priority` | priority score 및 queue 상태 모니터링 |
| GET | `/news/fetch-body` | 기사 본문 일부 추출 (private/loopback/link-local/non-global URL 차단) |

---

## 6. 개발 로드맵

### Phase 1: 핵심 플랫폼 — ✅ 완료

| 작업 | 상세 | 상태 |
|------|------|------|
| 백테스트 엔진 | 시뮬레이터 바이어스 제거, 결과 정확성 검증 | ✅ 완료 |
| 시그널 엔진 벡터화 | 전체 시계열 벡터화 평가로 성능 최적화 | ✅ 완료 |
| 전략연구소 (프롬프트 기반) | 자연어 전략 생성 + 대화형 수정 + SSE 백테스트 | ✅ 완료 |
| Optuna 최적화 통합 | 하이퍼파라미터 자동 최적화 | ✅ 완료 |
| AI 모델 v2 | Conv1D+RoPE+CLS Transformer + 분리 XGBoost | ✅ 완료 |
| 결과 대시보드 | 에퀴티 커브, 월별 수익, 종목별 통계 | ✅ 완료 |
| SHAP 설명 AI | 매매 판단 근거 시각화 | ✅ 완료 |
| AI 요약 생성 | Qwen 7B MLX 기반 자연어 리포트 | ✅ 완료 |

### Phase 1.5: 독립형 배치 테스트 — ✅ 완료

| 작업 | 상세 | 상태 |
|------|------|------|
| 모두 테스트 UI | 전략 만들기 채팅 상단 Primary CTA + Batch Results 모달 | ✅ 완료 |
| 서버 BatchRun API | `/api/strategy/batch-runs` 시작/상세/이력/취소 | ✅ 완료 |
| 서버 Queue/Worker | concurrency 제한, 상태별 체크포인트 저장 | ✅ 완료 |
| Content-addressed 저장 | `strategy_id = SHA-256(canonical_strategy_dsl)` 기반 dedupe/cache | ✅ 완료 |
| 결과 영구 저장 | `Strategy`, `BacktestResult`, `BacktestHistory`, `BatchRun`, `BatchRunCandidate` | ✅ 완료 |
| 복구 동작 | 서버 재시작 후 다음 요청 시 incomplete run 재등록 | ✅ 완료 |

### Phase 2: 가상 매매 시스템 — ✅ 완료

| 작업 | 상세 | 상태 |
|------|------|------|
| 가상 계좌 DB 스키마 | VirtualAccount, Position, Order, MarketState, MarketLog | ✅ 완료 |
| 주문 시스템 | 시장가/지정가 주문, 체결, 취소 | ✅ 완료 |
| 포지션 관리 | 실시간 평가, 평균 단가, peakPrice 추적 | ✅ 완료 |
| 실시간 시세 연동 | KIS WebSocket + 다중 Provider 폴백 | ✅ 완료 |
| 전략 자동 실행 | VirtualTrader 백그라운드 루프, 시그널 기반 자동매매 | ✅ 완료 |
| 거래 내역 & 정산 | 수수료·세금 포함 실현 손익, 매매 로그 | ✅ 완료 |
| 가상 매매 대시보드 | 계좌 현황, 포지션, 주문 이력, 로그 | ✅ 완료 |
| 장 스케줄러 | 사전/개시/1분 갱신/마감 자동 실행 | ✅ 완료 |

### Phase 3: 시장 데이터 & 분석 — ✅ 대부분 완료

| 작업 | 상세 | 상태 |
|------|------|------|
| 멀티 Provider 시세 | KIS→Naver→yfinance→pykrx→KRX 폴백 체인 + CircuitBreaker | ✅ 완료 |
| 글로벌 지수 | KOSPI, KOSDAQ, Nasdaq, DOW, S&P500, VIX, Nikkei 등 12+ | ✅ 완료 |
| 10단계 호가 | KIS API 실시간 호가 + SSE 스트리밍 | ✅ 완료 |
| 종목 상세 | 캔들스틱 차트, 재무제표, 시가총액, KIS 상세 | ✅ 완료 |
| 종목 검색 & 퀵서치 | 이름/코드 검색, 종목+전략 통합 검색 | ✅ 완료 |
| 가상계좌 내비게이션 | 브라우저 뒤로가기 시 `/virtual-account/[id] → /virtual-account` 경로를 유지하고, 일반 진입 시 마지막 상세 복구 유지 | ✅ 완료 |
| 유니버스 동기화 | KRX KIND 기반, 추가/상폐 이력 추적 | ✅ 완료 |
| 관심종목 | 그룹별 관리, DB 저장, 드로어 UI | ✅ 완료 |
| 홈 대시보드 | 시장 스냅샷, 전략/백테스트/가상매매 허브 | ✅ 완료 |
| 워크포워드 분석 | 롤링/앵커 윈도우 최적화 + 효율성 | ✅ 완료 |
| 몬테카를로 | 수익률 분포 확률적 분석 | ✅ 완료 |
| VI 식별 | 변동성 완화장치 상태 + 호가 단위 | ✅ 완료 |
| 섹터 분석 | 업종별 동향, 로테이션 | 🔲 미구현 |
| 상관관계 분석 | 종목 간 상관계수 히트맵 | 🔲 미구현 |

### Phase 3.5: 데이터 해결 엔진 (DataResolver) — ✅ 완료

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| DataResolver 코어 | 전략 조건의 누락 데이터를 자동 감지·해결하는 엔진 (`backend/engine/data_resolver.py`) | ✅ 완료 |
| 거래대금 자동 계산 | `trading_value_20_sma` 누락 시 close×volume 20일 SMA로 즉시 계산 | ✅ 완료 |
| 펀더멘털 즉시 보충 | PER/PBR/ROE/부채비율 누락 시 KIS API → Naver Finance 순으로 실시간 조회 | ✅ 완료 |
| 시가총액 계산 | `market_cap` 누락 시 상장주식수(Naver/pykrx) × close로 계산 | ✅ 완료 |
| PER/PBR 직접 산출 | EPS/BPS가 존재하면 close÷EPS, close÷BPS로 fallback 계산 | ✅ 완료 |
| 해결 과정 로그 | 모든 해결 시도를 `resolution_logs`로 프론트엔드 터미널에 실시간 표시 | ✅ 완료 |
| 유닛 테스트 | 20개 테스트 케이스 (`backend/tests/test_data_resolver.py`) | ✅ 완료 |

### Phase 3.6: Strategy Research Agent — ✅ 완료

> DSL 블록 기반 전략 후보 자동 생성 → 프리스크린 → 워크포워드/몬테카를로 견고성 검증 → Optuna 최적화 → 홀드아웃 검증 → 페이퍼 트레이딩 자동 승격 파이프라인.
> **설계 원칙:** 수익보다 견고성 우선 (Robustness 가중치 > 수익 관련 가중치).

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| Prisma 스키마 확장 | User.planTier (FREE/PREMIUM), ResearchRun, ResearchCandidate, ResearchEvent | ✅ 완료 |
| 몬테카를로 엔진 | `backend/engine/monte_carlo.py` — block bootstrap (block_size=21), log-return 재샘플링, 분위수 분포 반환 | ✅ 완료 |
| 전략 템플릿 | `backend/research/templates/` — momentum, mean_reversion, value, volume_breakout, ai_signal (5종) | ✅ 완료 |
| 후보 생성기 | `backend/research/generator.py` — SHA256 canonical hash dedup, seeded shuffle, max_n 제한 | ✅ 완료 |
| 탐색 공간 | `backend/research/search_space.py` — 템플릿별 파라미터 범위, cardinality 계산 | ✅ 완료 |
| 복합 스코어링 | `backend/research/scoring.py` — tanh-bounded 합성 점수, Deflated Sharpe Ratio, regime_consistency | ✅ 완료 |
| 안전 장치 | `backend/research/safeguards.py` — HoldoutGuard, CircuitBreaker, AIModelLeakGuard, PrescreenGates | ✅ 완료 |
| 이벤트 시스템 | `backend/research/events.py` — DB 기록 + asyncio.Queue SSE 팬아웃 | ✅ 완료 |
| 프리스크린 | `backend/research/prescreen.py` — 50종목 샘플 빠른 백테스트, CircuitBreaker 연동 | ✅ 완료 |
| 견고성 검증 | `backend/research/robustness.py` — MC + WFA 병합 스코어, regime_consistency | ✅ 완료 |
| 승격기 | `backend/research/promoter.py` — Strategy + VirtualAccount(auto) + VirtualMarketState(stopped) 트랜잭션 생성 | ✅ 완료 |
| 에이전트 오케스트레이터 | `backend/research/agent.py` — 상태머신 (_generate→_prescreen→_robustness→_optimize→_holdout→_finalize) | ✅ 완료 |
| FastAPI 라우터 | `backend/api/research_routes.py` — 9개 엔드포인트, premium 게이팅, SSE 스트림, 일일 예산 5000 | ✅ 완료 |
| 유닛 테스트 | `backend/tests/test_research_agent.py` — 25개 테스트 (generator/scoring/safeguards/MC/agent/promoter) | ✅ 완료 |

**핵심 설계 결정:**
- HoldoutGuard: DataLoader 수정 대신 request.endDate 클램핑 방식 (기존 코드 무침)
- Optuna n_trials 상한: √(search_space_cardinality) — 과적합 방지
- 승격 후 VirtualMarketState.status = 'stopped' — 사용자 명시적 시작 필요
- 복합 점수: `tanh(cagr/0.3)×0.15 + tanh(sharpe/2)×0.20 + tanh(pf/2)×0.10 + tanh(wr/0.6)×0.05 - tanh(mdd/0.3)×0.30 + robustness×0.20`

### Phase 3.7b: AI 전략 코치 — ✅ 완료

> 전략 파싱 완료 이후 AI 코치가 advisor_insight + news_agent_insight 를 바탕으로 맞춤형 1:1 코칭 메시지를 비동기 SSE 스트리밍으로 전달.

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| NLParser `chat()` | 비구조화 텍스트 생성 (MLX `mlx_lm.generate`) | ✅ 완료 |
| NLParser `stream_chat()` | 토큰 단위 스트리밍 (`mlx_lm.stream_generate`) | ✅ 완료 |
| coach_routes.py | `POST /strategy/coach` 단건 + `POST /strategy/coach/stream` SSE | ✅ 완료 |
| 모델 공유 | `set_parser()` — NLParser와 동일 Qwen 9B 모델 참조 공유 (메모리 중복 방지) | ✅ 완료 |
| 뉴스 우선순위 규칙 | news_agent_insight → risk_alert_level high 시 리스크 조언 최우선 | ✅ 완료 |
| Next.js 프록시 | `app/api/strategy/coach/stream/route.ts` SSE 패스스루 | ✅ 완료 |
| 프론트엔드 스트리밍 | `generateCoachResponse()` — ReadableStream 소비, 첫 토큰에 스피너→메시지 전환 | ✅ 완료 |
| StrategyAdvisorPanel 수정 | race condition 버그 수정 (cleanup에서 lastReqKey 리셋) | ✅ 완료 |
| clarification 제거 | `/strategy/parse` 에서 rule-based clarification 생성 완전 제거 | ✅ 완료 |
| 캐시/중복 제거 | Next.js/FastAPI 계층에서 JSON cache, SSE replay cache, in-flight dedupe 적용 | ✅ 완료 |
| 런타임 우선순위 | MLX priority lock에서 parse보다 낮고 summary보다 높은 priority로 실행 | ✅ 완료 |
| 전략 만들기 UI 정리 | 모델 로딩 배지 제거, 오른쪽 코치 패널 제거, 전략 요약 카드/코치 말풍선 중심으로 단순화 | ✅ 완료 |
| 옛 learning 템플릿 차단 | advisor_result 입력 필터와 최종 응답 가드로 표본 수/중앙값 나열형 조언 노출 방지 | ✅ 완료 |

### Phase 3.7c: RAG + Experience Memory 전략 조언 Agent — ✅ 완료

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| Strategy ID 정합성 | canonical DSL + SHA-256 기반 식별 및 캐시 재사용 | ✅ 완료 |
| Advisor memory schema | `BacktestRun`, `StrategyEmbedding`, `AdviceExperience` 저장 구조 | ✅ 완료 |
| 유사 전략 검색 | 텍스트 기반 검색 + DSL 구조 기반 검색 결합 | ✅ 완료 |
| 경험 검색/선별 | 과거 조언 성공/실패 사례와 lesson을 현재 전략 컨텍스트로 주입 | ✅ 완료 |
| 개선 후보 생성 | 리스크/성과 문제 기반 후보 DSL 생성 | ✅ 완료 |
| 후보 재백테스트 | `/analytics/new`에서 후보 백테스트와 WFA/OOS 컨텍스트를 advisor 요청에 반영 | ✅ 완료 |
| 성공/실패 평가 | 수익률, 위험, 거래 품질, 비용/슬리피지, OOS/WFA 악화 여부 종합 판단 | ✅ 완료 |
| Memory 저장 안전성 | Advisor 저장은 기존 사용자 `Strategy` row를 덮어쓰지 않는 insert-only 방식 | ✅ 완료 |
| 10,000건 학습 artifact | KOSPI200 smoke sample 10,000건 결과를 `data/advisor-learning` dataset/summary로 반영 | ✅ 완료 |
| 조언 품질 개선 | flat evidence 감지, 낮은 유사도 confidence downgrade, profit factor/trade count 반영 | ✅ 완료 |
| 사용자 문구 압축 | 유사 사례/Experience Memory 출처 설명을 숨기고, 비교 후보와 리스크 조치만 표시 | ✅ 완료 |
| 옛 조언 패턴 제거 | learning evidence는 내부 참고용으로만 사용하고, 조건 변경은 한 번에 하나씩 비교하도록 안내 | ✅ 완료 |

### Phase 3.8: 뉴스 Impact AI Agent — ✅ 완료

> 뉴스/공시 데이터를 수집·중복제거·분류하여 종목별 Alpha 시그널을 생성하고, 종목 상세 페이지의 뉴스·공시 탭에 실시간 표시하는 시스템.

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| 뉴스 수집 Provider | Naver Finance RSS (4개 피드), 한국경제·연합뉴스·매일경제 RSS | ✅ 완료 |
| 중복 제거 | Jaccard 유사도 + body hash, 24h 시간 윈도우, 배치 내 intra-batch dedup | ✅ 완료 |
| 뉴스 스키마 | `NormalizedArticle`, `NewsImpact` Pydantic 모델 | ✅ 완료 |
| Alpha 시그널 | 이벤트 분류 (earnings_beat / analyst_upgrade 등), 방향·confidence·expected_alpha 계산 | ✅ 완료 |
| FastAPI 라우터 | `news_routes.py` — 6개+ 엔드포인트 (`/news/symbol`, `/news/impact`, `/news/top`, `/news/fetch-body` 등) | ✅ 완료 |
| Next.js API 프록시 | `/api/news/symbol/[symbol]`, `/api/news/impact/[symbol]` (seed 데이터 폴백 포함) | ✅ 완료 |
| Seed 데이터 | 삼성전자(005930) 5건 뉴스 + Impact 시그널 (백엔드 미가동 시 표시) | ✅ 완료 |
| NewsImpactPanel | `components/stock/NewsImpactPanel.tsx` — Alpha 배지, 뉴스 목록, 위험 알림 표시 | ✅ 완료 |
| 종목 페이지 연동 | `app/stock-order/page.tsx` 뉴스·공시 탭에 `NewsImpactPanel` 적용 | ✅ 완료 |
| 유닛 테스트 | `backend/tests/test_news_dedup.py` — 중복 제거 로직 22개 테스트 케이스 | ✅ 완료 |
| 본문 fetch 보안 | Next.js 프록시와 FastAPI 라우터 모두 private/loopback/link-local/non-global URL 차단 | ✅ 완료 |

**핵심 설계 결정:**
- 뉴스 Provider는 키 없이 동작하는 RSS 기반 (Naver Finance 4개 피드)
- 중복 제거: body hash 일치 우선, 24h 내 타이틀 Jaccard ≥ 0.5 시 dup 처리, 10자 미만 짧은 제목 제외
- 백엔드 미가동 시: Next.js API Route에서 seed 데이터 자동 폴백 (개발/테스트 환경)
- `app/stock-order/page.tsx`: 5탭 구조(차트·호가/종목정보/뉴스·공시/거래현황/커뮤니티), 뉴스 탭은 NewsImpactPanel 렌더링

### Phase 3.8b: 종목 뉴스탭 캐시 파이프라인 + 우선순위 수집 엔진 — ✅ 완료

> 종목 상세 뉴스탭에서 크롤러/LLM을 기다리지 않고 이미 준비된 캐시를 즉시 렌더링하도록, 뉴스 수집과 분석을 백그라운드 파이프라인으로 분리했다.

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| 캐시 전용 뉴스탭 API | `GET /api/stocks/{symbol}/news?limit=30`는 `stock_news_cache`만 조회하고 news agent/crawler/LLM을 직접 실행하지 않음 | ✅ 완료 |
| 저장소 분리 | `news_raw`, `news_analysis`, `stock_news_cache`, symbol mapping/priority/queue 관련 저장 구조 분리 | ✅ 완료 |
| 중복 제거 v2 | 동일 URL 중복 방지, normalized title/hash 기반 유사 제목 dedup, 대표 뉴스 선별 기준 적용 | ✅ 완료 |
| Symbol Mapping | 제목/본문에서 종목명, 종목코드, 별칭, 섹터성 표현을 매핑하고 하나의 뉴스가 여러 종목에 연결 가능 | ✅ 완료 |
| 백그라운드 분석 | News Collector → Raw News DB → Deduplication → Symbol Mapping → News Agent Analysis → StockNewsCache 경로로 처리 | ✅ 완료 |
| 캐시 미스 처리 | API는 즉시 빈 배열을 반환하고 refresh job만 queue에 넣어 UI 요청을 blocking하지 않음 | ✅ 완료 |
| 프론트엔드 prefetch | 종목 상세 진입 시 React Query `["stock-news", symbol]`로 prefetch, 뉴스탭 클릭 시 캐시된 데이터 렌더링 | ✅ 완료 |
| 뉴스탭 상태 UI | loading, empty, stale, error 상태와 중요도/감성/impact score 표시 | ✅ 완료 |
| Priority Engine | 현재 조회 종목, 관심종목, 가상계좌 보유 종목, 최근 조회/검색, 거래대금, 뉴스 velocity, 지수 편입 기반 priority score 계산 | ✅ 완료 |
| Hot/Warm/Cold Queue | Hot 1~5분, Warm 10~30분, Cold 1~6시간 계층으로 수집 대상 자동 배치 | ✅ 완료 |
| Trending Detection | 조회 수, 뉴스 발생량, 거래대금, 관심종목 추가 급증 조건으로 Hot Queue 승격 | ✅ 완료 |
| Queue Scheduler | priority 5분 재계산, Hot/Warm/Cold queue 주기 dispatch, startup bootstrap collect 지원 | ✅ 완료 |
| Worker autostart | 백엔드 news scheduler 시작 시 Celery worker 자동 기동, shutdown 시 worker 종료 | ✅ 완료 |
| 중복 worker 방지 | pid lock file + Celery broker active queue inspect로 같은 머신/같은 broker 중복 worker autostart 방지 | ✅ 완료 |
| 장애 대응 | 외부 수집 실패 시 기존 캐시 유지, 분석 실패 시 raw news 기반 캐시 노출 및 retry/log 기록 | ✅ 완료 |

**핵심 설계 결정:**
- 뉴스탭 클릭 시점에는 절대 크롤링, 외부 뉴스 검색, LLM 분석을 실행하지 않는다.
- 사용자 행동 데이터가 시장 데이터보다 우선한다. 현재 조회 종목 > 관심종목/보유종목 > 최근 조회/검색 > 거래대금/뉴스 velocity/지수 편입 순으로 수집 자원을 배분한다.
- `NEWSV2_WORKER_AUTOSTART_ENABLED=false`로 운영 환경의 외부 worker manager와 충돌을 피할 수 있으며, 기본 autostart는 lock과 broker inspect로 중복 실행을 방지한다.

### Phase 3.9: 모멘텀 랭킹 전략 + 달력 기준 리밸런싱 — ✅ 완료

> "박스권 돌파 매수" 같은 서술형 시그널과 "최근 N일 수익률 상위 K종목" 같은 상대강도(모멘텀) 랭킹 전략을 자연어로 인식하고, 실제 달력 기준(일/월/분기/년) 리밸런싱(reconstitution)으로 백테스트할 수 있도록 파서·스키마·엔진을 확장했다.

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| 박스권 돌파 NL 인식 | "박스권을 위로 돌파", "N일 고점 돌파/신고가" 등 서술형 표현을 `breakout` 진입/청산 신호로 일반화 인식 (`_extract_breakout_lookback`로 lookback 추출, 기본 20/52주=252) | ✅ 완료 |
| 하이브리드 검증 원칙 | `_DESCRIPTIVE_INDICATORS`(ma_crossover/breakout/volume_spike)는 LLM 서술 신뢰, 나머지 지표는 키워드 검증 — case-by-case 정규식 추가 대신 핵심만 결정적 규칙, 긴 꼬리는 LLM 프롬프트 예시로 위임 | ✅ 완료 |
| 모멘텀 랭킹 스키마 | `ParsedStrategy.ranking_metric`("return"), `ranking_lookback_days`, `rebalancing_period`(none/daily/monthly/quarterly/yearly) 필드 추가 | ✅ 완료 |
| 모멘텀 랭킹 NL 추출 | "최근 N거래일/N일/N개월 수익률 상위 K종목" → `_extract_ranking()`으로 `ranking_metric="return"` + lookback 결정적 추출, 미지정 시 60일 기본 | ✅ 완료 |
| 진입 신호 누락 안전장치 | `detect_missing_entry_clarification()` — 진입 의도가 파싱에서 조용히 누락된 경우 명확화 질문 + 제안 칩 표시. 일반 누락과 "미지원 상대강도 랭킹 표현"을 구분해 각각 다른 안내 제공 | ✅ 완료 |
| 엔진 rank_df (모멘텀) | `backtest_engine.py` — `ranking_metric=="return"`이면 `price_df.pct_change(lookback)` 기반 `rank_df` 계산, 진입 신호 없으면 `available_df & valid`(초기 lookback NaN 구간 제외)로 후보군 구성 | ✅ 완료 |
| 달력 기준 리밸런싱 (reconstitution) | `engine/rebalance.py: compute_rebalance_dates()` — 주기별 첫 거래일 boolean (vbt 비의존, 단위테스트 가능). 시뮬레이터 커스텀 루프에서 리밸런싱일마다 목표 집합(상위 K) 재구성 → 목표 밖 보유 매도, 신규 편입, 유지 종목 그대로 | ✅ 완료 |
| 하이브리드 라우팅 | 순수 리밸런싱(SL/TP/TS/보유기간 없음) → `vbt.Portfolio.from_orders(size_type='targetpercent')` 네이티브 목표비중(비중 리셋 O); 리밸런싱+봉중간 리스크 혼재 → 기존 `from_signals` reconstitution 커스텀 루프(현실적 체결 유지, 비중 리셋 v1 미지원) | ✅ 완료 |
| UI 표시 | `getRankingLabel()` — "선정: N일 수익률 상위" 배지, `REBAL_LABELS`에 `daily: 매일` 추가 | ✅ 완료 |
| 컨버터 연동 | `rebalancing_period != "none"`이면 `max_holding_days=None`(리밸런싱이 회전 구동, 중복 방지); 랭킹 전략은 미지정 시 monthly 기본 | ✅ 완료 |
| 유닛 테스트 | `test_rebalance_dates.py`(6개, pandas만), `test_simulator_ranking.py`(랭킹 선정 + 두 라우팅 경로 회전 검증), `test_nl_parser_overrides.py`/`test_strategy_converter_strategy_id.py` 신규 케이스 추가 | ✅ 완료 |

**핵심 설계 결정:**
- "수익률 상위 K종목" 같은 상대강도 랭킹은 기존 per-stock boolean 시그널과 본질이 다른 cross-sectional 선정 — `rank_df`로 후보 재정렬 메커니즘을 재사용해 새 스키마 필드만 추가
- 비중 리셋이 필요 없는 순수 리밸런싱은 vbt 네이티브 `from_orders(targetpercent)`로, 봉중간 리스크 관리(SL/TP/트레일링)가 섞인 경우는 현실적 체결을 보존하는 커스텀 `from_signals` 루프로 — 두 경로를 자동 분기
- vbt 실행 환경은 `.venv`가 아니라 pyenv 3.11.2(`vectorbt 0.28.2`)이며, 실제 실행 검증으로 reconstitution 루프의 "고스트 포지션" 버그(같은 날 매도+매수 시 active_count 갱신 지연으로 빈 슬롯이 영구 차단)를 발견·수정함

### Phase 3.10: AI 예측 모델 보조 활용 검증 + 추천 비활성화 — ✅ 완료

> "AI 모델 단독으로는 수익을 못 내니 보조 도구로 어떻게 써야 최대 수익이 나는가"를 백테스트로 검증했다. 결론: **어떤 사용 방식으로도 바이앤홀드 대비 알파가 확인되지 않았다.** 이에 따라 조언/코치 에이전트와 전략연구소 예시에서 AI 모델 추천·노출을 전면 제거했다.

| 작업 | 상세 | 구현 상태 |
|------|------|----------|
| 점수 분포 진단 | AI 점수가 보정 안 된 좁은 분포(상승 0.20~0.30, 하락 0.33~0.40)에 밀집 → UI/파서 기본 threshold=70은 0거래. 분포 퍼센타일 기반 threshold 필요 | ✅ 완료 |
| per-stock 보조 활용 실험 | `backend/experiment_ai_auxiliary.py` — AI를 진입 필터/청산 타이밍/리스크 결합 등 15개 조합으로 비교. AI 선택적 청산(C1/C3)이 단일 3Y 구간에선 최고 위험조정수익 | ✅ 완료 |
| 워크포워드 검증 | `backend/experiment_ai_walkforward.py` — 2018~2025 연도별 8구간(약세장 2018·2022 포함). 전 구간 평균 B&H +15.2%/년이 모든 능동전략 압도, C1/C3는 8년 중 1년만 B&H 초과. 3Y 호성과는 강세장/생존편향이었음 | ✅ 완료 |
| breadth 위험 오버레이 검증 | `backend/experiment_ai_breadth_overlay.py` — 다수 종목 AI-하락 동시발화 시 전량 현금화(레짐 필터). 모든 임계값에서 B&H를 절대수익·CAGR·Sharpe에서 하회 | ✅ 완료 |
| Polars 데드락 수정 | AI in-process 백테스트가 polars rayon latch에서 무한정지 → 실행 시 `POLARS_MAX_THREADS=1` 필수(+ XGBoost segfault 회피 `KMP_DUPLICATE_LIB_OK`/`OMP_NUM_THREADS`) | ✅ 완료 |
| 조언 엔진 추천 비활성화 | `advisor/suggestion_engine.py::_build_ai_recommendation` 항상 `recommended=False`, `_build_experiments`에서 "AI 예측 신호 추가" 실험 제거 | ✅ 완료 |
| 코치 추천 차단 | `api/coach_routes.py` — `ai_model_recommendation`을 코치 LLM 컨텍스트에 미전달 + `COACH_SYSTEM_PROMPT`에 AI 모델 추천 금지 지시 추가 | ✅ 완료 |
| NL 파서 제안 정리 | `engine/nl_parser.py` 진입 누락 안내/빠른 제안 칩에서 "AI 모델 상승 예측" 제거(돌파·거래대금 신호로 대체) | ✅ 완료 |
| 전략연구소 예시 교체 | `components/strategy/StrategyExampleTabs.tsx` — AI 모델 예시 11개(초3/중4/전4) 전부 비AI 전략으로 교체, "AI 전략" 카테고리 제거 | ✅ 완료 |
| 종목 분석 AI 보조 게이지 | 종목 분석에서 항상 'AI 예측 데이터 없음'이던 문제 해결. `stock_analysis_routes.py`가 main이 이미 로드한 `engine.ai_engine`을 재사용 주입. `forecast_service.py`는 **종목 자기 시계열 퍼센타일**로 점수 보정(절대 net 임계값은 down>up 분포상 전 종목 '하락' 오류 → 폐기). **매매 결정 제외**: `recommendation_engine.py`에서 forecast 점수 완전 제거. 노출은 입증된 가치(하방 방어)에 맞춘 하방 리스크 게이지(elevated/moderate/calm)로만 — `AIForecastGauge` + `StockAnalysisPanel` "AI 하방 리스크" 카드, "매매 신호 아님" 명시 | ✅ 완료 |
| 종목 분석 뉴스 감성 | 종목 분석 패널 '뉴스 감성 데이터 없음' 상시 문제 해결. **근본 원인 = 저장소 불일치**: 라이브 news_v2는 **Postgres `simons_news`**(`.env`의 `NEWSV2_DB_URL`)에 실시간 크롤·감성 적재(news_raw/news_analysis 각 1.5만건+, 종목별 오늘자 기사+감성 정상)인데, `stock_analysis/news_service.py`는 sqlite를 읽어 텅 빈 결과. **수정**: news_service가 `news_v2.config.get_settings().db_url`(에이전트가 쓰는 그 DB)을 받아 **async 조회**(`asyncio.run(_async_load)`, asyncpg/aiosqlite 양쪽)로 `stock_news_cache`+`news_raw`+`news_analysis` 조인. 긍정/부정 다수결 집계, 부정 기사 importance로 위험 경보, 최근성 2일→7일(추천 점수 1/3). 라이브 `/stock/analyze`(005930)→news_sentiment=positive 검증. ※부차: news_v2 sqlite 기본경로도 Prisma와 통일(NEWSV2_DB_URL 없을 때만). ※운영: 백엔드 재시작은 `KMP_DUPLICATE_LIB_OK/OMP_NUM_THREADS/POLARS_MAX_THREADS` 가드 필수(없으면 起動 데드락) | ✅ 완료 |
| 종목 분석 후 액션 버튼 | 종목 분석 패널 아래 '돌아가기'(handleReset—초기 상태 복귀+입력 포커스)·'다른 종목 분석' 버튼(마지막 분석 메시지에만 노출). '다른 종목 분석'→"어떤 종목을 분석해 드릴까요?" 채팅 안내+입력창 포커스, `awaitingStockAnalysisRef`로 다음 입력을 분류 없이 바로 `/stock/analyze`에 `query`로 전달(백엔드 find_in_text 종목 해석, 못 찾으면 422→"종목을 찾지 못했어요" 재질문 루프). 기존 STOCK_ANALYSIS 분기와 `renderStockAnalysisResult` 헬퍼 공유(DRY). Next 프록시가 422 상태 보존 | ✅ 완료 |
| 종목 분석 → 전략 브리지(시도 후 철회) | 종목 분석 직후 "○○로 전략 만들기" 권유를 붙였으나 **개념적 모순으로 제거**. 플랫폼 전략/백테스트는 `universe=시장지수`에서 조건으로 종목을 골라내는 **스크리닝**이라 개별 종목을 유니버스로 지정 불가(ParsedStrategy.universe는 시장 리터럴만). 이미 종목 1개를 정한 사용자에게 '종목 찾는' 백테스트를 권하는 건 모순(+실제 삼성전자 못 담고 KOSPI200로 빠짐). 사용자 결정으로 브리지·헬퍼(`stockStrategyBridge.ts`)·`ChatMessage.suggestions` 삭제, 분석 후엔 입력창 자유 이어가기 | ❌ 철회 |
| 스크리닝 문구 오분류 수정 | "PBR 1 이하, PER 10 이하 저평가 종목" 같은 펀더멘털 스크리닝이 STOCK_ANALYSIS로 오분류돼 "어떤 종목을 분석할까요?" 막다른 길이 되던 버그 수정. `intent/classifier.py`에 `_SCREENING_SIGNAL`(지표+숫자 필터/가치·배당·규모+바스켓명사/비교+종목) 결정적 STRATEGY 신호 추가 + LLM 분류 프롬프트 보강(조건으로 종목 고르기=STRATEGY). 프론트 가드: 전략 작성 중 종목 미특정 STOCK_ANALYSIS는 전략 다듬기로 흘려보냄. 테스트 `test_intent_classifier.py::test_fundamental_screening_is_strategy` | ✅ 완료 |
| 열린 종목 추천 요청 → 전략 전환 (규제 안전) | "어떤 주식을 사야 하나요?·추천 종목 있나요?·살 만한 종목·수익 날 종목" 처럼 특정 종목명·정량 조건 없이 매수 대상을 골라 달라는 **열린 추천 요청**은 추천하지 않고 전략 설계로 대화를 전환한다. `intent/scope.py`에 결정적 `is_stock_pick_request`/`stock_pick_reply`(전략 전환 안내 3종, 해시로 결정적 선택) 신설 — 정량 스크리닝(PER/PBR+숫자)·밸류/배당/규모 카테고리 바스켓·전략 키워드·특정 종목명이 있으면 가로채지 않음(스크리닝/종목 분석은 정상 기능). 신규 `QueryIntent.STOCK_PICK`(suggested_reply 동반). 입력 게이트(`intent/classifier.py`)와 코치 가드(`api/coach_routes.py::_coach_scope_guard`) 공유 + LLM 분류 프롬프트에 STOCK_PICK 카테고리 추가. 프론트(`app/analytics/new/page.tsx`)는 GREETING/OFF_TOPIC과 동일 분기로 안내 표시. 테스트 `test_intent_classifier.py::test_open_stock_pick_is_redirected`, `test_coach_routes.py::test_scope_guard_open_stock_pick_redirects_to_strategy` | ✅ 완료 |
| 전략 빌더 모드 (열린 추천 후속 대화) | STOCK_PICK 전환 안내 직후 진입하는 **전략 빌더 모드**. "일단 코스피" 같은 짧은 답변을 거절하지 않고 전략 필드(유니버스→전략유형→기준기간→보유수→리밸런싱→청산조건)로 누적하고, 마지막(청산 조건: 손절·익절·트레일링·보유기간 — **필수**, 하나 이상 인식돼야 완료)까지 채우면 별도 텍스트 요약 없이 곧바로 검증된 한국어 프롬프트로 합성해 기존 파싱 파이프라인(`/strategy/parse/stream`) 재사용 → 전략 요약 카드 + 검증 + '백테스트 실행' 버튼 표시(버튼이 최종 확인). 결정적 상태 머신 `intent/strategy_builder.py`(parse_input·_parse_risk·detect_control·next_question·synthesize_prompt·step) + 무상태 라우트 `POST /strategy/builder/step`. 프론트(`app/analytics/new/page.tsx`)는 `builderModeRef`/`builderStateRef`(세션 스냅샷 보관)로 모드 관리, 분류/거절보다 **먼저** 빌더 step 호출, 확정 시 추출한 `runStrategyParseFlow` 헬퍼로 백테스트 실행. **전환 안내 직후 후속 입력을 기다리지 않고 곧바로 빌더의 첫 질문을 능동적으로 띄운다**(`startStrategyBuilder`가 빈 입력으로 step 호출 → `step`은 상태 변화 없이 현재 질문 반환). **빌더가 옵션 칩을 보여주는 동안에는 채팅 입력창을 숨겨 선택에 집중하게 하고**(마지막 어시스턴트 메시지에 `infoSuggestions`가 있으면 입력창 숨김), 전략 유형 질문 가장 오른쪽의 "직접 설명하기" 칩을 누르면 custom 진입조건 질문(칩 없음)으로 넘어가 입력창이 다시 나타난다. 청산 조건 단계 가장 오른쪽의 "직접 입력" 칩은 빌더 답변이 아니라 프론트 토글(`builderFreeTextRequested`)로, 빌더를 진행하지 않고 입력창만 다시 띄워 커스텀 청산 값을 직접 타이핑하게 한다. **청산 조건은 필수**라 '청산 조건 없음' 칩은 제거됐고, `_parse_risk`는 손절·익절·트레일링·보유기간을 하나 이상 인식했을 때만 `risk_done`을 켠다(없으면 같은 질문 재질문). 4가지 유형(모멘텀·돌파·거래량급증·평균회귀+직접설계) 엔드투엔드. 취소/처음부터/다른질문 종료·리셋 지원. 테스트 `test_strategy_builder.py`(케이스 1~4 + 청산 조건 + 빈 입력 첫 질문 계약 + 직접 설명하기 칩 포함) | ✅ 완료 |
| 전략별 특화 빌더 (STATE_SPECIFIC_STRATEGY_BUILDER) | 사용자가 특정 전략명을 지목하면 그 유형이 잠기고(일반 메뉴 스킵), 유형별 파라미터 스텝 레지스트리(`STRATEGY_PARAM_STEPS`)로 그 전략의 핵심 파라미터만 묻는다 — RSI(기간·과매도/과매수)·이동평균(SMA/EMA·단기/장기)·MACD(크로스/제로선)·돌파/모멘텀(기준일)·CCI(기간·기준값)·거래량(평균기간)·가치(PBR/ROE). 볼린저·스토캐스틱·과매도반등은 프리셋(무질문). 초보자용 '기본값' 지원. 완성 시 한국어 재파싱 왕복 대신 `build_parsed_strategy`가 `ParsedStrategy`(entry/exit `TechnicalSignal`+랭킹/재무필터/리스크)를 **직접 조립** → `to_backtest_request`로 요청 생성(파라미터 유실 방지). 라우트(`_run_builder_step`)가 confirmed 시 `parsed`+`backtest_request`+`notices`를 내려주고 프론트(`applyBuilderConfirmedStrategy`)가 재파싱 없이 소비, custom만 prompt 폴백. **엔진이 실제 반영하는 값만** 묻는다(조용한 드롭 방지): 볼린저 기간/표준편차·스토캐스틱 level·MACD fast/slow/히스토그램·**ATR 전체** 제외. 'RSI'는 mean_reversion보다, '볼린저'는 breakout보다 먼저 판정. 실데이터 스모크(골든크로스 485거래·볼린저 318·모멘텀 337). 테스트 `test_strategy_builder.py`(유형 인식·잠금 회귀·전 유형 DSL·기본값·가치필터·custom 폴백 16건). SRS FR-SA-002d | ✅ 완료 |
| 전략 빌더 옵션 진입 필터 (Tier 2) | 기술적 진입 전략에 옵션 "필터" 스텝 1개 추가 — 진입 신호와 **AND 결합되는 게이트**(추세 "EMA200 위에서만" / 거래대금 N억 이상 / RSI 결합 "30 이하일 때만"). `ParsedStrategy.entry_filters`(빌더 전용) → `to_backtest_request`가 `type='filter'`로 방출 → 엔진 `generate_signals`가 signal과 분리해 AND 결합. 엔진 변경은 `ema` 평가자에 지속 상태 `mode='above'/'below'` 신설뿐(크로스오버 아님, 벡터+행별 양 경로); 거래대금은 `trading_value`, RSI 결합은 `rsi` compare 재사용. `TechnicalSignal.mode`(above/below)·`indicator`(trading_value) literal 확장, `entry_filters`를 canonical DSL 해시에 포함(캐시 충돌 방지). 빌더 `_parse_filters`가 자유 입력서 추세·거래대금·RSI 동시 인식, "없음"·무매치도 완료(옵션). 프론트 `lib/strategy-summary.ts` `formatEntryFilter`로 진입 배지 노출. momentum(랭킹)·value·custom 제외. 원시 '평균 거래량 이상' 전용 평가자는 미구현(거래대금 유동성 필터로 대체). 검증: 신호 레벨 부분집합·파티션(above+below=전체)·AND 게이트 단위테스트, 실데이터 e2e(볼린저 필터無 317거래 → EMA200+거래대금+RSI 31거래). 테스트 `test_engine_signals.py`·`test_strategy_converter_strategy_id.py`·`test_strategy_builder.py`(총 9건). SRS FR-SA-002d Tier 2 | ✅ 완료 |
| 전략 빌더 시드 업종 기억 (2026-07-11) | 종목 질문 전환(FR-SA-006) 뒤 "반도체 주도주로 전략을 만들어줘"처럼 업종이 언급된 채 빌더에 진입하면 `seed_state`가 NL 파서의 결정적 섹터 추출(`_extract_sector`, FR-STR-066)로 `BuilderState.sector`를 미리 채우고, "주도주"를 모멘텀 유형으로 인식해 **종목 고르는 질문("어떤 방식으로 종목을 고를까요?")을 건너뛰고** 빠진 필드(시장·기준기간·보유수·리밸런싱·청산)만 묻는다. 기억한 업종은 첫 질문 도입부 확인("반도체 업종 대상, 모멘텀 전략으로 이해했어요") → 합성 프롬프트("코스피 반도체 업종 종목 중 …", custom 재파싱 경로에서도 '업종' 큐로 재인식) → 직접 조립 DSL(`ParsedStrategy.sector`)까지 흐른다. 섹터는 질문으로 묻지 않는 시드 전용 필드. **긴 꼬리 표현은 regex 확장 대신 LLM 레이어에서 해결**(같은 날 후속): 빈 전략→빌더 전환 시 프론트가 파싱 파이프라인(룰→LLM 검증 교정→LLM 폴백)의 최종 parsed를 `seed_parsed`로 전달, 빌더 `apply_parsed_seed`가 결정적 시드가 놓친 None-기본 필드(sector·청산)만 이어받음(universe·max_positions·rebalancing은 기본값 오염으로 제외, 결정적 시드 우선). 검증 프롬프트에 업종 누락 교정 규칙 명시(지어내기 금지). 테스트 `test_strategy_builder.py`(시드 인식·질문 스킵·prompt/DSL 관통·parsed 이어받기 5건)+`test_parse_validator.py`(sector 교정 적용). SRS FR-SA-002d | ✅ 완료 |
| 검증 교정 환각 AI 신호 주입 차단 + 백테스트 워치독 | 실사고(2026-07-03): 사용자가 AI를 언급하지 않은 KOSDAQ 모멘텀 랭킹 프롬프트에 Parse Fidelity Validator의 `correctedStrategy`가 `ai_model`("AI 매수 예측") 진입 신호를 환각 주입 — 스키마 검증만 통과하면 그대로 적용되던 구멍. 비활성화된 AI 백테스트가 실행되며 행(hang), SSE 스트림은 상태 메시지 무한 방출. **수정 4중**: ① `_maybe_apply_correction`이 교정본 진입/청산 신호를 LLM 본경로와 동일한 `_validate_signals`로 재검증(환각 신호만 드롭, 정상 교정 유지) + 검증 프롬프트에 신호 추가 금지 규칙(FR-STR-020b) ② `NL_PARSER_CACHE_VERSION` 3→4(오염 캐시 무효화) ③ 엔진 AI fail-fast — `AI_SIGNALS_ENABLED=0` 운영 스위치 거절 + AI 모델 로드 불가 시 0거래 침묵 진행 대신 즉시 에러(FR-BT-048) ④ 백테스트 워치독 `engine/watchdog.py` — `/backtest`(504)·`/strategy/backtest-stream`(SSE error 이벤트)이 `BACKTEST_TIMEOUT_S`(기본 600초) 안에 반드시 종료(FR-BT-047). 테스트 `test_parse_validator.py`(환각 스트립/정당 AI 유지), `test_backtest_watchdog.py`(타임아웃/전파/게이트 2종) | ✅ 완료 |
| 백테스트 엔진 감사(2026-07) 수정 | 퀀트 관점 전면 감사에서 발견된 결과 왜곡 요인 일괄 수정. **체결 충실도**: ① `from_signals(size_type='Percent')`의 '잔여 현금 비중' 의미론이 동시 진입 비중을 기하급수 감소시키던 문제 → 커스텀 루프가 의도(슬롯·스탑·리밸런싱)를 결정하고 `from_orders(targetpercent)`가 NAV 대비 목표비중으로 체결(이중 부기 해소, C1/C7) ② 정수 주 단위 체결 `size_granularity=1`(C2) ③ SL/TP/트레일링을 장중 low/high로 감지(종가 감지는 장중 리스크 누락, C5) ④ 거래정지일 청산은 다음 거래 가능일로 이월 `pending_exit`(C6) ⑤ 매수/매도 수수료 분리 + 매도 증권거래세 기본 0.15% `sell_tax_rate`(H3). **통계 무결성**: PF 클램프(10)·buy-and-hold 재정의 제거(C3), Sortino 표준 하방편차(전 기간 target-below RMS)+`risk_free_rate` 옵션(H4/M7), Exposure·MDD Duration·Expectancy·Recovery Factor 추가. **유니버스/신호**: 진입조건 없는 모멘텀 랭킹이 유동성 게이트·대형주 마스크를 덮어쓰던 버그(C4)+next_open 시 시총 마스크 1일 shift(look-ahead), 지표 최대 기간 기반 동적 warm-up(H6), 사유 부분문자열 매칭 제거(M5), loader 중복날짜/정렬 가드(M10). **공시 경고 채널**: 거래세 반영·소표본(<30건)·벤치마크 상장 전 구간·분배금 미반영·정적 주식수 근사·AI 학습기간 중첩(model_meta `train_end`)·리밸런싱 비중 미리셋·전일 거래대금 초과 매수(시장충격). WFE는 IS≤0이면 `wfe_valid=false`(M9). 결과 변경으로 `BACKTEST_ENGINE_VERSION`="audit-fixes-v4" 범프. 테스트: `test_audit_fixes.py`(PF/통계/Sortino/warm-up/모멘텀 유동성/경고) + `test_engine_simulator.py`(NAV 동일비중/정수주/거래세/장중 SL/이월) — 백엔드 1583·프론트 608 전체 통과, 실데이터 스모크(5종목 SL 혼합·순수/혼합 리밸런싱) 검증. **프론트 표시**: 신규 통계 4종을 `BacktestResult` 타입 + 매퍼 3곳(`backtestResultMapper.ts`·`BacktestService.ts`·`app/analytics/[id]/page.tsx` — [id] 재실행 경로는 누락돼 있던 calmar/avgHoldingDays도 함께 배선)에 매핑하고, `BacktestDashboard` '리스크 및 성과 분석' 섹션에 둘째 행(시장 노출도·최장 낙폭 기간·기대값·회복 계수)으로 설명 툴팁과 함께 표시. 매퍼 단위 테스트 2건 추가(`backtestResultMapper.test.ts`) | ✅ 완료 |

**핵심 결론:**
- AI 모델은 진입/청산/위험 오버레이 어느 방식으로도 사이클 전체에서 알파 없음. 유일한 관찰은 휩쏘성 기술적 매매(-65%/년)의 과매매 출혈을 청산으로 줄여주는 것뿐이며 그조차 B&H 미달.
- 사용자가 직접 "AI 모델"을 입력하면 파서·엔진은 여전히 인식·실행한다(기존 저장 전략 호환). 시스템이 **먼저 권하지 않을 뿐**이다.

### Phase 3.11: 관리자 콘솔 (Admin Console) — ✅ 완료

운영자 전용 단일 화면 관리자 콘솔. URL은 `/console` 하나뿐이며(하위 페이지 없음) 내부 탭 전환으로 모든 기능을 제공한다. 보안은 UI 숨김이 아니라 서버 권한 검증으로 보장한다.

| 작업 | 상세 | 상태 |
|------|------|------|
| 서버 권한 검증 | `lib/server/adminAuth.ts::requireAdmin()` — JWT 쿠키 + `User.role='ADMIN'` + `status='ACTIVE'` 3중 검사. 실패 시 페이지·API 모두 **404**로 응답해 콘솔 존재 자체를 숨김. ADMIN 부여는 DB에서만 가능(화면/API로 role 변경 불가) | ✅ 완료 |
| DB 스키마 | `User.role/status/lastLoginAt` 추가, `AdminAuditLog`(감사 로그, 삭제 API 없음), `PlanConfig`(플랜 한도 오버라이드). 마이그레이션 `20260707000000_admin_console` | ✅ 완료 |
| 콘솔 UI | `app/console/page.tsx`(서버 게이트 → `notFound()`) + `components/admin/AdminConsole.tsx` — Overview/Users/Backtests/Virtual Accounts/Strategies/Plans/Audit Logs 7탭, 선택된 탭만 렌더 | ✅ 완료 |
| 관리자 API | `/api/admin/{overview,users,backtests,accounts,strategies,plans,audit}` 7종 — 전부 `requireAdmin()` 게이트, 모든 변경 작업은 `writeAuditLog()`로 before/after JSON + IP 기록. 민감정보(password/token/key)는 어떤 응답에도 미포함 | ✅ 완료 |
| 사용자 관리 | 이메일 검색·플랜/상태 필터·정렬·페이지네이션, 상세 패널에서 플랜 변경/정지/활성화/삭제(soft, status=DELETED)/백테스트 사용량 조정. 자기 자신 정지·삭제는 차단 | ✅ 완료 |
| 정지 계정 차단 | 로그인 403 + 기존 세션도 무효(`getCurrentUser`가 `status!=='ACTIVE'`면 null). 로그인 성공 시 `lastLoginAt` 기록 | ✅ 완료 |
| 가상계좌 관리 | 목록(평가금·수익률·거래수), 일시 중지(`status='PAUSED'` — 기존 `assetService` 주문 가드가 자동 차단)/재개/초기화(포지션·주문 삭제+현금 복원)/삭제 | ✅ 완료 |
| 플랜 한도 오버라이드 | `PlanConfig` upsert → `planLimits.getEffectivePlan()`이 기본값(lib/plans.ts)에 병합, 백테스트 소비·전략/계좌 한도에 실시간 반영(-1=전략 무제한, null=기본값 복원) | ✅ 완료 |
| 테스트 | `lib/server/adminAuth.test.ts`(권한 게이트 6건), `app/api/admin/users/route.test.ts`(404 은닉·감사 로그·자기보호 6건), `planLimits.test.ts` 오버라이드 5건 추가, 로그인 정지 차단 회귀. 라이브 검증: 익명/일반 404 → 관리자 200, 정지→로그인 403+세션 401, 감사 로그 기록, 플랜 오버라이드 30→77→30 왕복 | ✅ 완료 |

### Phase 3.12: 개별 종목 분석 기능 제거 → 전략 설계 전환 (2026-07-10) — ✅ 완료

> 종목 분석 패널이 플랫폼 목적(전략 만들기)에 기여하지 않고 규제 리스크(유사투자자문 오인)만 키운다는 판단으로 기능을 제거했다. 특정 종목 매수·매도 질문에는 "추천·판단을 제공하지 않는다"를 안내하고, 그 종목에서 출발한 전략 설계로 대화를 전환한다(FR-SA-006).

| 작업 | 상세 | 상태 |
|------|------|------|
| 전환 안내 생성 | `intent/scope.py::stock_question_redirect(name, market)` — ① 매수·매도 판단/종목 추천 불가 명시 ② 언급 종목에서 출발한 전략 예시 3종(시가총액 상위 대형주(코스피200)+모멘텀 상위 5종목 / 저평가 우량주 가치 스크리닝 / RSI 과매도 반등) ③ 첫 예시 유니버스는 종목의 시장에 맞춤(KOSDAQ→코스닥). **예시는 엔진이 실제 실행 가능한 개념만 사용** — 당시 섹터/업종 전략은 파서 미지원이라 제안하지 않음(막다른 길 방지). 이후 Phase 3.13에서 섹터 유니버스가 지원되며 업종 예시가 첫 예시로 추가됨 | ✅ 완료 |
| 분류기 배선 | `intent/classifier.py` — STOCK_ANALYSIS(결정적 규칙 2·2-b anaphora·LLM 폴백 전부)에 `suggested_reply` 동반. 실사용 문구 "사볼까"를 `_STOCK_QUESTION`에 추가(결정적 커버) | ✅ 완료 |
| 백엔드 삭제 | `/stock/analyze` 라우트 제거, `api/stock_analysis_routes.py`→`api/intent_routes.py` 개명(classify/builder/general 유지). `stock_analysis/` 분석 파이프라인 8개 모듈(agent·data/technical/fundamental/risk/news→forecast·recommendation_engine·explanation) 삭제. 유지: `symbol_resolver`·`stock_master`(의도 분류), `guardrails`+`DISCLAIMER`(/query/general), `news_service`(advisor 뉴스 보강) | ✅ 완료 |
| 프론트 전환 | `app/analytics/new/page.tsx` — STOCK_ANALYSIS 분기가 분석 호출 대신 `suggested_reply` 표시. **빌더 모드 자동 진입은 하지 않는다(2026-07-11 수정)** — 안내가 이미 종목 기반 전략 예시를 제시하므로 빌더 첫 질문이 예시를 덮지 않게 후속 답변을 대기(회귀 `page.stock-redirect.test.tsx`). 전략 작성 중이면 안내만 표시(기존 전략 보존). `StockAnalysisPanel`·`/api/stock/analyze`·`renderStockAnalysisResult`·'다른 종목 분석' 버튼 삭제 | ✅ 완료 |
| 테스트 | `test_intent_classifier.py`에 전환 회귀 5종(안내 문구/종목명 포함/시장별 유니버스/행동 지시 표현 부재(guardrails)/LLM 폴백) 추가, 분석 파이프라인 테스트 3파일 삭제. 백엔드 1715·프론트 792 전체 통과 | ✅ 완료 |

### Phase 3.13: 섹터/업종 유니버스 지원 (2026-07-10) — ✅ 완료

> "반도체 관련주를 매수하는 전략" 같은 업종 제한 전략을 파서·엔진이 직접 실행할 수 있게 했다(FR-STR-066). 종목 질문 전환 안내(Phase 3.12)의 첫 예시도 언급 종목의 업종 전략으로 업그레이드.

| 작업 | 상세 | 상태 |
|------|------|------|
| 섹터 SOT·정규화 | `engine/universe_pit.py` — `CANONICAL_SECTORS`(38개, korea-stocks.json sector 필드=SOT), `normalize_sector`(동의어: 2차전지→이차전지, 제약→바이오/제약, AI→소프트웨어/플랫폼 등), `filter_by_sector` | ✅ 완료 |
| 파서 | `ParsedStrategy.sector` + field_validator 정규화(LLM 자유 문자열도 정본화, 미지원→None). 결정적 추출 `_extract_sector` = 섹터명+업종 큐(관련주/업종/섹터/테마주/종목/주식/주+중심/위주, '주가' 배제). `_apply_prompt_overrides`가 LLM 결과에도 덮어쓰기 + **시장 언급 없으면 universe=양시장**(KOSPI200 기본이면 시총 상위 200 ∩ 섹터로 과도 축소). 미지원 목록의 `sector` 항목은 제거하지 않고 조건화 — 패턴을 관련주/테마주까지 확장하되 추출 성공 시 제외('로봇 관련주'는 여전히 안내, 기존에 '관련주'가 아예 안 잡히던 침묵 누락도 개선). SYSTEM/COMPACT/MODIFY 프롬프트·parse_validator 스키마에 sector 반영, `NL_PARSER_CACHE_VERSION` 5→6 | ✅ 완료 |
| 전달·엔진 | canonical DSL에 sector 포함(None이면 키 없음 — 기존 전략 해시 불변), `to_backtest_request`·`BacktestRequest.sector`(extra=ignore 스키마 누수 함정 방어), 엔진이 PIT 해석 후 `filter_by_sector` 적용 + 0종목이면 fail-fast + **생존편향 경고**(섹터 분류는 현재 상장 종목 기준 — PIT 마스터엔 섹터 없음). 실데이터 스모크: 반도체 모멘텀 1Y → 78종목·36거래·전 거래 반도체 섹터 확인 | ✅ 완료 |
| 프론트 | `ParsedSummary.sector`·`StrategyBacktestRequest.sector` 타입, `getDisplayUniverseLabels`가 "반도체 업종" 배지 추가, 실행 요청 기반 요약(`buildStrategySummaryFromRequest`)에도 반영 | ✅ 완료 |
| 종목 질문 전환 안내 | `stock_question_redirect(name, market, sector)` — 언급 종목의 섹터를 알면 "○○가 속한 반도체 업종 종목만 대상으로 최근 3개월 수익률 상위 5종목 매수"를 첫 예시로(이/가 조사 처리 포함). 예시 문구 자체가 룰 파서로 파싱됨을 회귀로 보장 | ✅ 완료 |
| 테스트 | universe_pit 섹터 3종, nl_parser 섹터 7종(추출/양시장 기본/명시 시장/미지원 안내/스키마 왕복/해시 불변/validator 정규화), classifier 2종(섹터 예시·파싱 가능성) 추가 — 백엔드 1726·프론트 795 전체 통과 | ✅ 완료 |

### Phase 4: 미구현 기능 (향후)

| 작업 | 상세 | 우선순위 |
|------|------|----------|
| 팩터 분석 | Fama-French, 모멘텀, 밸류 팩터 분해 | P2 |
| 상관관계 분석 | 종목 간 상관계수 히트맵, 최적 분산 포트폴리오 | P2 |
| 벤치마크 비교 | KOSPI/S&P500 대비 알파/베타 분석 | P2 |
| NL 파서 고도화 | 복합 전략 해석, 다중 진입/청산 조건 조합 | P2 |
| 전략 템플릿 | 인기 전략 프롬프트 템플릿 (가치투자, 모멘텀 등) | P2 |
| 섹터 로테이션 | 업종별 동향, 순환 패턴 분석 | P3 |
| 포트폴리오 리밸런싱 추천 | 목표 비중 대비 조정 제안 | P3 |
| 성과 귀인 분석 | 종목·전략·타이밍별 기여도 | P3 |
| 전략 공유 | 전략 퍼블리싱, 설명 문서화 | P3 |
| 전략 마켓플레이스 | 공개 전략 검색, 복제, 평가 | P4 |
| 리더보드 | 수익률 기준 전략 랭킹 | P4 |
| 커뮤니티 피드 | 전략 리뷰, 댓글, 토론 | P4 |

### Phase 5: 인프라 확장 (향후)

| 작업 | 상세 | 우선순위 |
|------|------|----------|
| 미국 시장 데이터 | NASDAQ/NYSE OHLCV 수집 | P3 |
| 다중 통화 | USD/KRW 환산, 글로벌 포트폴리오 | P3 |
| PostgreSQL 마이그레이션 | SQLite → PostgreSQL (확장성) | P3 |
| Redis 캐싱 | 시세/백테스트 캐시 (현재 인메모리 PriceCache) | P3 |
| Docker 컨테이너화 | 프론트엔드/백엔드/DB 분리 | P3 |
| CI/CD | GitHub Actions 빌드/테스트/배포 | P3 |
| 모니터링 | Sentry (에러), Grafana (메트릭) | P4 |
| Rate Limiting | API 보호 | P3 |
| OAuth 2.0 | Google, Kakao 소셜 로그인 | P3 |

---

## 7. 테스트 현황

### 7.1 백엔드 테스트 (40+개 파일, pytest)

| 영역 | 파일 수 | 주요 파일 |
|------|---------|-----------|
| 시그널 엔진 | 5 | test_engine_signals, test_signal_robustness, test_or_isolation, test_live_signal_utils, test_specific_exit_reasons |
| 시뮬레이터 | 7 | test_engine_simulator, test_time_exit, test_ranking_logic, test_multi_reasons, test_multi_symbol_reasons, test_simulator_ranking(모멘텀 랭킹+리밸런싱 라우팅), test_rebalance_dates(달력 기준 리밸런싱일 계산) |
| AI/ML | 3 | test_ai_code_fixes, test_engine_ai*, test_ai_sell* |
| 최적화 | 2 | test_optuna_optimizer, test_optimizer |
| 데이터/로더 | 3 | test_engine_loader, test_loader_preprocess, test_vbt |
| 시세/Provider | 4 | test_market_data, test_providers, test_kis_realtime_providers, test_market_cap |
| 회귀 | 3 | test_regression_fixes, test_zero_trades, test_kospi200_symbol_handling |
| API/통합 | 3 | test_api_idempotency, test_api_isolation*, test_backtest_engine* |
| 유틸리티 | 6 | test_vi_utils, test_universe_history, test_nl_cache, test_summarize, test_stream_progress, test_sync_data_status |
| 백엔드 통합 | 3 | test_backend, test_backend_v2, test_stream_execution_time |
| 뉴스 모듈 | 1 | test_news_dedup (22개 테스트 — 중복제거 로직 전체) |

> `*` 표시: 서버/AI 모델 필요 (일반 실행 시 제외)

### 7.2 프론트엔드 테스트 (45개 파일, Vitest + jsdom)

| 영역 | 파일 수 | 주요 파일 |
|------|---------|-----------|
| 컴포넌트 | 7 | OrderBook, PriceRow, TrackedSymbolRow, TrackedSymbolsSkeleton, TopNavigationQuickSearch, AnalyticsStrategySummary, StrategyExampleTabs |
| API 라우트 | 10 | backtestHistory*, backtestSummarize*, batchQuotes*, stockDetail*, strategyApiGet, saveWithBacktest, xaiExplain*, universeHistory*, virtualAccount, virtualMarket* |
| 유틸리티 | 4 | monthlyReturns, formatMarketCap, orderbookDisplay, viPrice |
| 기타 | 3 | sample, backtestHistoryPayload, virtualMarketUnread, virtualMarketStockName |

### 7.3 Mock 데이터 생성기 ✅ 완료

| 항목 | 내용 |
|------|------|
| 백엔드 OHLCV 생성기 | `backend/engine/mock_data_generator.py` — GBM 기반, 6가지 시나리오, 한국 상하한가·호가 단위 반영 |
| pytest conftest | `backend/tests/conftest.py` — 공용 fixture (mock_ohlcv, mock_data_dir, sim_matrices 등) |
| 프론트엔드 생성기 | `lib/mock-stock-data.ts` — GBM + seeded PRNG(mulberry32) |
| CLI 도구 | `python -m engine.mock_data_generator --scenario bull --symbols A B --days 252` |
| 시나리오 | `bull` / `bear` / `sideways` / `volatile` / `crash_recovery` / `realistic` |

### 7.4 테스트 실행 커맨드

```bash
# 백엔드 (안전한 테스트만)
cd backend && pytest tests/ \
  --ignore=tests/test_backtest_engine.py \
  --ignore=tests/test_engine_ai.py \
  --ignore=tests/test_ai_sell.py \
  --ignore=tests/test_api_isolation.py

# 프론트엔드
npm run test:frontend

# 전체 백엔드 (서버/AI 필요)
cd backend && pytest tests/
```

### 7.5 테스트 개선 계획

| 영역 | 목표 | 우선순위 |
|------|------|----------|
| E2E 테스트 | Playwright 기반 전략 생성→백테스트 플로우 | P3 |
| 성능 테스트 | 대규모 유니버스 (100+ 종목) 벤치마크 | P3 |
| AI 모델 테스트 | 예측 정확도 모니터링, 드리프트 감지 | P3 |

---

## 8. 보안 고려사항

| 영역 | 현재 상태 | 개선 계획 |
|------|-----------|-----------|
| 인증 | JWT 기반 로그인 | OAuth 2.0 (Google, Kakao) 추가 |
| 데이터 보호 | 비밀번호 해싱 | 개인정보 암호화, GDPR 준수 |
| API 보안 | CORS 설정 | Rate Limiting, API Key 관리 |
| 입력 검증 | Pydantic 스키마 | 프론트엔드 검증 강화 |
| SSRF 방어 | 뉴스 본문 fetch URL 검증, redirect 후 최종 URL 재검증 | DNS rebinding 방어 강화, allowlist 운영 |
| 금융 데이터 | 로컬 저장 | 데이터 접근 권한 관리 |
| 관리자 콘솔 | `/console` 단일 화면, 모든 관리자 API `requireAdmin()` 서버 검증, 비관리자 404 은닉, 전 작업 AdminAuditLog 기록(삭제 불가), ADMIN 부여는 DB에서만 | 2FA, 관리자 IP allowlist |
| 이용약관 | 널스페이스의 `nullStock` 이용약관 초안 작성 | 사업자 정보, 유료서비스, 청약철회, 환불, 개인정보처리방침 법무 검토 후 확정 |

---

## 9. 기능 실현도 요약

### 전체 진행률: **~92%** (핵심 기능 기준)

| 영역 | 구현 상태 | 실현도 |
|------|-----------|--------|
| AI 전략 코치 (SSE 스트리밍) | ✅ 전체 완료 | 100% |
| 전략 설계 (자연어 프롬프트 기반) | ✅ 전체 완료 | 100% |
| 전략 배치 테스트 (독립형 Run All Tests) | ✅ 전체 완료 | 100% |
| 백테스트 엔진 | ✅ 전체 완료 | 100% |
| 지원 시그널·지표 (29종) | ✅ 전체 완료 | 100% |
| AI/ML (예측 + XAI + 요약) | ✅ 전체 완료 | 100% |
| 전략 최적화 (Optuna + Grid) | ✅ 전체 완료 | 100% |
| 가상 매매 시스템 | ✅ 전체 완료 | 100% |
| 시장 데이터 (멀티 Provider) | ✅ 전체 완료 | 100% |
| 호가/주문 시스템 | ✅ 전체 완료 | 100% |
| 워크포워드 + 몬테카를로 | ✅ 전체 완료 | 100% |
| 대시보드 & 포트폴리오 | ✅ 대부분 완료 | 90% |
| 관심종목 | ✅ 전체 완료 | 100% |
| 테스트 커버리지 | ✅ 양호 (backend 533 tests, frontend 198 tests 기준) | 85% |
| Strategy Research Agent | ✅ 전체 완료 | 100% |
| 뉴스 Impact AI Agent | ✅ 전체 완료 | 100% |
| 개별 종목 질문 대응 (Intent 분류 → 전략 설계 전환 안내 — 분석 패널은 2026-07-10 제거) | ✅ 전체 완료 | 100% |
| 고급 분석 (팩터, 상관관계, 섹터) | 🔲 미구현 | 0% |
| 소셜/마켓플레이스 | 🔲 미구현 | 0% |
| 인프라 (Docker, CI/CD, 모니터링) | 🔲 미구현 | 0% |
| 글로벌 확장 (미국 시장) | 🔲 미구현 | 0% |

---

## 10. 경쟁 분석 & 차별화

| 기능 | Simons | 증권사 HTS | QuantConnect | 뱅크샐러드 |
|------|--------|-----------|--------------|-----------|
| AI 대화형 전략 설계 | ✅ (자연어) | ❌ | ❌ (코딩 필수) | ❌ |
| AI 예측 신호 결합 | ✅ | ❌ | ⚠️ (직접 구현) | ❌ |
| SHAP 설명 | ✅ | ❌ | ❌ | ❌ |
| 자동 최적화 | ✅ (Optuna) | ❌ | ⚠️ (제한적) | ❌ |
| 한국 시장 특화 | ✅ | ✅ | ❌ | ❌ |
| 가상 매매 | ✅ | ⚠️ (제한적) | ✅ | ❌ |
| 무료 접근 | ✅ | ❌ (계좌 필요) | ⚠️ (제한) | ✅ |

### 핵심 차별화 포인트
1. **자연어 → 퀀트 전략:** 한국어 프롬프트만으로 AI가 투자 전략을 자동 생성
2. **대화형 전략 수정:** 채팅으로 점진적 파라미터 조정
3. **설명 가능 AI:** SHAP 기반 "왜" 매수/매도했는지 해석
4. **한국 시장 딥 커버리지:** 4,052개 한국 종목, PER/PBR/수급 등 국내 특화
5. **로컬 AI 프라이버시:** MLX/Ollama 기반 — 투자 전략이 외부로 전송되지 않음
6. **완전한 가상매매:** 전략 기반 자동매매, 리스크 관리, 매매 로그까지 일체형

---

## 부록

### A. 기술 스택 상세

**Frontend**
- Next.js 14.0.4, React 18.2, TypeScript 5.9.3
- Tailwind CSS 3.4, Recharts, TradingView Lightweight Charts
- TanStack Table 8.21, Framer Motion, Axios

**Backend**
- Python 3.x, FastAPI, Uvicorn
- Polars, Pandas, NumPy, vectorbt, stockstats
- PyTorch, XGBoost, SHAP, Optuna, joblib
- MLX (Apple Silicon NL 파싱)

**Infrastructure**
- SQLite + Prisma ORM (현재), PostgreSQL (목표)
- ESLint, Vitest (24 tests), pytest (38 tests)

### B. 개발 환경 설정

```bash
# 프론트엔드 설치
npm install

# DB 초기화
npm run db:migrate
npm run db:generate

# 백엔드 의존성
cd backend && pip install -r requirements.txt

# 개발 서버 실행
npm run dev          # Frontend (localhost:3000)
npm run dev:backend  # Backend  (localhost:8000)
npm run dev:all      # 프론트엔드 + 백엔드 + 스케줄러 동시
```

### C. 핵심 파일 참조

| 모듈 | 파일 |
|------|------|
| 전략연구소 UI | `app/analytics/page.tsx` |
| 전략 만들기 채팅 | `app/analytics/new/page.tsx` |
| 모두 테스트 모달 | `components/strategy/RunAllTestsModal.tsx` |
| NL 전략 파서 | `backend/engine/nl_parser.py` |
| 전략 변환기 | `backend/engine/strategy_converter.py` |
| 배치 실행 API | `app/api/strategy/batch-runs/route.ts` |
| 전략 DSL 타입 | `types/strategy.ts` |
| 백테스트 엔진 | `backend/backtest_engine.py` |
| 시그널 엔진 | `backend/engine/signals.py` |
| 시뮬레이터 | `backend/engine/simulator.py` |
| AI 엔진 | `backend/ai/ai_engine.py` |
| AI 요약 | `backend/ai/summarize.py` |
| AI 런타임 메트릭 | `backend/main.py`, `app/api/ai/runtime/metrics/route.ts` |
| AI 런타임 메트릭 초기화 | `app/api/ai/runtime/metrics/reset/route.ts` |
| XAI 엔진 | `backend/ai/xai_engine.py` |
| 최적화 에이전트 | `backend/ai/local_optimization_agent.py` |
| 가상매매 트레이더 | `backend/engine/virtual_trader.py` |
| 상장 상태 머신 (Python) | `backend/engine/listing_status.py` |
| 상장 상태 유틸 (TS) | `lib/listing-status.ts` |
| 상장 상태 훅 | `lib/hooks/useDelistingStatus.ts` |
| 상장폐지 리스크 배너 | `components/virtual-account/DelistingRiskBanner.tsx` |
| 강제청산 API | `app/api/virtual-account/[id]/liquidate/route.ts` |
| 상장 상태 조회 API | `app/api/market/delisting-status/route.ts` |
| 시세 데이터 | `backend/engine/market_data.py` |
| KIS Provider | `backend/engine/providers/kis.py` |
| 뉴스 수집 Provider | `backend/news/providers/naver_news.py`, `backend/news/providers/rss_provider.py` |
| 뉴스 중복 제거 | `backend/news/dedup.py` |
| 뉴스 FastAPI 라우터 | `backend/news/news_routes.py` |
| 뉴스 Impact 패널 | `components/stock/NewsImpactPanel.tsx` |
| 뉴스 API 프록시 | `app/api/news/symbol/[symbol]/route.ts`, `app/api/news/impact/[symbol]/route.ts` |
| 종목 거래 페이지 | `app/stock-order/page.tsx` (5탭: 차트·호가/종목정보/뉴스·공시/거래현황/커뮤니티) |
| 장 스케줄러 | `lib/scheduler.ts` |
| DB 스키마 | `prisma/schema.prisma` |

---

*이 문서는 프로젝트의 현재 상태와 향후 계획을 반영합니다. 최종 갱신: 2026-06-12 (레거시 블록 조합 5단계 위자드 빌더 및 `lib/strategy-blocks.ts` 제거 반영 — 전략 설계는 자연어 채팅 기반으로 일원화. 시그널은 엔진·DSL이 평가하는 조건으로 유지).*
