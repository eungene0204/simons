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
| LLM 검증 시간 단축(2026-07-14) ✅ 완료 | ① 검증 발화 잔여 어휘 로그(어휘집 보강 운영 루프) ② 출력 diff 계약(`correctedFields` — 유효 시 `{isValid, confidence}`만, 교정은 바뀐 필드만) ③ 입력 null 필드 생략 ④ `NL_VALIDATOR_MODEL` 검증 전용 모델 opt-in ⑤ SSE 비차단 후행 검증(`result_update`→`parsed_updated`, 룰 파스 즉답 후 교정만 후속 반영, 실행 후 도착 교정은 무시) — FR-STR-020/020d |

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
| `williams_r` | Williams %R (−100~0, 과매도 −80/과매수 −20) | period, operator, value | ✅ (2026-07-14, stockstats `wr_n`) |
| `mfi` | MFI 자금흐름지표 (0~100, ×100 스케일 정규화) | period, operator, value | ✅ (2026-07-14, stockstats `mfi_n`) |
| `roc` | ROC/모멘텀 (변화율 %) | period, operator, value | ✅ (2026-07-14, stockstats `close_n_roc`) |
| `dividend_yield` | 배당수익률 (%, TTM DPS/종가) | operator, value | ✅ (2026-07-14, KIS 예탁원 배당 API 배선 — 지원 지표 승격) |
| `payout_rate` | 배당성향 (%, TTM DPS/EPS) | operator, value | ✅ (2026-07-14, 배당 파이프라인) |
| `dividend_growth` | 배당성장률 (%, TTM DPS 전년比) | operator, value | ✅ (2026-07-14, 배당 파이프라인) |
| `revenue_growth` | 매출 성장률 | operator, value | ✅ (hidden) |
| `operating_margin` | 영업이익률 | operator, value | ✅ (KIS 손익계산서 영업이익/매출액 기반 필터) |
| `beta` | 시장 베타 | operator, value | ✅ (hidden) |
| `ev_ebitda` | EV/EBITDA (배, 낮을수록 저평가) | operator, value | ✅ (2026-07-14, KIS other-major-ratios 배선 — 지원 지표 승격) |

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
- **전략 검증 전문가 리포트(10섹션, 2026-07-21) ✅ 완료:** 결과를 다시 읽어주는 4블록(총평·장점·단점·개선방안) 요약을 "전략 검증 전문가" 리포트로 승격 — ① 핵심 요약 ② 핵심 통찰 ③ 강점 ④ 약점 ⑤ 숨은 위험 ⑥ 과최적화 분석 ⑦ 전략 성향 ⑧ 검증 로드맵 ⑨ 개선 우선순위 ⑩ 최종 평가(FR-BT-022). **핵심 발견: 엔진이 이미 `BacktestResult`에 근거 대부분을 계산해 두고도(`monthlyReturns`/`yearlyReturns`·`maxDrawdownDuration`·`expectancy`·`recoveryFactor`·`avgHoldingDays`·`perAssetStats`) 리포트가 LLM에 전달하지 않았음** → 이를 forward+해석해 결정론 evidence pack으로 주입(`backend/ai/report_evidence.py`: 수익 시간 집중도·수중 지속·'높은 승률·낮은 기대수익'·표본 적정성·회전율·종목 집중). 정확도가 중요한 등급(과적합)·전략 성향 태그·검증 로드맵·개선 우선순위는 결정론으로 산출하고 LLM은 서술 8섹션(executive_summary/top_insights/strengths/weaknesses/hidden_risks/overfitting_analysis/strategy_profile_note/final_verdict)만 담당(`build_expert_report_prompt`/`parse_expert_report`, num_predict 2600). **프롬프트 원칙: 숫자 반복 금지·근거 필수·위험 우선·검증 중심·추천 금지.** **개선 우선순위는 전략 점수 인지형** — 높은 점수→추가 검증 권장, 낮은 점수·구조적 문제→전략 수준 방향성(단순화·아이디어 재검토·시장 과의존 확인·재구성 후 재백테스트) 권장, **어느 경우에도 구체적 DSL 수정(손절/익절 값·지표·파라미터·매수매도 조건) 금지**(규제 안전, advisor `suggested_experiments`의 파라미터 값 실험도 로드맵 미병합). 응답은 가법적 확장(기존 summary/strengths/weaknesses/improvements/advisorScore/riskScore/overfitRisk 유지 + topInsights/hiddenRisks/overfittingAnalysis/strategyProfile/validationRoadmap/finalVerdict 추가). 화면은 SCORE 게이지+3다이얼 헤더 유지 + 10섹션(핵심 펼침/나머지 접기, `CollapsibleSection`). 캐시 generation v5 bump(구 4블록 리포트 재생성 유도), 프론트 AI 리포트 상태를 단일 `AiReportData` 객체로 통합(`components/strategy/backtest/aiReport.ts`), 구 저장 리포트는 확장 섹션 없이 graceful degrade. 회귀 테스트 `test_report_evidence.py`·`test_summarize.py`(expert 파싱)·`test_summarize_endpoint.py`(신규 계약)·`BacktestSummaryCard.test.tsx`(10섹션+접힘+하위호환)

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
| 모니터링 거래정지 필터 (FR-VM-071) | `filterMonitorableSymbols`가 DELISTED에 더해 TRADING_SUSPENDED도 추적 목록에서 제외 | ✅ 완료 |
| KIS 시세 기반 거래정지 동기화 (FR-VM-072) | `iscd_stat_cls_code=58` → `StockQuote.trading_halted` 파싱, VirtualTrader 사이클이 `sync_trading_halt`로 Stock 반영 (DART 분류 우선 보호) | ✅ 완료 |
| 보유 종목 시세 커버리지 | VirtualTrader 시세 조회 = 추적 종목 ∪ 보유 포지션 종목 — 추적 해제된 보유 종목의 청산·현재가 갱신·재개 감지 보장 | ✅ 완료 |
| 거래정지 재개 스윕 | `_sweep_suspended_resume`(600초 간격): 아무도 추적하지 않는 정지 종목의 거래 재개를 감지해 NORMAL 복원 — 영구 정지 데드락 방지 | ✅ 완료 |
| 매매 유니버스 상폐 제외 (FR-VM-073) | `resolve_live_universe`가 모든 해석 경로 끝에서 `delisted-stocks.json` 등재 종목 제거 — `korea-stocks.json`에 상장 상태 필드가 없어 상폐 67종목이 매매 대상에 남아 있었고, Stock 행이 없으면 FR-VM-066 게이트가 NORMAL로 통과시켰다(KOSPI 836→832, KOSDAQ 1819→1756) | ✅ 완료 |
| 유니버스 id 별칭·토큰 일치 (FR-VM-073) | 시장 판정을 부분 문자열 → `_` 토큰 일치로 교체하고 `_UNIVERSE_ALIASES` 도입 — `KOR_KOSPI200`이 `"kospi200"` 정확일치를 비껴가 KOSPI 전체(836종목)로 해석되던 잠재 결함. 미인식 표기는 확대 대신 폴백 | ✅ 완료 |
| KOSDAQ 150 구성종목 명부 (FR-VM-073) | `backend/engine/kis_master.py` + `scripts/build_index_rosters.py` → `data/kosdaq150-cache.json`(150종목). 출처=KIS 종목마스터 편입 플래그 — KRX(pykrx·FDR·직접)는 `LOGOUT` 거부, KRX Open API는 가격만, 네이버는 KOSPI200만 반환해 유일하게 접근 가능한 소스. 플래그 위치는 실측 특정(KOSPI50⊂KOSPI100⊂KOSPI200 포함관계로 확증). 종목수·형식·시장 소속 검증 실패 시 파일 미기록. `_INDEX_ROSTERS`로 kospi200과 동일 경로 처리 | ✅ 완료 |
| 지수 명부 출처 KIS 단일화 (FR-VM-073) | KOSPI200 명부 소스를 네이버 스크래핑 → KIS 종목마스터로 전환(네이버는 폴백 유지). 전환 후 구성 200종목 **완전 동일**(추가·제거 0건) — 두 소스는 원래 일치했고, 앞서 보고된 26/24건 불일치는 마스터의 무관한 컬럼을 읽은 오독이었음 | ✅ 완료 |
| KOSDAQ150 백테스트 배선 (FR-VM-073) | `parse_universe_markets`를 `(markets, index_top_n)`으로 일반화(kospi200→200, kosdaq150→150)하고 엔진 PIT 시총 게이트가 그 N을 사용. `_load_universe`에 KOSDAQ150 분기, DSL `UniverseSpec.markets` enum에 `KOSDAQ150` 추가. 명부 미확보 시 KOSDAQ 전체 폴백 금지 | ✅ 완료 |
| 지정가 대기 주문 상장상태 게이트 (FR-VM-073) | PENDING 지정가 체결이 가격 조건만 보고 진행돼 접수 후 거래정지·상폐된 종목이 체결되던 구멍 차단. 같은 사이클의 조회 결과 재사용(추가 DB 조회 없음) | ✅ 완료 |
| 테스트 | backend 21개 (test_listing_status.py), frontend 35개 (listing-status.test.ts), API 2개 + 거래정지 동기화/스윕 (test_listing_status_db.py 3개, test_virtual_trader.py 3개, tracked-symbol-filter.test.ts 1개) | ✅ 완료 |

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
| 홈 대시보드 통계 정비 | 계좌별 수익률 차트의 "합산"을 투자금 가중 포트폴리오 수익률로 교체(분모가 다른 퍼센트 단순합 폐기), 손실 계좌 바 빗금 구분, SSR 초기 데이터의 6개월 매도주문 필터 제거(account-monthly API와 동일한 전체 기간 누적 기준). 최근 백테스트 목록에 CAGR·MDD 컬럼 추가 및 미매핑 유니버스 라벨 원문 폴백. 요약바에 총 평가금액 카드 추가, 가상매매 현황 줄의 중복 통계(총 평가금·전체 계좌) 제거 후 자동매매 계좌 수 독립 타일화. 요약바 4개 지표(투자금·평가금액·수익률·수익금)와 계좌 수 배지는 운용중(ACTIVE) 계좌만 집계 — 삭제(CLOSED) 계좌·정산금 제외(가상계좌 목록에는 계속 표시) | ✅ 완료 |
| 포트폴리오 대시보드 | 전체 자산 현황, 수익률 추이, 포지션 분포, 품질 게이지 | ✅ 완료 |
| 요금제 & 플랜 제한 | Free/Pro/Premium 플랜별 계좌당 초기 투자금·가상계좌 수·저장 전략 수·월 백테스트 한도. 계좌는 플랜의 초기 투자금으로 독립 생성(공유 풀 폐기), 계좌 해지 시 금액 미이전. 요금제 페이지(무료 플랜 변경), 내 플랜/사용량 모달·페이지 | ✅ 완료 |
| 구독 시작/종료일 & 롤링 결제 주기 | "구독 시작하기" 결제 완료 시 `User.planStartDate` 기록, "내 플랜" 모달의 종료 날짜는 시작일 기준 롤링 1개월 후로 계산(`currentPlanCycle`). 월 백테스트 사용량 리셋도 이 롤링 주기를 따름 — 미구독자(FREE)는 가입일(`createdAt`)을 주기 앵커로 사용해 모달 시작/종료 날짜에 현재 주기를 표시. 백테스트 횟수 아래 리셋 카운트다운 표시(24시간 이하 "Reset in 5h", 그 외 "Reset in 3 days"). 가상계좌·전략 저장 한도는 주기 리셋 없는 상시 캡 유지. FR-PLAN-010 | ✅ 완료 |
| 토스페이먼츠 자동결제(빌링) 연동 | 유료 플랜(PRO/PREMIUM) 정기 구독 결제 — v2 SDK `requestBillingAuth`(카드 등록창) 기반. 흐름: `/pricing` "구독 시작하기" → `/pricing/checkout?plan=`(자동갱신 조건 고지, `PaymentCheckout`) → 카드 등록창 → `/pricing/success`에서 서버 승인(`POST /api/payment/confirm`: customerKey 대조 → 빌링키 발급 `/v1/billing/authorizations/issue` → 첫 달 청구 `/v1/billing/{billingKey}`) → `planTier`+`planStartDate`+`tossBillingKey`+`nextBillingAt`(+1개월) 갱신. 주문은 `POST /api/payment/order`가 서버 금액(lib/plans.ts)으로 `PaymentOrder`에 기록, 멱등키(orderId)·재승인 멱등 처리. `POST /api/user/plan`은 FREE 다운그레이드만 허용(무결제 유료 전환 차단, 빌링 상태 함께 해제). FR-PLAN-011 | ✅ 완료 |
| 구독 월 자동갱신·해지 | 인-프로세스 스케줄러가 매시 정각 `processDueBillingRenewals`(lib/server/billingRenewal.ts) 실행 — `nextBillingAt` 도래 구독을 빌링키로 자동 청구(갱신도 `PaymentOrder` 기록), 성공 시 예정 시각 기준 +1개월. 실패 시 1일 후 재시도, 연속 3회 실패 시 FREE 전환. 해지는 `POST /api/payment/billing/cancel`이 해지 예약(`subscriptionCanceledAt`)만 기록하고 다음 결제일에 청구 없이 FREE 전환(결제된 기간은 이용 유지). 요금제 페이지에 다음 결제일/자동갱신 해지/만료일 표시. 라이브 전환 시 토스 자동결제(빌링) 계약 필요. FR-PLAN-011a | ✅ 완료 |
| 설정 모달 (계정 삭제·요금제 취소) | 프로필 드롭다운 "설정" → 대형 사이드바 모달(`SettingsModal`) — 검색으로 메뉴 필터, 탭: 계정/결제/사용량. 계정 탭: 로그아웃·이메일 표시·본인 계정 삭제(`DELETE /api/user/account`, soft delete + 빌링 상태 초기화, 활성 자동갱신 구독 시 거부·구독 취소 먼저 안내, 성공 시 로그아웃). 결제 탭: 요금제 헤더(아이콘·월간·다음 갱신/만료일)+요금제 조정 → `/pricing`, 결제 수단(토스 자동결제), 청구서 목록(`GET /api/payment/orders` — 본인 주문, PENDING 제외, DONE=Paid/FAILED=Failed), 요금제 취소(자동갱신 해지 예약, `/api/payment/billing/cancel` 재사용). 사용량 탭: 계좌/전략/백테스트 바+리셋 카운트다운(공용 헬퍼 `planUsageFormat.ts`). FR-USR-005 | ✅ 완료 |
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
| ETF 등 금융상품 언급 시 맞춤 안내 (2026-07-19 오전) | "etf를 사는 전략은 어때?"에 일반 진입 예시(PBR·PER 재무 필터 칩)가 나오던 문제 수정 — ETF엔 개별 기업 재무지표가 없어 가격·추세 기반 예시 칩으로 안내. 같은 날 오후 ETF 정식 유니버스 승격(아래 행)으로 '미지원 안내'는 '지원 유니버스 안내'로 대체됨. SRS FR-STR-022 | ✅ 완료 |
| 상폐 ETF 백필 완료 (2026-07-19) | ETF 유니버스 생존 편향 제거. 조사 실측: FDR KRX-DELISTING의 수익증권 783건은 구식 공모펀드(ETF 브랜드 24건뿐, 펀드 클래스)라 상폐 ETF 소스가 아니며, openapi.krx.co.kr Open API는 증권상품 엔드포인트 미승인(401), data.krx.co.kr는 로그인제("LOGOUT"). 사용자가 KRX_ID/KRX_PW 제공 → `backend/scripts/backfill_delisted_etf.py`가 로그인 세션으로 'ETF 전종목 시세'(MDCSTAT04301)를 2015-01~2026-07 전 거래일(3,012일) 스윕(재개 가능 캐시 data/cache/krx-etf-daily/, gitignore) — 상폐 244종목 발견(parquet 신규 226개, 만기매칭형 채권 ETF 다수 포함). 주의사항 발견: pykrx `get_etf_ticker_list(과거일)`는 현재 상장분의 부분집합만 반환해 상폐분을 못 잡음(2020-02-28 실측 시세화면 451종목 vs 멤버십 350종목) — 전종목 시세 화면 직접 스윕만이 point-in-time. `build_etf_master.py`가 병합(코드 재사용 시 현재 상장분 우선, 152380 실충돌 dedup 검증) → 마스터 1,146→1,390종목(상폐 244 포함). universe_pit `get_delisting_dates` ETF 병합("상장폐지" 라벨)+`etf_master_includes_delisted`(경고 자동 소거, 실제 E2E로 소거 확인). 부수 발견 및 수정: 상폐 포함 전체 ETF E2E 검증 중 `DataLoader`가 ETF에도 무조건 재무 enrichment를 시도해 종목마다 KIS API가 헛되이 실패(500)하던 것을 발견 — `universe_pit.is_etf_symbol` 신설로 스킵, Phase1 16.1s→7.4s 단축+로그 소음 제거. 테스트 4건 추가(상폐 as-of·청산일 맵·ETF 스킵 2건), 백엔드 2,069 전체 통과. 미완: 신규 파케이 226개는 `data/ohlcv/`(git 미추적, 프로덕션 미러 전용)에 로컬 생성만 됨 — `npm run push-data`로 프로덕션 반영 필요(원격 배포라 사용자 확인 후 실행 권장), data/etf-master.json·etf-delisted.json은 git 추적이라 커밋 필요 | ✅ 완료(로컬), 프로덕션 반영 대기 |
| ETF 유니버스 지원 (2026-07-19, FR-STR-067) | ETF를 백테스트 가능한 독립 유니버스로 승격. ① `data/etf-master.json`(FDR ETF/KR 1,146종목 ∩ 로컬 OHLCV 1,140종목, `backend/scripts/build_etf_master.py` 멱등 생성) ② `universe_pit` — `resolve_etf_symbols`(as-of)·`filter_etf_by_theme`(상품명 정확일치 우선→이름 포함)·`extract_etf_theme`(어휘집 없이 **마스터 이름 자기검증 매칭**: "반도체 ETF"→반도체, "KODEX 200"→상품명, "사는 ETF"→무시) ③ 스키마 관통 — `ParsedStrategy.universe`에 "ETF"+`etf_theme` 신설, ETF 단독 정규화 검증기(주식 시장과 미혼합, sector 비움), canonical DSL·`BacktestRequest.etf_theme`(extra=ignore 드롭 함정 선언)·`to_backtest_request`·엔진 ETF 분기(생존편향 경고+테마 필터+**ETF 매도 증권거래세 0**) ④ 유니버스별 팩터 레지스트리 `engine/universe_capabilities.py` — ETF=기업 재무지표 불가(시가총액 포함, 거래대금은 가격 파생이라 허용), 향후 유니버스(미국주식·채권)도 항목 추가로 확장 ⑤ ETF×재무지표 충돌 시 조용한 드롭 금지 — `detect_etf_factor_conflict`(파스 경로, 설명+기술 지표 대안 칩, 정성 언급 포함)·`capability_validator`(인터프리터 경로, 오류+suggested_fixes) ⑥ LLM 계약 — 인터프리터 프롬프트 규칙 6-1·UniverseSpec ETF 정규화·SYSTEM_PROMPT/MODIFY_PROMPT·수정 RAG knowledge(market-universe 문서) ⑦ 빌더 시장 선택지 ETF+가치 전략 배제, 프론트 유니버스/테마 배지 ⑧ `etf_product` 미지원 목록 제거(개념 구현 시 목록 제거 원칙). E2E 실검증: "미국 ETF 골든크로스" → 미국 테마 275종목, 96거래, 2.8s. 테스트: 파서 7·universe_pit 6·capabilities 4·빌더 4·strategy_conversation 3·프론트 2 — 백엔드 2,065·프론트 967 전체 통과 | ✅ 완료 |
| 백테스트 설정 기본값 정확 답변 (2026-07-20, FR-SA-002c-5) | 실사용 사고: 전략 분석실에서 "슬리피지는 몇 %가 기본 값이지?"에 LLM 일반답변이 근거 없는 "0%"를 답함(결정적 분류 cue에 설정 용어가 없어 LLM 폴백 분류→`/query/general` LLM 환각). 수정 3겹: ① `intent/platform_defaults.py` 신설 — 설정 용어(슬리피지·수수료·거래세·초기자금·체결 시점)+값 질문 cue 결정적 감지(`is_default_question`, 값 변경 명령형은 제외), 답변 값은 하드코딩 없이 SOT(ParsedStrategy 필드 default·`MIN_INITIAL_CAPITAL`·시뮬레이터 `DEFAULT_SELL_TAX_RATE`)에서 읽어 드리프트 방지, 수수료 질문엔 매도 거래세(ETF 0%) 동반 안내 ② 분류기 결정 규칙 0-a(전략 키워드 게이트보다 먼저)+`_FINANCE_CUE`에 설정 용어 추가 ③ `generate_general_answer`가 기본값 질문이면 LLM 전에 결정적 답변(LLM 미가용에도 동작), 개념 질문("슬리피지가 뭐야?")에는 실제 기본값 사실 블록을 LLM 프롬프트에 주입(`facts_block`), 수정 오라우팅 백스톱(primary)의 질문 판정에도 cue 추가. 실사용 교정 2건 — '설정 패널' 같은 화면은 없으므로 답변·사실 블록 모두 채팅 요청으로 변경 안내(예: "슬리피지를 0.1%로 바꿔줘"), 직전 답변에 이어지는 설정 용어 단독 후속 질문("수수료는?")도 결정적 감지(`_BARE_TERM_QUESTION`). 테스트 28건(test_platform_defaults.py) — 백엔드 2,125·프론트 1,001 전체 통과 | ✅ 완료 |
| 단일/지정 종목 백테스트 (2026-07-20, FR-STR-068) | "삼성전자에 골든크로스 전략을 적용해줘"처럼 특정 종목+전략 언급을 유니버스 백테스트와 분리된 단일 종목 모드로 실행. ① `ParsedStrategy.target_symbols` 신설 — 종목명·별칭·6자리 코드→코드 해석은 LLM이 아닌 결정적 추출(`_extract_target_symbols`, symbol_resolver 정본), 문맥 가드(같은/처럼/속한/업종/관련주/빼고 등)로 업종 서술·예시·제외 발화의 오폭 차단(종목질문 리다이렉트·빌더 합성 문구 보호) ② symbol_resolver 경계 확장 — 조사 '에/로/으/의/만/과/랑' 인정+코드 뒤 한글 조사(\b 유니코드 함정 → lookaround), "삼성전자에"/"005930에"/"하이닉스로" 인식 ③ `to_backtest_request` — symbols=[지정 코드]·universe_id=None(엔진 PIT 재해석·섹터 필터 미적용, 기존 계약 재사용)·position_size 100/n·ranking_enabled=False·backtest_mode/target_stocks(표시용 이름) ④ 청산 누락 추천 보정(`apply_single_asset_adjustments`, `_build_parse_result` 공유) — 크로스오버 계열은 반대 신호 청산 추천 적용+notices, 그 외는 '기간 종료까지 보유' 안내(조용한 임의 실행 금지); 덕분에 지정 종목+기술 진입 단독도 룰 fast-path 유지 ⑤ 복수 종목 언급 시 임의 선택 없이 기존 clarification 채널로 되묻기(`detect_symbol_ambiguity`) ⑥ 수정 경로 — 종목 교체(별칭 표면형 잔여 차감으로 fast-path 유지)·명시적 시장/업종 전환 시 지정 해제·무관 수정 시 보존(`_target_change_from_utterance`, 섹터 ⑥/⑦과 동형 3지점 배선) ⑦ canonical DSL에 target_symbols 포함(빈 값 키 제거로 기존 해시 불변, 종목별 다른 strategy_id)+`BacktestRequest.backtest_mode/target_stocks` 선언(extra=ignore 드롭 함정) ⑧ 프론트 — 유니버스 배지 대신 '삼성전자 (005930)' 종목 배지('대상 종목' 라벨), '단일 종목 집중 투자' 표기(파싱 카드·실행 요청·저장 DSL 요약) ⑨ 종목질문 리다이렉트에 단일 종목 백테스트 예시 추가 ⑩ Primary 인터프리터 경로 배선(당일 버그 수정) — `run_primary_parse`가 컴파일 후 결정적 target 오버라이드(`_override_target_symbols`, 날짜 오버라이드와 동형)+지정 종목 시 유니버스형 청산 되묻기 억제(④ 보정이 처리), 분류기에 종목명+'테스트' 결정 규칙 추가(LLM 폴백의 STOCK_ANALYSIS 리다이렉트 오분류 방지). E2E 실검증: 삼성전자 골든크로스 3Y → 23거래. 테스트: 백엔드 신규 23(test_single_asset_backtest.py)+4(primary/분류기 회귀)·프론트 6 — 백엔드 2,096·프론트 1,001 전체 통과 | ✅ 완료 |
| 미제공 기능(뉴스 분석) 요청 안내 (2026-07-12) | "최근 뉴스가 좋은 종목을 사는 전략을 만들어줘"처럼 플랫폼에 없는 데이터 기능(뉴스·공시·SNS 여론) 기반 요청이 '전략' 키워드로 STRATEGY_ADVICE에 새서 빈 전략 파싱→**빌더 자동 진입**("어떤 시장을 대상으로 할까요?")으로 이어지던 문제 수정. `QueryIntent.UNSUPPORTED_FEATURE` 신설 — 결정적 게이트(`intent/scope.py::is_unsupported_feature_request`)가 뉴스 단어+선정/전략 맥락을 잡아 미제공 안내+다른 아이디어 유도로 응답, 프론트는 빌더·파싱을 호출하지 않고 안내만 표시. 지원 지표 혼합 요청·정의형 질문·종목명+행동 질문은 가로채지 않음(기존 흐름 유지), 긴 꼬리는 LLM 폴백 분류로 위임. nl_parser 미지원 개념 목록에 "news"(호재/악재, 뉴스·공시가 조건으로 쓰인 경우만 — flavor 언급은 결정적 파싱 유지) 추가로 혼합 요청 notice 배선. 테스트 `test_intent_classifier.py`(감지 5·혼합 3·경계 3)+`test_nl_parser_overrides.py`(news notice)+`page.unsupported-feature.test.tsx`(빌더 미진입 회귀). SRS FR-SA-002c-2 | ✅ 완료 |
| 손절·트레일링 표기 마이너스 통일 (2026-07-30, FR-STR-030b) | 사용자 지적: 같은 요약 카드에서 매도 조건은 "손절 -8% 하락시 매도", 리스크 관리는 "손절 8%"로 표기해 방향이 드러나지 않았다. 값은 하락 폭 **크기**로 저장(양수 정규화)되므로 **표기 시점에만** 부호를 붙인다 — 프론트는 단일 포매터 `formatDownsidePercent`(`lib/strategy-summary.ts`)를 두고 진행 요약 카드·파싱 카드 배지·결과/저장 `riskText` 4경로에 배선, 백엔드는 빌더 확인·삭제 안내와 인터프리터 복창(`responses.py`)에 적용. 트레일링 스탑도 하락 방향이라 함께 부호를 붙였다. **선택지 칩도 같은 표기**로 통일(`strategy_slots.py` 슬롯 칩, 빌더 청산 칩, `conversationDecision.ts` 수정 칩, planner 프롬프트 칩 예시) — 부호는 표기일 뿐이라 칩 결속(`_bind_chips`→`_apply_prompt_overrides`)·프론트 `parseFirstNumber`·빌더 청산 파서가 모두 "-10%"→`10.0`으로 크기를 뽑는 것을 실측 확인했다. 방향이 문구에 있는 라벨("최고가 대비 10% 하락 시 청산")·익절·MDD·크기 범위 검증 메시지는 불변. UI 칩 계약 게이트(`test_strategy_ui_exposes_only_suggestions_covered_by_backend_contract`)가 새 칩 표기의 백엔드 적용을 강제한다. 회귀 6건 추가·갱신, 프론트 1,291·백엔드 3,045 전체 통과, `qa_builder_fuzz.py` 빌더 스텝 15,197턴 0실패 | ✅ 완료 |
| 섹터 재귀속 96건 판정·적용 (2026-07-30) | 3자 교차 검증(현행/DART 코드/네이버)이 낸 불일치 96건을 종목마다 판정. **코드가 항상 옳지 않아** 자동 적용 불가 — 전이 유형(현행→코드) 단위 규칙 + 개별 예외로 표현했다(`scripts/sector_reassignment_2026_07_30.py`). **APPLY 63건** — 사명 부분 문자열 오매칭 피해자 다수: 이지바이오→사료, 바이오포트·우리바이오→식품, 셀바이오휴먼텍→패션, 에스디바이오센서 등 5곳→의료기기, 메가스터디교육→교육, 금호석유화학→화학, HMM·팬오션→해운, 크리스에프앤씨→패션, 금호전기→가구/인테리어. 역방향 2건도 잡았다 — 에스피시스템스(기계/장비→**로봇**, KSIC 29280 산업용 로봇으로 정확히 등록됐는데 사명에 '로봇'이 없어 규칙에도 안 걸렸다), 해성에어로보틱스(로봇→화학, 사명 '로보틱스'로 잘못 잡혔다). CUSTOM 1건 — 아모레퍼시픽홀딩스(화학/화장품 둘 다 아님 → 지주회사). **KEEP 33건** — 코드를 따르면 퇴행하는 것들을 사유와 함께 `OVERRIDDEN_SYMBOLS`에 고정: 로봇 19곳(KSIC 2928 등록 상장사가 거의 없어 292로 흩어짐 — 코드 따르면 로봇 유니버스가 빈다), 리츠 2곳(등록은 신탁업), 창투사 5곳(649가 지주사와 섞임), 반도체 장비 2곳, 사업지주 3곳, 비상교육. 예외 등록이 핵심 — 안 하면 감사 리포트에 96건이 영원히 남아 다음 사람이 같은 판정을 반복한다. 결과: **검토 대상 96 → 0건**(의도적 오버라이드 81). 부수 수정: `test_kg_membership_covers_delisted_and_preferred_shares`가 매직 넘버(72)를 박아 정당한 재귀속에 깨졌다 → 'KG 소속 == 파일 병합 결과' 불변식으로 교체(같은 회귀를 그대로 잡으면서 견고). 백엔드 3044 passed. SRS FR-STR-066 ⑬ | ✅ 완료 |
| 섹터 소속 정본을 KG로 전환 (2026-07-30) | 인터프리터가 지식을 찾는 곳은 KG인데 섹터 소속이 `korea-stocks.json`에만 있어 그래프로 "이 섹터에 어떤 종목이 있나"를 답할 수 없었다(`related_universe('원자력')` → `{}`, sector↔company 엣지 0개). **KG를 정본으로 전환**: `company -belongs_to→ sector` 엣지 3,242건을 `data/kg-sector-membership.json` 오버레이로 편입하고(손 큐레이션 시드는 깨끗하게 유지 — `theme_catalog`·`learned`와 같은 관례), `universe_pit._load_sector_map`이 KG를 읽는다. `korea-stocks.json`의 `sector`는 파생 캐시로 강등(참조부 71곳 호환, 드리프트 테스트로 고정). 작업 중 잡은 회귀 3건: ① 순환 재귀(`_load_sector_map` → `get_graph` → `_sector_node` → `_load_sector_map`) — 섹터 노드의 member_count가 오버레이를 직접 세도록 분리 ② 상폐 종목 누락으로 생존 편향 재발(에너지/원자력 72→66) — 상폐 마스터에서 이름 공급 ③ 우선주 모주 섹터 상속 누락(다시 72→66) — 오버레이 생성 시 상속을 구워 넣음. 병합 규칙은 `universe_pit.sector_map_from_files` 단일 구현(빌더·부트스트랩 폴백 공유). 직전 커밋의 '섹터↔종목 엣지 금지' 테스트는 정본 전환으로 대체됐다. KG 노드 3,919 / 엣지 12,971 / 검증 경고 0. SRS FR-STR-070 ⑦-2 | ✅ 완료 |
| 섹터 분류 근거를 KSIC 코드로 전환 (2026-07-30) | **사명 문자열 매칭이 근본 원인이었다.** `get_sector_from_industry`가 업종 문자열+사명을 이어붙여 키워드 부분 문자열 매칭 → 메"가스"터디교육이 '가스'에 걸려 에너지/원자력, 사명에 '바이오'만 있으면 동물사료·섬유가 바이오/제약(실측 13건). `OVERRIDDEN_SYMBOLS` 63건도 이를 손으로 덮은 결과. **DART 기업개황 `induty_code`를 전 종목 백필**(2,655/2,655, 실패 0)해 코드 기반으로 전환. KRX 문자열은 3자리까지만 주지만 DART는 5자리 — 화장품 제조업(20423)·표시장치 제조업(2621)이 별도 코드로 **존재**한다(앞선 작업에서 '코드가 없다'고 본 것은 KRX 문자열만 봤기 때문). `engine/ksic_sectors.py` 190항목·최장 접두 매칭, 커버리지 98%·현행과 92% 일치. 판정 순서: 개별 오버라이드 → 로봇(사명) → KSIC 코드 → 키워드 폴백. **사명 선점은 로봇만** 남기고 `test_name_matching_is_limited_to_robot`이 재발을 막는다. 3자 교차 검증 도구 `scripts/audit_sector_sources.py`(현행/DART/네이버) — 검토 대상 96건은 자동 교정하지 않고 목록만. 테스트 `test_ksic_sectors.py` 19건. SRS FR-STR-066 ⑬ | ✅ 완료 |
| 여행·레저 섹터 신설 (2026-07-30) | 묶음 섹터 전수 감사에서 발견 — `MAPPING_RULES["미디어/엔터"]`에 관광·숙박·카지노 어휘가 들어 있어 하나투어·모두투어·강원랜드·파라다이스·GKL·아난티 12곳(94종목의 13%)이 **미디어 업종**으로 분류되고 있었다. **여행**(여행사 6)·**레저**(숙박 3 + 카지노·유원지 3)로 분리. KSIC는 세 갈래로 갈리지만 여행사=중개업 / 숙박·카지노=시설 운영이라는 사업 모델 기준으로 둘로 묶었다(사용자 결정). 재귀속은 종목 목록이 아니라 **KSIC 코드 단위 규칙**(`scripts/reassign_by_industry.py`, 멱등)이라 신규 상장분도 자동 반영. 동의어는 '관광'→여행, '호텔·리조트·숙박'→레저만 등록 — **'카지노'·'여행사'는 제외**했다(KG 큐레이션 개념 `casino`·`travel-agency`를 가리기 때문, FR-STR-070 ③). 미디어/엔터 구성 안내도 관광 언급 제거로 갱신. `CANONICAL_SECTORS` 47→49. SRS FR-STR-066 ⑫ | ✅ 완료 |
| 디스플레이/부품 교정·분할 (2026-07-30) | 이름과 내용이 어긋나 있던 섹터. 132종목 중 131개가 KSIC '전자부품 제조업' 한 코드라 **디스플레이 부품이 아니라 전자부품 통짜 바구니**였다 — PCB(대덕전자·심텍)·MLCC(삼성전기)·카메라모듈(LG이노텍)·안테나(아모텍)·반도체 부자재(에스앤에스텍·리노공업)·이차전지 동박(롯데에너지머티리얼즈)까지 포함. ⓐ **오등록 5종목 이관** — 파미셀→바이오/제약, 두산→지주회사, 한화시스템→우주항공/방산, 알에스오토메이션→로봇, 캐프→자동차부품(KSIC도 '자동차 신품 부품'). 겸업·불확실 건(엠투엔·바이오스마트·시노펙스·HLB이노베이션)은 근거를 만들 수 없어 보류. ⓑ **분할** — 디스플레이 25 / 전자부품 109. 귀속 근거는 개발자 판단이 아니라 **외부 큐레이션 카탈로그**(네이버·주달 디스플레이 테마 ∩ 이 섹터 = 20종목) + 카탈로그 누락 5종목 명시 보강(`DISPLAY_SYMBOLS`, 종목마다 사유 기재). `test_display_membership_is_catalog_grounded`가 근거 목록과 데이터 일치를 강제한다. KG 엣지 2건(mlcc·pcb)도 sector:전자부품으로 재지정. `IT 하드웨어`와 중복 없음(그쪽은 통신·방송장비·정밀기기·컴퓨터·전선). SRS FR-STR-066 ⑪ | ✅ 완료 |
| 묶음 섹터 구성 고지 + 화장품 분류 교정 (2026-07-30) | ① **좁힘 감지 수정** — '원자력 업종만'이 안내 없이 에너지/원자력 72종목(정유·도시가스 포함)으로 넓어지던 기존 결함. `is_narrow_sector_approximation`이 '표현이 정본명 글자 안에 있으면 이름 표기 차이'로 판정해 False를 내던 것을, **매핑 결과가 묶음 섹터면 항상 True**로 바꿨다(원자력·미디어·기계·철강·디스플레이 모두 감지). 이제 기존 배선이 카탈로그 테마를 먼저 확인해 '원자력발전'(50종목)·'원자력발전(SMR)'(11종목) 후보로 이어진다. ② **구성 안내** — 카탈로그 후보가 없으면 섹터로 확정하되 무엇이 함께 들어 있는지 고지한다(`SECTOR_COMPOSITION_NOTES` 10쌍 + `sector_composition_notice`). 사람이 구성 한 줄을 쓰고 결정론이 종목 수를 채운다 — KSIC 코드명('전동기, 발전기 및 전기 변환·공급·제어 장치 제조업')을 노출하지 않으면서 LLM 환각 여지도 없다. 묶음 성격에 따라 문구 3유형(진짜 혼재 7 / 사실상 한쪽뿐 1 / 두 낱말 같은 분류 1). ③ **화장품 분류 교정** — KSIC에 화장품 코드가 없어 화장품사가 전부 '기타 화학제품 제조업'→화학에 있었고 '화장품/패션' 46종목에 화장품 기업이 **0개**였다(화장품 업종 백테스트 = 섬유·의류만). 브랜드·ODM 29종목을 귀속(원료·소재사는 화학 유지). 이로써 화장품 기업이 실재하게 돼 화장품/패션도 분할 가능해졌다 — 화장품 31 / 패션 53으로 독립. `scripts/apply_sector_overrides.py`(멱등)가 OVERRIDDEN_SYMBOLS와 korea-stocks.json 드리프트를 맞춘다. 테스트 `test_sector_composition_notice.py` 38건 + `test_sector_split.py` 보강. SRS FR-STR-066 ⑨⑩ | ✅ 완료 |
| 묶음 섹터 분할 — 'A/B' 섹터를 독립 유니버스로 (2026-07-30) | `에너지/원자력`·`미디어/엔터`처럼 두 업종을 한 섹터에 묶어두면 한쪽만 대상으로 하는 전략을 만들 수 없던 문제. 18개 묶음 섹터 중 **KSIC 산업분류가 두 갈래를 깨끗하게 가르는 6쌍만** 분할했다 — 증권/보험→증권·보험, 은행/금융지주→은행·금융지주, 조선/해운→조선·해운, 식품/음료→식품·음료, 소프트웨어/플랫폼→소프트웨어·플랫폼, 사료/축산→사료·축산, 화장품/패션→화장품·패션, 디스플레이/부품→디스플레이·전자부품 (`CANONICAL_SECTORS` 39→47, 872종목 재분류). 나머지 10쌍은 **의도적 보류** — 분류 데이터가 구분을 주지 않거나(에너지/원자력: KSIC에 원자력 코드가 없고 66종목 중 37개가 '전동기·발전기 제조업' 한 코드에 몰려 있음. 미디어/엔터: 최대 코드 '영화·방송프로그램 제작'이 양쪽 어디에도 안 붙음) 두 낱말이 포함·동의 관계다(철강⊂금속, 기계≈장비, 디스플레이/'부품'). 근거 없는 종목 귀속을 만들지 않기 위해 남겼고, 회귀 테스트가 임의 분할을 막는다. **하위 호환**: 구 묶음명이 들어오면 신규 두 섹터의 합집합으로 편다(`expand_legacy_sector` — `filter_by_sector`·`normalize_sector_value`·universe_resolver·capability_validator 4경로 배선) → 저장된 전략·백테스트 이력·PIT 유니버스 스냅샷이 그대로 재현된다. 두 데이터 파일의 industry 어휘가 달라(korea-stocks=KSIC 정식명 '보험업', stock-master=거래소 축약 '보험') 별도 매핑 테이블을 쓴다 — 한 테이블로 처리하면 상폐 보험사가 증권으로 넘어간다(실측). 마이그레이션 `scripts/split_combined_sectors.py`(멱등, dry-run 기본). prod DB 마이그레이션 불요 — `Stock.sector`(Postgres)는 KIS 프로파일 어휘라 유니버스 선정에 쓰이지 않고, 정본은 커밋·배포되는 JSON이다. 테스트 `test_sector_split.py` 40건. SRS FR-STR-066 ⑧ | ✅ 완료 |
| 상폐 종목 섹터 백필 — 섹터 유니버스 생존 편향 제거 (2026-07-12) | 섹터 분류 SOT(korea-stocks.json)가 현재 상장만 커버해 섹터 백테스트("반도체 관련주")에서 기간 중 상폐된 종목이 통째로 빠지고, 매 실행마다 생존 편향 경고가 출력되던 문제 해소. FDR KRX-DELISTING의 KRX 구 산업분류 단축명(474/474 커버)을 `sector_mapper.get_sector_from_krx_industry`로 정본 섹터에 매핑해 stock-master.json 상폐 엔트리에 industry/sector 백필(`scripts/backfill_delisted_sectors.py`, 멱등) + `build_stock_master.py` 재빌드 경로에도 동일 로직 통합(유실 방지). 단축 어휘는 KSIC 전체명 기준 키워드 매핑이 체계적으로 어긋나('전기·전자'→통신/유틸리티, '기계·장비'→IT 하드웨어, '금속'→화학, 기타 제조업 203건) 전수 감사 기반 오버라이드 테이블(`KRX_SHORT_INDUSTRY_OVERRIDES`) 신설 — 스팩('금융' 159건)은 현재 상장 스팩 관례(증권/보험)와 일관. `universe_pit._load_sector_map`이 마스터(상폐)+korea-stocks(현재 상장, 우선)를 병합하고 우선주는 모주(prefix+'0') 섹터 상속(미상 113→0). 경고는 상시 출력 대신 업종 미상 '상폐' 종목이 실제로 남을 때만(`sector_unknown_delisted`) 개수와 함께 고지. 실데이터 검증: PIT 3061종목 미상 0, 반도체 87(상폐 10 포함)·바이오 240(상폐 12)·건설 81(상폐 12). data/stock-master.json은 git 추적+prod compose `./data` 마운트라 커밋·배포로 프로덕션 자동 반영(prod checkout clean·상폐 sector 0 확인함). 테스트 `test_sector_mapper.py`(단축 어휘 3건)+`test_universe_pit.py`(병합·우선순위·우선주 상속·경고 대상 5건). SRS FR-STR-066 ④-1 | ✅ 완료 |
| 후속 질문 대화 맥락 분류 (2026-07-12) | 종목 질문 전환 안내가 전략 예시를 보여준 직후 "다른 예는 없어?"라고 물으면 문장만 보면 투자 신호가 없어 LLM 폴백 분류가 OFF_TOPIC으로 오판 → 역할 밖 거절 문구가 나가던 사고 수정. 프론트(`app/analytics/new/chatHistory.ts::selectClassifierHistory`)가 이번 입력 이전의 최근 대화 턴(기본 6턴, 로딩·빈 메시지 제외, 500자 절단)을 `history`로 분류(`/query/classify`)·일반 답변(`/query/general`) 호출에 함께 전송. 백엔드는 `ChatTurn` 스키마 신설, LLM 폴백 분류(`_classify_with_llm`)가 `[대화 맥락]`/`[최신 입력]` 구분 프롬프트(+후속 질문 판단 규칙: 직전 주제가 투자면 OFF_TOPIC 금지, 예시 추가 요청은 GENERAL_INVESTMENT)로 분류하고, `/query/general`도 같은 맥락(`format_history_context`, 턴당 240자·6턴 상한)을 받아 직전 답변과 겹치지 않게 이어 답함. 결정적 규칙은 현재 입력만 봄(맥락이 있어도 명백한 역할 밖 질문은 거절 유지). 테스트 `test_intent_classifier.py`(맥락 전달·무맥락 보존·결정적 불변·절단/상한·general 메시지 6건)+`chatHistory.test.ts`(헬퍼 4건)+`page.classify-history.test.tsx`(후속 질문 body 회귀). SRS FR-SA-002c-3 | ✅ 완료 |
| 검증 교정 환각 AI 신호 주입 차단 + 백테스트 워치독 | 실사고(2026-07-03): 사용자가 AI를 언급하지 않은 KOSDAQ 모멘텀 랭킹 프롬프트에 Parse Fidelity Validator의 `correctedStrategy`가 `ai_model`("AI 매수 예측") 진입 신호를 환각 주입 — 스키마 검증만 통과하면 그대로 적용되던 구멍. 비활성화된 AI 백테스트가 실행되며 행(hang), SSE 스트림은 상태 메시지 무한 방출. **수정 4중**: ① `_maybe_apply_correction`이 교정본 진입/청산 신호를 LLM 본경로와 동일한 `_validate_signals`로 재검증(환각 신호만 드롭, 정상 교정 유지) + 검증 프롬프트에 신호 추가 금지 규칙(FR-STR-020b) ② `NL_PARSER_CACHE_VERSION` 3→4(오염 캐시 무효화) ③ 엔진 AI fail-fast — `AI_SIGNALS_ENABLED=0` 운영 스위치 거절 + AI 모델 로드 불가 시 0거래 침묵 진행 대신 즉시 에러(FR-BT-048) ④ 백테스트 워치독 `engine/watchdog.py` — `/backtest`(504)·`/strategy/backtest-stream`(SSE error 이벤트)이 `BACKTEST_TIMEOUT_S`(기본 600초) 안에 반드시 종료(FR-BT-047). 테스트 `test_parse_validator.py`(환각 스트립/정당 AI 유지), `test_backtest_watchdog.py`(타임아웃/전파/게이트 2종) | ✅ 완료 |
| 백테스트 엔진 감사(2026-07) 수정 | 퀀트 관점 전면 감사에서 발견된 결과 왜곡 요인 일괄 수정. **체결 충실도**: ① `from_signals(size_type='Percent')`의 '잔여 현금 비중' 의미론이 동시 진입 비중을 기하급수 감소시키던 문제 → 커스텀 루프가 의도(슬롯·스탑·리밸런싱)를 결정하고 `from_orders(targetpercent)`가 NAV 대비 목표비중으로 체결(이중 부기 해소, C1/C7) ② 정수 주 단위 체결 `size_granularity=1`(C2) ③ SL/TP/트레일링을 장중 low/high로 감지(종가 감지는 장중 리스크 누락, C5) ④ 거래정지일 청산은 다음 거래 가능일로 이월 `pending_exit`(C6) ⑤ 매수/매도 수수료 분리 + 매도 증권거래세 기본 0.15% `sell_tax_rate`(H3). **통계 무결성**: PF 클램프(10)·buy-and-hold 재정의 제거(C3), Sortino 표준 하방편차(전 기간 target-below RMS)+`risk_free_rate` 옵션(H4/M7), Exposure·MDD Duration·Expectancy·Recovery Factor 추가. **유니버스/신호**: 진입조건 없는 모멘텀 랭킹이 유동성 게이트·대형주 마스크를 덮어쓰던 버그(C4)+next_open 시 시총 마스크 1일 shift(look-ahead), 지표 최대 기간 기반 동적 warm-up(H6), 사유 부분문자열 매칭 제거(M5), loader 중복날짜/정렬 가드(M10). **공시 경고 채널**: 거래세 반영·소표본(<30건)·벤치마크 상장 전 구간·분배금 미반영·정적 주식수 근사·AI 학습기간 중첩(model_meta `train_end`)·리밸런싱 비중 미리셋·전일 거래대금 초과 매수(시장충격). WFE는 IS≤0이면 `wfe_valid=false`(M9). 결과 변경으로 `BACKTEST_ENGINE_VERSION`="audit-fixes-v4" 범프. 테스트: `test_audit_fixes.py`(PF/통계/Sortino/warm-up/모멘텀 유동성/경고) + `test_engine_simulator.py`(NAV 동일비중/정수주/거래세/장중 SL/이월) — 백엔드 1583·프론트 608 전체 통과, 실데이터 스모크(5종목 SL 혼합·순수/혼합 리밸런싱) 검증. **프론트 표시**: 신규 통계 4종을 `BacktestResult` 타입 + 매퍼 3곳(`backtestResultMapper.ts`·`BacktestService.ts`·`app/analytics/[id]/page.tsx` — [id] 재실행 경로는 누락돼 있던 calmar/avgHoldingDays도 함께 배선)에 매핑하고, `BacktestDashboard` '리스크 및 성과 분석' 섹션에 둘째 행(시장 노출도·최장 낙폭 기간·기대값·회복 계수)으로 설명 툴팁과 함께 표시. 매퍼 단위 테스트 2건 추가(`backtestResultMapper.test.ts`) | ✅ 완료 |
| 유니버스에서 스팩(SPAC) 종목 배제 (2026-07-21) | 리밸런싱·랭킹 유니버스에 스팩(기업인수목적회사)이 섞여 들어갈 위험을 사전 차단해달라는 요청. 조사 결과 스팩은 종목마스터·유니버스 어디서도 걸러지지 않고 그대로 포함돼 있었음(리츠와 달리 배제 로직 부재, 섹터 매퍼는 '증권/보험' 분류 근거로만 언급). 실제 백테스트/랭킹/리밸런싱이 공유하는 유일한 유니버스 해석 지점 `engine/universe_pit.resolve_symbols`에 `_is_spac`(종목명에 "스팩" 포함 여부, 리츠 접미사 판정과 동형 패턴 — 실측 232개 전량 이 패턴, 오탐 없음)을 적용해 배제. 캐노니컬 DSL·종목 수 추정 경로(`strategy_converter._load_universe`, KOSPI200 네이버 스크래핑 실패 시 KOSPI 전체 폴백 포함)에도 동일 필터를 적용해 추정치와 실행 결과가 어긋나지 않게 함. 단일/지정 종목 백테스트(FR-STR-068, 사용자가 종목을 직접 지정하는 경로)는 유니버스 해석을 거치지 않아 이 필터의 영향을 받지 않음(의도된 범위 — 사용자가 스팩 종목코드를 직접 지정하는 것까지 막지는 않음). 테스트 `test_universe_pit.py`(스팩 종목 배제·이름 패턴 판정 2건 추가) — 백엔드 2,179·프론트 1,014 전체 통과. SRS FR-VM-067 | ✅ 완료 |
| 지정 ETF 상품을 열린 테마처럼 되묻던 문제 수정 (2026-07-21) | "kodex 반도체 etf를 매수"처럼 이미 특정 ETF 상품(KODEX 반도체, 091160)을 지정한 발화에 `nl_parser.detect_missing_entry_clarification`의 ETF 진입조건 되묻기가 여러 ETF 중 고르는 것처럼 읽히는 일반 문구(`_ETF_PRODUCT_QUESTION`, '정기 리밸런싱' 등 언급)를 그대로 써 사용자가 "또 어떤 ETF를 살지 되묻는다"고 오인하던 버그 수정. 조사 결과 하위 파이프라인(DataLoader·backtest_engine)은 이미 심볼 무관(ETF/주식 동일 처리)이라 문제는 순수히 되묻기 문구 선택 로직에 있었음. `universe_pit.resolve_single_etf_product` 신설 — `etf_theme`이 ETF 마스터 이름과 정확히 일치하면(테마 키워드의 부분 매칭과 구분) 해당 마스터 항목 반환. `detect_missing_entry_clarification`이 이를 이용해 단일 상품이면 상품명·종목코드를 확정해 보여주는 전용 문구(`_ETF_SINGLE_PRODUCT_QUESTION`, 리밸런싱 언급 제거)로, 열린 테마("반도체")면 기존 일반 문구를 유지한다. 테스트 `test_universe_pit.py`(`resolve_single_etf_product` 3건)+`test_nl_parser_overrides.py`(단일 상품 확정 문구·열린 테마 유지 2건) — 백엔드 전체(2,248건, AI/서버 의존 제외) 통과. SRS FR-STR-022 | ✅ 완료 |
| 명확화 되묻기 칩 노출 중 채팅 입력창 노출 (2026-07-21) | 위 ETF 되묻기 수정 후, 사용자가 스크린샷으로 지적: 예시 칩("직접 입력" 포함)과 자유 입력창이 동시에 보이면 "직접 입력" 칩을 눌러야 하는 이유가 불분명하고, 열린 입력창이 마치 선택을 무시한 채 또 물어보는 것처럼 오인된다(빌더 옵션 칩엔 이미 이 규칙이 있었으나 일반 명확화 되묻기 칩엔 없었음, FR-SA-002c). `chatNavigation.shouldShowChatInputBox`에 `clarificationAwaitingChoice`(마지막 어시스턴트 메시지에 `clarification`+`clarificationSuggestions`가 있으면 true) 추가, 기존 `builderAwaitingChoice`와 동일하게 처리(칩 노출 중엔 입력창 숨김, "직접 입력" 클릭 시 `builderFreeTextRequested` 토글로 재노출). `hasRespondedMessage` 판정에도 `clarification`을 포함(이전엔 clarification-only 메시지가 '응답 없음'으로 오판되던 잠재 결함). 예시 칩이 없는 되묻기(자유 서술만 가능)는 그대로 입력창 유지. 테스트 `chatNavigation.test.ts`(2건 추가) + 기존 `page.scroll.test.tsx` 회귀 테스트 1건을 새 동작(칩 노출 중 textbox 부재 → 클릭 후 등장)에 맞게 갱신 — 프론트 전체(1,017건) 통과. SRS FR-SA-002c | ✅ 완료 |
| 익절 오타('익설') 수정 요청 미해석 오안내 수정 (2026-07-21) | 스크린샷 사고: "30% 익설 설정해줘"(익절 오타)를 인터프리터가 올바르게 익절 30%로 해석해 전략 요약에 반영했음에도, 결정적 환각 게이트(`strategy_conversation/primary.py::_patch_cue_supported`)가 정규화된 원문에서 `익절`류 cue를 문자 그대로 못 찾아 패치를 거부 → "요청을 전략 변경으로 해석하지 못해 전략을 유지했다"는 모순된 안내가 함께 표시됨. 원인은 `engine/nl_parser.py`의 흔한 오타 보정 테이블(`_TYPO_CORRECTIONS`)에 이미 있던 `손졀→손절`·`익졀→익절`과 달리 `익설→익절`이 빠져 있던 것 — 모든 결정적 추출기와 위 게이트가 공유하는 단일 정규화 지점(`_compact`)이라 항목 추가만으로 양쪽 다 해결. 테스트 `test_nl_parser_overrides.py::test_typo_take_profit_iksul_variant` 추가 — 백엔드 전체(2,249건, AI/서버 의존 제외) 통과 | ✅ 완료 |
| 단일 종목 연구 프로파일 + 프로파일 기반 대화 (2026-07-24, FR-STR-068b) | 단일 종목 지정 시 종목을 티커로만 다루지 않도록 결정론 사전 분석 계층 신설. ① `engine/stock_profile.py` — `StockProfileService`가 OHLCV parquet(수정주가·기업행사 보정 `DataLoader.preprocess_data` 재사용)에서 `StockResearchProfile`(frozen dataclass: 커버리지·설명 통계·신호 발생 빈도·지원/미지원 피처·품질 경고)을 결정론 계산. 신호 통계는 고정 격자(RSI 20/25/30·70/75/80 교차, 골든크로스 5/20·10/60·20/120, MACD, 볼린저 상/하단, 돌파 20/60/120, 거래량 3배 급증, 60일 고점 -10%, CCI, 스토캐스틱)의 발생 횟수+연간 빈도만 — 수익률 기준 사후 최적값(best_value)은 계산·저장 금지(과최적화 방지). 계산 불가 필드는 null(시장지수 상관 등 — 지수 시계열이 데이터셋에 없음), 수급·공매도·실적발표일 등 파이프라인 부재 데이터는 `unsupported_features`로 정직 노출. 재무는 parquet 병합이 이미 PIT-safe(OpenDART available_from/결산+90일)라 `point_in_time_safe=true`+커버리지 산출 ② 캐시 — `data/cache/stock_profiles/{symbol}.json`, fingerprint(parquet mtime+size)+PROFILE_VERSION 무효화, 섹션별 fingerprint 기록(향후 소스 분리 시 부분 갱신), 메모리 캐시 공유(프로세스 전역 서비스). 실측 빌드 0.4s/캐시 0ms ③ `engine/stock_question_templates.py` — 질문 템플릿이 required_features·minimum_signal_count·advanced를 선언, `select_stock_questions`가 프로파일 근거로 노출/제외(이유 필수)/희소(10회 미만)·과다(연 30회 초과) 경고를 결정. 재무(PBR/PER/배당수익률)는 advanced(당시 값 시계열 신호)로만 — 기본 노출 안 함. 횡단면 선별 질문은 템플릿에 아예 없음 ④ 파스 흐름 배선 — `engine/single_asset_review.py::review_single_asset_strategy`를 `_build_parse_result`에 연결: 진입 신호를 격자에 근사('유사 조건 기준' 명시)해 희소/과다 경고, 재무 조건 미보유 시 '지원 불가+기술 지표 대안' 안내, 보유 시 PIT 적용 사실 안내, 품질 경고 전달(전부 비차단 notices — 조건 임의 삭제 없음, 실패 시 조용히 통과) ⑤ 빌더 단일 종목 모드 — `BuilderState.single_symbol/single_label` 신설: 유니버스·보유 종목 수·리밸런싱 주기 질문 스킵, 전략 유형 질문을 "언제 사고팔지"(프로파일 신호 횟수를 근거로 선택지 설명, 실패 시 정적 폴백)로 교체, 모멘텀 랭킹·가치 스크리닝 선택은 조용히 무시하지 않고 이유 설명+대안(돌파/직접 서술)으로 되묻기, 확정 시 target_symbols·max_positions=1·리밸런싱 none DSL 직접 조립+단일 종목 서술 프롬프트 합성 ⑥ API — `GET /stock/{symbol}/research-profile`(+Next 프록시): 데이터 기간·가능 카테고리·노출/제외 질문과 이유(§17 계약), include_advanced 토글, 구조화 로그(노출/제외/경고 수) ⑦ 코치 배선 — parsed_strategy가 단일 종목이면 프로파일 압축 JSON+행동 제약(미보유 데이터 지원 표현 금지·10회 미만 신뢰 경고·사후 최적값 추천 금지·미래 예측/보장 금지·null 추정 금지·선별 대신 진입/청산 질문) 주입 ⑧ 프론트 — 빌더 진입 시 single_symbol 전달, 백엔드 프로파일 질문을 우선 표시(정적 문구는 폴백). 테스트: 신규 `test_stock_profile.py` 21·`test_builder_single_asset.py` 7·`test_stock_profile_routes.py` 3 — 백엔드 2,334+31·프론트 1,066 전체 통과 | ✅ 완료 |

**핵심 결론:**
- AI 모델은 진입/청산/위험 오버레이 어느 방식으로도 사이클 전체에서 알파 없음. 유일한 관찰은 휩쏘성 기술적 매매(-65%/년)의 과매매 출혈을 청산으로 줄여주는 것뿐이며 그조차 B&H 미달.
- 사용자가 직접 "AI 모델"을 입력하면 파서·엔진은 여전히 인식·실행한다(기존 저장 전략 호환). 시스템이 **먼저 권하지 않을 뿐**이다.

### Phase 3.11: 관리자 콘솔 (Admin Console) — ✅ 완료

운영자 전용 단일 화면 관리자 콘솔. URL은 `/console` 하나뿐이며(하위 페이지 없음) 내부 탭 전환으로 모든 기능을 제공한다. 보안은 UI 숨김이 아니라 서버 권한 검증으로 보장한다.

| 작업 | 상세 | 상태 |
|------|------|------|
| 서버 권한 검증 | `lib/server/adminAuth.ts::requireAdmin()` — JWT 쿠키 + `User.role='ADMIN'` + `status='ACTIVE'` 3중 검사. 실패 시 페이지·API 모두 **404**로 응답해 콘솔 존재 자체를 숨김. ADMIN 부여는 DB에서만 가능(화면/API로 role 변경 불가) | ✅ 완료 |
| DB 스키마 | `User.role/status/lastLoginAt` 추가, `AdminAuditLog`(감사 로그, 삭제 API 없음), `PlanConfig`(플랜 한도 오버라이드). 마이그레이션 `20260707000000_admin_console` | ✅ 완료 |
| 콘솔 UI | `app/console/page.tsx`(서버 게이트 → `notFound()`) + `components/admin/AdminConsole.tsx` — Overview/Users/Backtests/Virtual Accounts/Strategies/Plans/Audit Logs 7탭, 선택된 탭만 렌더. 이후 Knowledge(2026-07-25)·Agents(2026-07-29, AI 파이프라인 설계 시각화) 탭 추가 | ✅ 완료 |
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
| 섹터 SOT·정규화 | `engine/universe_pit.py` — `CANONICAL_SECTORS`(45개 — 2026-07-13 '로봇' 신설, 2026-07-30 묶음 섹터 6쌍 분할, korea-stocks.json sector 필드=SOT), `normalize_sector`(동의어: 2차전지→이차전지, 제약→바이오/제약, 인터넷→플랫폼 등), `expand_legacy_sector`(구 묶음명 → 신규 2섹터), `filter_by_sector` | ✅ 완료 |
| 파서 | `ParsedStrategy.sector` + field_validator 정규화(LLM 자유 문자열도 정본화, 미지원→None). 결정적 추출 `_extract_sector` = 섹터명+업종 큐(관련주/업종/섹터/테마주/종목/주식/주+중심/위주, '주가' 배제). `_apply_prompt_overrides`가 LLM 결과에도 덮어쓰기 + **시장 언급 없으면 universe=양시장**(KOSPI200 기본이면 시총 상위 200 ∩ 섹터로 과도 축소). 미지원 목록의 `sector` 항목은 제거하지 않고 조건화 — 패턴을 관련주/테마주까지 확장하되 추출 성공 시 제외('로봇 관련주'는 여전히 안내, 기존에 '관련주'가 아예 안 잡히던 침묵 누락도 개선). SYSTEM/COMPACT/MODIFY 프롬프트·parse_validator 스키마에 sector 반영, `NL_PARSER_CACHE_VERSION` 5→6 | ✅ 완료 |
| 전달·엔진 | canonical DSL에 sector 포함(None이면 키 없음 — 기존 전략 해시 불변), `to_backtest_request`·`BacktestRequest.sector`(extra=ignore 스키마 누수 함정 방어), 엔진이 PIT 해석 후 `filter_by_sector` 적용 + 0종목이면 fail-fast + **생존편향 경고**(섹터 분류는 현재 상장 종목 기준 — PIT 마스터엔 섹터 없음). 실데이터 스모크: 반도체 모멘텀 1Y → 78종목·36거래·전 거래 반도체 섹터 확인 | ✅ 완료 |
| 프론트 | `ParsedSummary.sector`·`StrategyBacktestRequest.sector` 타입, `getDisplayUniverseLabels`가 "반도체 업종" 배지 추가, 실행 요청 기반 요약(`buildStrategySummaryFromRequest`)에도 반영 | ✅ 완료 |
| 종목 질문 전환 안내 | `stock_question_redirect(name, market, sector)` — 언급 종목의 섹터를 알면 "○○가 속한 반도체 업종 종목만 대상으로 최근 3개월 수익률 상위 5종목 매수"를 첫 예시로(이/가 조사 처리 포함). 예시 문구 자체가 룰 파서로 파싱됨을 회귀로 보장 | ✅ 완료 |
| 테스트 | universe_pit 섹터 3종, nl_parser 섹터 7종(추출/양시장 기본/명시 시장/미지원 안내/스키마 왕복/해시 불변/validator 정규화), classifier 2종(섹터 예시·파싱 가능성) 추가 — 백엔드 1726·프론트 795 전체 통과 | ✅ 완료 |
| 목록 밖 업종 침묵 유실 수정 (2026-07-12) | "로봇주 관련 전략을 만들어보자"가 빌더에서 안내 없이 전체 시장으로 백테스트되던 버그. ① 업종 큐를 맨 '관련/테마'로 확장(`_SECTOR_CUE`·미지원 감지 패턴 — '관련주' 어순만 보면 "로봇주 관련"·"로봇 테마"·"반도체 관련 전략"을 놓침), "업종 상관없이" 무관 표현은 오탐 제외(`_SECTOR_AGNOSTIC_RE`) ② 빌더 시드·대화 입력이 목록 밖 업종 언급을 감지하면(`BuilderState.sector_unresolved`) "지원 목록에 없어 업종 제한 없이 진행 + 지원 업종 예시" 안내를 1회 표시(즉시 confirmed면 notices 채널, 라우트는 하한선 notices에 병합) ③ 대화 중 지원 업종 언급("기계/장비 업종으로")은 `parse_input`이 캐치해 sector 반영+확인. 테스트: builder 4종+nl_parser 2종 추가 — 백엔드 1762·프론트 852 전체 통과 | ✅ 완료 |
| 목록 밖 업종 LLM 매핑 (2026-07-12) | "원자로 관련주 전략을 만들자" — 결정적 정규화가 실패한 업종/테마도 지원 업종의 하위 테마면 LLM이 매핑해 배지까지 만든다. `llm_extract_sector`(지원 업종 38개 전체 목록 프롬프트, normalize_sector 재검증)를 빌더 step의 `sector_resolver`로 주입(라우트, risk_extractor와 동일 패턴) — `sector_unresolved`+`sector_hint`(원문)를 보고 안내 표시 **전에** 해석 시도, 성공 시 sector 반영+확인 문장("에너지/원자력 업종 대상으로 이해했어요"), 실패 시에만 기존 안내. 실측: 원자로→에너지/원자력, K뷰티→화장품/패션, 메타버스→소프트웨어/플랫폼, 로봇주→기계/장비. COMPACT 프롬프트에도 지원 업종 전체 목록+매핑 지침 추가(메인 파싱 경로 동일 개선, 비정본 예시 '게임' 제거). **곁들인 기존 버그 수정**: `_CANCEL_RE`의 `관둘?`이 맨 '관'에 매칭돼 '관련주로 해줘'가 빌더 취소로 오인되던 버그 → `관[두둬둘]`. 테스트 6종 추가 — 백엔드 1772·프론트 852 전체 통과 | ✅ 완료 |
| 업종 매핑 관례 주석 (2026-07-12) | '전력설비 관련주'를 LLM이 이름 연상('전력→유틸리티')으로 통신/유틸리티(실제: 통신사·한전 등 사업자 25종목)에 매핑 — 변압기·전력설비 제조사는 이 분류 체계에서 에너지/원자력, 전선 제조는 IT 하드웨어. 근본 원인=LLM이 업종 '이름'만 보고 분류 관례를 모름 → `universe_pit.sectors_for_llm_prompt()`(단일 출처)가 혼동 업종 3곳에만 짧은 관례 주석을 붙여 빌더 해석기·COMPACT 프롬프트 양쪽에 공급. 실측 8케이스 검증: 전력설비/변압기→에너지/원자력, 전선→IT 하드웨어로 교정, 통신주/5G→통신/유틸리티 유지, 기존 매핑(원자로·K뷰티·메타버스) 회귀 없음. 백엔드 1773·프론트 852 전체 통과 | ✅ 완료 |
| LLM 폴백 스키마 드리프트 복구 — 섹터 유실 근본수정 (2026-07-12) | "2차전지에 투자하는 전략을 만들자"(업종 큐 없는 표현)가 섹터 없이 전체 시장으로 백테스트되던 버그. 실측 원인: LLM 폴백은 업종을 이해했으나 **sector를 universe 필드에 넣고 description을 빼먹는 스키마 드리프트** → ValidationError → `_build_fallback_strategy`가 LLM 해석을 통째로 폐기. 수정: ① `ParsedStrategy._repair_llm_schema_drift`(model_validator, mode=before) — universe의 비시장 값을 정본 업종으로 해석해 sector로 이동(한글 시장명 정규화 포함, 업종만 있었으면 양시장 기본), description 누락은 다른 전략 내용이 있을 때만 빈 문자열로 채움(빈 출력 {}은 여전히 폴백) ② `_apply_prompt_overrides`가 빈 description을 원문으로 채움 ③ parse() LLM 경로에서 sector 있고 universe가 스키마 기본(KOSPI200)+시장 언급 없으면 양시장 강제(FR-STR-066 ③, modify 경로 제외) ④ COMPACT 프롬프트에 "universe에 업종명 금지·description 필수" 지침 추가. LLM이 잡은 sector는 `seed_parsed` 채널로 빌더까지 관통("이차전지 업종 대상으로 이해했어요" 실측 확인). 테스트 4종 추가 — 백엔드 1766·프론트 852 전체 통과 | ✅ 완료 |
| 수정 경로 섹터 반영 — 후속 요청 침묵 유실 수정 (2026-07-13) | 완성된 전략에 "반도체 섹터 종목만 테스트 해줘" 후속 요청이 조용히 무시되고 동일한 전략 요약이 재출력되던 버그. 원인: 수정(modify) 경로에 섹터 처리가 통째로 부재 — ① 결정론 fast-path(`_modify_rule_based`)에 `_extract_sector` 미배선(`_MODIFY_FIELD_CUES`에 sector 항목 없음) ② LLM diff 경로는 `MODIFY_PROMPT`에 섹터 안내·예시 전무(전 예시 sector:null)+diff 스키마 description 부재 ③ 파스 경로의 결정적 보정(`_apply_prompt_overrides` 섹터 추출)이 LLM diff 병합 후에는 미적용. 수정: fast-path에 sector 추출+잔여 판정 어휘(정본 섹터명·동의어 동적 생성+업종 큐, '테스트' 실행 동사 필러) 추가, LLM diff가 sector를 놓치면 결정적 추출로 보정(파스 경로와 동형), `MODIFY_PROMPT`에 지원 업종 목록+예시 추가, '업종/섹터'+삭제어 인접 표현("업종 제한 빼줘")의 해제 보정(종목 제외 요청 오발동 방지). **수정 경로는 기존 universe 보존**(양시장 기본 확장은 최초 파싱 전용 — `_apply_prompt_overrides(preserve_universe=True)`), KOSPI200 ∩ 반도체=12종목 실측 확인. 테스트 6종 추가 — 백엔드 1807·프론트 913 전체 통과. SRS FR-STR-066 ⑥ | ✅ 완료 |
| 섹터 어휘집 파생 구조 — NL/분류 드리프트 근본 차단 (2026-07-13) | "로봇 섹터도 추가해줘"가 '지원 목록에 없는 섹터' 안내로 빠지던 버그 — '로봇'은 종목 분류(`sector_mapper.MAPPING_RULES`)엔 기계/장비로 있으나 NL 동의어(`universe_pit._SECTOR_SYNONYMS`)엔 없던 수동 동기화 드리프트. 통째 합집합은 금물('투자'→증권/보험 등 일반어의 거짓 양성) — `sector_mapper.NL_SAFE_TERMS`(모호하지 않은 사용자 산업어 31개 opt-in 화이트리스트)에서 `_derive_mapper_nl_synonyms`가 정본 자동 파생(단일-정본 검증 fail-fast)+사용자 전용 통칭 오버라이드(`_SECTOR_SYNONYM_OVERRIDES`). 정본 손 중복 기입 제거로 두 어휘집 불일치가 구조적으로 불가. 가드 `tests/test_sector_nl_synonyms.py` 5종(무모순·단일정본·거짓양성·로봇 회귀). SRS FR-STR-066 ①-1 | ✅ 완료 |
| 다중 섹터 + 수정 4의도 통합 판정 (2026-07-13) | "로봇 섹터도 추가해줘"(기존 반도체)가 **교체**로 처리돼 반도체가 사라지던 버그 — sector가 단일 str이라 '추가'를 표현 불가. 수정: sector 정규형 None/str(단일 — 기존 해시·직렬화 하위 호환)/list(복수, 엔진 `filter_by_sector` 합집합) — `normalize_sector_value`, ParsedStrategy·Diff·BacktestRequest `Union[str, List[str]]`, canonical DSL은 복수만 정렬 list(기존 전략 해시 불변). 수정 4의도는 `_sector_change_from_utterance` 결정적 통합 판정이 LLM diff에 우선: 추가('도'+업종명사/추가·포함 동사 인접)=합집합, 교체=덮어쓰기, 개별 삭제("반도체 업종은 빼줘")=그 항목만(목록 밖 대상이면 오폭 없이 유보), 전체 해제. rule-based·LLM 병합·`_apply_prompt_overrides` 3지점 동일 배선 — 삭제 발화가 `_extract_sector` 재추출로 되살아나던 선행 재주입 버그도 함께 수정. 프론트 업종별 개별 배지(`strategy-summary` string|string[]). MODIFY_PROMPT·`modify_knowledge.json`에 추가 의미론 반영. 테스트 백엔드 9종+프론트 1종 — 백엔드 1825·프론트 914 전체 통과. SRS FR-STR-066 ⑦ | ✅ 완료 |
| '로봇' 독립 정본 섹터 신설 (2026-07-13) | 로봇을 기계/장비 동의어가 아니라 39번째 정본 섹터로 분리. KSIC 공식 분류에 로봇 업종이 없어('특수 목적용 기계 제조업' 등) **사명(로봇/로보틱스/로보) 기준** 분류 — `MAPPING_RULES["로봇"]` 우선순위 최상단(사명 부분매칭 오분류 선점: 해성에'어로'보틱스→수산 '어로' 매칭 버그도 수정), 사명 무표지 로봇 전문기업은 `OVERRIDDEN_SYMBOLS`(뉴로메카), 상폐 경로도 단축명 오버라이드 전에 사명 판정. 데이터 SOT 외과 패치: korea-stocks.json+stock-master.json 27종목 sector=로봇(전면 재분류 churn 없이 로봇 판정 종목만). '공장자동화'는 기계/장비 유지. NL은 파생 구조가 자동 반영(NL_SAFE_TERMS 로봇/로보틱스), `nl_cache` v8(로봇=기계/장비 캐시 무효화), LLM gloss("일반 자동화 설비는 기계/장비"). **⚠ 배포 후속 조치(미완)**: parquet sector 컬럼을 읽는 유일한 소비자는 종목 상세 엔드포인트(`main.py::_resolve_investment_sector` — 종목 소개 문구용, 백테스트 필터는 JSON SOT만 사용)인데 프로덕션 parquet에는 로봇 27종목이 구값(기계/장비 등)으로 남아 있음 → **배포 후 prod에서 `python scripts/backfill_sector_data.py` 1회 실행 필요**(전 종목 parquet sector를 현행 매퍼로 재기록). 로컬 parquet은 sector 전부 None이라 폴백 매퍼가 커버(무영향), `npm run pull-data`로 백필 이후 값 수신 | ✅ 완료 |
| 수정 RAG 코퍼스 신호 추가 의미론 보강 (2026-07-14) | 수정 경로 정확도 실측 하니스(`scripts/qa_modify_accuracy.py`, 27케이스 — RULE/LLM 라우팅·정확도·diff-contract 과다변경 분리 측정) 신설로 LLM 위임 슬라이스의 유일한 실질 공백이 **기술적 신호 추가**(골든크로스/RSI/데드크로스 → `entry/exit_signals` 미추가)임을 확인 — 원인: Ollama 수정 경로(`build_dynamic_modify_prompt`)의 유일한 신호 지식 소스인 `modify_examples.json`에 신호 예시 0건 + `modify_knowledge.json`의 "전체 교체가 명확할 때만 구조화 목록 출력" 규칙이 부분 추가를 억제. 수정: knowledge filters-and-signals 문서에 **"신호 목록은 diff가 통째로 대체하므로 추가 요청이면 기존+새 신호 전체 목록 출력"** 규칙+스키마 값 명시(골든크로스=ma_crossover buy 5/20 등)+예시 1→4건, examples에 신호 예시 13건 신설(entry/exit_signal 카테고리, 전건 `ParsedStrategyDiff` 스키마 검증). 재실측: 전체 22/26(85%)→**26/26(100%)**, LLM 경로 9/12(75%)→11/11(100%), 과다변경 0건 유지 | ✅ 완료 |
| 수정 경로 펀더멘털 필터 인식 + 미지원 퀀트 팩터 안내 (2026-07-14) | 스크린샷 사고: "영업이익률을 추가해 볼까?" 수정 요청이 조용히 무시됨(전략 요약 재출력) — 원인 2중: ① 수정 RAG 코퍼스(525건)에 펀더멘털 필터 예시 **0건**+knowledge에 지원 metric 목록 부재 → LLM diff가 필터를 못 냄, ② LLM diff의 fundamental_filters는 통째 대체 의미론인데 few-shot이 새 필터만 출력하도록 유도 → 추가 발화에서 기존 필터 소실. 수정: (1) modify_knowledge filters-and-signals에 지원 metric 17종 명세+필터도 기존+새 전체 목록 규칙+**미지원 지표는 diff에 넣지도 대체하지도 않는다** 규칙+임계값 없으면 수익성 지표 >=10 기본값 규칙, 예시 2건(영업이익률 vs 영업이익증가율 구분), (2) modify_examples에 fundamental_filter 카테고리 14건 신설(525→539), (3) `parse_modification`에 결정적 병합 보정 — 제거 의도(_REMOVE_INTENT_RE) 없으면 `_merge_fundamental_filters`(같은 지표 갱신·새 지표 추가·기존 보존)가 LLM diff에 우선, 제거 발화는 LLM 전체 목록 존중(sector 보정과 동형), (4) fundamental_filters cue에 '조건'·'필터' 추가로 값 명시 수정("영업이익률 15% 이상 조건 추가")은 LLM 없이 fast-path 즉답, (5) 미지원 퀀트 팩터 8종 감지 확장(`_UNSUPPORTED_CONCEPT_PATTERNS`): EV/EBITDA·ROIC·베타·이자보상배율·피오트로스키/알트만·회전율·자사주+cash_flow에 PCF — 기존 notices 채널(프론트 렌더링 기배선)로 "아직 직접 지원되지 않아요" 안내, 지원 지표(영업이익률 등) 오탐 방지 테스트 동반. E2E 실검증(로컬 Ollama): "영업이익률을 추가해 볼까?"→기존 ROE·부채비율 보존+operating_margin>=10 추가, "EV/EBITDA 8배 이하 조건도 추가해줘"→유사 지표 대체 없이 기존 유지+notice 생성. 테스트 test_nl_parser_overrides.py 4건+파라미터 11건 추가 | ✅ 완료 |
| 배당 파이프라인 확장: 배당수익률·배당성향·배당성장률 메트릭 + 전 종목 백필 (2026-07-14) | 기존 배당 인프라(`scripts/backfill_dividends.py`=KIS 예탁원 배당 API `ksdinfo/dividend`로 주당 현금배당을 `face_val` 액면분할 역조정해 `dividends` 컬럼 백필; `engine/dividends.py` 총수익 보정) 위에 **배당 메트릭 3종을 신설**. ① **배당수익률**(`dividend_yield`, %)=TTM(252거래일 롤링) 주당배당 합÷종가×100, **배당성향**(`payout_rate`, %)=TTM 주당배당÷EPS×100, **배당성장률**(`dividend_growth`, %)=TTM 주당배당의 전년(shift 252) 대비 증가율 — 순수함수(`engine/dividends.trailing_dividend_yield`/`dividend_payout_ratio`/`dividend_growth_yoy`). **롤링 합 방식**이라 배당 중단 종목은 1년 내 0으로 감쇠(전진충전이 겪는 '무배당 연도 오인' 회피). 배당성장률은 '가장 최근 확정 연배당'의 전년비를 안정적으로 노출(선언 전 미래 배당을 앞당겨 반영하지 않음), 첫 배당 종목은 직전 TTM=0이라 NaN(정의 불가), 배당 삭감은 −100%. ② **3중 산출 경로**: `backfill_dividends.py`(dividends 백필 시 메트릭 동시 산출·1차)+`enrich_ohlcv_with_fundamentals`(dividends 컬럼 존재 시, `_add_dividend_metrics` 헬퍼로 fundamentals 비어도 계산)+DataResolver 런타임 폴백(`_resolve_dividend_metrics`, 메트릭 도입 전 백필된 parquet 대응). ③ **필터 지표 전 계층 배선**: `signals.FUNDAMENTAL_LABELS`·NL 결정적 패턴(`배당수익률|시가배당률|배당률`, `배당성향|배당지급률`, `배당성장률|배당증가율|배당성장|배당증가`)·DSL Literal·LLM 프롬프트 예시·`parse_validator`·프론트 라벨·`FUND_COLS`. ④ **미지원 목록 조건부 제외**: `배당` 미지원 안내는 유지하되 `dividend_yield`/`payout_rate`/`dividend_growth` 필터(수치 포함)가 추출되면 억제(섹터와 동형) — 수치 없는 막연한 '배당주/배당 성장주'만 미지원 안내. 실검증: 삼성전자 23 ex-date 분할조정 백필, 2023 배당수익률 3.68%·배당성향 23.9%·최근 배당성장률 15.4%(실제와 일치), 필터 백테스트 커버리지 dividend_yield 100%·payout_rate 99.8%·dividend_growth 91.7%(첫해 NaN=partial 정직 고지). **전 종목(~4830) 로컬 백필 실행**(dividend_yield/payout는 KIS 재조회, dividend_growth는 기존 dividends 컬럼서 로컬 재계산·무네트워크). ⚠ prod: 프로덕션 parquet 별도 백필 필요(로컬 gitignore). 테스트 `test_dividends.py`(TTM·감쇠·적자·성장률·첫배당NaN·삭감 6건)+`test_fundamental_metrics_extraction.py`(추출·미지원 아님 6건). 백엔드 전체 회귀 통과 | ✅ 완료 |
| 퀀트 지표 확장: 기술 오실레이터 3종 + EV/EBITDA + 데이터 커버리지 로그 (2026-07-14) | "세상의 거의 모든 퀀트/재무지표 이해" 요청에 대한 1차 확장. ① **기술적 오실레이터 3종 신설**: Williams %R(`williams_r`, stockstats `wr_n`, −100~0 과매도 −80/과매수 −20)·MFI(`mfi`, `mfi_n`을 0~1→0~100 ×100 정규화)·ROC/모멘텀(`roc`, `close_n_roc` %). OHLCV 기반이라 데이터 의존 없음. 엔진(`indicators.py` 컬럼 등록+MFI 스케일, `signals.py` `_eval_vec`·`evaluate_condition`·`get_condition_description`)·컨버터(`strategy_converter._tech_signal_to_condition`)·DSL 스키마(`TechnicalSignal.indicator` Literal)·NL 파서 결정적 추출(cci/스토캐스틱과 동형)·`data_resolver` 필요 컬럼·warmup(`_max_indicator_period`)·프론트 `IndicatorType`·`parse_validator` 전 계층 배선. ② **EV/EBITDA 지원 지표 승격**: KIS other-major-ratios(FHKST66430500)에 EBITDA·EV/EBITDA가 2005~ 연간 제공됨을 실호출로 확인 → `_KIS_FINANCE_ENDPOINTS` 4번째→5번째 엔드포인트로 추가, `ANNUAL_FUNDAMENTAL_KEYS`에 `ebitda`/`ev_ebitda` 추가(결산 스냅샷 전진충전). ev_ebitda의 0.00 센티널(2010 이전)은 비양수 제거해 가치 필터가 무데이터 연도를 저평가로 오인하지 않게 함. `FUNDAMENTAL_LABELS`·NL 패턴(`ev[/\\s-]?ebitda|에비타`)·기본연산자(<=)·프론트 라벨·validator 배선 + **미지원 목록(`_UNSUPPORTED_CONCEPT_PATTERNS`)에서 제거**(데이터 구현 시 목록 제거 원칙 적용). ③ **데이터 커버리지 로그 신설**(`engine/data_coverage.py`): 전략이 참조한 펀더멘털 지표별로 백테스트 창의 (기간 커버리지%·종목 커버리지%·사용가능 시작·종료일·used/partial/unused)를 종목별 순수함수 집계→단일스레드 fold로 산출, 결과 `dataCoverage` 필드+데이터 부족 경고를 `warnings` 채널 합류. FR-BT-016. 실검증: 10종목 PER/ROE 필터 백테스트에서 PER 99.8%·ROE 99.8% 커버리지, williams_r 43거래; ev_ebitda 필터 백테스트에서 stale 캐시 종목 미보유가 partial(50%)로 정직하게 노출. 테스트: `test_engine_signals.py`(오실레이터 5건)·`test_indicators.py`(컬럼·MFI 스케일 1건)·`test_data_coverage.py`(6건)·`test_fundamental_metrics_extraction.py`(EV/EBITDA 추출·미지원 아님·전진충전 3그룹). 백엔드 전체 1902 통과. ⚠ **prod 반영**: ev_ebitda는 parquet 백필 필요(`scripts/enrich_all_fundamentals.py` 재실행 시 combine_first로 기존 종목에도 추가); 미백필 종목은 DataResolver가 백테스트 시 라이브 조회하되 커버리지 로그가 부족을 투명 고지 | ✅ 완료 |
| 영업이익률(operating_margin) 펀더멘털 파이프라인 신설 + 백필 (2026-07-14) | `operating_margin`은 `diagnoser.py`/`experiment_learning.py`에 라벨/화이트리스트만 있고 **데이터 파이프라인이 없던 죽은 참조**였음. KIS 재무비율 3종(financial/profit/stability-ratio)에는 영업이익률 필드가 없음을 실호출로 확인 → KIS 손익계산서(`income-statement`, FHKST66430200)의 영업이익(`bsop_prti`)/매출액(`sale_account`)으로 직접 계산해 정규 파이프라인에 4번째 엔드포인트로 병합(`fundamental_fetcher._parse_kis_income_statement`, `ANNUAL_FUNDAMENTAL_KEYS`에 추가 → `enrich`/`merge_fundamentals` 자동 반영). 필터 지표로 완전 배선: `signals.FUNDAMENTAL_LABELS`(영업이익률)+NL 파서 결정적 패턴(`매출액영업이익률|영업이익률`, 영업이익증가율과 disjoint 검증)+LLM 프롬프트 용어집/예시+`parse_validator` 스키마+프론트 라벨맵 2곳(`strategy-summary.ts`·`parsedStrategyMerge.ts`). 실검증: 삼성전자 23행 전부 operating_margin 산출, 값이 실제와 일치(2023년 2.54%·2022 14.35%·2021 18.47%). 전 종목 parquet 백필(`scripts/backfill_fundamentals.py --force`, ~4830개). ⚠ **prod 반영**: 프로덕션 parquet은 별도 백필 실행 필요(로컬 parquet은 gitignore, `npm run pull-data` 정본은 프로덕션). 상폐 종목은 KIS 미제공이라 DART 경로 확장은 별건(향후). 테스트 `test_fundamental_fetcher.py`(income-statement 파서 2건)+`test_fundamental_metrics_extraction.py`(추출·영업이익증가율 혼동 방지·라벨 3건) | ✅ 완료 |
| 파싱 타임아웃 사고 수정: 로컬 LLM 연결거부 fast-fail + '섹션' 섹터 큐 (2026-07-16) | 스크린샷 사고: "반도체 섹션 종목만 테스트 해보자"가 120s 후 `Strategy parse stream proxy error: timeout`. 원인 2중: ① '섹션'('섹터'의 통용 오칭)이 결정적 섹터 큐(`_SECTOR_CUE`)에 없어 LLM 폴백으로 위임됐는데, ② 로컬 Ollama가 꺼진 상태의 연결 거부를 Modal 콜드스타트용 재시도 루프(`_ollama_ensure_warm` 200s/`_ollama_open_with_retry` 320s)가 transient로 간주해 계속 재시도 → 프록시 120s 예산이 먼저 만료. 수정: (1) `nl_parser._is_local_connection_error` 신설 — `is_local_ollama()`면 연결 오류(URLError/ConnectionError, HTTPError 제외)를 재시도 없이 즉시 raise해 기존 503 친화 메시지("전략 분석 서버에 연결할 수 없습니다")로 빠르게 안내(URLError 재시도는 원격 Modal 전용이 됨), (2) '섹션'을 `_SECTOR_CUE`·`_SECTOR_NOUN`·`_MODIFY_FIELD_CUES["sector"]`에 추가해 결정적 추출로 즉답. E2E 실검증(Ollama 다운 상태): 동일 문장이 14s 내 sector="반도체"+양시장 기본으로 정상 파싱(수정 전 120s 타임아웃). 테스트 `test_ollama_cold_start_retry.py`(로컬 fast-fail 2건, 기존 원격 재시도 테스트는 `is_local_ollama` monkeypatch로 원격 명시)+`test_nl_parser_overrides.py`(섹션 큐 회귀 1건) | ✅ 완료 |

### Phase 3.14: LLM-first 전략 대화 아키텍처 — Phase 1 Shadow Mode (2026-07-16) — ✅ 완료

전략 대화의 자연어 의미 해석을 결정론 Regex 파서에서 LLM(Qwen 3.5 4B)으로 이관하는 구조 전환의 1단계. 설계 원칙: **LLM-first / Validation-heavy / Registry-driven / Deterministic execution / No silent assumptions**. 신규 패키지 `backend/strategy_conversation/` (상세: `docs/software_architecture.md` §4.2.1).

| 작업 | 상세 | 상태 |
|------|------|------|
| StrategyIntent 중간 표현 | `interpreter/models.py` — LLM 출력 계약(schema_version 1.0): intent Enum 10종, 조건별 factor/operator/value/unit/source_text, 값 출처 분리(USER_PROVIDED/…/SYSTEM_RECOMMENDED/MISSING — 추천값≠확정값), missing_fields·unsupported_features·clarification_questions·confidence. 4B 드리프트 형식 복구(문자열 수치 "10%"→10.0, confidence 0~100 스케일, 한글 시장명, 문자열 질문 승격)는 field validator(형식 정규화 = 결정론 영역) | ✅ 완료 |
| LLM Strategy Interpreter | `interpreter/llm_strategy_interpreter.py` — Ollama /api/chat(format=json·think=false·temp 0), 기존 콜드스타트 내성(warm-up+재시도) 재사용, Registry 주입 시스템 프롬프트(`prompts.py`, PROMPT_VERSION 관리). JSON 추출→Pydantic 검증 실패 시 오류 첨부 **1회 자동 수정 요청**(`output_repair.py`, 무한 재시도 금지) → 재실패 시 InterpreterError. transport 주입식이라 테스트가 LLM 없이 스텁 검증 | ✅ 완료 |
| Indicator/Capability Registry | `registry/indicator_registry.py` — 지표 지원 여부의 단일 진실 소스(SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED). 엔진 실지원과 1:1(재무 21종·기술 16종·랭킹), canonical ID·허용 연산자·ParamSpec 범위·추천 시작값·engine_binding·미지원 개념 18종(FCF·ROIC·베타 등, 대체 지표 명시 제안용). 엔진 Literal과의 드리프트를 테스트가 가드. `capability_registry.py` — 리밸런싱 주기/비중 방식/시장 화이트리스트 | ✅ 완료 |
| 검증 계층 | `validation/` 4종+파이프라인 — Capability(미지원 조용한 대체 금지, factor canonical 정규화), Parameter(임계값·파라미터 범위), Conflict(AND 구간 공집합·단기≥장기·보유기간<리밸런싱·진입=청산 동일조건), Completeness(누락 필수값→Registry 추천값 딸린 되묻기 질문, 최대 3개/턴, **조용한 기본값 확정 금지**). confidence는 높아도 검증 생략 없음, 낮으면(설정 파일 `config.py` 임계값) 확정 금지 | ✅ 완료 |
| Strategy Compiler | `compiler/strategy_compiler.py` — 검증 READY만 ParsedStrategy(기존 내부 DSL)로 결정론 컴파일(Fail Fast). 별도 AST 계층 없이 기존 파이프라인(`strategy_converter`→백테스트 엔진)에 그대로 합류 | ✅ 완료 |
| 대화 상태 + JSON Patch | `conversation/strategy_draft.py`(StrategyDraftState·DraftStore 인메모리, revision·confirmed_fields)+`patch_applier.py`(JSON Patch 부분집합 replace/add/remove, 경로 검증+적용 후 스키마 재검증, 실패 시 PatchError) — MODIFY_STRATEGY는 전체 재생성 대신 patch 방식 | ✅ 완료 |
| Shadow Mode 배선 | `shadow.py` + main.py 초기 파스 경로 — `STRATEGY_INTERPRETER_MODE=shadow`일 때만 신규 파이프라인을 백그라운드 스레드로 병행 실행(비차단, 사용자에겐 기존 결과만), 기존 룰 파스와의 field diff·관측성 계약(llm_raw_output·validation_*·compiler_output·latency_ms)을 `backend/logs/strategy_interpreter_shadow.jsonl`에 기록(.gitignore `/backend/logs/` 앵커 추가) | ✅ 완료 |
| 평가 하니스 | `evaluation/datasets/parse_cases.json` 34케이스(동일의미 이표현·모호·값누락·복수조건·부정·수정·문맥의존·미지원·충돌·비정형 오타) + `evaluator.py`(`--legacy`로 규칙 파서 비교)+`metrics.py`(intent/지표/임계값 정확도, **false assumption rate**, missing detection recall, 미지원 오판율, repair 사용률, p50/p95 지연) | ✅ 완료 |
| 테스트 | `tests/test_strategy_conversation.py` 38건 — 드리프트 복구·Registry(엔진 Literal 가드 포함)·검증 파이프라인(충돌/누락/미지원/범위/신뢰도)·컴파일러·Patch·복구 루프(스텁 LLM)·Shadow diff·지표 계산. 백엔드 2002·프론트 963 전체 통과 | ✅ 완료 |
| Phase 2: Primary Mode 승격 (2026-07-16) | `STRATEGY_INTERPRETER_MODE=primary`면 초기 파스를 인터프리터 파이프라인이 담당(`strategy_conversation/primary.py`), 실패·비전략 intent·컴파일 불가는 기존 규칙 파서 하이브리드로 폴백. READY=전체 컴파일, NEEDS_CLARIFICATION=**부분 컴파일**(`compile_partial` — 누락값 지적 조건 제외, 조용한 기본값 확정 금지)+되묻기 질문·추천값 칩을 기존 clarification 채널로 전달(칩 클릭→일반 수정 메시지→modify 결정적 병합, condition_builder와 동일 무상태 패턴). 수정 경로·대화 상태(프론트 previous_parsed)는 기존 유지. **evaluator 실측 기반 드리프트 복구 3종 추가**: 추천값 리스트→문자열, 백테스트 기간 일수→버킷, 랭킹 지표 entry 중복→ranking 이동/승격 + LLM 잉여 질문은 결정론 missing_fields 교차 확인만 채택 + 프롬프트 규칙·예시 보강(크로스오버 파라미터, '낮은/높은' 수치 미명시=null, 정성표현≠UNSUPPORTED). E2E 실검증(uvicorn primary 모드): READY 즉시 컴파일·되묻기 케이스 단일 질문+칩, v1 실패였던 골든크로스 파라미터·모멘텀 랭킹 케이스 READY 확인. **evaluator 승격 게이트 실측(qwen3.5:4b)**: 34케이스 19→28 통과, 스키마 실패 8→1건, false assumption rate **0.0**, missing detection recall **1.0**, threshold 정확도 **1.0**, conflict 감지 **1.0**, intent 분류 96%. 잔여 실패 6건=4B 한계의 긴 꼬리(난해 패러프레이즈·오타 분류·'알에스아이' 음역)+modify JSON 1건(modify는 primary 미배선이라 무영향) — primary 모드에선 전부 폴백/되묻기로 안전. 테스트 56건, 백엔드 2020·프론트 963 전체 통과 | ✅ 완료 |
| Phase 2 후속: Modify Primary 이관 + dev 실사용 개시 (2026-07-17) | ① **수정 경로 인터프리터 이관**: Decompiler(`compiler/strategy_decompiler.py`, ParsedStrategy→StrategySpec 역매핑)로 기존 전략을 draft 주입 → LLM은 patches만 출력(전체 재출력 불수락) → 적용 후 검증 READY만 재컴파일, 거부는 전부 기존 하이브리드 폴백. 안전장치: **라운드트립 가드**(decompile→재compile 불일치 시 이관 거부 — rsi rebound 등 표현 불가 전략), StrategySpec 밖 필드(description·execution_timing·entry_filters) 원본 이월, 과잉 삭제 패치("/entry_conditions" 전체 remove)는 스키마 거부 실측 확인(폴백 후 legacy가 정확 처리). ② **연산자 토큰 드리프트 복구**: greedy 결정적 재현되던 modify JSON 실패(`"operator":">="`→`"operator">="` 붕괴)를 output_repair의 멱등 구문 복구로 해결. ③ 프롬프트 modify 계약(예시 5: patches 필수·인덱스 remove 강제). ④ **dev `.env`에 STRATEGY_INTERPRETER_MODE=primary 활성화**(실사용 개시) + conftest가 테스트에선 off 고정(dev .env 누출로 파스 경로 테스트 6건 비결정 실패하던 것 격리). E2E 실검증(dev GGUF 모델): "ROE를 20%로 올리고 부채비율 조건은 빼줘" → patches 2건, ROE만 20 갱신·부채비율만 제거·나머지 전부 보존, 9.3s. **evaluator v3(qwen3.5:4b): 29/34(v1 19→v2 28→29), modify 3/3 전부 통과, 미지원 감지 1.0·무단확정 0.0·누락recall 1.0·충돌 1.0·repair 사용률 0, p50 12.6s** — 잔여 5건=4B 긴 꼬리 3(난해 패러프레이즈·오타)+malformed JSON 1(폴백 안전)+모멘텀 저신뢰 확인요청 1(설계상 보수). 테스트 63건, 백엔드 2027·프론트 963 전체 통과 | ✅ 완료 |
| Phase 2 검수: 실사용 시뮬레이션 관찰 (2026-07-17) | prod 전환 게이트용 실측 — 기존 `qa_modify_accuracy` 27케이스를 main.py와 동일한 primary→폴백 체인에 통과(dev GGUF 모델). 1차: PRIMARY 21/27·정확도 24/26에서 실패 패턴 3종(보유기간 달력일 출력·트레일링→손절 오귀속·빈 배열에 replace) 확인 → 프롬프트 보강(거래일 변환표·trailing 정의·add/- 규칙)+patch_applier가 replace-on-"-"를 append로 수용(드리프트 실측). 2차: **정확도 26/26(100%)·과다변경 0건(legacy와 동률), PRIMARY 20/27 처리, 웜 p50 2.1s**(기존 수정 LLM 25~50s 대비 대폭 단축 — patches 출력이 짧아서). 초기 파스(v3 29케이스): PRIMARY 19 처리·설계상 폴백 8(미지원/비전략/추천 — 의도된 동작)·비의도 폴백 2(심한 오타 분류·malformed JSON, 둘 다 legacy가 안전 처리). 백엔드 2028 전체 통과 | ✅ 완료 |
| prod Shadow 배포 (2026-07-17) | 사용자 결정: prod는 shadow부터(실사용자 프롬프트 diff 수집, UX 무변화). `/opt/simons/.env`에 `STRATEGY_INTERPRETER_MODE=shadow`+`STRATEGY_INTERPRETER_SHADOW_LOG=/app/data/logs/strategy_interpreter_shadow.jsonl`(data 볼륨 = 컨테이너 재생성에도 영속) 추가 → 커밋 bc9f8aac(strategy_conversation 전체, 세션 파일만 선별 — 타 세션 미커밋 작업물 제외, 스테이징 단독 상태로 테스트 검증 후 푸시) → CI 통과+Vultr 배포(6m46s). **prod E2E 검증**: 컨테이너 env·shadow_enabled 확인, 파스 1건 실행 → 사용자 응답은 규칙 fast-path 즉답(무영향), shadow 스레드가 Modal 콜드스타트(101s) 견디고 JSONL 기록 — validation_status=READY, **field_diff 빈 객체(규칙 파서와 완전 일치)**. 관찰 방법: `tail /opt/simons/data/logs/strategy_interpreter_shadow.jsonl` | ✅ 완료 |
| 사용자 노출 정리 — 자기회의 문구·잉여 질문 제거 (2026-07-17) | dev 실사용 스크린샷 사고: "요청을 정확히 이해했는지 확신이 낮습니다 — 확인해 주시겠어요?"·"전략 이름 붙여드릴까요?"·재무지표 커버리지 블랭킷 경고가 노출. 원칙 확정: **의도 해석 책임은 시스템에 있다 — 사용자에게 확인을 요구하지 않는다. 질문은 실행에 필요한 값이 실제로 비었을 때만.** 수정: ① confidence 사용자 노출 전면 제거(저신뢰 경고·확인 질문·상태 게이트 삭제 — 4B가 자주 누락해 0.0이 되는 신뢰 불가 신호, runtime.interpreter 텔레메트리 전용) ② LLM 자체 질문은 결정론 missing_fields 교차확인만 노출 ③ 사전 커버리지 경고 제거(백테스트 데이터 커버리지 로그가 정본) ④ 수치 있는 근사 표현("8종목 정도"/"15개쯤")은 질문 대신 그 수치로 확정 — 질문 차단으로 기본값에 조용히 덮이던 유실 방지(E2E 실측 8·15 정확 추출). 테스트 64건·백엔드 2028 통과, 커밋 1433d99b 배포 | ✅ 완료 |
| LLM 왕복 콘솔 로그 (2026-07-17) | 사용자 요청("LLM이 대답하는 내용을 눈으로 확인하고 싶어") — 인터프리터 경로에 `[LLM-INTERPRETER]` print 로그(uvicorn 설정 무관 항상 표시, [NL-PARSE] 관례): ▶요청(수정 모드 표기) → ◀원본 응답(가공 없이 그대로) → ⟳복구 요청/◀복구 응답(회차별) → ✓해석(intent/status/patches/지연) → ✓검증(오류/누락/질문/미지원) → ↩폴백(사유). capsys 테스트 2건. 실모델 확인: LLM이 낸 잉여 질문 8개를 결정론 검증이 걸러 질문 0으로 정리되는 과정이 로그로 보임 | ✅ 완료 |
| 활성 전략 중 정의형 질문 무응답 수정 (2026-07-17, FR-SA-002c-4) | dev 실사용 사고: 전략 요약 후 "pbr이 뭐야?"가 GENERAL_INVESTMENT로 정확히 분류되고도 `conversationDecision.ts`의 `!hasCurrentStrategy` 게이트에 막혀 수정 파싱으로 흘렀고, 인터프리터가 CLARIFY로 정확히 판단한 질문마저 폴백이 버려 무변경 전략 요약만 재렌더링(질문 무응답). 수정 2겹: ① **프론트 라우팅** — GENERAL_INVESTMENT는 활성 전략과 무관하게 `answer_general`(history 포함, 기존 배선 재사용), UNKNOWN만 기존 게이트 유지 ② **백엔드 2차 방어선** — `run_primary_modification`이 CLARIFY(패치 없음)+질문을 폴백으로 버리는 대신 전략 유지+질문을 clarification 채널로 전달(`primary_modify_clarify`), 단 결정적 fast-path가 처리 가능한 단순 수정은 기존대로 폴백(과질문이 단순 수정을 가로막지 않게). 테스트: 프론트 2건+백엔드 3건, 백엔드 2033·프론트 965 전체 통과 | ✅ 완료 |
| 정의형 질문 무응답 2차 수정 (2026-07-17, FR-SA-002c-4) | 재발 실측: 인터프리터가 "pbr이 뭐야?"를 CLARIFY+질문이 아니라 `unsupported_features=["PBR 개념 설명 요청"]`(패치 없음)로 보고 → 2차 방어선(CLARIFY 채널)이 안 걸리고 침묵 폴백 → 무변경 요약 재렌더링. 수정 2겹: ① `run_primary_modification`에 3차 방어선 — 패치 없이 EXPLAIN_INDICATOR/unsupported_features만 보고되면 침묵 폴백 대신 전략 유지+notices로 미반영 안내(`primary_modify_unsupported`) ② 프롬프트 1.2 — 초안이 있어도 용어·개념 설명 질문은 EXPLAIN_INDICATOR이며 unsupported_features 금지 계약. 질문의 실제 답변은 프론트 라우팅(GENERAL_INVESTMENT→answer_general, 기구현)이 담당 — 백엔드는 오라우팅 시 침묵 방지가 역할. 테스트 2건 추가, 백엔드 2041·프론트 965 전체 통과 | ✅ 완료 |
| 정의형 질문 실제 설명 답변 (2026-07-19, FR-SA-002c-4) | 사용자 교정: "'전략은 변경하지 않았어요' 안내만 보여주지 말고 실제로 설명을 해줘야지". 3차 방어선이 안내 대신 답변하도록 — ① `/query/general`의 답변 생성을 `generate_general_answer` 동기 헬퍼로 추출(엔드포인트와 공유) ② `run_primary_modification`이 정의형 질문(결정적 cue `is_definition_question` 신설 — 4B 라벨 무관, 입력 기준)이면 LLM 설명을 생성해 notices로 전달(`primary_modify_explain`), LLM 미가용은 정직한 안내, 비질문 미지원 요청은 기존 미반영 안내 유지 ③ 되묻기 억제를 explain 모드에도 적용. 라이브 E2E: "pbr이 뭐야?" → PBR 설명 3문장 notices 반환(11.2s), 전략 무변경. 테스트 3건(설명 전달·LLM 미가용 폴백·비질문 미호출 가드), 백엔드 2042·프론트 965 전체 통과 | ✅ 완료 |
| 명시적 백테스트 날짜 유실 수정 (2026-07-17) | dev 실사용 사고: "백테스트를 2020년 1월 부터 2025년 12월 까지 해줘" → 배지 "백테스트 2020~"(종료일 유실). 원인 2중: ① 결정적 추출(`_extract_backtest_dates`)이 연도 전용이라 월 포함 표현 미인식 → LLM 위임 ② 인터프리터가 오늘 날짜를 몰라 "2025-12는 미래일 수 있음" 오판(assumptions 실측)으로 종료일 누락. 수정 4겹: ① 추출기 연+월(+일) 확장(종료 월=말일, 불가능한 날짜는 Fail Fast 미인식) ② **결정적 fast-path 우선 게이트** — `run_primary_modification`이 `_modify_rule_based` 처리 가능 입력에서 인터프리터 생략(LLM 왕복·드리프트 원천 회피) ③ primary 경로(파스·수정)에 `_override_explicit_dates` 결정적 날짜 오버라이드(레거시 `_apply_prompt_overrides`와 동형) ④ 인터프리터 프롬프트 오늘 날짜 주입+날짜 규칙 12(PROMPT_VERSION 1.1). 테스트 6건 추가(사고 재현 포함), 백엔드 2039·프론트 965 전체 통과 | ✅ 완료 |
| 재무 팩터 음수 데이터 처리 업그레이드 (2026-07-21) | 적자·자본잠식·음수 현금흐름 시 PER/PBR/ROE/PCR/EV-EBITDA/EV-EBIT가 금융적으로 무의미한 음수/왜곡값을 그대로 계산하던 것을 null 처리로 전환. **신규 모듈** `engine/fundamental_status.py`(순수 함수, `NEGATIVE_EARNINGS`/`NEGATIVE_EQUITY`/`NEGATIVE_CASHFLOW`/`NEGATIVE_EBIT`/`NEGATIVE_EBITDA`/`TURNAROUND`/`LOSS_TRANSITION`/`LOSS_NARROWED`/`LOSS_WIDENED`/`DIVIDE_BY_ZERO`/`MISSING_DATA` 상태코드는 parquet에 영속화하지 않고 원천 raw 컬럼에서 API/리포트 응답 시점 즉석 계산) + `data/fundamental-status-messages.json`(상태코드→한국어 설명, 프론트 공유). **원천 파서 확장**(`fundamental_fetcher.py`): income-statement의 raw 영업이익(`ebit`)·매출액을 더 이상 버리지 않고 보존, DART 응답(이미 매년 호출 중인 fnlttSinglAcntAll.json)에서 추가 API 호출 없이 CAPEX(`ifrs-full_PurchaseOfProperty...`/`...IntangibleAssets...ClassifiedAsInvestingActivities`, 2026-07-21 삼성전자/SK하이닉스/현대차 실측으로 계정ID 확정)와 자본총계(`ifrs-full_Equity`)를 신규 파싱, EV=ev_ebitda(KIS 비율)×ebitda(raw)로 역산해 EV/EBIT 신설, FCF=OCF-CAPEX 신설, EV/EBITDA 0.00 센티널 삭제 로직을 "비양수 전체 삭제"에서 "0.00만 삭제"로 수정(진짜 음수 보존). **성장률 로컬 재계산**: KIS가 직접 제공하는 영업이익/순이익 증가율은 부호 왜곡 가능성 때문에 신뢰하지 않고 raw 값(ebit·net_margin×revenue)으로 연도별 로컬 재계산 + 신규 EPS/EBITDA/영업현금흐름/FCF 증가율 4종(모두 흑자↔적자 전환 시 일반 공식 대신 TURNAROUND/LOSS_TRANSITION/LOSS_NARROWED/LOSS_WIDENED 상태코드로 분류, `_compute_derived_annual_metrics`). **랭킹 버그 수정**(`backtest_engine.py`): value+quality 랭킹이 결측 PBR/ROE를 `fillna(1.0)`/`fillna(0.0)` 중립값으로 위장시켜 자본잠식 종목이 "최고 가치주"로 최상위 랭크되던 결함 제거(NaN을 percentile rank까지 보존해 자연 배제) + 가중치 0인 팩터의 NaN이 `NaN*0=NaN` 전파로 종목 전체를 배제하던 별도 버그 수정. **스크리닝 배선**: `ev_ebit`/`eps_growth`/`ebitda_growth`/`ocf_growth`/`fcf_growth` 5종 신규 지표를 `signals.py`/`fundamental-factors.json`/`condition_builder.py`/`nl_parser.py`/`indicator_registry.py` 전 계층에 배선(PCR은 기존 미지원 정책 유지, 손대지 않음). 프론트(`StockDetail.tsx`/`stock-order` 등)는 기존 truthy 체크가 이미 null-safe라 코드 변경 불필요(백엔드가 null만 반환하면 자동 "—" 표시). 테스트 다수 신규(`test_fundamental_status.py` 등)+기존 재작성(`test_enrich_negative_eps_produces_negative_per`→`_nan_per`), 백엔드 전체 통과. **prod 반영 완료(2026-07-21)**: `merge_fundamentals`가 combine_first(기존값 우선)라 재백필로 자가 치유되지 않는 문제를 신규 `scripts/fix_negative_fundamental_ratios.py`(추가 API 호출 없이 이미 저장된 eps/bps로 로컬 재계산, PER/PBR/ROE 강제 보정)로 해결 — 로컬 5,055개 중 2,557개 종목·약 354만 셀 보정. `mirror_data.py --push`(디렉터리 전체 push)는 프로덕션이 그사이 자체 일일 스케줄러로 갱신한 무관한 종목(~1,578개)까지 로컬 stale 데이터로 덮어쓸 위험이 있어(dry-run으로 발견), `rsync --files-from`으로 보정한 2,557개 파일만 스코프를 좁혀 push — 프로덕션 반영 확인 완료(재-dry-run 차이 0건). **신규 컬럼(EBIT/CAPEX/자본총계/FCF/EV/EV-EBIT·성장률 4종) 전 종목 백필 완료(2026-07-21)**: `scripts/backfill_fundamentals.py --force`로 로컬 5,055종목 재수집(KIS 5엔드포인트+DART, 오류 0건, 약 3시간) — 2,723개 enriched·1,557개 market_cap_only·775개 no_data(DART 미제공 종목). 실측 검증: 삼성전자(정상 성장 이력)·000040(적자 이력)에서 TURNAROUND/LOSS_TRANSITION/LOSS_NARROWED/LOSS_WIDENED 상태코드가 실제 API 응답 기준으로 정확히 분류됨을 확인. 갱신된 4,280개 파일만(mtime 기준) `rsync --files-from`으로 스코프를 좁혀 프로덕션 반영 완료(재-dry-run 차이 0건) | ✅ 완료 |
| 빌더 퍼징 QA 19결함 일괄 수정 (2026-07-24) | 적대적 퍼징(가상 사용자 1,200명·step 14,725턴, `scripts/qa_builder_fuzz.py`)으로 발견한 BF-01~19 전부 수정(`docs/builder_fuzz_qa_report.md`). ① 취소어 오인 가드 — "됐어, 손절 10%로"·"취소하지 말고"가 빌더를 날리던 버그(`_CANCEL_NEG_RE`·`_PROCEED_CUE_RE`) ② 정의 질문 필드 오염 차단 — "볼린저가 뭐야?"가 전략 유형을 확정하던 버그(글로서리 8종 확장+미커버 용어 폴백 안내, 정의 질문은 파싱 차단) ③ 정정 경로 — 변경 cue(`바꿔|말고|…`) 있으면 채워진 유니버스·유형 덮어쓰기+유형 특화 파라미터 리셋, "3개월 말고 6개월"은 마지막 조각 채택(`_correction_focus`), 청산 정정은 키워드 재부착(`_apply_risk_correction`) ④ 값 검증 — 손절/트레일링 0~100%·익절>0을 입력 시점 검증(범위 밖은 게이트 통과 전 되묻기+사유, LLM 백스톱 값도 동일), RSI 0~100·과매도<과매수(라벨 모순은 재정렬 금지)·MA 단기<장기·기간 2~250·종목 수 1~100(조용한 클램프 제거) ⑤ 가치 방향 가드 — "PBR 5 이상"을 PBR≤5로 뒤집지 않고 안내 ⑥ 필터 스텝 무관 입력 비소비 ⑦ 빌더 중 단일 종목 요청("삼성전자만 테스트") 안내 ⑧ ETF×가치 차단 사유 설명 ⑨ '10프로/퍼센트/퍼' 결정적 인식(빌더 `_PCT_NUM_RE`+메인 파서 `_compact` % 정규화) ⑩ 복합 답변 체이닝(RSI 기간+라벨 경계, MA 종류+기간) ⑪ 연속 미인식 2회부터 이해 실패 안내(`BuilderState.miss_streak`) ⑫ 미지원 지표 감지 확장(이치모쿠·VWAP·PEG·PCR·피보나치·엘리엇·캔들패턴 — '도지'는 '정도 지나면' 충돌로 문맥 한정) ⑬ restart 시드 승계("처음부터. 코스닥으로")+단일 종목 유지. 테스트 19종 추가(builder 17·nl_parser 2), 하니스 재실행 159→0 실패, 백엔드 2,359·프론트 1,066 전체 통과 | ✅ 완료 |
| 흑자/적자 조건 지원 승격 + 검증 화이트리스트 SOT 동기화 (2026-07-24) | 스크린샷 사고 2건 동시 수정. **사고 1(검증 오탐)**: "작년도 흑자종목" 전략의 진입 필터가 전략 검증 패널에서 "현재 시스템에서 지원하지 않는 필드입니다"로 차단 — `StrategyValidationAgent._SUPPORTED_CONDITIONS` 하드코딩 사본이 펀더멘털 팩터 확장(순이익증가율·ROA·PSR 등)과 후기 기술 지표(williams_r/mfi/roc)를 반영하지 못한 드리프트. 재무 지표는 `engine.signals.FUNDAMENTAL_CIDS`(SOT) import로 대체하고 기술/리스크 세트만 유지(`_TECHNICAL_CONDITIONS`/`_RISK_CONDITIONS`). **사고 2(파싱 환각)**: "흑자"가 미지원 개념(`profitability_sign`)이라 LLM 폴백을 탔고 LLM이 `순이익증가율 >= 100`으로 환각(흑자=부호 조건≠증가율). parquet에 이미 있는 `eps` 컬럼으로 정식 지원 승격 — ① `FUNDAMENTAL_LABELS`/`FundamentalFilter.metric`/프론트 `METRIC_LABELS`에 `eps` 추가(제네릭 필터 eval·컴파일 경로 그대로 통과, NaN fail-closed 확인) ② `_extract_fundamental_filters`에 값 없는 키워드 결정적 추출(`_keyword_profitability_operator`): 흑자→eps>0, 적자 제외/아닌→eps>0, 적자만→eps<0, 현금흐름·영업이익 등 다른 항목의 부호 언급은 문맥 가드로 제외(LLM 위임) ③ 미지원 목록은 제거 아닌 조건화(커버리지 가드 원칙) — `profitability_sign`→`profitability_transition`(흑자전환·N년 연속 등 시계열 형태만, 추출 가드와 동일 패턴 공유) ④ LLM 폴백·parse_validator 프롬프트에 eps 매핑 지침+순이익증가율 오해석 금지 명시 ⑤ indicator_registry 승격(`fundamental.eps`, 흑자/적자 alias 재배선, 전환은 unsupported 유지) ⑥ 프론트 배지는 사용자 어휘로("흑자 기업 (EPS > 0)"). 원본 사고 입력이 LLM 없이 결정적으로 정확 파싱됨을 회귀 테스트로 고정. 테스트: 백엔드 신규 13(validation SOT 가드 1·nl_parser 12)+기존 1 갱신·프론트 신규 3 — 백엔드 2,371·프론트 1,069 전체 통과. SRS FR-STR-023d | ✅ 완료 |
| 첫 응답 전략 재정리 문장 (2026-07-24) | 사용자 교정: 전략 입력의 첫 응답이 "작년도 순이익이 흑자인 종목 중에서 PER이 10 이하인 저평가 종목을 매수하는 전략이군요."처럼 사용자의 자연어를 백테스트 가능한 전략 개념으로 정리해 되돌려주며 시작해야 한다(단순 반복이 아닌 개념 재정리). 신규 `app/analytics/new/strategyRestatement.ts::buildStrategyRestatement` — 파싱 결과에서 결정적으로 문장 합성: 재무 필터 서술절(eps 부호→"순이익이 흑자/적자", 시총 억/조 한글 단위, 받침 기반 이/가 조사 선택 — 라틴 약어·숫자 한국어 독음 받침 매핑), 진입 신호 트리거절(임계값 비교="…일 때"·이벤트형="…가 발생하면", `getSignalLabel` 재사용), 모멘텀 랭킹("N일 수익률 상위 종목"), 업종/명시 유니버스 접두어(`hasExplicitUniverse` — 기본 양시장은 되풀이 안 함). 매수 기준 없음·지정 종목(별도 빌더/되묻기 흐름)은 생성 안 함. `finalizeParse`가 요약 패치에 포함해 요약 카드·되묻기보다 먼저 렌더(후행 검증 교정 시 함께 갱신), 지표 연구 질문은 제외. 테스트 `strategyRestatement.test.ts` 11건 — 프론트 1,089 전체 통과 | ✅ 완료 |
| 확정된 완성 전략 재되묻기 수정 (2026-07-24) | 스크린샷 사고: 8/8 조건을 다 채우고 "이 전략으로 확정"까지 눌렀는데 "어떤 조건으로 종목을 선택할까요?"를 다시 물어 백테스트로 진행 불가. 원인: 확정 시 누적 프롬프트를 인터프리터(primary)가 재파싱 → LLM이 '흑자 기업'을 진입에서 통째로 누락 → 완결성 검증이 진입 누락 질문을 냄. 그런데 `_apply_prompt_overrides`가 흑자→eps>0 필터로 **결정적으로 되살려** parsed엔 진입이 있는데(요약 카드는 "흑자 기업 (EPS > 0)" 표시) 되묻기 질문만 잔존 — 완결성 검증이 보정 **전** intent에 대해 돈 탓의 불일치. 수정 2겹: ① **백엔드 근본 수정** — `run_primary_parse`가 `_apply_prompt_overrides` 직후 `_prune_clarifications_filled_by_overrides`로 보정이 채운 조건(진입: entry_signals/fundamental_filters/ranking_metric/target_symbols, 청산: exit_signals/hold_period/정기 리밸런싱/손절·익절·트레일링)의 되묻기 질문을 제거 ② **프론트 안전망** — `presentStrategyClarification`의 `shouldSuppressContradictedQuestion`에 "종목을 선택" 질문이 진입 조건 있는 parsed에 모순되면 억제(기존 배당·상위 몇 종목 억제와 동일 패턴). 테스트: 백엔드 1(`test_primary_entry_restored_by_override_drops_entry_question`)·프론트 1(`clarificationPresentation.test.ts`) — 백엔드 strategy_conversation+nl_parser_overrides 590·프론트 analytics/new 365 전체 통과 | ✅ 완료 |
| 전략 확정 재파싱 제거 — 누적 전략 직접 컴파일 (2026-07-24) | 위 재되묻기 수정의 잔여 사고: "영업이익 흑자인 기업 투자 전략"은 결정적 eps 필터의 문맥 가드(`_PROFITABILITY_CONTEXT_EXCLUDE_RE` — 영업이익·현금흐름의 부호 언급은 eps로 표현하면 왜곡이라 LLM 위임)에 걸려 `_apply_prompt_overrides`가 되살릴 수 없는 LLM 전용 조건이다. 확정 시 결정적 조건 플로우(`confirmDeterministicStrategy`)가 대화 전체를 재파싱(previous_parsed 없이 primary LLM 재해석)하던 구조라, 재해석 LLM이 이 필터를 비결정적으로 누락하면 진입 조건이 통째로 사라져 요약 카드에서 매수 조건이 실종되고 "다음으로 어떤 조건에서 매수할지 정해볼까요?"를 다시 묻는 사고(스크린샷). 근본 수정: 확정은 재해석이 아니라 컴파일 — ① 신규 `POST /strategy/compile`(`api/intent_routes.py`): 누적 ParsedStrategy dump를 진실로 삼아 `enforce_strategy_minimums`+`to_backtest_request`만 수행(특화 빌더 `_run_builder_step` confirmed의 '한국어 재파싱 왕복 없이 그대로 적용' 계약과 동형)+Next 프록시 `app/api/strategy/compile/route.ts` ② 프론트 `confirmDeterministicStrategy`가 `runStrategyParseFlow` 재파싱 대신 누적 `latestParsed`를 compile로 보내고 기존 `applyBuilderConfirmedStrategy`로 적용(코치·요약·실행 버튼 동일). LLM 왕복이 사라져 확정 지연도 제거. 테스트: 백엔드 4(`test_strategy_compile.py` — LLM 전용 필터 보존·설정 유지·하한선 보정·422)·프론트 신규 1(`page.confirm.test.tsx` — 확정 시 재파싱 0회+compile 1회+매수 조건 재질문 없음)+기존 2 갱신(scroll·unknown-intent, 재파싱 계약→컴파일 계약) — 백엔드 2,377·프론트 전체 통과 | ✅ 완료 |
| 영업이익 흑자/적자 조건 지원 승격 (2026-07-24) | 스크린샷 사고: "영업이익 흑자인 기업 투자 전략"의 첫 응답 재정리 문장이 "영업이익증가율이 0 이상인 종목을 매수하는 전략이군요."로 노출 — 결정적 eps 부호 필터의 문맥 가드가 '영업이익 흑자'를 LLM에 위임했는데 LLM이 부호 조건을 증가율(operating_income_growth>=0)로 환각 파싱(순이익 쪽 금지 지침만 있고 영업이익 쪽이 빠짐), 재정리 문장이 그 DSL을 그대로 읽음(요약 규칙 위반: 개념 치환+수학식 노출). parquet에 raw `ebit`(영업이익, 억원) 컬럼이 이미 있어 eps 승격(FR-STR-023d)과 동일 패턴으로 정식 지원 승격 — ① `_keyword_profitability_operator`→`_keyword_profitability_filters` 재설계: 흑자/적자 키워드 직전 문맥으로 metric 라우팅(무문맥=eps, '영업이익/영업'=ebit, 현금흐름·OCF/FCF=LLM 위임 유지), '적자 제외'의 이중 매치는 항목별 positive 우선으로 해소, 한 문장 혼합("순이익도 흑자, 영업이익도 흑자")은 둘 다 추출 ② `FUNDAMENTAL_LABELS`/`FundamentalFilter.metric`/프론트 `METRIC_LABELS`에 `ebit` 추가(제네릭 필터 eval·컴파일 경로 그대로 통과) ③ LLM 폴백·parse_validator·modify_knowledge에 ebit 매핑+증가율/이익률 오해석 금지 지침 ④ indicator_registry `fundamental.ebit` 승격+영업이익 alias ⑤ 프론트 배지 "영업이익 흑자 기업"·재정리 문장 "영업이익이 흑자인 종목을 매수하는 전략이군요."(전략 요약 생성 규칙 준수 — 수학식·임의 지표 치환 금지). 흑자전환·연속 시계열 형태는 여전히 미지원(profitability_transition) 유지. 테스트: 백엔드 신규 7(문맥 라우팅 5·혼합 1·스크린샷 재현 결정적 파싱 1)+기존 1 갱신(영업이익 문맥이 '미추출'→'ebit 추출' 계약으로)·프론트 신규 3(배지 2·재정리 1) — 백엔드 2,383·프론트 1,094 전체 통과 | ✅ 완료 |
| 용어 그라운딩 — 인터넷 검색 기반 테마 용어 학습 (2026-07-24) | 스크린샷 사고: "ess 관련 투자 전략을 만들어 볼까?"에서 빌더가 ESS를 전혀 인식 못 하고 시드를 버린 채 빈 플로우로 시작 — `sector_hint`는 잡혔지만(`_mentioned_unsupported_concepts`) `llm_extract_sector`(4B 내부 지식)가 매핑 실패. 신규 `engine/term_grounding.py::resolve_sector` — 빌더 sector_resolver를 어휘집 결정적 조회 → 내부 지식 LLM(기존) → **인터넷 검색 그라운딩** 체인으로 확장(`api/intent_routes.py` 배선). 그라운딩: LLM 용어 추출("ESS") → 네이버 API 허브 검색(백과사전+웹문서, `X-NCP-APIGW-API-KEY-*` 헤더 — 구 openapi.naver.com과 인증 다름, 401 삽질 기록) → 스니펫 근거로 LLM이 정의+지원 업종 매핑 → `normalize_sector` 게이트. **같은 용어 재검색 금지**: 검색 수행 시 결과(정의·업종·출처·시각)를 성공/매핑불가 모두 `data/term_lexicon.json`(gitignore)에 영속 저장, 이후 결정적 해석(실측 ESS 1차 9.9s → 2차 0.000s). 검색 호출 실패는 캐시하지 않음(복구 후 재시도). 라틴 약어 lookaround 경계('process'≠'ess'), 그라운딩 프롬프트에 인젝션 방어(본문 지시 무시) 명시, 자격증명 미설정 시 그라운딩만 조용히 비활성. 한계: 테마를 기존 지원 업종으로 근사(종목별 테마 멤버십은 향후). prod 반영 시 Vultr `.env`에 NAVER_CLIENT_ID/SECRET 수동 추가 필요. 테스트: 신규 7(`test_term_grounding.py` — 캐시 계약·게이트·경계·실패 비캐시) — 백엔드 2,404·프론트 1,128 전체 통과. SRS FR-STR-069 | ✅ 완료 |
| 용어 그라운딩 '검색 중...' 진행 표시 (2026-07-24) | 인터넷 검색 진입 시 로딩 버블이 '분석 중...' 대신 '검색 중...'을 표시(사용자 요청). 빌더 스텝을 SSE로 승격 — ① `resolve_sector`에 `on_search` 콜백(검색 그라운딩 ④ 실제 진입 시에만 1회, 어휘집/그래프/내부 LLM 히트 시 미호출) ② 신규 `POST /strategy/builder/step-stream`(`api/intent_routes.py`): parse-stream의 thread+stage_holder 폴링 패턴 재사용, `stage:"searching"` → `result`(기존 StepResult 계약 그대로) 순 방출, 기존 POST는 호환 유지, LLM 헬퍼 쌍은 `_builder_llm_helpers`로 공유 추출 ③ Next 프록시(`builder/step/route.ts`)는 URL 유지한 채 백엔드 SSE 파이프(timeoutMs 120s) ④ 프론트 `requestBuilderStepData` 헬퍼: content-type으로 SSE/JSON 분기(기존 테스트 mock JSON 계약 무수정 호환), 3개 호출부(시드 진입·이전으로·빌더 턴) 교체, `loadingStage:"searching"`+`ANALYSIS_STAGE_LABEL` "검색 중..." 추가. 테스트: 백엔드 신규 4(`test_builder_step_stream.py` 3 — result 계약·searching 순서·error 이벤트, on_search 발화 조건 1) — 백엔드 2,415·프론트 1,128 전체 통과, 선재 tsc 테스트파일 에러 외 클린. SRS FR-STR-069 ⑤ | ✅ 완료 |
| Investment Knowledge Graph Phase 1 — 투자 지식 그래프 (2026-07-24) | 용어 그라운딩(FR-STR-069)의 평면 '용어→섹터' 매핑을 노드·엣지 그래프로 일반화 — 개념·산업·공급망·기업·ETF·지표·매크로를 관계로 잇는 IKG 기반 구축(설계 `docs/knowledge_graph.md`). 신규 `engine/knowledge_graph.py`: 시드(`data/knowledge-graph.json`, 개념 30노드·관계 100여 엣지 — HBM 공급망·전력기기·원자력/SMR·ESS/양극재·휴머노이드·바이오시밀러·LNG/조선 등, 종목·ETF 심볼 전건 정본 검증) + 섹터 노드(CANONICAL_SECTORS 자동) + 기업/ETF 노드(korea-stocks·etf-master 참조 시 자동, 오타 fail-fast) + 학습 노드(term_lexicon 오버레이 편입 — 검색 학습이 그래프도 키움)를 로드 시 합성(mtime 캐시). 결정적 개념 스캔은 normalize_sector 어휘와 충돌 용어 자동 제외(이중 매칭 방지)+라틴 lookaround 경계. 섹터 해석은 소속 엣지(is_a/part_of/belongs_to)만 깊이 3 탐색, 모호(복수 섹터·다업종 테마)면 None으로 기존 폴백 유지 — FR-STR-069 체인의 ①b 단계로 배선(시드 개념은 LLM·검색 0회: "SMR"→에너지/원자력). `related_universe()`가 관계 근거(via) 포함 섹터·기업·ETF·개념 확장 반환(Phase 2에서 지정 종목 유니버스·UI 배선 예정). 규제 안전: 객관적 관계만 저장, 추천·전망 노드/엣지 금지. 테스트: 신규 7(`test_knowledge_graph.py` — 시드 무결성 0위반·스캔 유일성/충돌 제외·경계·섹터 해석·확장·학습 오버레이·체인 단락)+기존 4 갱신(시드 개념이 된 ESS/SMR→그래프 밖 용어로) — 백엔드 2,411·프론트 1,128 전체 통과. SRS FR-STR-070 | ✅ 완료 |
| 데이터 스케줄러 시각 변경 — 00:00→21:00(정본)/21:15(미러) (2026-07-25) | 프로덕션 OHLCV 권위 sync가 매일 00:00 KST에 돌던 것을 21:00으로, 로컬 미러 pull은 정본 sync 완료 여유(15분)를 두고 21:15로 변경 — 장 마감(15:30 KST) 이후 당일 시세가 FDR/KIS에 정착할 시간을 확보하려는 의도(`scripts/scheduler.py`). ① 일일 발사 조건을 '날짜 변경'(자정 경계 의존)에서 **목표 시각 도달**(`(hour,minute)>=target`)로 재설계 — 절전에서 늦게 깨어나도 target 이후 첫 tick에 즉시 실행되는 캐치업 성질은 유지하면서, 같은 날 target을 다시 만나도 중복 실행하지 않도록 시작 시 이미 오늘분을 처리했으면 `last_sync_date`를 오늘로 찍는다. ② `_last_expected_trading_day`(캐치업 판정용 '기대 거래일' 계산)를 시각 인지로 재설계 — 21:00 이전엔 여전히 '직전 평일'을, 21:00 이후엔 '당일'을 기대치로 삼는다(00:00 sync 시절엔 항상 직전 평일이 기대치였음). `docker-compose.yml` scheduler 서비스 주석 동기화. 코드베이스 자체는 정규장을 09:00~15:30으로 다뤄(`market_data.py`·`virtual_trader.py`) "장이 저녁 8시에 끝난다"는 사용자 전제와는 어긋남을 안내했으나, 21:00이라는 목표 시각은 명시 지시대로 반영. 테스트: 기존 9건 전원 통과(테스트 헬퍼가 09:00 고정이라 21:00 이전 분기만 검증하던 것 확인) + 신규 6건(21:00 경계 정확히·이후·주말 미전이·데이터 신선/캐치업 시나리오) — `test_scheduler_catchup.py` 15건, 백엔드 2,436 전체 통과 | ✅ 완료 |
| 섹터 오분류 9종목 근본수정 — '어로' 부분매칭·'총포탄' 부재·오버라이드 심볼 오기 (2026-07-24) | IKG 시드 검증 중 발견: ① 수산 키워드 낱말 '어로'가 사명 부분매칭으로 '에**어로**스페이스'(한화에어로스페이스·켄코아에어로스페이스)·'히**어로**'(키움히어로스팩 1·2호)를 수산으로 오분류 — 수산이 우선순위 목록에 있어 산업분류('항공기,우주선 및 부품 제조업')보다 사명 매칭이 먼저 이김(해성에어로보틱스 사고 때 로봇 선점만 하고 키워드를 남긴 잔재). '어로' 제거(실제 수산 업종은 '어로 어업'/'어업'으로 전부 커버) ② KSIC '무기 및 총포탄 제조업'(LIG디펜스앤에어로스페이스·퍼스텍·삼양컴텍) 매핑 키워드 부재로 수산/기타 제조업에 흩어짐 — '총포탄' 추가('무기'는 '기초 무기 화학물질 제조업' 충돌로 금지) ③ `OVERRIDDEN_SYMBOLS` 심볼 오기: 우성을 006910으로 적어 보성파워텍이 사료/축산 — 우성=006980 교정+보성파워텍은 에너지/원자력 오버라이드(전력기기 제조, KSIC '구조용 금속제품…'이 화학 '금속' 오귀속). 적용: 전수 재계산 dry-run으로 diff 9건 확인 후 `data/korea-stocks.json` 9건+해당 `data/ohlcv/*.parquet` sector 컬럼 9건 교정(parquet은 stock_analysis·stock_profile이 우선 읽는 SOT, mtime 변경으로 프로파일 캐시 자동 무효화). 상폐 501종목(`get_sector_from_krx_industry`) 영향 0. 방산 섹터 유니버스에서 한화에어로스페이스가 조용히 빠지던 실사용 버그 해소. 주의: `scripts/enrich_sectors.py`는 규칙 중복 구세대(불일치) — 재실행 금지. prod 반영: 코드·JSON은 커밋·배포, parquet은 push-data/재수집. 테스트: 신규 5(`test_sector_mapper.py` — 에어로/히어로 회귀·어업 유지·총포탄 방산·무기≠방산·오버라이드 교정)+기존 1 예시 교체('무기 및 총포탄'→'악기 제조업') — 백엔드 2,419·프론트 1,128 전체 통과 | ✅ 완료 |
| 테마 관련 투자 라우팅 + 일반답변 용어 정의 주입 (2026-07-24) | 스크린샷 사고: "ess 관련 투자"가 결정 규칙 UNKNOWN → LLM 일반답변으로 새서 ESS를 '에너지 효율성·저탄소'로 환각 정의+성장 잠재력 평가(규제 위반 표현). Knowledge Graph 원인 아님(KG는 빌더 섹터 체인 전용). 수정 2겹 — ① **분류**: `_THEME_INVEST_CUE`("관련 주/투자/종목/산업/테마"·"테마주") 결정 규칙 1에 합류 → STRATEGY_ADVICE(빌더 시드→그라운딩 체인 관통). 가드 3종: 열린 추천(`is_stock_pick_request`)=STOCK_PICK 유지, 종목명+행동질문=STOCK_ANALYSIS 유지, 정의형(`pure_definition`)=미가로챔 ② **일반답변 사실 주입**: `term_grounding.general_facts_block` — KG 시드 개념(description+ESS 등 31노드) → 어휘집 → 검색 그라운딩(재검색 금지 캐시) 순으로 검증 정의를 `_build_general_user_msg` facts에 합류(glossary_facts 동형), 전망·성장성 평가 금지 지시 포함, 기초 용어 질문은 `allow_search=False`로 검색 스킵, `_ground_and_learn` 공통 헬퍼로 resolve_sector ④와 로직 공유. 테스트: 분류 신규 2(테마 4케이스 파라미터+가드)·grounding 신규 3(KG 결정적/그라운딩 학습·캐시/검색 스킵 3분기) — 백엔드 2,427·프론트 1,128 전체 통과. SRS FR-SA-002c-7 | ✅ 완료 |
| 지식그래프 학습 편입 — 관계 엣지 자동 생성+검증 (2026-07-25) | 사용자 제안(검색→근접노드→노드→엣지→신뢰도→검증 편입) 구현, FR-STR-070b. 설계 조정: 근접 노드 탐색은 LLM이 아니라 **결정적**(스니펫 본문에 실제 등장한 시드 개념만 후보 앵커 — `knowledge_graph.find_concepts` 재사용, 닫힌 세계로 노드 환각 차단). ① `term_grounding._propose_edges`: LLM은 후보 목록 안에서 관계 유형만 선택(객관적 서브셋 7종 — is_a/part_of/belongs_to/related_to/uses/supplier/competitor, 추천·전망 관계 금지), 후보 밖 타깃·미허용 유형 게이트 드롭 ② 신뢰도=출처 수(LLM 자기보고 비신뢰): 교차지지 ≥2 자동 verified / 1개 pending, 엣지는 어휘집 엔트리 `edges`에 저장(git 시드와 출처 분리) ③ KG 로더: verified만 그래프 합성(타입·타깃 재검증), 섹터 없이 verified 엣지만 있어도 노드 편입 ④ 운영 콘솔 Knowledge 탭+`/api/admin/knowledge`(requireAdmin 404 은닉·감사 로그·원자적 파일 쓰기·TERM_LEXICON_PATH 테스트 주입): verified 사후 반려·pending 수동 승인·용어 삭제(재학습 가능), 로더는 mtime 자동 재로드. 실측: 'CoWoS' 학습(10.2s) — 섹터 반도체·정확한 정의, LLM의 부정확 엣지(part_of→메모리 반도체)는 출처 1개라 pending 억류(게이트 의도대로 동작). 함정 기록: 섹터 어휘(양극재 등)는 KG 스캔 인덱스에서 의도적 제외라 앵커 불가(normalize_sector 이중 매칭 방지 설계). 테스트: 백엔드 신규 3(앵커·자동승격·드롭/무앵커 스킵/로더 verified 합성)·프론트 신규 6(admin route — 404 은닉·승인/반려/삭제·감사 로그) — 백엔드 2,430·프론트 1,134 전체 통과 | ✅ 완료 |
| 파싱 경로 KG 섹터 배선 — "ess 관련 투자" 소실 수정 (2026-07-25) | 실측: 재시작 후에도 "ess 관련 투자"가 빈 빌더 가이드로 시작. 추적 결과 빌더 미진입 — STRATEGY_ADVICE→**파싱 파이프라인**→인터프리터 UNSUPPORTED_REQUEST 폴백→규칙 파서에서 ESS 소실→빈 전략 최소 조건 게이트("먼저 어떤 시장·종목을..."=프론트 backtestReadiness 문구, 빌더 질문 아님). KG는 빌더 sector_resolver에만 배선돼 있었음. 근본 수정: `nl_parser._extract_sector`에 KG 폴백 합류(`_KG_SECTOR_CUE_RE` — 섹터/업종/관련/테마 큐 동반 시에만 `resolve_sector_from_text`, 큐 없는 개념 언급 오폭 방지) — 공유 추출기라 규칙 파스·시드·수정(`_sector_change_from_utterance` (True,'이차전지') 확인)·LLM 폴백 복구(`_apply_prompt_overrides`)·미지원 안내 억제(3250행) 전 경로 자동 관통. 라이브 서버 step-stream 직접 호출로 빌더 경로 정상(sector=이차전지) 재확인 — 문제는 파싱 경로뿐이었음. 테스트: 신규 1(`test_sector_nl_synonyms.py::test_kg_seed_terms_resolve_with_sector_cue_only` — ESS/SMR/HBM 해석+큐 게이트+안내 억제) — 백엔드 2,437 전체 통과. SRS FR-STR-070 ④ 확장 | ✅ 완료 |
| 파싱 경로 검색 그라운딩 — "마운자로 관련주" 미지원 처리 수정 (2026-07-25) | 실측: "마운자로 관련주 전략을 만들어보자"가 파싱 경로(인터프리터 primary)로 흘러 인터넷 검색 없이 unsupported_features 처리 — 검색 그라운딩(FR-STR-069)이 빌더 sector_resolver에만 배선돼 있었고, 07-25 KG 배선은 결정적 조회(①b)만이라 미학습 용어의 최초 검색 학습이 파싱 경로에 없었음. 수정 4겹 — ① `term_grounding.learn_sector_term`: 파싱 경로 사전 학습 진입점(게이트=`nl_parser.mentions_unresolved_sector` — 업종 큐는 있는데 결정적 추출 실패, 섹터 되묻기와 동일 판정). `_run_nl_parse`(main.py)가 파싱 전에 호출(`_learn_unknown_sector_term` — inference lock 공유, 실패 무해, 학습 성공 시 해석 안내 notice+defer_holder extra_notices로 후행 검증 재빌드에도 보존) ② **학습분 어휘집 스캔 폴백**: learned 노드는 KG 스캔 인덱스에서 의도적 제외(이중매칭 방지)라 KG 배선만으론 학습분을 못 읽음 → `_extract_sector`에 `lexicon_entry`(mtime 캐시 신설) 폴백 합류 — 규칙·인터프리터 오버라이드·수정 전 경로 관통 ③ primary 정리: `_prune_clarifications_filled_by_overrides`가 sector 채움 시 `strategy.universe.sectors` 질문 제거+같은 테마를 가리키는 unsupported_features 필터(`_extract_sector` 해석되면 드롭 — "반영 안 됐어요" 모순 안내 방지) ④ parse-stream `stage:"searching"` 방출+프론트 수용(라벨 기존 재사용). 라이브 검증: 마운자로→바이오/제약(정의·출처 어휘집 저장), 재요청 재검색 0회. 테스트: 신규 3(`test_term_grounding.py` 사전학습 관통/게이트, `test_strategy_conversation.py` 질문 prune) — 백엔드 2,440·프론트 1,134 전체 통과. SRS FR-STR-069 ⑥ | ✅ 완료 |
| 테마 관련 상장사 학습 + 테마 유니버스 되묻기 (2026-07-25) | 사용자 요구: "마운자로 관련주 전략"은 바이오/제약 전체가 아니라 관련주만 백테스트해야 함. FR-STR-071 — ① `_propose_company_edges`: 스니펫 등장 상장사를 정본 마스터 매칭(find_in_text, 해외 제외)으로 `related_company` 엣지 수집(**LLM 무관여** — '함께 언급'은 객관적 사실), 출처 ≥2 verified / 1 pending(콘솔 검토), 뉴스 쿼리 `"{용어} 관련주"` 8건 추가(4건 실측=전부 pending) ② first_known_date=뉴스 보도일 최솟값(시점 편향 1단계 — 정식 시점별 멤버십은 별도 프로젝트) ③ KG 로더가 verified 기업 엣지의 company: 노드 자동 생성(정본 밖 심볼은 issues 없이 스킵, resolve_endpoint report 파라미터) ④ `detect_theme_universe_clarification`: 자동 적용 대신 목록+출처+편향 경고 되묻기, 칩 왕복 계약(종목명+'종목 전체를 함께'+'YYYY년부터' — '관련주/테마' 단어는 TARGET 가드가 차단하므로 금지), `detect_symbol_ambiguity`에 집합 의도 큐('전체/모두/함께') 억제 추가 ⑤ 테마 질문은 clarification_priority="theme_universe"로 인터프리터 질문에 안 덮임(apply_primary_meta 가드+NLParseResponse 스키마 필드 — response_model 필터 함정 재확인). 라이브 왕복: 마운자로→한미약품 verified·펩트론 pending, 칩→symbols=[128940]+startDate=2026-01-01. 테스트: 신규 3(기업 엣지 학습·칩 왕복·KG company 노드) — 백엔드 2,443·프론트 1,134 전체 통과. SRS FR-STR-071 | ✅ 완료 |
| KG 읽기 경로 통합 — 학습 용어 스캔 인덱스 편입 (2026-07-25) | 사용자 설계 리뷰("어휘집이 따로 필요한가? KG로 편입하자") 반영 — 어휘집=**학습 원장**(영속 저장·부정 캐시·pending 검토 대기열·출처 증거)으로 역할 한정, **지식 읽기는 그래프 단일 경로**로 통합. ① `_build_scan_index`: learned 노드 포함(제외 조건을 sector:/company:/etf: 접두사로 교체), 시드·학습 용어 충돌 시 시드 우선(taken dict — 큐레이션 우선, 비결정적 인식 방지) ② 로더: 학습 엣지에 support/first_known_date 실어 나르기+learned 노드에 searched_at ③ `KnowledgeGraph.listed_companies`(깊이 1)+`theme_listed_companies`를 knowledge_graph로 이동(학습=어휘집/시드=그래프 이원 분기 제거) ④ `_extract_sector`의 어휘집 스캔 폴백 제거 — KG 폴백이 시드·학습 공통 해석 ⑤ 매핑 불가 항목은 노드가 아니므로 스캔에도 없음(부정 캐시는 원장 담당) — resolve_sector 내부의 원장 자기 조회(재검색 금지)는 유지. 부수 효과: 학습 용어도 엣지 학습 앵커·related_universe 앵커 가능. 라이브: 콘솔 승인분 포함 5개사(펩트론·한미약품 등) 그래프 경로로 서빙 확인. 테스트: 신규 1(스캔 편입·시드 우선·부정캐시 비스캔)+기존 3건 그래프 경로로 갱신 — 백엔드 2,444·프론트 1,134 전체 통과. SRS FR-STR-070 ③·069 ⑥·071 ④ 갱신 | ✅ 완료 |
| Concept–Stock Knowledge Builder 첫 실행 — 시드 확장 절차 확립 (2026-07-25) | 사용자 제공 빌더 프롬프트(공식 근거 기반 Concept 발굴→ETF 후보→공시·공식자료 검증→관계유형·관련도 점수화)로 IKG 시드 확장 — 방법론 SOT·저장 규약·편입 가드 체크리스트는 `docs/kg_concept_builder.md`. 저장 규약: 조사 원장(전 후보·점수·출처·제외 사유)=`data/kg-research/<concept>.json`(git 추적 증거 원장), 시드에는 **Core/Strong 관계만** 편입(Moderate/Weak/Unverified는 원장 보존 — 기본 Backtest Universe 제외 원칙). 첫 배치 2개 Concept: ① 전고체 배터리(`solid-state-battery`) — 삼성SDI(Producer/Core 90, ASB 파일럿 S라인·2027 양산·유상증자 4,500억 라인 투자)·이수스페셜티케미컬(Supplier/Core 87, 황화리튬 국내 유일 양산·852억 상업설비)+SOL 0005D0·KODEX 0209D0, 하나기술·씨아이에스·롯데에너지머티리얼즈 등 6종은 Moderate/Weak로 원장만, 대주전자재료는 실리콘음극재(별개 Concept) 사유로 제외 기록 ② 비만치료제(`obesity-drug`) — 한미약품(Producer/Core 90, 에페글레나타이드 3상·H.O.P)·펩트론(Supplier/Strong 75, 릴리 SmartDepot 평가계약 공시)·디앤디파마텍(Supplier/Strong 72, 멧세라 기술수출)+글로벌비만 ETF 3종. 함정 확인: 시드 동의어에 개별 약품명(마운자로·위고비) 금지 — 학습 원장·grounding 테스트 용어와 충돌 시 시드 우선으로 학습 경로가 죽음(체크리스트 명문화). 검증: 무결성 0위반, '전고체→이차전지'·'GLP-1→바이오/제약' 결정적 해석, 테마 유니버스 왕복, 학습 경로('마운자로' 5개사) 보존 — 백엔드 전체 통과. SRS FR-STR-070 ① 갱신 | ✅ 완료 |
| Concept–Stock Knowledge Builder 2차 배치 — 유리기판·액침냉각·폐배터리 리사이클링 (2026-07-25) | `docs/kg_concept_builder.md` 절차 계속 — 3개 Concept 조사·검증·편입. ① 유리기판(`glass-substrate`) — SKC(Producer/Core 88, 자회사 앱솔릭스 美 조지아 양산 추진·공식 IR 등재)·삼성전기(Producer/Strong 78, CES 2024 공식 사업화·세종 파일럿 샘플·2026 양산 계획) 편입, 필옵틱스(TGV 장비)·HB테크놀러지는 수주 공시 미확인이라 Moderate로 원장만, 켐트로닉스·와이씨켐·LG이노텍은 근거 미확보 제외 기록 ② 액침냉각(`immersion-cooling`) — GST(시제품·에쓰오일/LS일렉트릭 협력)·케이엔솔(Submer 협력 진입) 모두 매출·계약 미확인 Moderate → **기업 엣지 0, 노드+used_in 데이터센터만 편입**(억지 추가 금지 원칙 실적용, 매출 확인 시 재조사) ③ 폐배터리 리사이클링(`battery-recycling`) — 성일하이텍(Producer/Core 92, 국내 유일 전처리~하이드로센터 일관공정·3공장)·새빗켐(Producer/Core 85, 재활용 매출 과반 52%)+RISE 배터리 리사이클링 ETF(446700). 사고·교정: 동의어 '폐배터리'가 grounding 테스트 정본 예제 용어와 충돌해 테스트 5건 실패(시드가 학습 경로 가로챔 — 가드 ③ 그대로 재현) → 동의어 제거로 해소, 빌더 doc에 `grep tests/test_term_grounding.py` 사전 확인 절차 추가. 검증: 무결성 0위반, '유리기판→반도체'·'배터리 재활용→이차전지' 해석, 테마 유니버스(SKC·삼성전기 / 성일하이텍·새빗켐) 왕복 — 백엔드 전체 통과. 시드 누적: 개념 36노드 | ✅ 완료 |
| Concept–Stock Knowledge Builder 3차 배치 — 우주발사체·탄소배출권·전력반도체 (2026-07-25) | `docs/kg_concept_builder.md` 절차 계속 — 3개 Concept 조사·검증·편입(시드 누적 39노드). ① 우주발사체(`space-launch-vehicle`) — 한화에어로스페이스(Producer/Core 90, 누리호 체계종합기업·항우연 기술이전 계약 2,400억 공식 뉴스룸 확인)·이노스페이스(Producer/Core 92, 한빛 소형발사체 주력 — CShark 35기 등 해외 발사 서비스 계약·2025-12 알칸타라 첫 상업 발사 수행)+SOL 우주항공밸류체인 ETF(0207G0). 쎄트렉아이(위성 제조)·컨텍(지상국)은 별개 Concept 사유로 제외 기록 ② 탄소배출권(`carbon-credit`) — 에코아이(Producer/Core 95, 감축사업 배출권 창출·판매 주력 — KIND 사업보고서 직접 확인·'탄소배출권 1호 상장'). 무소속 개념이라 part_of 섹터 엣지 없음(에코아이 정본 섹터=기타 서비스), 배출권 추종 상품은 ETN·해외선물형이라 정본 밖 — ETF 미연결(탄소효율그린뉴딜은 광범위 ESG로 연결 금지 명시). 후성은 과거 CDM 사업의 현재화 금지 원칙으로 제외 ③ 전력반도체(`power-semiconductor`) — DB하이텍(Producer/Core 89, 전력반도체 파운드리 매출 비중 70%·GaN HEMT 공정 개발 완료 시험생산)·KEC(Strong 73, GaN/SiC 소자 상용화)·아이에이(Strong 68, 자회사 트리노테크놀로지 SiC 중국 납품·합자법인) — 동의어에 SiC·GaN 포함('GaN 관련주'→반도체 결정적 해석). 검증: 무결성 0위반, 섹터 해석('발사체'→우주항공/방산·'SiC'→반도체)·테마 유니버스 3종 왕복, 백엔드 전체 통과 | ✅ 완료 |
| Concept–Stock Knowledge Builder 4차 배치(최종) — CXL·온디바이스 AI·AI 에이전트·양자컴퓨터·인공위성·마이크로바이옴 (2026-07-25) | `docs/kg_concept_builder.md` 절차로 잔여 후보 6개 일괄 처리 — 총 14 Concept 완료, 시드 45노드. ① CXL — 삼성전자·SK하이닉스(Producer/Strong 72, CXL D램 개발·CMM-DDR5 양산 돌입)·네오셈(Supplier/Strong 75, 세계 최초 CXL 검사장비 상용화·삼성 납품), 오킨스전자 Moderate ② 온디바이스 AI — 오픈엣지테크놀로지(Producer/Core 87, 엣지 AI 설계 IP 주력·LPDDR6 IP 글로벌 3사 수준)·칩스앤미디어(Strong 70), 다업종이라 part_of 없음(related_to AI만 — 섹터 해석 None 의도) ③ AI 에이전트 — 솔트룩스(Producer/Strong 72, '구버' 이용자 100만·루시아 LLM), is_a AI 체인으로 소프트웨어/플랫폼 깊이 2 해석 확인 ④ 양자컴퓨터 — **기업 엣지 0**(핵심 SDT 비상장·Pre-IPO, 상장 테마주는 양자내성암호 인접 분야 — 근거 미확인), 노드만 편입 ⑤ 인공위성 — 쎄트렉아이(Core 92, 2026-07-23 KAIST 단일판매·공급계약 공시·SIIS SpaceEye-T 해외 서비스)·인텔리안테크(Core 85, 해상 위성 안테나 세계 1위·수출 95%)·AP위성(Strong 72)+uses 우주발사체 관계. '위성' 단독은 섹터 어휘 선점이라 동의어 제외(가드 ② 실적용) ⑥ 마이크로바이옴 — CJ 바이오사이언스(Core 88, 정본 종목명 'CJ 바이오사이언스' 띄어쓰기 주의)·쎌바이오텍(Core 85, DUOLAC)·고바이오랩(Strong 68), 지놈앤컴퍼니는 사업 전략 전환으로 Moderate. 검증: 무결성 0위반, 신규 6테마 유니버스·섹터 해석 왕복, 백엔드 전체 통과 | ✅ 완료 |
| 개념 확인 진행 표시 — kg_lookup stage (2026-07-25) | 전략 agent가 KG(지식그래프)에서 개념을 찾을 때 사용자에게 진행을 알리는 표시 부재(사용자 요청, 문구='개념 확인 중...'). 기존 '검색 중...'(FR-STR-069 ⑤) stage 패턴 확장 — ① `term_grounding.resolve_sector`에 `on_kg_lookup` 콜백(개념 해석 체인 진입 시 1회, 콜백 예외 무해, `learn_sector_term` 관통) ② 빌더 SSE(`intent_routes._builder_llm_helpers`+step-stream): `stage:"kg_lookup"` 방출(검색 진입 시 searching이 교체) ③ parse-stream(`main._learn_unknown_sector_term`): searched 플래그를 stage_entered로 일반화 — kg_lookup만 발화해도 종료 후 parsing 복귀 ④ 프론트(`app/analytics/new/page.tsx`): loadingStage 유니언+`ANALYSIS_STAGE_LABEL.kg_lookup="개념 확인 중..."`+수신 핸들러 4곳(빌더 3·parse-stream 1). 테스트: 신규 2(`test_builder_step_stream.py` kg_lookup 순서, `test_term_grounding.py` 발화 계약·searching 교체 순서·예외 무해)+기존 fake 시그니처 갱신 — 백엔드 2,446·프론트 1,134 전체 통과, 선재 tsc 테스트파일 에러 외 클린. SRS FR-STR-069 ⑤ 확장 | ✅ 완료 |
| 복합 테마구 가드 + 빌더 테마 유니버스 되묻기 — '반도체 소부장' 사고 (2026-07-25) | 스크린샷 사고: "반도체 소부장 전략을 만들자"가 업종=반도체로 단독 확정돼 '소부장' 수식어가 조용히 소실(원인 ①: `_CUE_LESS_SECTOR_RE`가 앞 테마어만 접두 매칭 후 즉시 반환, 원인 ②: KG/그라운딩 게이트가 업종 큐(섹터/업종/관련/테마) 필수라 큐 없는 발화는 검색 학습 미도달). FR-STR-071b — ① `nl_parser._compound_theme_hint`: 큐리스 테마어+미지 한글 후속어(아는 어휘·섹터어·종목명 아님) 복합구 감지 → `_extract_sector` 단독 확정 금지(그래프 해석 시도 후 None), `_mentioned_unsupported_concepts`가 큐 없이도 sector 미해결 플래그(되묻기·학습 게이트 개방), `detect_theme_universe_clarification` 큐 동급 인정 ② `_weak_theme_candidate`+`BuilderState.sector_hint_weak`: 미지 명사+머리명사("소부장 전략")를 빌더 시드 한정 약한 힌트로 — 실패 시 되묻기 없이 조용히 해제(오탐 UX 가드), 형용사꼴(ㄴ받침)·아는 어휘 제외 ③ `term_grounding._prefers_search_first`: 복합구·약한 힌트는 검색 학습을 내부 지식 LLM보다 먼저(LLM이 '반도체'로 근사하면 소부장이 영영 학습 안 되는 공백), 용어 추출 프롬프트 복합 표현 예시 추가+정본 섹터어 추출 시 학습 스킵(어휘집 오염 방지) ④ 빌더 테마 되묻기: `_consume_sector_notice`가 해석 후 verified 관련 상장사 있으면 '이 종목들로만 vs 업종 전체' 되묻기(재사용 발화는 시드에서 즉시), '종목들로만'→`theme_symbols` 확정+업종 근사 해제+유니버스 질문 생략+`build_parsed_strategy`가 target_symbols+backtest_start_date(시점 편향) 직접 조립+합성 프롬프트 종목명 나열('업종/테마' 단어 금지 — TARGET 가드), 프론트 요약 카드 '대상 종목'=theme_label. 라이브 검증: 실제 네이버 검색+4B로 '반도체 소부장' 학습(정의·업종·관련 상장사 10곳 — 전부 출처 1건 pending, 콘솔 승인 전까지 업종 근사 동작). 테스트: 빌더 신규 7(`test_strategy_builder.py` 복합구/약한 힌트/되묻기 왕복)+그라운딩 신규 3(검색 우선·LLM 폴백·오염 가드) — 백엔드 2,456·프론트 1,134 전체 통과. SRS FR-STR-071b | ✅ 완료 |
| KG 시각화 서브탭 — 운영 콘솔 Knowledge (2026-07-25) | 사용자 요청: 합성 지식그래프를 항상 눈으로 확인할 수 있는 화면 부재. FR-STR-070c — ① 백엔드 `GET /knowledge/graph`(intent_routes): 로더 합성 결과(시드+정본 섹터·기업·ETF+verified 학습 오버레이) nodes/edges/issues 전체 덤프 ② Next 프록시 `/api/admin/knowledge/graph`(requireAdmin 404 은닉·백엔드 미가용 502 — 합성 SOT는 knowledge_graph.py, 프론트 재합성 없음) ③ Knowledge 탭 서브탭('학습 검토'/'KG 시각화')+`KnowledgeGraphView`: 외부 라이브러리 없는 캔버스 포스 레이아웃(O(n²) 반발+링크 스프링+중심 중력, 결정적 나선 초기 배치), 줌/팬/노드 드래그/호버 툴팁/클릭 시 이웃 하이라이트+관계 목록("HBM –produced_by→ SK하이닉스"), 그룹 5종(개념·테마/섹터/학습 용어/상장사/ETF) 범례·카운트 — 색은 다크 표면 전쌍 검증 3색+중립 회색 2단, 도형(원/마름모/사각형)·라벨이 2차 인코딩(색 단독 식별 금지) ④ 로더 검증 경고(issues) 노출. 테스트: 백엔드 신규 1(라우트 덤프 계약)+프론트 신규 7(프록시 404 은닉/패스스루/502 변환·서브탭 전환·범례 카운트·조회 실패 에러) — 백엔드 2,457·프론트 1,141 전체 통과. SRS FR-STR-070c | ✅ 완료 |
| KG 시드 3차 배치 — 공백 개념 7종 편입 (2026-07-25) | 빌더 절차(`docs/kg_concept_builder.md`)로 시드 공백 스스로 발굴·편입: 배터리 분리막(SKIET Core 95·더블유씨피 Core 90), 음극재(포스코퓨처엠 Core 90·대주전자재료 Core 90 실리콘 세계 최초), 수소연료전지(두산퓨얼셀 Core 95·범한퓨얼셀 Core 88·일진하이솔루스 Supplier/Strong 76), 의료 AI(루닛 93·뷰노 90·제이엘케이 85 — is_a AI 체인), 협동로봇(두산로보틱스 92·뉴로메카 88·레인보우로보틱스 Strong 72), 미용 의료기기(클래시스 95·원텍 88·에이피알 Strong 74), 항체약물접합체(리가켐바이오 93, ETF 부재 미연결). 시드 45→52노드·158→194엣지, 원장 7건(`data/kg-research/`). 가드 실적용: '분리막'·'음극재'·'수소'·'로봇' 섹터 어휘 동의어 제외(②), 비올 정본 부재 편입 불가(①), 에스프리즘(구 에스퓨얼셀 추정) Unverified 원장만. **가드 ③ 확장 발견**: 런타임 학습 커밋('반도체소부장')이 전역 어휘집 오버레이로 '학습 전' 전제 테스트 3건을 깨는 기존 실패 규명 — `_LEXICON_PATH`+`_CACHED` monkeypatch 격리 적용(`test_term_grounding.py` 2건·`test_strategy_builder.py` 1건). 검증: 무결성 0위반, 9개 문장 결정적 해석·테마 유니버스 스모크 — 백엔드 2,457·프론트 1,141 전체 통과 | ✅ 완료 |
| KG 카탈로그 레이어 — 주달 테마 분류 일괄 편입 (2026-07-25) | 사용자 지정 신뢰 소스(judal.co.kr)의 테마→종목 분류를 시드와 분리된 **카탈로그 레이어**로 편입(개별 검증 생략은 사용자 지시, 저장 위치·포함 범위는 사용자 결정 — 산업·기술+그룹주만, 정치인·이벤트·시장분류 제외). ① `scripts/ingest_judal_themes.py`: 323테마 발굴→분류·가드 4종(정본 심볼 필터 8드롭·섹터 어휘 32스킵·시드 중복 15스킵·테스트 정본 용어 2스킵)→`data/kg-theme-catalog.json` 209테마·2,673엣지(재실행=갱신) ② 로더(`engine/knowledge_graph.py`): `_CATALOG_PATH` 합성 — 스캔 우선순위 시드>학습>카탈로그(삽입 순서), 소속 엣지 없어 **섹터 해석 불참**(테마→종목 조회 전용), 정본 밖 심볼 조용히 스킵(무결성 단언 비대상), mtime 캐시 포함 ③ 효과: '초전도체'(15종목)·'자율주행'(34)·'수소차'(70)·'삼성그룹'(12) 등 테마 유니버스 즉답, 시드 개념(협동로봇·HBM)은 기존 Core/Strong 유지 확인. 데이터베이스제작자 권리 리스크는 사용자 인지下 진행. 테스트: 신규 2(`test_knowledge_graph.py` — tmp 카탈로그 합성·시드 우선·심볼 드롭·섹터 불참 / 실파일 합성·조회) — 백엔드 2,459·프론트 1,141 전체 통과. 상세=docs/kg_concept_builder.md 카탈로그 절 | ✅ 완료 |
| KG 시드 4차 배치 — 엔터 개념 4종 편입 (2026-07-25) | 사용자 요청("엔터관련주 정보 부족") — 시드에 엔터 개념 0, 카탈로그도 '엔터테인먼트'·'영화'는 섹터 어휘 스킵이라 세분 개념이 공백. 빌더 절차로 편입: K-팝 기획사(하이브 95·에스엠 92·JYP 92·와이지 88, ETF KPOP포커스·K-POP&미디어), 드라마 제작사(스튜디오드래곤 95·에이스토리 87·팬엔터테인먼트 Strong 78, uses 웹툰 — IP 파이프라인 엣지), 웹툰(디앤씨미디어 90·키다리스튜디오 88·와이랩 Strong 75 — 노드명이 섹터 어휘라 스캔은 '웹소설' 등 동의어 담당), 팬덤 플랫폼(디어유 92·하이브 Strong 74 — 다업종 part_of 없음, '버블'·'위버스' 상품명 동의어 금지). 시드 52→56노드·194→218엣지, 원장 4건. '드라마' 단독 동의어는 '드라마틱' substring 오폭 위험으로 제외(신규 함정 기록). 검증: "케이팝/연예기획사/아이돌/웹소설/K드라마 관련주"→미디어/엔터 결정적 해석, 테마 유니버스 왕복, 무결성 0위반 — 백엔드 2,459·프론트 1,146 전체 통과 | ✅ 완료 |
| KG 누락 연결 감사 배치 1 — 현대차·삼성전자·LG전자·NAVER (2026-07-25) | 사용자 제보: "현대차는 로봇 산업과 밀접한데 그래프에 연결이 안 돼 있다" — 기존 개념 노드의 회사 커버리지 감사(신규 Concept 발굴 아님, `docs/kg_concept_builder.md` "누락 연결 감사" 절 신설). 실측 확인: judal 카탈로그(209테마)에도 '로봇' 테마 자체가 아예 없어(사용자에게 규모 재안내 — 기업 1,423개·카탈로그 209개로 커짐을 확인 후 범위 재확정) 감사 필요성 재확인. 편입: 휴머노이드 로봇(`robot-humanoid`)에 현대자동차(Investor/Strong 78, 보스턴다이내믹스 지분 100% 확보 — 2021년 80%+2026-07 소프트뱅크 풋옵션 행사로 잔여 20% — 아틀라스 2028~2030 생산현장 투입 로드맵)·삼성전자(Investor/Strong 78, 레인보우로보틱스 지분 35.0%·최대주주·연결자회사 편입)·LG전자(Supplier/Strong 70, 액추에이터 B2B 공급 공식화+CES 2026 '클로이드' PoC), AI 에이전트(`ai-agent`)에 NAVER(Producer/Strong 72, 'AI 국민비서' 행안부 공동 구축 — 클로바X·큐:는 2026-04 종료 확인 후 반영) 신규 편입. 원장: `data/kg-research/robot-humanoid.json`(신규, 기존 3사는 재조사 없이 unspecified로 구분 표시)·`ai-agent.json`(추가). 새 관례 확정: Investor 엣지만 회사가 source(`{company} –invests_in→ {concept}`)로 가독성 우선 — 나머지 관계유형은 기존대로 concept가 source. 검증: `test_conglomerate_diversification_edges_present` 신규(4개 엣지 고정), 무결성 0위반 — 백엔드 2,460 전체 통과. 남은 범위(사용자 승인 "전체 노드 완전 전수조사" 중 감사=curated seed로 축소 합의): 나머지 54개 기존 개념 감사+judal 미대응 108개 주요 테마의 신규 Concept 편입은 후속 배치 | ✅ 완료(배치 1/N) |
| KG 누락 연결 감사 배치 2 — LNG운반선·한전KPS·현대위아·큐브엔터 (2026-07-25) | 사용자 "계속 진행해줘"로 배치 1 이어서 진행. 발견: LNG운반선(`lng-carrier`) 개념은 2026-07-24 최초 배치에 있었으나 상장사 엣지가 하나도 없던 공백(K조선 3사의 LNG선 세계 시장 과점은 잘 알려진 사실인데도 누락). 편입: LNG운반선에 HD한국조선해양(Core 88, 2026 수주목표 233억 달러 최대)·한화오션(Core 85, LNG선 7척 2조5891억원 수주)·삼성중공업(Core 85, LNG선 4척 1조4641억원 수주) — 한국 대형 LNG선 점유율 약 65~69%. 원자력(`nuclear`)에 한전KPS(Producer/Core 87, 국내 전 원전 정비 전담·원자력정비 매출비중 34%). 협동로봇에 현대위아(Producer/Strong 68, 모빌리솔루션사업부 신설+CES 2026 시연·PoC 단계). K-팝 기획사에 큐브엔터(Producer/Core 85, (여자)아이들·비투비 — 매출 872억원 확인해 재조사 대기 Moderate에서 승격). CDMO는 롯데바이오로직스 사업 실체 확인했으나 korea-stocks.json 정본에 없어(비상장 자회사) 가드 ①로 편입 보류. 원장: `lng-carrier.json`·`nuclear.json` 신규, `collaborative-robot.json`·`kpop-agency.json`·`ai-agent.json` 갱신. 검증: `test_missing_edge_audit_batch2_present` 신규(6개 엣지 고정), 무결성 0위반 — 백엔드 2,461 전체 통과. 남은 범위: 나머지 50개 기존 개념 감사+judal 미대응 108개 테마 신규 Concept 편입 | ✅ 완료(배치 2/N) |
| KG 누락 연결 감사 배치 3 — 데이터센터·인공위성 (2026-07-25) | 배치 2 이어서 진행. 편입: 데이터센터(`data-center`, 상장사 엣지 0이던 공백)에 삼성에스디에스(Producer/Strong 72, DBO 사업 진출+액침냉각 시범)·LG씨엔에스(Producer/Strong 70, 자카르타 하이퍼스케일 AI 데이터센터 구축), 인공위성에 한국항공우주/KAI(Producer/Core 85, 다목적실용위성 30년 본체개발 주관·7호 2025-12 발사). 편입 보류(근거 부족으로 Moderate 판정): LG화학→battery-cathode(양극재 생산능력 축소 중, 매출비중 미확인), 동아에스티→biosimilar(스텔라라 바이오시밀러 매출 비중 2.4%로 일부 사업). 원장: `data-center.json` 신규, `satellite.json` 갱신. 검증: `test_missing_edge_audit_batch3_present` 신규(3개 엣지 고정), 무결성 0위반 — 백엔드 2,462 전체 통과. 남은 범위: 나머지 48개 기존 개념 감사+judal 미대응 108개 테마 신규 Concept 편입 | ✅ 완료(배치 3/N) |
| KG Part B 배치 1 — 자율주행·사이버보안·전기차충전·양자암호통신 신규 편입 (2026-07-25) | 사용자 "PART B로 진행" — judal 카탈로그에만 있고 우리 그래프엔 대응 개념이 없던 주요 테마를 정식 Concept-Stock Builder 절차(ETF 조사·복수 후보 검증)로 신규 편입(기존 개념 감사와 별개 트랙). 편입: 자율주행(현대모비스 Core 85·HL만도 Core 82 — HL클레무브 자율주행 전문 조직, ETF 3종)·사이버보안(안랩 Core 90·파수AI Strong 70, part_of 소프트웨어/플랫폼)·전기차 충전(채비 Core 85, 舊 대영채비 — 2026 1분기 매출 207억원)·양자암호통신(SK텔레콤 Investor/Strong 70 — 스위스 IDQ 지분 50%+ 인수, 기존 quantum-computing과 related_to로만 연결). 원장 4건 신규(`data/kg-research/`). 정본 미등재로 제외: 시큐아이. 시드 56→60노드·218→232엣지. 검증: `test_part_b_new_concepts_batch1_present` 신규(개념 인식 4건+엣지 6건 고정), 무결성 0위반 — 백엔드 2,463 전체 통과. 남은 범위: judal 미대응 108개 후보 중 나머지(수소차·전기차·LCD·게임·방산주·5G·핀테크·MLCC 등) | ✅ 완료(Part B 배치 1/N) |
| KG Part B 배치 2 — 5G 장비·핀테크·PCB 신규 편입 (2026-07-25) | 사용자 "계속 진행"으로 Part B 이어서 진행. 편입: 5G 장비(RFHIC Core 88 — GaN 전력증폭기·트랜지스터 매출비중 99%+·케이엠더블유 Core 85 — 국내 유일 5G MMR·매출 90% 해외, '5G' 단독 문구는 카탈로그가 담당하도록 역할 분담)·핀테크(카카오페이 Core 90 — 2026 1분기 매출 3,003억원 역대 최대)·PCB(심텍 Core 87·대덕전자 Core 85 — 서브스트레이트·MLB 글로벌 리더). 편입 보류: 유콘시스템(드론, 정본 미등재)·에이스테크(5G, 근거 부족). 원장 3건 신규. 시드 60→63노드·232→241엣지. 검증: `test_part_b_new_concepts_batch2_present` 신규(개념 인식 3건+엣지 5건 고정), 무결성 0위반 — 백엔드 2,464 전체 통과. 남은 범위: judal 미대응 108개 후보 중 나머지(수소차·전기차·LCD·게임·방산주·영상콘텐츠·사물인터넷·MLCC·6G·LED·초전도체 등) | ✅ 완료(Part B 배치 2/N) |
| KG Part B 배치 3 — 게임·LED·광통신 신규 편입 (2026-07-25) | 사용자 "계속 진행해줘"로 Part B 이어서 진행. 편입: 게임(크래프톤 Core 92 — 2026 1분기 영업이익 1위·NC Core 88 — 舊 엔씨소프트, 리니지 클래식 흥행 반등·넷마블 Core 90 — 2025 매출 2조8,351억원 사상 최대. 넥슨은 매출 1위지만 도쿄증권거래소 상장이라 정본 밖으로 편입 불가)·LED(서울반도체 Core 85 — 2025 매출 1조135억원)·광통신(오이솔루션 Core 80 — 2025 매출 574억원 79%↑·2026 흑자전환 전망, data-center·5g-equipment와 related_to 연결). 원장 3건 신규. 시드 63→66노드·241→253엣지. 검증: `test_part_b_new_concepts_batch3_present` 신규(개념 인식 3건+엣지 5건 고정), 무결성 0위반 — 백엔드 2,465 전체 통과. 남은 범위: judal 미대응 108개 후보 중 나머지(수소차·전기차·LCD·방산주·영상콘텐츠·사물인터넷·MLCC·6G·초전도체 등) | ✅ 완료(Part B 배치 3/N) |
| KG Part B 배치 4 — 니켈·희토류 원자재 편입, 수소차·스마트팩토리 근거부족 보류 (2026-07-25) | 사용자 "계속 진행"으로 Part B 이어서 진행. 편입: 니켈(회사 엣지 없는 순수 원자재 노드, 기존 구리·리튬과 동일 패턴 — battery-cathode가 requires로 연결)·희토류(sector:자동차부품이 affected_by로 연결). 편입 보류(조사했으나 Core/Strong 기준 미달): 수소차(효성첨단소재·이엠코리아·효성하이드로젠 모두 매출 미미이거나 근거 낡음), 스마트팩토리(로보스타·싸이맥스 매출 비중 미확인). 고려아연의 니켈 제련소(2026 준공 예정)·희토류 정제(2026-2030 R&D)는 가동 전 단계라 회사 엣지 미편입, 원자재 노드만 편입(억지 추가 금지). 시드 66→68노드·253→256엣지. 검증: `test_part_b_new_concepts_batch4_present` 신규, 무결성 0위반 — 백엔드 2,466 전체 통과. 남은 범위: judal 미대응 108개 후보 중 나머지(전기차·LCD·방산주·영상콘텐츠·사물인터넷·MLCC·6G·초전도체·LFP배터리·수소차(재조사) 등) | ✅ 완료(Part B 배치 4/N) |
| KG Part B 배치 5 — 생체인식·렌터카·광고 신규 편입 (2026-07-25) | 사용자 "계속 진행"으로 Part B 이어서 진행. 편입: 생체인식(슈프리마 Core 88 — 바이오인식 보안 전업·수출 81%·지문인식 알고리즘 세계 1위 4회)·렌터카(롯데렌탈 Core 85 — 국내 1위·2025 매출 2조9,188억원, SK렌터카는 매각으로 정본 밖)·광고(제일기획 Strong 75·이노션 Strong 72 — 둘 다 등록 업종=광고업이나 최신 매출 공시 미확인이라 Strong). 원장 3건 신규. 시드 68→71노드·256→265엣지. 검증: `test_part_b_new_concepts_batch5_present` 신규(개념 인식 3건+엣지 4건 고정), 무결성 0위반 — 백엔드 2,467 전체 통과. 남은 범위: judal 미대응 108개 후보 중 나머지(전기차·LCD·방산주·영상콘텐츠·사물인터넷·MLCC·6G·초전도체·LFP배터리·수소차(재조사) 등) | ✅ 완료(Part B 배치 5/N) |
| KG Part B 배치 6 — 건강기능식품 신규 편입 (2026-07-25) | 사용자 "계속 진행"으로 Part B 이어서 진행. 편입: 건강기능식품(콜마비앤에이치 Core 85 — 건기식 OEM/ODM·2026 1분기 영업이익 189%↑·뉴트리 Core 82 — 에버콜라겐 등 이너뷰티 자체 브랜드, 최근 실적 부진하나 사업 관련성은 명확). 편입 보류: 하림펫푸드(반려동물)·캐리마(3D프린터) 둘 다 비상장으로 정본 확인 실패. 원장 1건 신규. 시드 71→72노드·265→267엣지. 검증: `test_part_b_new_concepts_batch6_present` 신규, 무결성 0위반 — 백엔드 2,468 전체 통과. 남은 범위: judal 미대응 108개 후보 중 나머지(전기차·LCD·방산주·영상콘텐츠·사물인터넷·MLCC·6G·초전도체 등) | ✅ 완료(Part B 배치 6/N) |
| KG Part B 배치 7 — 폴더블폰 신규 편입 (2026-07-25) | 사용자 "계속 진행"으로 Part B 이어서 진행. 편입: 폴더블폰(KH바텍 Core 85 — 2025년 전사 매출 4,249억원 중 힌지 매출 2,539억원·44%↑ 반등, 2026년 삼성 라인업 확대+애플 진입 전망). 편입 보류: 창투사(미래에셋벤처투자·SBI인베스트먼트, 구체적 실적 근거 미확보)·파인테크닉스(정본 업종이 조명장치 제조업이라 폴더블 관련성 미확인). 원장 1건 신규. 시드 72→73노드·267→268엣지. 검증: `test_part_b_new_concepts_batch7_present` 신규, 무결성 0위반 — 백엔드 2,469 전체 통과. 남은 범위: judal 미대응 108개 후보 중 나머지(전기차·LCD·방산주·영상콘텐츠·사물인터넷·MLCC·6G·초전도체 등) | ✅ 완료(Part B 배치 7/N) |
| KG 카탈로그 소스 오류 제거 — 반도체 제품(SOC) 오분류 (2026-07-25) | 사용자 제보: KG 시각화에서 '반도체 제품(SOC)' 테마가 삼성물산·현대건설·대우건설 등 건설사 6곳과 연결 — 조사 결과 **주달 원본 자체의 오분류**(사회간접자본(SOC) 인프라 테마에 반도체 제품(System on Chip) 계열 이름을 붙임, themeIdx=133 실페이지로 확인). 실사용 영향: "SOC 관련주" 질의가 건설사 6곳을 반도체 이름으로 응답 중이었음. 수정: 카탈로그에서 judal-133 제거(209→208테마)+수집 스크립트 `EXCLUDE_SOURCE_ERROR` 가드(재수집 시 재유입 방지)+회귀 테스트(`test_catalog_source_error_theme_excluded`). 나머지 208개 테마는 테마명↔종목 섹터 구성 대조 전수 스크리닝으로 정상 판정(HBM→기계/장비 다수=장비 수혜주 관례, 렌터카→IT하드웨어=정본 섹터 분류 특성 등 설명 가능). 건설사는 섹터 유니버스가 커버하고 'SOC' 약어는 반도체와 중의적이라 이름 수정 대신 제거 선택 — 백엔드 2,470 전체 통과 | ✅ 완료 |
| KG Part B 배치 8 — 전기차·수소차·MLCC 신규 편입 (2026-07-25) | SOC 소스 오류 수정 후 사용자 "part b" 재개 지시. 편입: 전기차(현대자동차 Core 90 — 아이오닉 전 차급·기아 Core 90 — 2026 상반기 EV 7만 대 돌파+연 40만 대 목표 공식 발표, ETF 2종. **함정: 동의어 'EV'는 EV/EBITDA 재무지표와 라틴 경계 오매칭이라 의도적 제외+테스트 고정**)·수소차(현대자동차 Core 92 — 넥쏘 국내 점유율 92.6%·2025 글로벌 판매 1위, uses→hydrogen-fuel-cell 기존 개념 연결, 배치 4 보류分 재조사 성공)·MLCC(삼성전기 Core 88 — 컴포넌트 부문 매출 비중 43.9%·삼화콘덴서공업 Core 85 — MLCC 매출 비중 52%). 제외: 방산(섹터 어휘라 스캔 무력화 — 섹터 유니버스 담당). 원장 3건 신규. 시드 73(SOC 제거 반영)→76노드·268→283엣지. 검증: `test_part_b_new_concepts_batch8_present` 신규(개념 인식 3건+EV 오매칭 방지+엣지 5건+개념 간 연결 고정), 무결성 0위반 — 백엔드 2,473 전체 통과(공유 작업트리라 타 세션 추가 테스트 포함 실측치) | ✅ 완료(Part B 배치 8/N) |
| KG Part B 배치 9 — 풍력발전·임플란트·초전도체 신규 편입 (2026-07-25) | 사용자 "계속 하자"로 Part B 이어서 진행. 편입: 풍력발전(씨에스윈드 Supplier/Core 90 — 풍력타워 글로벌 1위·연 7,000기+, '풍력' 단독은 섹터 어휘라 동의어 제외·신재생 광의 ETF 연결 금지)·임플란트(덴티움 Core 90 — 임플란트 매출 88%·업계 유일 KOSPI 상장, 오스템임플란트는 자진 상폐로 정본 밖)·초전도체(서남 Core 85 — 고온초전도 선재 전업, 매출 극소·적자이나 관련도와 실적 별개(뉴트리 전례), LK-99 테마주 전부 제외). **함정 발견**: 카탈로그 실파일 테스트의 예제 테마가 '초전도체'라 시드 승격 직후 깨짐(스캔 우선권 이동의 의도된 동작) — 예제를 카탈로그 전용 테마(골판지)로 교체+시드 승격 체크리스트에 추가. 원장 3건 신규. 시드 76→79노드·283→289엣지. 검증: `test_part_b_new_concepts_batch9_present` 신규, 무결성 0위반 — 백엔드 전체 통과 | ✅ 완료(Part B 배치 9/N) |
| KG 감사 최종 배치 — Part A/B 종결 (2026-07-25) | 사용자 "남은 모든 작업을 마무리하고 커밋하자". **Part B 배치 10**: 카지노(강원랜드 Core 90 — 국내 유일 내국인 카지노·파라다이스 Core 90 — 외국인 전용 8,998억원/2025)·여행사(하나투어 Core 90·모두투어 Core 85 — '여행' 단독은 일반명사 오폭이라 동의어 제외)·면세점(호텔신라 Core 90 — 면세 비중 83.1%)·탄소섬유(HS효성첨단소재 Strong 70 — 국내 유일 생산, used_in→수소차 연료탱크) 신규 편입. **Part A 종결**: 기업 엣지 0인 시드 개념 19개 전수 분류 — 실제 공백 1건(SMR에 두산에너빌리티 Core 88, 뉴스케일 지분+테라파워 기자재 수주) 보완, 나머지는 정당한 0(매크로·원자재·추상 개념) 또는 문서화된 보류(액침냉각·양자컴퓨터). **Part B 종결**: 잔여 judal 후보 전체를 5개 사유(섹터 커버/전업 부재/비상장/중복/외국기업 테마)로 최종 처분 확정 — docs/kg_concept_builder.md에 처분표 기록. 원장 5건 신규(casino·travel-agency·duty-free·carbon-fiber·smr). 시드 79→84노드·289→303엣지. 검증: `test_part_b_batch10_and_part_a_closure_present` 신규, 무결성 0위반 — 백엔드 전체 통과. **누락 연결 감사 프로젝트 종료** — 이후 신규 개념은 사용자 요청 또는 검색 학습 경로로 계속 | ✅ 완료(감사 종결) |
| KG Phase 2 파서 배선 + 개념 인식 히트율 실측 (2026-07-25) | 사용자 요청("Phase 2 배선과 히트율 실측하자"). ① **공급망 확장 되묻기**: `detect_theme_universe_clarification`이 기존 깊이 1(직접 관련 종목) 되묻기에 더해 `related_universe` 깊이 2가 공급망·인프라 상장사에 닿으면 세 번째 칩(확장 종목 전체 나열, 상한 15) 추가 — 질문 본문에 via 중간 개념 요약("HD현대일렉트릭(전력기기)"), 칩은 FR-STR-071 프로토콜 준수·symbol_resolver 전량 재파싱 실증(데이터센터 2사→공급망 포함 13사). 확장 없는 개념(HBM·전고체)은 2칩 유지. 빌더 되묻기 배선은 동시 진행 중인 복수 업종 작업과 `_theme_reask_prompt` 충돌을 피해 보류. ② **히트율 하니스**(`scripts/qa_kg_concept_hits.py`): judal 테마명+시드 용어 492개 코퍼스로 3지표를 git 이력 시드와 A/B 측정 — 감사 전(45노드)→현재(84노드): 결정적 인식 74.4→93.5%(+94건), 섹터 해석 23.0→41.9%(+93건), 종목 목록 63.6→83.7%(+99건), 미검증 카탈로그 히트 47건이 검증 시드로 승격. 테스트: `test_theme_universe_expansion.py` 신규 4건(확장 칩·왕복·비확장 개념·via 라벨) — 백엔드 전체 통과. docs/knowledge_graph.md Phase 2 상태 갱신 | ✅ 완료 |
| 복수 업종 언급 전부 수집 — 첫 매치 단독 확정 수정 (2026-07-25) | 스크린샷 사고: "반도체와 로봇관련 종목에 투자 하는 전략을 만들어 보자"가 빌더 시드에서 '업종 로봇' 단독으로 인식 — 반도체가 조용히 소실. 원인: `nl_parser._extract_sector`가 `search` 첫 매치만 반환(큐 매치 '로봇관련'이 선점, 큐리스 매치 '반도체와'는 도달 불가). 다중 섹터 정규형(FR-STR-066 ⑦ None/str/list)·엔진 합집합 필터·프론트 배지는 기배선이라 추출층만 공백. 수정: `_extract_sector`가 큐 매치(`finditer`)+큐리스 매치를 전부 수집해 발화 순서로 정렬 후 `normalize_sector_value` 정규형 반환(단일=str 하위 호환·dedup), 복합 테마구 가드는 매치별 판정(`_compound_theme_follower` 분리 — '말고' 정정 발화의 앞 업종도 이 가드가 배제), `BuilderState.sector`를 `Union[str, List[str]]`로 확장+표시 라벨 `_sector_label`('·' 연결: 확인 문장·시드 요약·합성 프롬프트·테마 되묻기 칩), LLM 시드 병합도 list 수용(`apply_parsed_seed`→`normalize_sector_value`). 합성 프롬프트("코스피 반도체·로봇 업종 …") 재파싱도 두 업종 재인식 확인. 부수 의미 개선: "바이오 헬스케어 전략"이 바이오/제약 단독→[바이오/제약, 의료기기] 수집(기존 테스트 기대값 갱신). 테스트: `test_extract_sector_multiple_mentions`+빌더 시드 2종 — 백엔드 2,472·프론트 1,164 전체 통과. SRS FR-STR-066 ⑦ | ✅ 완료 |
| 인터프리터 프롬프트 업종 규칙 6-0 (2026-07-25) | 복수 업종 파서 수정 후속 — LLM 인터프리터(strategy_conversation)가 "반도체와 로봇관련 종목" 발화에서 업종을 `unsupported_features`("업종/테마 기반 종목 선택")로 분류하고 sectors를 비운 채 되묻기를 내던 드리프트. 원인: 규칙 3('지원 지표 목록에 없는 개념→unsupported')을 4B가 유니버스에도 적용(기존 규칙 6은 markets/sectors 배치만 언급). 수정: 규칙 6-0 신설 — 업종/테마 제한은 지원 기능(지표 목록은 조건용), 언급 업종 전부 `universe.sectors` 배열로("반도체와 로봇"→["반도체","로봇"]), unsupported_features·업종 되묻기 금지. PROMPT_VERSION 1.2→1.3. E2E 실측(로컬 4B): 사고 문장 sectors=['반도체','로봇']·미지원 0·업종 질문 0, 메타버스(목록 밖)는 미지원 유지, 뉴스 신호 미지원 유지, '2차전지' 공백 드리프트('2 차 전 지')는 `_sector_key`가 흡수해 이차전지 정본화 확인. 하류 안전망: `capability_validator`가 sectors를 정본 화이트리스트 재검증(조용한 왜곡 불가). 테스트 2종(프롬프트 계약 가드+복수 섹터 정규화) — 백엔드 2,476·프론트 1,164 전체 통과. SRS FR-STR-066 ⑦-1 | ✅ 완료 |
| 매수 조건 예시 칩 현실화·확충 (2026-07-25) | 사용자 제보: 빌더 매수 조건 단계의 예시 칩 3개("골든크로스 발생 시 매수"·"PBR 1 이하"·"RSI 30 이하에서 매수")가 빈약하고 PBR 1 이하는 비현실적 기준. 프론트 게이트(`backtestReadiness.ts`)와 백엔드 `_missing_backtest_conditions`(nl_parser.py) 양쪽 칩을 8종으로 동기화 — 골든크로스·RSI 30 이하·MACD 골든크로스·볼린저밴드 하단 터치·20일 고점 돌파·거래량 급증·PER 10 이하·ROE 15% 이상. `deterministicConditionFlow.ts` 진입 분기를 if-체인→ENTRY_SIGNAL/FILTER_BY_CHOICE 맵으로 바꿔 전 칩 결정적 적용(PBR 1 이하 매핑은 하위 호환 보존), 각 문구가 룰 파서에서도 동일 신호로 추출됨을 실측(macd crossover·bollinger buy·breakout 20·volume_spike). 칩 문구↔매핑 키 불일치가 조용히 LLM 폴백으로 새는 것을 막는 동기화 잠금 테스트 추가(`page.scroll.test.tsx`) — 프론트 1,165·백엔드 2,477 전체 통과 | ✅ 완료 |
| 전략연구소 대화 표면 리디자인 (2026-07-25) | 사용자 요청(tasteskill.dev 스킬 적용) — 스킬 문서가 스스로 "multi-step product UI는 범위 밖"이라 명시해 랜딩 전용 규칙은 제외하고 `redesign-skill`(기존 앱 대상) + taste-skill의 이식 가능 절(§4 디자인 지시·§8 다크모드·§9 AI Tells·§11 리디자인 프로토콜·§14 프리플라이트)만 적용. 범위=타겟 진화(IA·대화 흐름·칩 프로토콜 보존), 규칙 충돌 시 taste-skill 우선 + `docs/UI_GUIDELINES.md` 갱신(둘 다 사용자 결정). **①폰트 배선 버그**: `tailwind.config.js`에 `fontFamily` 확장이 없어 `font-outfit`(22개 파일 사용)·`font-inter`가 정의되지 않은 죽은 클래스였고 실제 렌더 폰트는 `globals.css`의 Arial + 한글은 OS 폴백 → 한글 우선 스택(Inter→Pretendard→Apple SD Gothic Neo→Malgun Gothic) 정의, body의 `font-family` 하드코딩 제거. **②표면 위계**: `USER_CHAT_BUBBLE_CLASS`와 `COACH_CHAT_BUBBLE_CLASS`가 문자열까지 동일해 여섯 종류 블록이 같은 글래스 카드였던 것을 맨 텍스트 산문/산출물 카드/오류 카드/사용자 카드로 분리(되묻기는 강조색 아이콘+선택 칩으로 구분). **세로 레일은 전부 제거**(사용자 지시 2회 — 되묻기 카드의 강조색 3px, 산문의 헤어라인, 오류 카드의 레드 레일): 산문은 카드가 없다는 사실 자체가 구분이고, `border-l` 금지를 가드 테스트로 고정. 부수로 '돌아가기' 버튼이 라벨 회색으로 바뀌어 정적 캡션처럼 읽히던 affordance 회귀를 사용자 제보로 수정 — `BACK_CONTROL_CLASS`(테두리·면·`hover`·`active`·`focus-visible`)로 색 대신 형태로 컨트롤임을 표시. **③강조색 단일화**: amber·yellow·orange·sky·blue-indigo 그라디언트·aurora 3색 등 6+ 색조를 `--chat-accent` 하나로(역할="사용자 차례+진행 상태"), 의미색은 보존. **④glow·그라디언트 제거**: 주 CTA를 단색 강조 채움으로(가이드 §2 glow 금지 vs §10 glow 규정 자기모순 해소), BacktestRunningStatus의 blur+mix-blend-mode 3레이어를 1레이어로. **⑤감속 설정**: 인라인 `style` animation 4종을 클래스로 이관해 `prefers-reduced-motion` 존중, shimmer/닷 스피너/헤드라인/`animate-spin` 전부 커버. **⑥헤드라인 연출**: 38ms `setInterval`로 글자마다 전체 리렌더하던 것을 `animation-delay` 캐스케이드로 대체(타이머 제거). **⑦대비**: placeholder 3.0:1·라벨 3.98:1 미달을 `--text-placeholder`(5.9:1)·`--text-label`(7.6:1) 토큰으로. **⑧기타**: `100vh`→`100dvh` 4곳, 반경 스케일 통일(모달 3xl→2xl 등), 한글 `uppercase tracking-widest` eyebrow 정리, 칩 위계 상승+`focus-visible` 링+`active` 눌림. 보류(사용자 선택 범위 밖): 진행률 레일 반응형 상시 노출·`뒤로가기`/`돌아가기` 라벨 통합(백엔드 답변 프로토콜)·`pb-56` 매직넘버. **⑨tailwind 투명도 수정자 결함**: 작업 중 `bg-[var(--x)]/80`·`ring-[var(--x)]/50` 형태가 tailwind에서 **아무 클래스도 생성하지 않음**을 CLI로 실측 확인(조용한 죽은 클래스) → 투명도 단계를 `--chat-accent-line`/`-ring`/`-underline`/`--error-red-line` 토큰으로 전환. 같은 결함의 **기존 버그도 발견·수정**: 'AI 모델 로드 실패' 배지가 `bg-[var(--main-blue)]/10 border-[var(--main-blue)]/20`으로 배경·테두리 없이 렌더되고 있었다(의미색 파랑=하락 오용도 함께 해소, 삭제 버튼 관례대로 테두리·글자만 레드). 테스트: 신규 `chatSurfaceDesign.test.ts` 12건(폰트 배선·감속·강조색·투명도 수정자·100dvh·표면 분리 가드), `page.auth-entry.test.tsx` 헤드라인 계약을 타이머→CSS 캐스케이드로 갱신, 이스케이프 한글 회귀는 기존 `chatInputText.test.ts` 가드가 즉시 검출 — 프론트 1,158·백엔드 2,463 전체 통과 | ✅ 완료 |
| 테마 상장사 개념 1홉 폴백 — 'bts 관련주' 사고 (2026-07-25) | 스크린샷 사고: "bts 관련주에 투자 해보자"가 미디어/엔터 업종 전체로 확정 — 그라운딩 검색은 실행돼(19:10 어휘집 학습) 하이브 `related_company` 엣지까지 수집했으나 출처 1건 pending이라 그래프 합성에서 제외됐고, verified 개념 엣지(bts→K-팝 기획사, 출처 4건) 너머의 하이브·에스엠 등은 `listed_companies`의 깊이 1 제한에 막혀 테마 되묻기(FR-STR-071)가 미발동. 수정: ① 즉효 — 콘솔에서 하이브·신세계 pending 엣지 승인(사용자 수행, 레이=치과기기 노이즈는 잔류) ② 구조 — `KnowledgeGraph.listed_companies_via_concepts` 신설, `theme_listed_companies`가 **학습 앵커** 한정으로 직접 verified 상장사가 없을 때만 verified 개념 엣지 1홉 너머 개념의 직접 상장사로 후보를 채움(직접 목록 우선·시드/카탈로그 앵커 제외·홉 상장사 first_known_date는 기존 계약대로 학습일 폴백). 테스트: `test_theme_companies_via_verified_concept_hop`(재현+직접 우선 가드) — 백엔드 2,482·프론트 1,165 전체 통과. SRS FR-STR-071 ④ 갱신 | ✅ 완료 |
| KG 재연결 감사 + 학습 TTL 재검토 (2026-07-25) | 사용자 질문("새 개념이 KG에 추가되면 기존 노드와 연결 체크하나?")에 대한 답: 신규 학습→기존 노드는 학습 시점 스니펫 co-occurrence로만, 역방향(기존 학습 항목←신규 노드)은 전무. 수정 3종: ① **역스캔**(`term_grounding.propose_relink_edges`/`relink_lexicon`) — 학습 항목의 저장 정의·출처 제목을 현재 그래프로 재스캔, 미연결 개념을 pending related_to 제안(LLM 무관여·자동 verified 금지·rejected 부활 금지·멱등). 실측: 마운자로→obesity-drug 미연결 공백 즉시 검출 ② **시드 편입 가드 5** — kg_concept_builder.md 체크리스트에 편입 후 감사 실행 추가 ③ **TTL 조건부 재검토**(FR-STR-069 ⑦) — TERM_REGROUND_TTL_DAYS(기본 90일, 0=영구 캐시) 경과한 미해결 항목은 재언급 시 재검색 허용, 재학습=병합(_merge_entry_edges, 검토 상태 보존). 성공 항목은 핫패스 재검색 없음 — 배치(`scripts/kg_relink_audit.py --reground-stale`) 담당. 테스트: 역스캔 멱등·rejected 보존, TTL 0/90 분기·병합 보존 2건 — 백엔드·프론트 전체 통과. SRS FR-STR-069 ⑦·FR-STR-070b ⑥ | ✅ 완료 |
| Concept Universe Builder — 개념 중심 유니버스 결정론 생성 (2026-07-25) | 사용자 스펙(NullStock Concept Universe Builder) 구현. 핵심 설계 판단: 스펙의 '재현 가능·동일 기준' 요구+FR-STR-070b 신뢰도 원칙에 따라 관련도를 LLM 자기평가가 아닌 **KG 근거 결정론 산출**로 — 시드 note 원장 점수 "(Core 95)" 파싱(무표기 0.70)·학습 verified 출처 수(0.55+0.05×support≤0.80)·개념 1홉 ×0.85 감쇠·카탈로그 0.45, pending 불참, 심볼별 최고 점수 유지. 선정: ≥0.5 기본, <10이면 floor 0.30까지 완화(후보 부족 시 있는 만큼 — 억지 채움 금지, 스펙 '최소 10개'의 의도적 완화), >30이면 상위 30, tie-break 심볼순(재현성), threshold_used/relaxed 메타 기록. 진입점: engine/concept_universe.py+GET /knowledge/concept-universe+CLI scripts/concept_universe.py. 실측: BTS→6종목(하이브 0.81 최상위·업종 전체 아님·pending 레이 제외), HBM→6종목. 테마 되묻기 후보 통합은 향후. 테스트 5건(점수 파싱·출처 스케일·선정 규칙·결정성·홉 감쇠/pending 제외) — 백엔드 전체 통과. SRS FR-STR-072 | ✅ 완료 |
| 지분 관계 레이어 + 검색 리콜 보강 + 콘솔 수동 엣지 (2026-07-25) | 사용자 제보(넷마블=하이브 주주·LB인베스트먼트=초기 투자사인데 미포착) 3종 대응. ① 검색 리콜: `"{용어} 수혜주"` 뉴스 쿼리 추가+스니펫 24건+링크 dedupe(교차지지 이중계산 차단). ② 공시 정공법(FR-STR-072b): `scripts/build_equity_edges.py` — DART 타법인출자현황 전 상장사 스윕(재개 가능), 양쪽 상장사+지분율 ≥5%만 invests_in 엣지로 kg-equity-edges.json(git 추적) 저장, 법인명 정규화 정확 일치 매칭. Concept Universe만 소비(KG 본체 비합성 — 기존 그래프 소비자 의미 보존), 회사 홉 ×0.70 감쇠 1단계(자기 제한: 부모 0.72↑만 임계 통과). 실측: 넷마블→하이브 9.2% 수집, BTS 유니버스 넷마블 0.57 편입. ③ 콘솔 수동 엣지(FR-STR-070b ⑦): addEdge API(화이트리스트·중복 409·감사 로그·즉시 verified/proposed_by=manual)+KnowledgeTab 폼(모듈 레벨 컴포넌트 — 리마운트 함정 회피)+로더 note 운반→Concept Universe 이유 표시(0.70). LB인베스트먼트류 펀드 경유 투자가 이 경로. 테스트: 라우트 2·equity 홉·수동 note·dedupe — 백엔드·프론트 전체 통과. SRS FR-STR-069 ②·FR-STR-070b ⑦·FR-STR-072b | ✅ 완료 |
| Concept Universe 테마 되묻기 통합 — 'bts 관련 종목' 사고 2차 (2026-07-25) | 스크린샷 사고: "bts 관련 종목 전략"이 여전히 미디어/엔터 업종 전체로 진행. 원인 2중: ① **프론트 회귀** — 백엔드는 테마 되묻기(`clarification_priority=theme_universe`, 신세계·하이브 칩)를 정상 전송했으나 `page.tsx`의 explicit 설정 게이트(`getNextMissingBacktestCondition(requireExplicitConfiguration)`)가 시장 질문으로 덮어써 컨셉 종목 제한 선택지가 소멸(칩 답변은 로컬 결정 적용이라 재노출 기회도 없음) ② **배선 공백** — FR-STR-072 `build_concept_universe`(BTS→13종목 점수·근거)가 지식 API에만 붙고 되묻기 종목 집합은 직접 학습 엣지 2곳(신세계·하이브)뿐. 수정: ① `knowledge_graph.theme_backtest_companies` 신설(되묻기 전용 확장 뷰 — **학습 앵커 한정** Concept Universe 기본 임계 이상 선정, 시드/카탈로그 앵커 비확장=지분 홉 노이즈 차단, 뉴스 보도일 심볼 이월, `theme_listed_companies` 정밀 계약 불변) + nl_parser 되묻기·strategy_builder 소비 전환, 문구 "사업적 관련 근거가 확인된 상장사(등록 관계·공시·검색 출처 근거)" ② `page.tsx`가 theme_universe 되묻기를 explicit 게이트보다 우선 표시. 실측: 되묻기 칩=하이브·JYP·에스엠·YG·큐브·LB인베·신세계·넷마블·키이스트·드림어스 10종목, 칩 왕복 10/10 target_symbols 확정. 테스트: `test_theme_backtest_companies_expands_learned_anchor`+시드 비확장 가드+프론트 되묻기 우선 가드 — 백엔드 2,497·프론트 1,168 전체 통과. SRS FR-STR-072 ④ 갱신 | ✅ 완료 |
| 테마 되묻기 프록시 우선순위 마커 누락 수정 (2026-07-25) | 'bts 관련 종목' 3차 증상: 백엔드(빌더·파스·SSE 전부)와 프론트 게이트가 정상인데 UI는 여전히 시장 질문 — 라이브 계층별 이분 탐색으로 원인 격리: **Next 프록시**(app/api/strategy/parse/stream/route.ts)가 백엔드 result→parsed_final 변환 시 필드 화이트리스트에서 `clarification_priority`를 누락(스키마 누수 함정의 프록시판). 프론트 theme_universe 우선 게이트가 마커를 못 봐 explicit 설정 질문(시장)이 되묻기를 덮어씀. 수정: 프록시 passthrough 1필드+회귀 테스트(우선순위 계약의 프록시 구간 고정). 교훈: 이벤트 변환 프록시의 명시적 필드 목록은 백엔드 스키마 확장 시 동기화 지점 — result 계열 새 키 추가 시 프록시 화이트리스트도 확인할 것 | ✅ 완료 |
| 테마 유니버스 되묻기 폐지 — 자동 적용 전환 (2026-07-25) | 사용자 결정("메세지 삭제하고 종목들을 유니버스로 설정해, 물어보지마"). FR-STR-071 ④·071b ④ 개정 — ① 파싱: `detect_theme_universe_clarification`(+Phase 2 공급망 확장 칩) 삭제 → `apply_theme_universe` 신설(DSL 변환 전 target_symbols 자동 설정+sector 해제+비차단 notice로 목록·근거·시점 고지, 자동 다종목은 symbol_ambiguity 게이트 제외) ② 빌더: `_theme_patch` 즉시 확정형(theme_symbols·label·sector None), `_theme_reask_prompt`/`_answer_theme_reask` 기계장치 제거, 시작일 클램프(theme_first_date) 폐지(조용한 1개월 축소 방지 — 시점 편향은 notice만) ③ clarification_priority 필드·프록시 passthrough·프론트 우선 게이트는 스키마 호환 유지(항상 None). 라이브 E2E(:3000): "bts 관련 종목 투자 전략" → 질문 없이 10종목 지정+notice+다음 질문은 일반 최소조건 가이드. 테스트: 되묻기 계약 테스트 3건→자동 적용 계약으로 개편(test_theme_universe_autoapply 신설, expansion 테스트 폐기) — 백엔드 2,494·프론트 1,169 전체 통과 | ✅ 완료 |
| 테마 자동 적용 후속 결함 2종 — 종목명 미표시·매수 조건 게이트 우회 (2026-07-25) | 테마 유니버스 자동 적용(FR-STR-071 ④ 개정) 직후 스크린샷 제보 2건. ① **빌더 요약 카드 종목명 미표시**: "현재까지 이해한 전략입니다"의 유니버스가 코드만 나열(352820 · 035900 …) — `buildBuilderTurnPresentation`이 `getDisplayUniverseLabels`에 `backtestRequest`(백엔드 `target_stocks` 코드→종목명)를 전달하지 않던 배선 공백. `builderProgressPresentation.ts`에 `backtestRequest` 파라미터 신설+`page.tsx` 호출부 6곳 배선(요청 미도달 시 코드 폴백 유지) ② **매수 조건 없이 "모든 조건을 정했습니다" 확정 유도**: 진행률 7/8(매수 조건 미체크)인데 확정 버튼 노출 — 최소 조건 게이트(프론트 `backtestReadiness.hasEntry`+백엔드 `_missing_backtest_conditions.has_entry`)가 `target_symbols`를 진입으로 인정(2026-07-22 Q2)했으나, 엔진은 빈 진입 조건 그룹에 all-False 시그널을 반환해(signals.py) 지정 종목이어도 매수 시점 규칙 없이는 **0거래**다. 테마 자동 적용이 target_symbols를 채우면서 이 판정 오류가 상시 노출. 지정 종목 진입 인정을 양쪽 게이트에서 제거(FR-STR-023의 "진입 신호·재무 필터·랭킹만 매수 기준" 원칙에 정렬) — 단일 종목 빌더(FR-STR-068b)는 원래 진입을 묻므로 UX 변화는 지정 종목 파싱 경로에 매수 질문이 추가되는 것뿐. 테스트: 프론트 회귀 2(요약 카드 이름/코드 폴백·테마 지정 종목 진입 필수)+백엔드 갱신 2·신규 1(`test_incomplete_conditions_theme_universe_still_requires_entry`) — 백엔드 2,495·프론트 1,171 전체 통과 | ✅ 완료 |
| 검색으로도 못 찾은 테마 '전략 불가' 종결 안내 — '리센즈 관련주' 사고 (2026-07-26) | 스크린샷 사고: "리센즈 관련주 투자 하는 전략"이 그라운딩 검색까지 수행됐고(어휘집 학습: sector=null·관련 상장사 엣지 0건 — 올바른 '못 찾음' 판정) 백엔드는 섹터 되묻기(SECTOR_REASK)를 반환했는데, 프론트 explicit 설정 게이트(`getNextMissingBacktestCondition`)가 `clarification_priority`가 없는 백엔드 질문을 삼켜 일반 시장 질문("먼저 어떤 시장·종목을…")으로 조용히 강등 — 사용자에겐 테마가 무시된 채 전략 생성이 계속됐다. 사용자 결정: 검색 후 관련주를 찾으면 즉시 유니버스 적용(기존 FR-STR-071 ④), 못 찾으면 **'관련주를 찾을 수 없어 이 테마로는 전략을 만들 수 없다'고 종결 안내**(억지 매핑 금지). 수정: ① `nl_parser.detect_unresolved_sector_clarification` — 어휘집에 검색 수행 원장(searched_at)이 있고 sector 매핑·테마 자동 적용 모두 실패한 용어는 `THEME_NOT_FOUND_QUESTION`(칩에 '업종 상관없음' 제외 — 이 테마로는 진행 불가) 종결 안내, 미검색 용어는 기존 오타 정정 되묻기 유지 ② `main._build_parse_result` — 미해결 업종/테마 질문에 `clarification_priority="sector_unresolved"` 마커(primary 인터프리터 질문 덮어쓰기 방지 겸용) ③ `page.tsx` — theme_universe 전용이던 우선 게이트를 임의 non-null priority로 일반화(게이트 삼킴 방지). 테스트: 백엔드 신규 4(종결 안내·테마 적용 시 스킵·미검색 되묻기 유지·priority 마커)+프론트 회귀 1(`page.scroll.test.tsx` — 게이트가 종결 안내를 삼키지 않음). **후속('이재명 관련주' 사고, 같은 날)**: 테마 자동 적용이 10종목을 확정했는데도 업종 되묻기가 그 위에 뜸 — priority 마커가 생기며 종전엔 프론트 게이트에 삼켜져 안 보이던 백엔드 결함(테마 적용돼도 reask 반환)이 표면화. `detect_unresolved_sector_clarification`에 target_symbols 확정 시 `(None, None)` 조기 종결(테마 언급=종목 목록으로 해석 완료 → 다음 최소 조건 질문으로 전략 만들기 계속)+`_build_parse_result`의 미지원 안내 exclude에 theme_notice 추가('설정했어요'와 '지원되지 않아요' 공존 모순 방지). 테스트: 갱신 1·신규 1(`test_build_parse_result_theme_applied_continues_without_sector_reask`) — 백엔드 2,500·프론트 1,174 전체 통과. 사용자 문구 결정으로 종결 안내에서 '인터넷 검색' 표현 제거. SRS FR-STR-069 ⑧ 신설 | ✅ 완료 |
| 복수 지정 종목 '한 종목만 고르기' 되묻기 폐지 (2026-07-26) | 스크린샷 사고: 테마 유니버스 10종목 확정 상태에서 "종목을 교체 할 수 있나?" 질문에 `detect_symbol_ambiguity`가 종목 선택 칩 10개("삼성전자만으로 백테스트해줘" …)를 띄움 — 발화에 종목명이 하나도 없는데 이전 상태의 target_symbols(테마 적용분)만 보고 발동. 사용자 결정: 옵션창 삭제, LLM이 있으니 채팅 입력만으로 교체·축소를 처리("삼성전자만으로"·"현대약품은 빼줘"는 기존 수정 경로 `_target_change_from_utterance`가 결정적 처리). `detect_symbol_ambiguity`+`_COLLECTIVE_TARGET_CUE_RE` 삭제, `_build_parse_result` 배선 제거(theme_notice 억제 게이트도 불필요해짐 — 여러 종목=전체 백테스트가 유일 동작). 테스트: 폐지 계약 2건(`test_symbol_ambiguity_reask_removed`·`test_build_parse_result_multi_symbol_no_pick_one_clarification`)으로 기존 되묻기 테스트 2건 교체 — 백엔드 2,500·프론트 1,174 전체 통과. SRS FR-STR-068 ④ 개정 | ✅ 완료 |
| 종목 변경 의향 채팅 안내 + respond 요약 카드 상시 동반 (2026-07-26) | 스크린샷 사고: "종목을 변경 할 수 있나?"가 값 없는 수정 되묻기 테이블(`conversationDecision.MODIFICATION_CLARIFICATIONS`)에 '종목' 항목이 없어 수정 파싱으로 흘러 무변경 재렌더링+다음 조건 질문("어떤 조건에서 매수할지")으로 흐름이 끊김. ① 신규 항목 `missing_target_symbols_change`: 구체 종목명 없는 교체 의향("종목을 변경/교체/바꿀 수 있나?"·"다른 종목으로")을 가로채 **칩 없이**(사용자 결정 — 특정 종목 선택지는 추천 소지, LLM 수정 경로가 자유 발화 처리) 채팅 입력 안내만 응답("삼성전자만으로"·"빼줘"·"관련주로" 예시 포함). 구체 종목명 동반 발화는 어미 인접성 규칙으로 topicPattern 미매칭 → 기존 수정 파싱 통과 ② `page.tsx` respond 두 분기(결정론 즉답·분류 후 즉답)에 현재 전략이 있으면 '현재까지 이해한 전략입니다' 요약 카드(`builderPresentation`)를 항상 동반(사용자 지시 "채팅창 보여줄 때 요약 카드 항상"). 테스트: conversationDecision 신규 2그룹(의향 4케이스 가로챔+구체 4케이스 통과)+page 레벨 1(카드 동반·칩 없음·재파싱 없음) — 프론트 1,183 전체 통과(백엔드 무변경) | ✅ 완료 |
| 빌더 조건 수정 규칙 — 진행 중 삭제·선행 설정·값 없는 변경 (2026-07-26) | 사용자 결정: 전략 생성 과정 어느 시점이든 이미 결정된 조건을 변경·삭제·추가할 수 있어야 한다(FR-SA-002e 신설, 판정은 전부 결정적 정규식 — LLM 분류기 없음). ① **REMOVE**(`_parse_removal`): 삭제 cue(빼·삭제·제거·없애·지워·취소)가 채워진 필드를 지목하면 그 필드만 비우고 "…조건을 제거했습니다" 안내 후 진행 위치 복귀 — 청산 개별/전부·필터 종류별/전부·업종·테마 종목·보유 종목 수, 리밸런싱 삭제는 '안 함' 명시 변경, 청산 값 전부 소실 시 청산 단계 재개(필수 유지), "손절 취소해줘"의 '취소'는 빌더 취소보다 삭제 우선 ② **SET-ahead**: 다른 단계에서 미리 말한 청산 조건을 키워드 앵커 파서로 흡수(`risk_done` 완료+확인 문장 — 이미 준 값 안 되묻기), 필터는 '필터' 명시 시에만("60일 이동평균" 파라미터 답의 추세 필터 오귀속 방지) ③ **값 없는 변경**(`_parse_valueless_change`): "시장 바꿔줘"·"전략 바꿀래"(활용형 '바꿀' cue 추가)처럼 새 값 없는 변경은 해당 필드를 비워 그 질문으로 자연 복귀(청산은 값 유지+단계만 재개) ④ 가치 전략 상태의 ETF 유니버스 변경 차단 안내(BF-12 역방향)+업종 변경 cue 덮어쓰기(BF-05 확장). 발견 결함 2: 업종 삭제 문구가 미지원 업종 되묻기로 새던 것, 변경 cue '바꿀' 활용형 누락. 테스트: 신규 17(`test_builder_modify_rules.py`) — 백엔드 2,517·프론트 1,183 전체 통과+퍼징 게이트(`qa_builder_fuzz.py`) 0실패. SRS FR-SA-002e | ✅ 완료 |
| 지정 종목 개별 삭제 오독 — "현대약품은 빼조"가 단일 종목 지정으로 교체되던 사고 (2026-07-26) | 스크린샷 사고: 테마 유니버스 10종목("이재명 관련주") 상태에서 "현대약품은 빼조"(빼줘 오타)를 보내자 현대약품 **단일 종목** 전략으로 교체됨. 원인: `_target_change_from_utterance`에 삭제 의미론이 없고(종목 언급=지정/교체가 유일 해석), 문맥 가드 `_TARGET_SYMBOL_CONTEXT_GUARD_RE`가 '빼고/제외/말고'만 알아 '빼줘/빼조' 활용형을 통과시킴 — 룰 fast-path(`_modify_rule_based`)와 LLM 병합 두 경로 모두 동일 결함(FR-STR-068 ⑥의 "'현대약품은 빼줘' 처리" 기술은 실구현 없는 상태였음). 수정: ① `_removal_mentioned_target_refs` — 기존 지정 목록 중 표면형+삭제어 **인접**(종목/주식 명사·조사 허용, 섹터 개별 삭제 패턴과 동형) 언급 종목을 제거 대상으로 판정, "현대약품 손절 빼줘"(청산 삭제)와 혼동 차단 ② `_target_change_from_utterance`에 삭제 분기(지정/교체보다 우선) ③ `_modify_rule_based` fast-path에도 삭제 분기+표면형 잔여 차감 ④ `_extract_target_symbols`가 삭제어 인접 언급을 지정으로 승격하지 않음(초기 파싱 오폭 방지). 테스트: 신규 6(`test_single_asset_backtest.py` — 빼조 오타·빼줘·제외, 손절 혼동 가드, 초기 파싱, fast-path 삭제/교체 회귀) — 백엔드 2,522 전체 통과. SRS FR-STR-068 ⑥ 개정 | ✅ 완료 |
| 리로드 직후 로그인 사용자에게 로그인 모달 오노출 수정 (2026-07-25) | 사용자 제보: 페이지 리로드 후 이미 로그인돼 있는데 간헐적으로 "Google로 시작하기" 모달이 뜸. 원인: `page.tsx` 인증 게이트가 `authState !== "authenticated"`로 판정하는데 리로드 직후 `authState`는 `"loading"`(`/api/user` 왕복 — 원격 Postgres 수백 ms~수 초)이라, 하이드레이션이 끝나기 전에 전략 프롬프트를 보내거나 예시 칩을 누르면 loading을 비로그인으로 오인해 모달 노출(간헐성=왕복 시간과의 레이스). 수정: loading 중 전송은 `pendingAuthGatePromptRef`에 보관 후 조용히 대기 → 하이드레이션 완료 시 authenticated면 자동 재전송, anonymous 확정 시에만 pending prompt 저장+모달 표시. 테스트: `page.auth-entry.test.tsx` 회귀 2건(loading 중 전송 → 로그인 확정 시 모달 없이 자동 전송·소프트 내비게이션 / anonymous 확정 시에만 모달) — 프론트 1,173 전체 통과 | ✅ 완료 |
| 해석 파이프라인 권한 역전 — 결정론 선점 폐지·전면 되묻기 폴백 (2026-07-26) | 발단 사고: "제주반도체를 추가해줘"가 HTTP 500("전략을 해석하지 못했습니다") 후 **무엇을 입력해도 같은 에러**인 영구 교착. 원인 2중 — ① 오염 주입: 프론트 최소조건 칩('ROE 15% 이상')이 `deterministicConditionFlow.ts`에서 정본이 아닌 `metric:"roe"`(정본 `roe_or_gpa`)를 프론트 상태에 직접 기록 ② 영구 교착: 이후 모든 수정 발화에서 `_modify_rule_based`의 `ParsedStrategy.model_validate(previous)`가 **이전 상태** 검증으로 ValidationError → `main.py`가 500 변환(사용자 입력은 멀쩡한데 "입력을 바꾸라"). 근본 진단: 얕은 결정론(문자열 cue 차감)이 **최초 해석자이면서 동시에 실패시킬 권한**을 가진 구조. 수정 ① 권한 역전(FR-STR-019h): 수정 경로 fast-path 선제 게이트를 `STRATEGY_MODIFY_INTERPRETER_MODE`(기본 `llm_first`, 롤백 `fast_path_first`)로 전환 — fast-path 코드는 **삭제하지 않고 폴백으로 강등**(인터프리터가 패치 미출력·전량 환각 거부·검증 미통과·호출 실패면 fast-path가 즉답). ② 예외 격리: fast-path 예외는 로그만 남기고 "내 소관 아님"(None)으로 강등(`primary.fast_path_can_handle`·`parse_modification` 양쪽) ③ 500→되묻기: 모든 해석 레이어 실패 시 `main._interpretation_failure_result`가 기존 전략 보존+예시 칩+`clarification_priority="interpretation_failed"`로 되묻는다. **500/503은 인프라 장애 전용**(LLM 연결 실패는 503 유지) ④ 별칭 정규화(FR-STR-019i): `FundamentalFilter.metric`에 `BeforeValidator`(별칭 표 `roe`→`roe_or_gpa` 등 + 대소문자/공백/하이픈/슬래시 정규화) — `model_validate` 전 지점 1회 커버(경로별 새니타이저 금지). 표에도 없는 값은 그 필터만 드롭+비차단 notice(전체 실패도 조용한 드롭도 금지, `dropped_filter_notices`는 직렬화 제외라 DSL·캐시키·라운드트립 불변) ⑤ 오염원 차단: 프론트 칩 metric을 정본 `roe_or_gpa`로 교정 + 레거시 표기 라벨 매핑(`lib/strategy-summary.ts`). 실측 A/B(dev primary, 27케이스=qa_modify_accuracy): **정확도 24/26 → 24/26 동일**(케이스별 차이 0, 과다변경 0), 지연 중앙값 **59ms → 3,596ms**(단순 수정 "손절 10%로" 6ms → ~6s — fast-path 선점 폐지의 대가, 롤백 플래그로 즉시 복원 가능). 테스트: 신규 13(`test_interpretation_authority.py` — 오염 previous 무500·별칭 정규화·미지 값 드롭+notice·fast-path 예외 강등·해석 실패 되묻기·503 보존·모드 플래그 4) — 백엔드 2,535·프론트 1,183 전체 통과, `qa_builder_fuzz.py` 0실패 유지. **미완(권고)**: 프론트 `conversationDecision.ts` 규칙 이관은 보류 — 개별 되묻기 규칙만 떼면 같은 발화가 프론트의 `answer_follow_up`/`classify` 분기에 삼켜져 백엔드에 도달조차 못 한다(실측 확인). 선행 과제는 **턴 중재권(어떤 발화가 백엔드에 가는가) 이관**이며 그 뒤에 규칙 이관 | ✅ 완료 |
| 유니버스 해석 권한 이관 — 1a+4 (2026-07-26) | 자연어 해석 계약([`docs/nl_interpretation_contract.md`](nl_interpretation_contract.md)) 마이그레이션 1단계. 목표: 지식 조회(업종·종목 정본 매핑)를 **원문 정규식에서 떼어내 LLM 출력을 입력으로 받는 registry로 재배치** — 이 레이어는 LLM이 대체 불가(4B는 종목코드를 환각)하므로 삭제가 아니라 이동 대상. ① `registry/universe_resolver.py` 신설 — `resolve_sectors`(정본 사전 `normalize_sector` → 지식그래프 `resolve_sector_from_text` 2단계, 정규형 None/str/list 유지)·`resolve_symbols`(6자리 코드=`resolve_by_symbol`, 종목명=`find_in_text`, 해외 종목은 OHLCV 부재로 unresolved 강등). 둘 다 **해석 실패 표현을 반환**해 조용한 소실 금지 ② `UniverseSpec.symbols` 신설(FR-STR-068 스키마 공백 해소 — 지정 종목이 `nl_parser._extract_target_symbols` 결정적 추출로만 존재하던 상태) + 단일 문자열·비문자열 드리프트 정규화(`_coerce_str_list`) ③ 컴파일러 배선 — 기존에는 `strategy.universe.sectors`를 **정본화 없이** `ParsedStrategy.sector`에 직접 넣어 LLM이 비정본 표기를 내면 유실됐고 `target_symbols`는 아예 미배선. 이제 둘 다 resolver 경유 ④ 디컴파일러 왕복에 `symbols` 추가(수정 초안에서 지정 종목 소실 방지) ⑤ 프롬프트 규칙 6-0-1(종목 표현은 원문 그대로, 코드 환각 금지) + PROMPT_VERSION 1.3→1.4. 하위 호환: `_apply_prompt_overrides`는 이 단계에서 유지 — 원문 정규식이 침묵할 때만 LLM 값이 살아남는 가산적 변경(제거는 1b/2단계). 테스트: 신규 17(`test_universe_resolver.py` — 정본화·복수·dedup·미해석 보고·코드/종목명/해외·컴파일 배선·왕복·드리프트) — 백엔드 2,552·프론트 1,183 전체 통과 | ✅ 완료 |
| 결정적 보정 제거 실측 + 가려진 결함 4종 수정 — 2+1b (2026-07-26) | 자연어 해석 계약 마이그레이션 2단계. `_apply_prompt_overrides`(컴파일 결과를 사용자 원문 정규식으로 덮어쓰는 레이어) 제거를 시도하고 **실측으로 판정**했다. ① 롤백 플래그 `STRATEGY_PROMPT_OVERRIDE_MODE`(on 기본/off) — primary 호출부 3곳 게이트, 기존 `STRATEGY_MODIFY_INTERPRETER_MODE` 선례와 동형 ② 계측기 `scripts/qa_prompt_override_ab.py` — qa_complex_llm_parse 103케이스를 ON/OFF로 `run_primary_parse`에 통과시켜 필드 단위 비교(LLM 응답 프롬프트 캐시로 측정시간 절반). **실측: ON 85~87 vs OFF 36→51/103** — 잔여 34건 중 20건이 4B의 조건 누락/오지정(모델 recall 한계), 프롬프트 규칙 한계수익 붕괴(v3→v4 신규통과 9·신규실패 6). **결론: 기본값 off 전환 보류**, 선행 조건은 인터프리터 모델 승격 또는 검증 레이어 recall 체크(원문 '대조'는 계약 위반 아님). ③ **보정이 가리고 있던 결함 4종을 양쪽 경로에서 수정** — (a) 미러 청산 가드 오폭: `_drop_mirrored_valueless_exits`가 골든/데드크로스·볼린저 하단/상단처럼 factor 같고 value 없는 **정당한 반대 방향 이벤트 청산**을 삭제(진입에 없는 이벤트 연산자면 보존하도록 수정) (b) 표준값 파라미터 조건 드롭: 사용자가 명시한 신호("데드크로스에 청산")를 기간 미언급 이유로 `compile_partial`이 통째 제외 → Registry 표준값(20/60)으로 컴파일하되 되묻기는 유지(임계값 누락은 기존대로 제외 — 전략 의미 미정) (c) `execution_timing` 스키마 공백: `BacktestSpec`에 신설+컴파일러/디컴파일러 배선+출력형식·규칙 11-1, 겸해서 `_carry_over`의 무조건 이월 제거("당일 종가로 체결해줘" 수정이 삼켜지던 결함) (d) 오실레이터 연산자: Registry가 비교 연산자만 허용하는데 LLM이 `crosses_above`를 내 operator/value가 소실 → 프롬프트 규칙 5-3. 추가 규칙 4-1(조건 누락 방지)·5-0(미언급 기간 지어내기 금지)·5-2(이상/이하=포함 비교)·5-2-1(가격 vs 단일 MA=short 1/long N), PROMPT_VERSION 1.4. 테스트: 신규 7(미러 가드 반대방향 보존·같은방향 폐기, 표준값 파라미터 보존·임계값 제외 경계, execution_timing 컴파일/기본값/왕복) — 백엔드 2,559·프론트 1,183 전체 통과 | ✅ 완료 |
| 수치 반영 대조 검사 — 2′a (2026-07-26) | 마이그레이션 2단계의 선행 과제. `_apply_prompt_overrides`가 **값을 채우던** 일을 계약 위반 없이 대체한다: 원문을 해석하지 않고 **대조**만 해서 누락을 감지하고 LLM에 재생성을 요청한다. ① `validation/recall_validator.py` — 입력 숫자 앵커와 출력(StrategyIntent) 전 필드의 수치를 대조, 단위 환산 인정(5000억↔5000·1조↔10000·1억↔1e8·52주↔252/260·3개월↔63·2020년↔"2020-01-01"·3년↔"3y"), 부호 무시(CCI -100), 6자리 종목코드 제외. `source_text` 인용은 반영으로 **불인정**(조건 버리고 원문만 인용하는 우회 차단), `unsupported_features`는 인정(표현 불가 명시는 정당한 결과) ② 인터프리터 루프 배선 — 스키마 검증 통과 후 대조, 누락 시 증거("미반영: 80%, 5000억")를 실어 1회 재요청, 재요청 예산은 `MAX_REPAIR_ATTEMPTS` 공유, 소진 후 잔존해도 요청을 실패시키지 않음(누락은 스키마 오류가 아님). 롤백 `STRATEGY_RECALL_CHECK=off` ③ 계약서 § 3-1에 '대조 예외' 명문화 — 허용 조건 4개(의미 미결정·출력 미수정·실패 시 재생성만·유한 예산) 전부 충족해야 하며, **어휘 대조는 금지**(동의어 매핑=해석). **실측(103케이스 A/B)**: OFF 51→58, ON 85→87, 대조 발동 약 21건 전부 재요청 1회로 해소(**잔존 0**), `fundamental_filters` 불일치 16→10·`execution_timing` 2→0. 잔여 29건은 `ma_crossover` 7·`breakout` 5 등 **수치 없는 신호 누락**이라 이 방식의 사정거리 밖 — 2번(보정 제거)의 남은 선행 조건은 인터프리터 모델 승격(2′b). 테스트: 신규 14(`test_recall_validator.py` — 누락 감지·source_text 불인정·unsupported 인정·오탐 방지 8종) — 백엔드 2,573·프론트 1,183 전체 통과. SRS FR-STR-019j | ✅ 완료 |
| 결정적 보정 기본값 off 전환 — 2+1b 완료 (2026-07-26) | **사용자 결정**("어떤 경우라도 regex가 자연어를 해석/이해 하려는 시도는 없어야 해")에 따라 `STRATEGY_PROMPT_OVERRIDE_MODE` 기본값을 on→off로 전환. 인터프리터 경로에서 `_apply_prompt_overrides`가 더 이상 LLM 해석을 덮어쓰지 않는다(함수 자체는 레거시 파서가 써서 존치, 삭제는 1c 이후). ① **A/B를 전환 기준으로 쓰지 않기로 판정** — 잔여 26건 중 7건이 하니스 `expect`가 정규식 인코딩 관례를 기대값으로 담은 것('주가가 20일선 위'→`ma_crossover(short=1,long=20)`; LLM의 `ema(mode=above)`가 틀린 게 아님). ON 점수는 정답이 아니라 '정규식과 일치하는 정도'이므로 이후 개선은 실사용 케이스로 진행. ② **모델 승격은 답이 아니었음** — 4B→9B가 OFF를 58→57로 못 움직였고, 대신 계약 결함을 닫자 57→64(v6~v8). v9의 프롬프트 규칙 추가는 순감(신규통과 2/신규실패 4)이라 되돌림 — 한계 수익 소진. ③ **보정 대체 배선** — 지정 종목=LLM `universe.symbols`→resolver, 명시 날짜=LLM `backtest.start_date/end_date`, 누락 수치=대조→재생성, 업종=LLM `sectors`→resolver, 체결 시점=`BacktestSpec.execution_timing`. ④ **전환 중 막은 회귀** — `/universe/symbols` 패치가 환각 게이트 키워드 큐(`universe`=시장·업종·섹터)에 걸려 거부되던 FR-STR-068 구멍. 종목명은 열린 집합이라 큐로 열거 불가·원문 스캔은 계약 위반이므로 **해석 가능성**(마스터 조회)으로 거르도록 변경. ⑤ **부수 수정** — AI 예측 임계값이 사용자 값(80%)을 무시하고 Registry 기본값 70%로 백테스트되던 컴파일러 버그(`_param`이 `cond.value`보다 먼저 기본값을 채움), Registry `notes`의 프롬프트 미주입(구별 근거 없는 `fundamental/technical.trading_value` 동명 지표), `assumptions` 서술로 조건을 빠뜨리던 대조 우회로, JSON 문자열 내 미이스케이프 따옴표(사용불가 6→3). ⑥ 기존 계약 테스트 5건을 새 계약으로 재작성 + **롤백 가드 테스트** 병행(탈출구가 조용히 썩지 않도록). 프로덕션 영향 없음(`STRATEGY_INTERPRETER_MODE` 코드 기본값 여전히 off). 롤백=`STRATEGY_PROMPT_OVERRIDE_MODE=on`. 백엔드 2,580 통과. SRS FR-STR-019j | ✅ 완료 |
| strategy_conversation 잔여 원문 해석 5곳 제거 (2026-07-26) | 계약 수립 후 재감사에서 새 파이프라인 안에 남아 있던 원문 정규식/어휘 판정 5곳을 전부 LLM 해석(또는 § 3-1 대조/§ 3-2 지식 조회)으로 이관(계약서 § 11-4). ① **패치 환각 게이트** — 필드별 한국어 어휘 목록(`_PATCH_FIELD_CUES`) 발화 스캔 폐기 → **출처 대조**(`_patch_provenance_supported`): `PatchOp.source_text`(신설, LLM이 인용한 원문 조각) 실재 확인(표기 정규화 후 포함 — %↔퍼센트 흡수)+패치 수치의 입력 수치 대조(단위 환산, recall_validator 재사용)+종목 해석 가능성. 프롬프트 규칙 10이 패치별 인용을 계약화(PROMPT_VERSION 1.5), QA 20-3(무근거 패치 거부) 보호 유지 ② **질문 여부 판정** — `is_definition_question`·`is_default_question`·질문 정규식(원문 의도 분류) 제거 → 인터프리터 라벨(`EXPLAIN_INDICATOR`)만 신뢰, 라벨 드리프트는 프롬프트 규칙 10 소관(질문이 unsupported로 오라벨되면 미반영 안내로 강등 — 원문 cue 재해석 금지) ③ **조건 교정** — `_fill_deterministic_condition_params`의 원문 폴백 제거, 조건 `source_text`(LLM 인용)만 입력(52주 신고가 환산·거래량 급증 재분류) ④ **ETF 테마** — 컴파일러의 `extract_etf_theme(user_input)` 원문 추출 폴백 제거, LLM `universe.etf_theme`만(규칙 6-1) ⑤ **수정 fast-path 상담 제거** — llm_first에서 패치 부재·전량 거부 시 `_modify_rule_based`(원문 정규식) 상담하던 2곳 제거, LLM 되묻기가 그대로 전달·전량 환각은 정직한 미해석 안내(롤백 `fast_path_first` 모드에만 잔존). 계약서 § 3-1을 (a) 수치 대조/(b) 출처 대조로 확장, § 11 격차 2 잔여 항목 해소. 테스트: 갱신 7·신규 3(출처 대조 판정·무근거 패치 안내·llm_first 비상담) — 백엔드 2,583 전체 통과 | ✅ 완료 |
| 수정 레거시 폴백 제거 + 엔진 실효값 정규화 (2026-07-26) | 사고: "제주반도체 종목도 추가해줘"가 기존 테마 유니버스를 통째로 교체 — 원인 2중. ① 라운드트립 가드 오폭: 최소조건 칩("골든크로스 발생 시 매수", `deterministicConditionFlow.ts`)은 기간 필드 없이 저장되고, 수정 이관 왕복(decompile→compile)은 Registry 표준값(20/60)을 채워 원본(None)과 불일치 → '표현 불가'로 LLM 레인 진입 거부. **가드 판단 자체는 옳았다** — 엔진 실효값은 5/20이라 이관 허용 시 전략이 조용히 바뀜(Registry 20/60 ≠ 엔진 5/20 이원화 발견) ② 폴백된 레거시 레인의 결정적 종목 판정은 추가/교체를 구분하지 않아(합집합 의미론=LLM 소유, regex 판정 금지 봉인) 언급 종목으로 교체. 수정 2겹: ① `compiler/engine_defaults.py` — `materialize_engine_defaults`가 None 파라미터를 **엔진 실효값**(signals.py SOT: ma 5/20·stochastic 9·breakout 20·rsi 14 등, ema는 모드 전환 위험으로 의도적 제외)으로 명시 채움(의미 불변·요약 카드에 실제 기간 노출) → 라운드트립 성립 → 규칙 10-1 union 패치가 정상 추가 ② **llm_first 레거시 수정 폴백 제거(사용자 지시)** — 인터프리터가 처리 못 한 수정은 `parse_modification`(원문 regex 해석 포함)으로 절대 안 떨어지고 전략 보존+되묻기(FR-STR-019h 재사용). 연결 장애(OSError)는 되묻기로 위장하지 않고 재던져 503 경로 유지. 롤백=`STRATEGY_MODIFY_INTERPRETER_MODE=fast_path_first`(레거시 전체 보존, 회귀 테스트로 가드). **미결**: Registry 표준값(20/60) vs 엔진 기본값(5/20) 통일 — 신규 파스 결과값이 레인별로 갈리는 문제, 백테스트 결과 변경 사안이라 사용자 결정 필요. 테스트: 신규 7(`test_modify_roundtrip_migration.py` — 정규화 3·왕복 무손실·사고 재현 union·폴백 제거·롤백 보존) — 백엔드 2,637·프론트 1,184 전체 통과 | ✅ 완료 |
| 크로스 칩 기간 명시화 (2026-07-26) | 후속: 최소조건 칩 "골든크로스 발생 시 매수"가 기간 필드 없이 저장돼(엔진이 5/20을 조용히 적용) 요약 카드에 기간이 안 드러나고 라운드트립 오폭의 씨앗이 되던 불투명성 제거. 라벨·값 모두 기간 명시 — "골든크로스(5일/20일) 발생 시 매수"/"데드크로스(5일/20일) 발생 시 매도"(표기는 기존 `_MISSING_ENTRY_SUGGESTIONS` 선례, 값은 엔진 실효 기본값 5/20이라 **백테스트 결과 불변**). 동기화 3곳: `deterministicConditionFlow.ts`(매핑 키+short/long_period 값)·`backtestReadiness.ts`(칩 목록)·`engine/nl_parser.py detect_incomplete_backtest_conditions`(칩+질문 예시). 테스트: 신규 `deterministicConditionFlow.test.ts` 3건(기간 포함 매핑 계약+구 라벨 매핑 해제로 반쪽 갱신 방지)+기존 라벨 단언 갱신(백엔드 3·프론트 6) — 백엔드 2,637·프론트 1,187 전체 통과 | ✅ 완료 |
| 정규식 폴백 전면 차단 — 1c (2026-07-26) | **사용자 지시**("모든 정규식 폴백을 제거해줘") — "폴백은 자연어 재해석이 아니라 실패 보고"(계약 § 8-1)를 초기 파스 레인까지 적용(계약서 § 11-5). ① **초기 파스 인터프리터 폴백 차단** — primary 모드에서 `run_primary_parse` 실패(None: LLM 실패·비전략 intent·컴파일 실패) 시 `parser.parse()`(규칙 하이브리드) 재해석으로 떨어지던 폴백 제거 → 실패 보고(`interpretation_failed` 되묻기, 수정 레인과 동형). 규칙 하이브리드는 primary가 꺼진 환경(off/shadow)의 **기본 경로로만** 동작 ② **연결 장애 위장 방지** — `run_primary_parse`가 전송 오류를 None으로 삼키던 것을 그대로 던지도록 변경, main의 503 경로가 처리(인프라 장애가 "입력을 바꿔라"로 위장 금지) ③ **`_build_fallback_strategy` 삭제** — LLM 구조화 출력 불량(ValidationError/JSON 부재) 시 원문 정규식 전체 추출로 전략을 조립하던 최후 폴백(2026-07-12 "2차전지" 조용한 오해석 사고의 근원) 제거, 예외 전파 → 실패 보고/503 변환+부활 방지 테스트. 의도적 잔존(폴백 아님): off/shadow 규칙 하이브리드(1d 이관 전까지 primary), 롤백 knob 2종(`fast_path_first`·`STRATEGY_PROMPT_OVERRIDE_MODE=on`), 룰 파스 검증 미가용 graceful degrade(규칙이 primary인 경로의 검증 강등). 로드맵 1c ✅(5번 승격보다 먼저 랜딩), 1c'(KG text-in→term-in)는 구 파서가 기본 경로인 동안 보류. 테스트: 신규 5(`test_parse_fallback_blocked.py` — 실패 보고·off 기본 경로 보존·전송 오류 전파·부활 가드)+구계약 테스트 1건 삭제·4건 갱신 — 백엔드 2,641 전체 통과 | ✅ 완료 |
| 크로스 기간 옵션 되묻기 (2026-07-26) | 사용자 결정: "골든크로스로 매수해줘"처럼 기간 미지정 크로스는 조용한 기본값 확정 대신 **옵션 칩과 함께 되묻는다**. completeness는 이미 파라미터별 질문(단기/장기 각각, required ParamSpec)을 내고 있었으나 칩이 없고 질문이 쪼개져 있었음. ① `_build_clarification`이 ma_crossover 기간 파라미터 질문들을 **조건(역할)당 1개로 병합** — "매수(진입)/매도(청산) 이동평균 크로스의 기간(단기/장기)은 몇 일로 할까요? (일반적으로 20일/60일…)" + 옵션 칩 3종(5/20·20/60·60/120)은 **조건 전체를 담은 무상태 재전송 표기**("골든크로스(5일/20일) 발생 시 매수" — 크로스 칩 기간 명시화와 동일 정본, 재전송 시 수치 대조·환각 게이트 통과) ② 수정 경로 개선 — 패치 적용 후 오류 없이 질문만 남은 미완성("데드크로스 청산 추가해줘")은 폴백(→generic 되묻기) 대신 전략 무변경+구체 질문+옵션 칩 반환(`primary_modify_needs_value` 모드). 전략 본문은 표준값으로 실행 가능하게 유지(조건 소실 금지)하되 확정 대신 질문 병행. 테스트: 신규 3(`test_cross_period_clarification.py` — 병합+칩 계약·초기 파스 옵션 되묻기·수정 미완성 옵션 반환) — 백엔드 2,644·프론트 1,187 전체 통과 | ✅ 완료 |
| STRATEGY_INTERPRETER_MODE 기본값 primary 승격 — 5 (2026-07-26) | 자연어 해석 계약 로드맵 5번. 코드 기본값 `off`(규칙 파서 우선 하이브리드)→`primary`(LLM 인터프리터가 초기 파스 해석 주체) 전환 — 계약상 해석 주체는 LLM이며 off 기본값은 과도기 상태였다. **명시적 env가 계속 우선**: prod `/opt/simons/.env`의 `shadow`는 그대로라 프로덕션 동작 불변(prod primary 전환은 Modal 콜드스타트·keep-warm 검토와 함께 별도 결정 — 관찰 단계), dev `.env`의 `primary`도 기존과 동일, 테스트는 `backend/conftest.py`가 off 고정(격리 유지). 롤백=env `STRATEGY_INTERPRETER_MODE=off`. 갱신 문서: 계약서 § 11-1 게이팅 격차 해소 표기·로드맵 5 ✅, deployment.md env 표에 변수 추가. 테스트: 기본값 가드 신규 1(`test_interpreter_mode_defaults_to_primary` — 기본 primary+명시 env 우선) — 백엔드 전체 통과 | ✅ 완료 |
| KG 입력 계약 term-in 전환 — 1c′ (2026-07-26) | 자연어 해석 계약 로드맵 1c′(§ 11-3). 지식그래프·검색 그라운딩은 § 3-2의 정당한 지식 조회 계층이지만 입력이 사용자 원문이면 발화 스캔(계약 위반) — **primary 초기 파스 레인의 KG 입력을 원문→LLM이 뽑은 표현(term)으로 전환**. ① `primary._resolve_sector_terms_term_in` — 컴파일 후 리졸버가 못 푼 `universe.sectors` 표현별 체인: KG 테마 상장사 자동 적용(`apply_theme_companies` — `apply_theme_universe`에서 원문 큐 게이트 없이 분리한 코어, FR-STR-071 ④ 동일 계약)→검색 그라운딩 학습(`ground_term` 도구, 큐 게이트 없음 — '미해결' 판정은 리졸버 소관)→테마 재조회/섹터 병합(FR-STR-066 ⑦ 필드 계약)→끝까지 미해결이면 되묻기(검색 소진 테마=THEME_NOT_FOUND 종결 안내, `clarification_priority=sector_unresolved` 프론트 게이트 계약 유지) ② primary 초기 파스에서 원문 스캔 차단 — `_build_parse_result(scan_prompt_for_sector=False)`로 `apply_theme_universe`·`detect_unresolved_sector_clarification` 생략+미지원 안내에서 sector 상시 제외(term-in 체인이 단일 권위), 파싱 전 어휘집 학습(`_learn_unknown_sector_term`)도 생략 ③ 해석 실패 보고에도 원문 테마 스캔 미적용 — 실패 결과에 테마 상장사가 자동 적용되면 실패가 전략처럼 위장됨 ④ mini-planner shadow는 학습 전 상태를 관측하도록 체인보다 먼저 발사. **의도적 잔여**: 레거시 레인(off/shadow 기본 경로)·수정 레인·빌더의 원문 스캔은 유지 — 각각 1d·단계 3에서 이관. 테스트: 신규 8(`test_sector_term_in_chain.py` — 테마 적용·학습 병합·되묻기·종결 안내·필드 계약·검색 게이트·우선순위 이월·실패 보고 무스캔) — 백엔드 2,653 전체 통과 | ✅ 완료 |
| 빌더 자유 서술 LLM 레인 — 단계 3 C안 Phase 1 (2026-07-26) | **사용자 결정(C안)**: 빌더의 칩 클릭·값 답변("10프로")의 결정적 처리는 제한된 답의 형식 정규화로 목표 상태에 포함(계약 위반 아님), **자유 서술 해석만 LLM으로 점진 이관**. Phase 1: `intent/builder_interpreter.py` 신설 — 결정적 레이어(칩·값 파서·삭제/정정 큐)가 **아무것도 해석하지 못한** 자유 서술("일곱 종목쯤으로 널널하게")을 LLM이 제한된 ops JSON(set/remove/reopen×필드 화이트리스트)으로 해석 → 결정적 검증(enum·값 범위 `_risk_value_valid`/`_valid_count`·수치는 입력 수치와 대조(거래일 필드는 주5/월21/년252 환산 인정)·`source_text` 인용 실재(§ 3-1 출처 대조)·삭제=채워진 필드만·reopen=`_parse_valueless_change` 동일 계약·ETF×가치/단일종목 차단 가드 미러) → 기존 BuilderState patch 계약으로 적용, 탈락 op는 안내 노트로 알림(조용한 드롭 금지). 청산 전량 삭제 시 risk_done 재개방(FR-SA-002e 동일). `step(freetext_interpreter=)` 주입식 배선(routes `_builder_llm_helpers` 3-튜플) — 미주입/LLM 실패는 기존 미인식 안내 그대로(원문 재해석 폴백 없음), **미인식 표현에 regex 추가 금지(긴 꼬리는 이 레인 소관)**. 롤백=`BUILDER_FREETEXT_MODE=deterministic`. 잔여(Phase 2): 기존 결정적 자유 서술 큐 레이어(FR-SA-002e)의 권한 역전 — 실사용·QA 축적 후. 테스트: 신규 12(`test_builder_freetext_interpreter.py` — 값 적용·환각 수치/무인용 거부·삭제 게이트·risk 재개방·reopen·탈락 노트·경계(값 답변은 LLM 미호출)·LLM 장애 시 미인식 유지·env 게이트)+스트림 스텁 3-튜플 갱신 — 백엔드 2,665 전체 통과·**빌더 퍼징 QA 0실패 유지**(결정적 동작 보존 확인) | ✅ 완료 |
| Phase 3: prod primary 전환 — 1d 재정의 (2026-07-26 결정) | **사용자 결정 2건**: ① 레거시 파서(engine/nl_parser 해석 정규식·어휘집)는 **삭제하지 않고 코드 보존, 사용만 중지**(롤백 전용 — off/shadow 모드로만 도달, 구 계획의 'Regex·어휘집 제거'는 폐기) ② 테스트 단계라 **Modal scale-to-zero 유지**(콜드스타트 첫 파스 ~2분 수용, keep-warm 불요 — 종전 전환 블로커 해제). 실행: prod `/opt/simons/.env`의 `STRATEGY_INTERPRETER_MODE=shadow`→`primary`(코드 기본값과 일치, 코드 변경 불요)+컨테이너 재시작 — 이때부터 prod 사용자 응답도 LLM 인터프리터 레인이 담당. 주의: 프록시 SSE 스트림 예산 120s vs 콜드스타트 실측 101s — 근접하므로 콜드스타트 파스 실패 시 재시도 안내가 UX → **'다시 시도' 버튼 구현 완료(2026-07-26)**: 파싱 SSE가 결과(parsed_final) 없이 끊기면 조용한 로딩 방치 대신 타임아웃 안내 오류로 승격(`runStrategyParseFlow` 스트림 종료 검사)+오류 버블에 재시도 버튼(`ChatMessage.retryPrompt/retryAssumptions`, `handleRetryParse` — 사용자 버블 중복 없이 오류 버블을 로딩으로 되돌려 같은 턴 재실행, 분류 생략, 재실패 시 버튼 유지). parse_strategy 실패 catch 2곳 배선. 테스트 `page.parse-retry.test.tsx`(끊긴 스트림→버튼→재호출→본문 프롬프트 보존) — 프론트 1,188 전체 통과. **전환 실행 완료(2026-07-26)**: main 배포(1차 실패 — 크로스 칩 커밋의 `ParsedSummary` 타입 공백으로 Next 빌드 중단, `short/long_period` 추가로 해소 c2c6eef5; vitest는 타입체크를 안 해 CI 테스트로는 안 잡힘, 서비스는 무중단) → prod `.env` shadow→primary(백업 `.env.bak-shadow-20260726`)+backend 재생성 → 검증: 컨테이너 env=primary·Modal 워밍업 완료·실파싱 `runtime.interpreter.mode=primary`(9B, 웜 10.8s)·크로스 기간 옵션 칩 정상. 관찰 1건: "익절 25%" 수치를 인터프리터가 드롭(recall 재생성으로도 미복구) — 청산 되묻기가 표면화해 조용한 소실은 아님, 관찰 단계 품질 백로그 | ✅ 완료 |
| 백테스트 결과 화면에서 탑메뉴 '전략연구소' 이동 (2026-07-27) | 사용자 제보: 백테스트 결과 화면에서 탑메뉴 '전략연구소'를 눌러도 화면이 그대로여서 이동이 안 되는 것처럼 보임. 원인: 결과 화면은 전략연구소 라우트(`/analytics`) 안의 **상태**로만 렌더되므로(`showingBacktestResult`, 별도 URL 없음) 같은 경로로 `router.push`해도 리마운트가 없고, 다른 경로에서 들어와도 세션 스냅샷(`stage: "done"`)이 결과 화면을 복원. 수정: `strategyTemplateSession.ts`에 `requestStrategyLabChatView()` 신설 — ① 스냅샷 `stage: "done"`→`"ready"` 강등(대화·결과 데이터는 보존, 새로 마운트되는 화면용) ② `STRATEGY_LAB_CHAT_VIEW_EVENT` 디스패치(이미 마운트된 화면용). `TopNavigation.handleMenuClick`이 `analytics` 메뉴에서 호출하고, `app/analytics/new/page.tsx`가 이벤트 수신 시 `stage: "done"→"ready"`로 결과 화면을 내린다(실행 중 `running`은 대상 아님). 대화 유지 계약은 그대로 — 결과 화면만 내려가고 채팅은 복원된다. 테스트: `TopNavigationQuickSearch.test.tsx` 기존 스냅샷 보존 테스트를 새 계약(메시지·결과 보존+stage 강등+이벤트 발행)으로 갱신 — 프론트 1,189 전체 통과 | ✅ 완료 |
| 전략연구소 복귀 시 대화 끝(최대 스크롤)에서 표시 (2026-07-27) | 후속 제보: 전략연구소로 돌아오면 마지막 버블('백테스트 시작하기')이 고정 입력창(`ChatInputBox variant="fixed"`) 뒤에 걸려 보임. 원인: 복원된 대화에도 새 메시지용 입력창 회피 자동 스크롤(`[messages]` 이펙트, `computeChatScrollDelta`)이 그대로 돌아 **레이아웃이 안정되기 전 측정값**으로 아래로 내려가 버림(이후 카드가 커지며 마지막 버블이 다시 입력창 뒤로). 수정: ① `chatScroll.ts`에 `scrollChatViewToTop()`(main 컨테이너+윈도우) 추가 ② 스냅샷 복원 시 `suppressChatAutoScrollRef`로 그 1회 자동 스크롤을 맨 위 스크롤로 대체(빈 메시지 렌더에서 플래그가 소진되지 않도록 `messages.length === 0` 조기 반환) ③ 결과 화면 **이탈** 시(탑메뉴·뒤로가기)에도 맨 위 스크롤(`leavingResultView`) ④ 탑메뉴 이벤트 수신 시 대화 화면이면 스크롤만 맨 위로. 대화 중 새 메시지의 기존 자동 스크롤 동작은 그대로. ⑤ 재제보 후 실브라우저 재현으로 확정한 진짜 원인: 결과 화면→대화 화면 복귀는 **리마운트가 아닌 같은 마운트의 상태 전환**(URL 동일 `/analytics`)이라 복원 경로의 1회성 억제가 걸리지 않고, 복귀로 바뀐 상태(`stage`)와 뒤늦게 렌더되는 요약 카드·'백테스트 시작하기' 버튼이 `[messages]` 자동 스크롤을 다시 돌려 **맨 위 스크롤 직후 대화 끝으로 되끌어감**(rAF가 이펙트보다 늦게 실행). 수정: ⓐ 자동 스크롤을 '사용자가 대화를 이어갈 때만' 켜지는 게이트로 재설계 — `pendingScrollToEndRef`(복원·복귀 시 1회)+`chatAutoScrollEnabledRef`(기본 off, `appendUserMessage`·`handleSuggestionClick`에서 on), 의존성은 `[messages, isSending, backtestReq, stage]`로 확장 ⓑ **복귀 위치는 대화 끝(최대 스크롤)** — `scrollChatViewToEnd()`(main이 스크롤되면 main, 아니면 윈도우; 실측 기본형은 윈도우). 최대 스크롤에서는 대화 컨테이너 하단 여백 `pb-56`(224px)이 고정 입력창(≈135px)보다 커 마지막 버블이 항상 입력창 위에 놓인다. 요약 카드가 늦게 렌더돼 문서가 길어지는 경우를 위해 300ms 뒤 1회 재정렬. ※ 중간에 '맨 위' 해석으로 구현했다가 사용자 재확인으로 '끝'으로 정정("스크롤을 위로 최대로"=내용을 위로=대화 끝). 검증: playwright-core+로컬 Chrome로 실제 경로 재현(로그인 스텁 필수 — 익명은 `QueryProvider`가 `/`로 replace해 리마운트가 섞여 버그가 가려짐) — 같은 마운트 복귀·리마운트 복원 양쪽에서 `scrollY == maxScroll`(atEnd), 버튼이 입력창보다 113px 위(overlap false), 복귀 후 새 메시지 전송 시 자동 스크롤 정상 복귀 실측. 테스트: 신규 3(`chatScroll.test.ts` — main 스크롤러/윈도우 스크롤러/main 부재) — 프론트 1,192 전체 통과 | ✅ 완료 |

### Phase 3.15: Planner → Tool/Engine → Responder 아키텍처 전환 (2026-07-26 결정)

전략 생성을 에이전틱 구조로 점진 전환한다(전면 재작성 금지 — 사용자 합의). 로드맵:
① 자연어 해석 계약 랜딩(3.14에서 완료) → ② Tool 레이어 공식화 → ③ Responder 계약 분리+규제
가드 관문 이전 → ④ 테마/유니버스 해석 구간 한정 mini-planner(9B, 스텝 상한+고정 파이프라인
폴백+shadow 비교) → 검증 후 확대.

| 작업 | 상세 | 상태 |
|------|------|------|
| Phase 1: Tool 레이어 공식화 (2026-07-26) | `backend/strategy_conversation/tools/` 신설 — `base.py`(ToolSpec/등록/`call` 단일 진입점: pydantic 입력 형식 검증→실행→출력 계약 확인, 도메인 예외는 전파·`ToolError`는 계약 위반 전용)+`catalog.py`(7종: `kg_resolve_sector`·`kg_theme_companies`·`ground_term`(비결정론, chat 주입 필수)·`resolve_universe`·`lookup_capabilities`·`validate_intent`·`compile_strategy`(partial 플래그)). `primary.py`의 검증·컴파일 호출(초기 파스 2곳+수정 라운드트립·최종 컴파일 3곳)을 tools 경유로 재배선 — **동작 변화 0**(위임만), `run_backtest` 도구는 소비자(planner) 생길 때 추가(YAGNI). 테스트: 신규 13(`test_strategy_tools.py` — 카탈로그 등록·형식 위반 ToolError·도구별 위임·검증→컴파일 관통·부분 컴파일 dropped 보고) — 백엔드 2,604·프론트 1,184 전체 통과. 아키텍처 문서 § 4.2.2 | ✅ 완료 |
| Phase 2: Responder 계약 분리 + 출력 관문 (2026-07-26) | ① `response/output_guard.py` 신설 — 결정론 규제 관문: 종목 행동 지시·확정 수익(stock_analysis/guardrails `_FORBIDDEN` 정본 공유, 중복 정의 금지)+전략 대화 고유 위반(전략 추천·우열 판단·시장 전망·성과 기대·보장) 문장 단위 제거. **'추천' 단어 자체는 금지 아님** — 시스템이 추천을 하는 문장(추천합니다·권장합니다)만 제거, 거절 안내("'종목 추천' 조건은 지원되지 않아요")·면책 문구('보장하지 않습니다' 부정형 lookahead)는 보존. 위반 없으면 원문 무변형(개행 보존 — 관문이 정상 응답을 변형하면 회귀), 제거 시 warning 로그 ② `finalize_user_response` — clarification_question·suggestions(질문 전체 제거 시 칩도 무효화)·notices 필드 관문, `primary.py` 반환 6곳(초기 파스 1+수정 경로 5: clarify/explain·unsupported/결정적 종목/전량 환각/최종) 배선 — LLM 자유 텍스트(generate_general_answer 설명 답변 포함)가 관문 없이 나가던 경로 봉쇄 ③ Responder 계약 명문화(`response/__init__.py`) — 구조화 결과만 입력(원문 해석 금지), planner 도입 후에도 관문 우회 불가. 입력측 가드(coach `_coach_scope_guard`·상류 분류기)는 별개 표면이라 이동하지 않음(코치 코드 보존 원칙). 테스트: 신규 13(`test_output_guard.py` — 위반 4종 제거·거절 안내/면책/정상 다중행 보존·질문 제거 시 칩 무효화·메타 보존) — 백엔드 2,617·프론트 1,184 전체 통과 | ✅ 완료 |
| Phase 3: mini-planner 구현 (2026-07-26) | `strategy_conversation/planner/` 신설 — `mini_planner.py`(plan_universe_resolution: 9B가 KG 조회→검색 그라운딩→되묻기 순서를 동적 결정)+`shadow.py`(비차단 관측 실행+JSONL). 결정론 안전 계약 5중: 화이트리스트 3종만·스텝 예산(기본 4, 상한 8)·동일 호출 루프 차단·**finish 값은 도구 관찰값에서만 채택**(LLM 주장값 무시 — 근거 없는 finish 거부)·되묻기 질문 출력 관문 통과. 실패=전부 None(고정 파이프라인 폴백 — planner는 단독 실패 지점 불가). 배선: `run_primary_parse`가 미해석 업종 표현 감지 시 shadow 스레드만(기본 off, `STRATEGY_PLANNER_MODE=shadow`), ground_term은 planner chat 공유 주입. 테스트: 신규 13(`test_mini_planner.py` — 정상 4(KG 히트·테마 종목 관찰 채택·chat 주입·clarify 관문)+안전 장치 7+shadow 2) — 백엔드 2,630·프론트 1,184 전체 통과 | ✅ 완료 |
| Phase 3 후속 ①: 승격 판정 배치 하니스 (2026-07-26) | `scripts/qa_planner_promotion.py`+코퍼스 24건(`qa_planner_promotion_terms.json`) — planner vs 고정 체인(`_resolve_sector_terms_term_in`) 오프라인 A/B. 공정 비교 계약: 레인별 서브프로세스(어휘집 `_load_lexicon_cached`·KG 인프로세스 캐시 격리)+레인 전후 `data/term_lexicon.json` 스냅샷/복원(순서 오염·searched_at 원장 오염 방지)+precheck 결정적 해석 스킵(planner 소관 아님). **하니스가 잡은 프로덕션 버그**: 공유 chat 계약 위반 — `_default_ollama_chat`이 `max_tokens` kwarg 미수용 → term_grounding 호출부(`chat(..., max_tokens=40)`) 전부 TypeError → strategy_conversation 레인의 검색 그라운딩(planner ground_term 주입·term-in 체인 `_ground_sector_term`)이 broad except에 삼켜져 조용히 실패. 수정+회귀 2건(`test_default_chat_contract.py`). **1차 판정(비교 9건)**: 초판 planner 완패(resolved 0 — KG 미스 1회에 즉시 clarify+첫 턴 계약 위반 폴백 4건) → 프롬프트 규칙 보강(action enum 명시·clarify 최후수단 도구 체인 순서 강제) 후 재실행 resolved 7/clarify 2로 fixed와 동률, 폴백 0. 잔여 격차: 지연 planner p50 8.9s vs fixed 3.1s(추가 LLM 턴), 해석 형태 분화(planner=섹터 우선 vs fixed=테마 상장사 우선 — K뷰티 ODM 화학/0곳 vs None/9곳), '따뜻한 감성주'→식품/음료 오확정은 **양 레인 공통**(상류 ground_term 환각 — 별도 백로그) | ✅ 완료 |
| Phase 3 후속 ②: 격차 해소 3종 + dev shadow 가동 (2026-07-26) | ① dev `.env`에 `STRATEGY_PLANNER_MODE=shadow` 활성(다음 백엔드 재시작부터 관측 로그 누적) ② planner 해석 형태 격차 — 검색 학습 후 `kg_theme_companies` 재조회를 루프 차단에서 면제(`seen_calls` 리셋 — 고정 체인의 학습→apply_theme_companies 재시도와 같은 계약)+프롬프트 규칙 5 추가+스텝 예산 기본 4→6(전체 체인 5결정). planner가 섹터+상장사 둘 다 확보(K뷰티 ODM 화학/9곳 — fixed는 None/9곳) ③ ground_term 무의미 표현 오확정 게이트 — grounding 프롬프트에 '검색 결과가 주식·투자 테마 문맥이 아니면 sector null' 규칙('따뜻한 감성주'→식품/음료 오확정이 양 레인 clarify로 교정, 재발 검증 하니스 2건). 테스트: `test_theme_requery_after_ground_learning_not_loop` 추가 — 백엔드 2,668 전체 통과. **2차 배치 판정(비교 9)**: planner resolved 5(섹터+상장사 복합 4건은 fixed보다 풍부)/clarify 4, fixed resolved 6/clarify 3, 오답 확정 양 레인 0 — 그러나 지연 planner p50 21s vs fixed 3.2s(6~7배)로 **승격 보류 유지**. 주의: 하니스와 pytest 동시 실행 금지(어휘집 스냅샷 경합) | ✅ 완료 |
| Phase 3 후속 ②b: planner 턴 구조 개편 — 지연 격차 6~7배→2배 (2026-07-26) | LLM 턴을 판단에만 쓰도록 재구성: ① **KG 사전 관찰** — kg_resolve_sector·kg_theme_companies는 판단 없는 결정적 조회(~ms)라 LLM 턴 없이 선실행, 관찰이 해석을 주면 LLM 0턴 종료(KG-히트 케이스 3.5s→15ms) ② **검색 후 결정론 에필로그** — ground_term 관찰 후 테마 재조회·종료는 절차라 무LLM 수행 ③ **action 표기 정규화** — 9B가 도구명을 action 필드에 쓴 출력(`{"action": "ground_term"}`)을 결정론 복구(계약 § 판정 기준의 'LLM 출력 표기 정규화' — 원문 해석 아님) ④ 프롬프트 재작성: 남은 LLM 결정='검색할 가치 vs 되묻기'+되묻기 질문 작성뿐 ⑤ `scripts/qa_planner_shadow_report.py` — shadow JSONL 요약(outcome 분포·지연 백분위·baseline 불일치). **3차 배치 판정(비교 9)**: 판정 9/9 fixed와 일치(resolved 6/clarify 3), planner가 3건에서 섹터+상장사 복합 확보(로봇 감속기 로봇/29곳 vs fixed None/10곳), 오답 확정 양 레인 0, 지연 planner p50 9.8s vs fixed 4.9s(**2배로 축소**, 잔여 격차=planner가 무의미 표현도 검색 후 되묻는 안전 비용). 테스트 15건(`test_mini_planner.py` 재편) — 백엔드 2,669 전체 통과 | ✅ 완료 |
| Phase 3 후속 ③: dev primary 승격 (2026-07-26) | 배치 A/B 판정(판정 9/9 일치·오답 0·복합 해석 3건 우위·지연 2배)을 근거로 사용자 결정 승격. `STRATEGY_PLANNER_MODE=primary` 신설(config 3모드 off/shadow/primary) — `run_primary_parse`의 미해석 업종·테마 구간을 `_resolve_sector_terms_planner_primary`가 담당: planner의 결정은 '검색 가치 vs 되묻기'뿐, **적용은 고정 체인과 같은 결정론 경로 재사용**(apply_theme_companies 우선→_merge_learned_sector→상장사 직접 반영), 되묻기 칩=SECTOR_REASK_SUGGESTIONS. planner 실패(None)·예외는 **표현 단위로 고정 체인 폴백**(단독 실패 지점 불가 유지). dev `.env`=primary 전환, prod=env 미설정(off) 유지. 테스트: 신규 6(`test_planner_primary_mode.py` — 섹터 병합·상장사 반영·되묻기 칩·None/예외 폴백·config)+E2E 스모크('유리기판 관련주'→SKC·삼성전기 정본 notice) — 백엔드 2,675 전체 통과 | ✅ 완료 |
| Phase 3 후속 ④: primary 실사용 검증 → prod 결정 | dev primary 실사용에서 배치 판정 재현 확인(오해석·되묻기 품질·지연 체감) + 기존 QA 하니스(빌더 퍼징·레드팀·grounding) acceptance 게이트 → prod 반영 여부 결정(현 prod=off). shadow 리포트(`qa_planner_shadow_report.py`)는 shadow 모드 재활용 시 사용 | ⬜ 예정 |
| Phase 4 착수: DAG Planner — 대화 턴 전체 Action DAG 계획 (2026-07-27) | 계약 문서 `docs/planner_dag_contract.md` 확정 후 구현. Planner LLM의 **유일한 출력=Action DAG(JSON)** — 실행은 전부 결정론 러너: ① `planner/dag.py` — DagNode 모델+결정론 검증(비순환 Kahn·id 고유·의존 존재·화이트리스트 7종·노드 예산·ask 질문 필수·동일 도구+인자 중복 금지·**done 노드 불변**(재발행 시 type/tool/args 변경·누락=위반, 의존 재배선만 허용)·**finish→compile_strategy→validate_intent 의존 사슬 강제**(검증·컴파일 없는 확정 경로 구조 차단))+ready 스케줄링 ② `planner/dag_planner.py` — DAG 프롬프트(규제 원칙·출력 계약·유니버스별 ask topic 규칙(ETF 재무 질문 금지·단일종목 유니버스 질문 금지)·최소 질문 5조건·예시 DAG)+턴 루프: 발행→검증→ready 실행 가능 도구(kg 2종·ground_term·resolve_universe·lookup_capabilities — validate/compile은 러너 보유 intent 필요로 primary 승격 시 배선) 전이 실행→**ask 표면화는 무관찰 턴에만**(관찰이 질문을 불필요하게 만들 수 있어 LLM에 수정 1턴)+output_guard 통과, 동일 호출 관찰 재사용(루프 구조 차단), ground_term 학습 후 테마 재조회=결정론 에필로그, 확정값=도구 관찰값만, 턴 예산(`STRATEGY_DAG_PLANNER_MAX_TURNS` 기본 4)·무진전 동일 발행·모든 실패=None 폴백 ③ `planner/dag_shadow.py`+`run_primary_parse` 진입부 비차단 배선(기본 off, `STRATEGY_DAG_PLANNER_MODE=shadow`, JSONL `logs/strategy_dag_planner_shadow.jsonl`). 테스트: 신규 20(`test_dag_planner.py` — 구조 검증 9+루프 안전 장치 9+shadow 2) — 백엔드 2,696 전체 통과 | ✅ 완료 |
| Phase 4 dev primary 승격 — 되묻기 질문·칩을 DAG planner가 담당 (2026-07-27) | 사용자 결정으로 shadow 관측 생략 승격('반도체 etf' ETF 재무 칩 노출 사고가 계기 — 프론트 고정 게이트가 유니버스 무인지). `STRATEGY_DAG_PLANNER_MODE` 3모드(off/shadow/primary) — primary는 `run_primary_parse`의 되묻기 조립 지점에서 `_dag_planner_clarification`이 질문·칩을 대체(**sector_unresolved 우선순위 질문은 불가침**, planner 실패·예외·ask 아님=기존 고정 질문 유지 폴백)+`clarification_priority="dag_planner"` 마커로 프론트 explicit 게이트(유니버스 무인지 고정 칩) 삼킴 방지 — **프론트 수정 0**(기존 우선순위 채널 재사용). `_dag_state_summary`가 파이프라인 확정값(유니버스·etf_theme·신호 타입 등)을 planner에 전달해 재질문 방지. **9B 실측 교정 3종**: ① done 노드 재발행 생략=위반→러너 보유 사본 병합(표기 정규화 — 생략이 매턴 발생해 전량 폴백되던 문제) ② 긴 DAG JSON 닫는 괄호 누락→결정론 괄호 균형 보정(`_balance_braces`) ③ 공유 chat max_tokens=4096 명시(2048 절단). E2E: '반도체 etf 투자 전략'→질문 "모멘텀 기간은?"+기간 칩(재무 칩 0), priority=dag_planner. 테스트 26건+conftest 밀폐 픽스처(main.py load_dotenv가 .env primary를 프로세스에 누출→순서 의존 실패 교정) — 백엔드 2,702 전체 통과. dev `.env`=primary, prod=off | ✅ 완료 |
| (동시 수정) 인터프리터 etf_theme 드리프트 — '반도체 etf' 테마 소실 (2026-07-27) | 9B가 "반도체 etf 투자 전략"에서 etf_theme을 채우지 않고 missing_fields로 분류+"정확한 상품명을 알려달라" 되묻기(규칙 6-1 위반, 이미 말한 값 되묻기). 규칙 문장 보강만으론 불복 → **few-shot 예시 4-1 추가**("반도체 etf 투자 전략"→etf_theme="반도체", 상품명 불필요·etf_theme 질문 금지)로 교정, PROMPT_VERSION 1.6→1.7. E2E 재현으로 수정 확인(etf_theme="반도체" 확보) | ✅ 완료 |
| Phase 4 프롬프트 재설계: 진행 골격 8슬롯 + 유니버스별 디테일 (2026-07-27) | 승격 직후 '반도체 etf'에 "모멘텀 기간은?" 질문 사고 — 사용자가 말한 적 없는 전략 유형을 전제(원인: 예시 DAG의 모멘텀 프라이밍+ETF 허용 topic 목록을 체크리스트로 해석해 6개 ask 전부 생성). 사용자 확정 설계로 재작성: **모든 전략은 전략 진행률 8슬롯(유니버스→매수→매도→최대 보유→리밸런싱→리스크 관리→백테스트 기간→초기 자본, 프론트 `builderProgressPresentation.ts`와 동일 골격)을 따르되 유니버스별 디테일만 분화** — 단일종목=유니버스·최대 보유·리밸런싱 슬롯 스킵, ETF=재무 질문·칩 금지(기술 지표 칩), 코스피/코스닥=재무+기술 모두. 특정 전략 파라미터(모멘텀 기간 등)는 사용자가 언급한 경우만, 언급 없는 조건 공백은 열린 질문+유니버스별 칩(자기완결 문장 — 무상태 재전송 정본 표기). 예시도 열린 매수 질문 케이스로 교체. E2E 3유니버스 검증: ETF→기술 칩(재무 0)/코스피 저평가→재무 칩/삼성전자→최대 보유·리밸런싱 무질문. 계약 정본 `docs/planner_dag_contract.md` 동기화 | ✅ 완료 |
| (동시 수정) startup 모델 preload에 9B 인터프리터 슬롯 누락 (2026-07-27) | 로컬 dev startup preload(`_kick_local_ollama_model_preload`)가 레거시 파서 슬롯(NL_OLLAMA_MODEL 4B)만 적재 — 07-26 슬롯 분리 때 `STRATEGY_INTERPRETER_MODEL`(9B)이 빠져 재시작 후 첫 전략 파싱이 9B 로드 지연(수십 초)을 떠안음. `_local_preload_models`가 **인터프리터 슬롯(9B)만** 적재(4B는 사용 중지라 미적재 — 사용자 결정, 잔존 레거시 경로는 lazy 로드로 동작. 슬롯 미설정 시 인터프리터가 실제 폴백하는 파서 모델 적재)+인터프리터 chat에 로컬 한정 `keep_alive:-1`(Ollama는 마지막 요청 keep_alive로 언로드 타이머 갱신 — preload -1만으론 첫 요청 후 5분 idle 언로드). 원격(Modal)은 불변. 테스트 2건(`test_startup_model_preload.py`) — 백엔드 2,704 전체 통과 | ✅ 완료 |
| (동시 수정) 수정 라운드트립 etf_theme 소실 — '삼성전자 투자 etf' 해석 불가 사고 (2026-07-27) | etf_theme 드리프트 수정으로 테마가 실제로 채워지자 기존 공백이 노출: `strategy_decompiler`의 UniverseSpec이 etf_theme을 왕복시키지 않아 ETF 테마 전략의 **모든 수정**이 라운드트립 불일치('반도체'→None, 표현 불가 판정)로 레거시 레인 폴백 — 인터프리터가 입력을 읽기도 전에 탈락, 레거시는 "삼성전자 투자 etf" 해석 불가로 일반 되묻기(KG·검색 미도달은 테마 체인이 초기 파스 레인 소관이라 부수 증상). decompiler에 `etf_theme=parsed.etf_theme` 왕복 추가. E2E: 같은 입력이 인터프리터 레인 도달→ETF 테마 교체(반도체→삼성전자)로 해석. 회귀 `test_etf_theme_strategy_roundtrips_losslessly` — 백엔드 2,705 전체 통과 | ✅ 완료 |
| Phase 4 수정 턴 재계획 — "입력=답변 귀속이 아니라 State 변경 판정이 먼저" (2026-07-27) | 사용자 계약 확정: 후속 입력("삼성전자 관련 etf를 매수하자")은 직전 질문(매수 조건)의 답이 아니라 **State의 어느 슬롯을 바꾸는지 먼저 판정**해야 한다(이 판정자=modify 인터프리터의 patches). 배선: `run_primary_modification` 성공 경로에서 수정 적용 후 골격 공백이 남으면(결정론 게이트 detect_incomplete_backtest_conditions) **갱신된 State로 DAG planner가 다음 질문을 재계획**+priority 마커. 함께 잡은 인터프리터 드리프트 2겹: ① "삼성전자 관련 etf"를 KOSPI200 지수로 재해석 패치+**같은 필드에 자기 질문 병행** → 조용히 적용되어 ETF 유니버스 소실 — **자기 의심 패치 게이트**(`_self_doubt_patch_fields`: 패치 경로와 질문 필드 겹치면 적용 대신 그 질문 표면화, 전략 무변경) ② 프롬프트 예시 5-1(ETF 테마 교체 — markets 패치·지수 재해석 금지, 확신 없으면 질문만). E2E: 턴1 ETF·반도체+매수 질문 → 턴2 테마 교체(반도체→삼성전자, universe ETF 유지)+갱신 State로 매수 질문 재계획(ETF 기술 칩). 테스트 +2(`test_modify_turn_replans...`·`test_self_doubt_patch...`) — 백엔드 2,707 전체 통과 | ✅ 완료 |
| (동시 수정) 수정 턴 원문 테마 스캔이 인터프리터 출력을 덮어씀 — ETF에 삼성그룹 주식 10곳 혼입 (2026-07-27) | "삼성전자 관련 etf 매수" 수정 턴: 인터프리터는 올바르게 etf_theme 교체(ETF 유지)했으나, `_run_nl_parse`의 `scan_prompt_for_sector=(not primary_holder) or bool(previous_parsed)`가 **수정 턴은 primary 처리 후에도 원문 스캔을 켜둠** → `apply_theme_universe`('관련' 큐 원문 스캔)가 삼성그룹 상장사 10곳을 target_symbols로 적용, ETF 단독 유니버스에 주식 혼입. 수정 2겹: ① 배선 — primary가 처리한 턴(초기·수정 모두)은 원문 스캔 OFF(`scan_prompt_for_sector=not primary_holder`, 원문 스캔은 인터프리터 미처리 레거시 레인에만 잔존) ② 방어 — `apply_theme_universe`에 ETF 단독 유니버스 가드(universe==["ETF"]면 테마 '상장사' 적용 금지 — ETF 테마는 etf_theme 상품명 매칭 소관, 레거시 레인도 보호). API 경로 E2E로 수정 확인. 회귀 2건(`test_theme_scan_never_applies_stocks_to_etf_universe`·`test_modify_primary_result_not_overridden_by_raw_theme_scan`) — 백엔드 2,709 전체 통과 | ✅ 완료 |
| (동시 수정) 완결 패치가 needs_value에 폐기 — '최근 3개월 수익률 상위 매수' 답변 소실 (2026-07-27) | 랭킹 패치(return/90일)가 **수락되고도** 완결성 검증의 리밸런싱 질문에 `primary_modify_needs_value`(전략 무변경+질문)로 묶여 통째로 폐기 → 프론트 게이트가 매수 조건을 재질문(needs_value 질문은 priority 없어 게이트가 삼킴). 재정의: 질문 필드가 **패치 필드와 겹치면**(수정 자체의 값 누락 — 기간 없는 데드크로스) 기존대로 전략 유지+칩 되묻기, **안 겹치면**(다른 슬롯 완결성) 부분 컴파일로 수정 반영 후 공통 재계획 경로(DAG planner+priority)로 — 판정=`_self_doubt_patch_fields` 재사용(결정론). 추가: planner가 랭킹=매수 조건 충족을 못 읽어 매수 재질문 → `_dag_state_summary`에 **결정론 filled_slots**(8슬롯 충족 판정, 게이트와 동일 계약) 주입+프롬프트 'filled_slots가 정본' 규칙. E2E: 랭킹 보존+다음 슬롯(매도 조건) 질문 진행. 회귀 2건(`test_complete_patch_survives...`·`test_dag_state_summary_ranking...`) — 백엔드 2,711 전체 통과 | ✅ 완료 |
| Phase 4 계약 개정: State 중심 Action DAG 계약 명문화 (2026-07-27) | 외부 원 설계(State-Driven Action DAG 프롬프트)를 이 아키텍처에 맞게 이관해 `docs/planner_dag_contract.md` 전면 개정 — 레인 분리 표(Interpreter/병합기/Validator/Planner/러너/Responder)·Intent 사용 제한(IntentType=보조 메타데이터, 변경은 strategy/patches만)·State 중심 처리 원칙(§4 답변 강제 귀속 금지)·State 구조(StrategySpec 정본 참조)·State Patch 생성·병합·무효화(§6 — 기존 Interpreter patches+patch_applier+validator 구조의 계약 승격, 동작 변화 없음)·원 설계 Action 11종→노드 3종+화이트리스트 7종 매핑 표·이탈 답변 처리 표·모호성 처리 명문화. `_system_prompt()` 동기화: DAG 규칙 7(이탈 답변 — 최신 입력은 직전 질문의 답이 아닐 수 있음, 채워진 슬롯 ask 삭제+영향받는 pending만 수정)·규칙 8(tool로 해결 가능한 정보는 묻지 않기)·모호성 처리 절(해석 tool 우선, 확정 불가+결과 분기 클 때만 ask+chips 범위 질문) 추가. 백엔드 2,711+프론트 1,188 전체 통과 | ✅ 완료 |
| Phase 4 후속 ①: 칩 답변 결정론 귀속 — pending_ask 에코+LLM 생략 (2026-07-27) | planner ask 응답에 `pending_ask`({topic, question, chips}) 채널 신설 — 프론트가 다음 파스 요청에 그대로 에코(previous_coach_text와 같은 무상태 컨텍스트 에코 계약). 입력이 그 칩과 **정확히 일치**(형식 비교)하면 열거형 옵션 선택으로 판정, `primary.run_chip_answer`가 수정 인터프리터 LLM 없이 결정적 추출(`_apply_prompt_overrides` — 칩=planner LLM 출력 자기완결 정본 표기라 원문 해석 아님)로 State 반영 후 `_replan_next_question`(수정 턴 재계획과 공용 헬퍼로 추출)으로 다음 질문+다음 pending_ask 재계획. 효과: ① 칩 클릭 오귀속 구조적 제거(어느 ask의 답인지 에코가 확정) ② 칩 턴 LLM 왕복 생략(지연·비용 절감). 안전망: 미일치 자유 서술·결정적 추출 실패 칩=기존 인터프리터 경로 그대로(§4 답변 강제 귀속 금지 유지), finalize_user_response가 pending_ask를 가드 통과 질문·칩과 동기화(불일치 금지), 캐시 키에 pending_ask 포함. 배선: DagPlanResult.topic, `_dag_planner_clarification` 3-튜플, main.py 수정 턴 칩 레인(가드·인터프리터보다 선행)+NLParse 요청/응답 모델, 프록시 화이트리스트(route.ts — priority 마커 누락 사고와 같은 함정 명시)+page.tsx pendingAskRef 에코. 테스트: 신규 `test_chip_answer.py` 11건+프록시 보존 1건+수정 턴 pending_ask 회귀 — 백엔드 2,722·프론트 1,189·npm run build 전체 통과 | ✅ 완료 |
| 백테스트 입력 예시에 ETF·테마 카테고리 추가 (2026-07-27) | 정식 유니버스로 승격된 ETF(FR-STR-067)·업종/테마(FR-STR-066)를 예시에서 고를 수 없던 공백 보완. `ExampleCategory`에 `ETF`·`테마` 추가(배지 cyan/rose), 예시 16개 신설 — ETF 8개(전체 ETF 골든크로스·반도체·배당·미국S&P500·2차전지·KODEX 200 단일 상품·원자력·나스닥100)는 **기업 재무지표를 쓰지 않는 가격·거래대금 조건만**(universe_capabilities: ETF는 PER·PBR·ROE 불가), 테마 8개(반도체·2차전지·로봇·방산·원자력·바이오·조선·반도체 퀄리티+모멘텀)는 업종 유니버스 — 정치 테마는 제외. 테마·상품명은 실제 정본에 매칭되는 것만 사용(`extract_etf_theme`/`filter_etf_by_theme`로 8개 전부 매칭 확인: KODEX 200=단일 상품 1개, 반도체 57개 등 / `normalize_sector`로 업종 7종 전부 정본 매핑 확인). `/analytics/templates` 카테고리 탭 7개로 확장(모바일 2열·sm 4열·lg 7열). 예시 목록 자체를 지키는 데이터 가드 테스트 신설(`StrategyExampleTabs.examples.test.ts` — 제목 중복 금지(카드 key)·배지 스타일 정의·ETF 예시 재무 지표 금지) 4건+템플릿 페이지 탭 필터 1건 — 프론트 1,197·백엔드 2,722 전체 통과. **후속(같은 날): 예시 노출 순서 무작위화** — 첫 화면 20개가 항상 같은 예시로 고정돼 새 카테고리가 묻히던 문제까지 해소. `shuffleExamples`(Fisher-Yates)를 전략연구소 탭·템플릿 페이지 양쪽에서 **마운트 이후(useEffect)에만** 호출(서버 렌더와 순서가 어긋나면 하이드레이션 파손), 원본 배열 불변. 순서 의존 기존 테스트는 `Math.random`→1 수렴 고정(j===i라 정의 순서 유지)으로 보존하고, 섞임 자체는 신규 `StrategyExampleTabs.shuffle.test.tsx` 3건+템플릿 페이지 1건으로 검증 — 프론트 1,201 전체 통과·`npm run build` 통과. **후속(같은 날): 해외 지수 ETF 예시 교체** — 나스닥100·미국S&P500 예시가 nl_parser `overseas` 미지원 패턴(`나스닥|s&p|…`)에 걸려 "해외 시장/종목 미지원" 안내로 빠짐(나스닥100은 프롬프트의 '정배열'이 `ema_alignment` 미지원까지 이중 저촉 — 상품명 매칭만 확인하고 미지원 개념 스캔은 확인하지 않았던 공백). 나스닥100→방산 ETF(EMA 쌍+60일선 표현으로 정배열 회피, 14개 매칭)·미국S&P500→헬스케어 ETF(12개 매칭)로 교체, 교체 프롬프트는 `_mentioned_unsupported_concepts`=빈 리스트 확인. 가드 테스트에 해외 키워드 금지(`OVERSEAS_TERMS`) 1건 추가. 잔여 알려진 저촉(별건): EMA 예시 2건 프롬프트의 '정배열'(`ema_alignment`)·배당 ETF 예시의 '배당'(`dividend`) — 프론트 1,202·백엔드 2,731 전체 통과 | ✅ 완료 |
| 테마 유니버스 카탈로그 우선 재정비 — 'LCD 부품 관련주' 무관 종목 사고 (2026-07-27) | 스크린샷 사고: "LCD 부품 관련주 투자 전략"의 유니버스가 심텍·대덕전자·SK하이닉스·심텍홀딩스·대덕(전부 LCD 부품과 무관) — KG 카탈로그에는 'LCD 부품/소재' 테마(삼성SDI·LG화학 등 44곳)가 있는데도 미사용. 원인 2중: ① 카탈로그 테마명 'LCD 부품/소재'는 슬래시 병기라 부분 문자열 스캔에 절대 안 걸리고 synonyms도 빈 배열 — 사실상 도달 불가 죽은 노드 → 과거 질의가 미인식으로 검색 그라운딩 학습(`lcd부품`: verified 엣지=uses→pcb·related_company→SK하이닉스뿐) ② 학습 노드가 스캔 taken 선점 후 Concept Universe 확장이 pcb 개념 홉(시드 심텍·대덕전자)+지분 홉(심텍홀딩스·대덕)으로 유니버스를 왜곡. 수정 3겹: ① **슬래시 별칭**(`_slash_aliases`) — 로더가 "X A/B"→"X A"·"X B" 결정적 표기 변형을 동의어로 생성(괄호 안 슬래시 제외, 섹터 어휘·테스트 정본 용어 가드 유지) ② **학습 앵커 카탈로그 정합 우선** — `catalog_theme_nodes`(정확 키 인덱스, 부분·접두 매칭 금지)로 표기가 정확히 일치하는 카탈로그 테마가 있으면 뉴스 동시언급 학습 엣지 대신 카탈로그 수록 종목이 유니버스(theme_listed_companies), 백테스트 확장 뷰도 Concept Universe 확장 생략(theme_backtest_companies)+카탈로그 정합은 시점 편향 경고 제외 ③ **네이버 금융 카탈로그**(사용자 지정 1순위 신뢰 소스) — `scripts/ingest_naver_themes.py` 신설(업종별 79+테마별 169=248개·엣지 5,398, 주달과 동일 기계적 가드 4종+스코프 키워드 가드)→`data/kg-naver-theme-catalog.json`, 로더가 주달보다 먼저 합성(같은 표기 겹치면 네이버 승). TEST_RESERVED_TERMS는 engine/knowledge_graph로 이동(ingest 2종과 공유). 테스트: 신규 9(`test_knowledge_graph.py` 별칭 변형·별칭 도달·사고 회귀(학습 앵커 카탈로그 우선·pcb 홉 오편입 부재)·네이버 실파일 합성 + `test_ingest_naver_themes.py` 파서·가드 5) — 백엔드 2,730·프론트 1,201 전체 통과. **후속(같은 날, 사고 2차 — 유니버스 통째 소실)**: 위 수정 후 같은 질의가 유니버스를 아예 못 잡음(스크린샷: 일반 시장 질문으로 강등). 원인=게이트·검증기 판정 불일치 — 검증기(capability_validator)는 normalize_sector만 알아 'LCD 부품'을 sectors에서 제거하는데, primary 체인 게이트는 resolve_sectors(KG 층 포함)를 써 검색 학습 노드의 belongs_to(디스플레이/부품)로 '해석 성공' 판정 → 체인(테마 상장사 적용) 미도달+게이트 해석값은 `_`로 폐기 → 유니버스 소실(첫 질의 때는 어휘집 학습 전이라 게이트를 통과해 증상이 안 보였고, 학습 후 두 번째 질의부터 발현). 수정: `_sector_terms_for_chain` — 게이트 기준을 검증기와 동일하게 normalize_sector만으로 통일(KG 섹터 해석·테마 적용은 체인 소관, 테마 상장사가 섹터 근사보다 우선). 동시 발견: 슬래시 별칭이 '카메라모듈/부품'→'부품' 일반어 조각을 스캔 어휘로 만들어 '부품' 포함 질의 전부에 오매칭 — `_ALIAS_STOPWORDS`(부품·소재·장비·제품·기기·재료 단독 별칭 차단, 수식어 붙은 '반도체 부품'은 통과). 재현 스모크: 게이트→체인→카탈로그 10곳(삼성SDI·LG화학…, `_THEME_COMPANY_CHIP_MAX` 기존 상한) 적용 확인. 회귀 2건(`test_gate_uses_validator_criterion_not_kg_resolution`·별칭 스톱워드) — 백엔드 2,731·프론트 1,201 전체 통과. **후속(같은 날): KG 조회 로그 콘솔 미출력 수정** — KG 조회·그라운딩·Concept Universe 로그는 `logger.info`로 찍히고 있었으나 앱에 `logging.basicConfig`가 없어 최후수단 핸들러(WARNING 이상)에서 전부 버려짐([LLM-INTERPRETER]는 print라 보였음). `engine/console_logging.console_logger` 헬퍼 신설 — 전용 StreamHandler+INFO+propagate=False(스크립트 basicConfig 중복 출력 방지), knowledge_graph=[KG]·term_grounding=[KG-GROUND]·concept_universe=[KG-UNIVERSE] 태그 배선. 로깅 미설정 재현으로 출력 확인 — 백엔드 2,731·프론트 1,201 전체 통과 | ✅ 완료 |
| ETF·테마 예시 파싱 실패 5겹 근본 수정 — 예시는 **파싱까지** 검증한다 (2026-07-27) | 사용자 지적으로 발견: '반도체 업종 종목 중 ROE 10% 이상, 부채비율 120% 이하 조건을 먼저 적용하고, 그중 …거래대금 50억…8종목' 예시가 조건을 하나도 못 잡고 빈 전략(KOSPI200 기본값 10종목)+"해석하지 못했어요"로 끝났다. **예시를 추가할 때 어휘·상품명 매칭만 확인하고 실제 파싱을 돌리지 않은 것이 1차 원인**(하니스가 이미 있었다). 원인 5겹 전부 수정: ① **수치 재요청이 정상 해석을 폐기** — recall 대조(§3-1)가 '50억' 누락을 잡아 재요청하자 9B가 수정 턴처럼 patches만(strategy=null) 돌려주고, 인터프리터가 그 출력으로 1차 정상 해석을 통째 교체 → 초기 파스엔 적용할 초안이 없어 interpretation_failed. 수정: 재요청 출력이 비면(초기=strategy null, 수정=strategy·patches 모두 없음) **폐기하고 재요청 직전 해석 유지**+재요청 프롬프트가 턴별 출력 형식 명시(초기=strategy 전체·CREATE, 수정=patches) ② **잔존 누락 침묵** — 로그만 남던 미반영 수치를 `InterpreterResult.unreflected_numbers`로 실어 보내고, primary가 컴파일·결정적 보정까지 끝난 전략으로 한 번 더 걸러(`labels_absent_from`, **description 제외** — 원문 에코가 자기 자신과 매칭돼 안내가 영구 침묵하던 함정) 비차단 notices ③ **되묻기를 반영으로 인정** — recall이 `clarification_questions`를 반영으로 세던 탓에 "거래대금 조건을 추가해 드릴까요?"로 미룬 조건이 READY 상태에서 질문 폐기와 함께 사라졌다(입력에 있는 값을 되묻는 것은 처리가 아니다 → 대조 대상에서 제외, 계약 §3-1 명문화) ④ **레지스트리가 정본 표기를 오류로 판정** — `ma_crossover.short_period` 최소 2가 '종가 대비 N일선'(short=1, 엔진 `close_1_sma`=종가, 레거시 파서 동일 표기)을 거부해 모든 'N일선 이탈' 전략이 오류+부분 컴파일로 흘렀고 그 오류는 사용자에게 전달되지도 않았다 → minimum 1+정본 표기 주석 ⑤ **출력 형태 누락이 ETF 테마를 삼킴** — `_OUTPUT_SHAPE.universe`에 `etf_theme` 키가 없어 9B가 형태를 그대로 베끼며 테마를 빠뜨렸다(규칙 6-1·few-shot으로도 못 이김): "반도체 ETF만 대상으로"가 전체 ETF 1,384종목 전략이 되던 것을 한 줄로 교정(7개 ETF 예시 중 6개가 테마 소실 상태였다). **프롬프트 1.8→1.9**: 규칙 6-0(universe엔 시장·업종·종목만 — 스크리닝 기준은 entry_conditions, 자동 적용 없음), 규칙 5-3(두 선의 상하 관계=crossover 표기·value null·기간 parameters — >,< 로 쓰면 "기준값을 얼마로?" 되묻기로 조건 소실: MA/EMA 상태 조건을 잃던 예시 4건의 원인), few-shot 4-3(스크리닝 다단계 '먼저 적용하고 그중'). **QA 하니스 게이트화**(`scripts/qa_template_detect.py`): `--category`·`--refresh`, 치명 항목(해석 실패·ETF 유니버스 오류·ETF 재무 조건·ETF 테마 소실(ETF 마스터 추출기 기대값 대조)·업종 미반영·진입 규칙 공백) 발생 시 종료 코드 1, 이동평균/EMA 커버리지 검사 추가(없어서 조건 소실 4건이 통과했다), 요약에 ETF테마·업종 표시. 예시 2건은 엔진이 표현할 수 없는 문구를 명시 임계로 교정('거래대금이 너무 적은 종목 제외'·'당일 거래대금이 20일 평균보다 많은' → '일평균 거래대금 N억 원 이상'). 하니스를 게이트로 돌리자 같은 예시 묶음에서 **추가 결함 4건**이 더 드러나 함께 고쳤다: ⑥ MA/EMA 상태 조건 소실 4건(위 규칙 5-3) ⑦ ETF 유동성 조건 소실 — 모델이 `fundamental.trading_value`를 'ETF 금지 재무 지표'로 오해하고 `universe.filter`라는 없는 슬롯에 적용했다고 서술 → 규칙 6-1에 '거래대금은 이름이 fundamental.*여도 ETF 사용 가능, 조건은 entry_conditions에' 명시(하니스의 ETF 재무 조건 치명 검사도 trading_value 제외로 교정) ⑧ ETF 전략에 주식 종목명 오타 되묻기 오발동 — '배당 ETF 중에서…'가 '오아'·'일승' 종목 확인 질문으로 빠졌다(자모 근접 매칭이 원문 전체를 훑는 레거시 검사). `universe==["ETF"]`면 종목 오타 되묻기 스킵(ETF는 주식 마스터에 없어 전부 오발동) ⑨ 반영된 etf_theme과 모순되는 미지원 안내 — '배당'을 etf_theme와 unsupported_features 양쪽에 넣는 드리프트로 "'배당 조건'은 지원되지 않아요"가 함께 나갔다 → 섹터 프루닝과 동형으로 etf_theme 이름과 겹치는 미지원 항목 제거. 덤으로 규칙 5(보유 기간)에 '지표 청산과 보유 기간은 별개 슬롯' 명시("20일선 이탈 시 청산 + 최소 보유 6개월"에서 청산이 사라지던 드리프트). E2E: ETF·테마 16개 전수 재검증 **치명 0·미탐지 0**(#16 예시는 업종·ROE·부채비율·거래대금·랭킹·8종목·월간·손절 전부 반영, ETF 7개 예시 테마도 전부 반영). 하니스 치명 검사에 '명시 청산 규칙 소실'·'ETF 테마 소실' 추가. 테스트 +11(recall 4·인터프리터 2·검증 2·primary 2·심볼 리졸버 1)+스텁 3곳 보강 — 백엔드 2,753·프론트 1,205 통과 | ✅ 완료 |
| Planner prod 승격 — 전 플래그 primary (2026-07-28) | 사용자 결정으로 프로덕션 planner 전환 완료: Vultr `/opt/simons/.env`에 `STRATEGY_PLANNER_MODE=primary`(Phase 3 mini-planner) 추가 — `STRATEGY_INTERPRETER_MODE=primary`·`STRATEGY_DAG_PLANNER_MODE=primary`는 기존 반영 상태였음. 백업 `.env.bak-planner-on-20260728`, 롤백=추가 줄 삭제 후 `docker compose up -d`. 예시 파싱 5겹 수정 커밋(5472073c)과 함께 CI 배포(컨테이너 재생성)로 반영 — 컨테이너 env 3플래그 확인·백엔드 `/docs` 200·Modal 워밍업 완료·사이트 200 검증. 실패 시 안전망은 코드 내장(planner 실패=고정 체인/고정 질문 폴백 — 단독 실패 지점 불가) | ✅ 완료 |
| Phase 5: 제어 역전 — planner 최선두 실행 + Universe-first (2026-07-28) | 발단 '보안주 관려 투자 전략' 사고: 인터프리터가 sectors를 비우고 질문 텍스트에만 '보안주'를 남김 → 검증기가 sectors 질문을 결정론 missing_fields 불일치로 폐기 → term-in 체인 입력(`pre_validation_sectors`)이 비어 유니버스 해석 전체 침묵+매수 조건 질문만 노출. 사용자 확정 원칙(Intent≠흐름 결정·planner 최선두·Universe-first·CONCEPT≠SECTOR·질문 순서=Action Dependency)을 기존 Phase 4 DAG planner의 승격으로 구현(전면 재작성 금지 유지): ① **제어 역전** — `run_primary_parse` 최선두에서 `_plan_first`(plan_strategy_dag) 실행(dag_planner_mode=primary), planner가 유니버스 표현 추출·분류·해석을 소유. 실패=None이면 현행 고정 파이프라인 그대로(규제 게이트는 planner 앞 상류 유지, validate→compile 결정론 게이트 불변 — 단독 실패 지점 불가) ② **유니버스 분류 Action** — `classify_universe` 도구(결정론: MARKET/ETF/SINGLE_STOCK/SECTOR/CONCEPT, 입력=planner LLM이 뽑은 표현) ③ **CONCEPT 범위 후보** — KG `catalog_theme_candidates`(포함 일치, 상장사 0곳 제외, 정확 일치 우선)+`list_concept_candidates` 도구, 프롬프트 Universe-first 절(CONCEPT는 후보 조회 먼저 — 후보 2개 이상=ask(topic 유니버스, chips=후보 표기 그대로), 유니버스 ask가 조건 ask보다 선행 의존) ④ **관찰값 결정론 적용** — `_apply_planner_first_universe`(적용은 고정 체인 경로 재사용: apply_theme_companies·_merge_learned_sector, planner 소유 표현은 term-in 체인 제외로 이중 검색·되묻기 방지), ask 채택은 결정론 게이트가 최종 권한(`_planner_first_ask` — 유니버스 ask=미해결 표현 있을 때만, 조건 ask=detect_incomplete 게이트 인정 시만) ⑤ **9B 드리프트 결정론 교정 3종**(실측): 범위 후보 2개+유니버스 ask면 kg 테마 조용한 자동 적용 차단('보안' 10곳 적용+범위 질문 동시 노출 모순)·topic 변주('유니버스 범위') 포함 판정·LLM 지어낸 칩을 관찰된 카탈로그 후보 표기로 교체 ⑥ **유니버스 칩 결정론 귀속** — `run_chip_answer` topic 유니버스 분기(`_apply_universe_chip`: 정본 섹터 병합 또는 카탈로그 정확 일치 테마 적용, LLM 생략) 후 `_replan_next_question` 공용 재계획. E2E 실측: '보안주 관려 투자 전략'→범위 질문+칩 [보안주(물리), 보안주(정보)](planner 3턴 20.7s)→칩 클릭 결정적 반영 10곳(LLM 0)→다음 질문 "어떤 조건에서 매수할까요?"(의존성 순서). 테스트: 신규 22(`test_planner_first.py` — 분류 6·후보 2·관찰 적용 5·ask 판정 4·통합 3·칩 2)+도구 등록 갱신 — 백엔드 2,775 전체 통과. prod=이미 3플래그 primary라 다음 배포에 실적용 | ✅ 완료 |
| Phase 5 후속: 유니버스 칩이 의도 분류에서 OFF_TOPIC 거절 (2026-07-28) | 실사용 첫 왕복 사고: 범위 칩 "보안주(정보)" 클릭 → `handleSend`가 의도 분류(`/api/query/classify`)를 거치는데 카탈로그 테마명은 금융 단서가 없어 OFF_TOPIC → scope.py 거절 문구 노출, 파스 레인(백엔드 결정론 칩 귀속)에 도달 못 함. 기존 칩("손절 8%" 등)은 금융 어휘 덕에 우연히 통과했던 것 — pending_ask 칩은 시스템 생성 열거형 선택지의 '답'이라 분류 대상이 아니다. 수정: `page.tsx handleSend`에 결정론 우회 — `pendingAskRef` 칩과 정확 일치+전략 존재+빌더 모드 아님이면 분류 없이 `runStrategyParseFlow` 직행(pending_ask 에코 포함, 미일치·자유 서술은 기존 분류 흐름 그대로). 회귀: `page.pending-ask-chip.test.tsx` 신규 1(수정 없이는 실패 확인 — 칩 텍스트가 classify로 새지 않음+pending_ask 에코 검증) — 프론트 1,206 전체+`npm run build` 통과 | ✅ 완료 |
| Phase 5 후속 ②: planner 드리프트 시 미해결 표현 증발 — 범위 되묻기 결정론 소유화 (2026-07-28) | '미용기기 관련주' 사고: planner가 classify(CONCEPT)+후보 조회(1건)까지 하고 kg 해석·검색 없이 매수조건 ask로 드리프트 → **체인 제외 버그**(planner가 건드린 미해결 표현을 유니버스 ask 표면화 여부와 무관하게 term-in 체인에서 제외)로 KG에 상장사 19곳이 있는 표현이 어느 레인에도 못 가고 증발, 미지원 안내만 잔존. 재설계 — 9B 복종에 의존하던 두 판단을 결정론으로 이관: ① **범위 모호성 되묻기=결정론 소유**(`_planner_scope_ask`) — 후보 2개 이상(관찰값)이면 planner ask topic과 무관하게 범위 질문 확정(문구는 planner 유니버스 ask 재사용, 없으면 고정 템플릿, 칩=항상 카탈로그 후보 표기), 자동 적용 차단도 ask 여부와 무관하게 상시화 ② **체인 제외=planner가 실제 종결한 표현만**(해석 완료분+범위 질문 표면화분) — 못 푼 나머지는 반드시 term-in 체인으로(KG 테마→검색 그라운딩→되묻기 복구) ③ `_planner_first_ask`는 조건 슬롯 ask 전용으로 축소(유니버스 topic=scope 소유). E2E 실측: '미용기기'→체인이 미용 의료기기 10곳 반영+미지원 안내 소거+조건 질문 유지, '보안주'→범위 질문+카탈로그 칩 불변. 테스트: test_planner_first.py 26건(드리프트 회귀 2·scope 3 신규) — 백엔드 2,779 전체 통과 | ✅ 완료 |
| Phase 5 후속 ③: 카탈로그 이중 수록 → 가짜 범위 모호성 (2026-07-28) | '퓨리오사ai 관련주' 사고: 같은 테마가 네이버('퓨리오사AI' 11곳)·주달('퓨리오사ai' 7곳) 양쪽에 수록 → `catalog_theme_candidates`가 노드 2개를 후보 2개로 반환 → 범위 모호성 판정(후보≥2)이 발동해 **동일 라벨 2개 중 하나를 고르라는 무의미한 범위 되묻기** 노출. 수정: 후보 열거에서 표기 정규화(_norm_key) 동일 노드를 병합 — 대표 표기=네이버 우선(카탈로그 우선순위 계약), 상장사 수=병합 합집합. E2E: '퓨리오사ai 관련주 투자 전략'→범위 질문 없이 체인이 '퓨리오사AI' 관련 상장사 10곳 자동 반영+매수조건 질문 진행, '보안주' 2후보 불변. 회귀: `test_concept_candidates_merge_same_theme_across_catalogs` — 백엔드 2,780 전체 통과 | ✅ 완료 |
| 테마 유니버스 종수 상한 절단 폐지 — '비만치료 관련주' 10종목 사고 (2026-07-28) | 스크린샷 사고: "비만치료에 관련주" 전략의 유니버스가 KG 검증 상장사 36곳(전부 학습 verified 동률 0.60) 중 심볼 번호 앞 10곳(유한양행·삼천당제약…)만 됨. 원인 3겹 절단: ① `nl_parser.apply_theme_companies`의 안내문용 상한(`_THEME_COMPANY_CHIP_MAX=10`)이 target_symbols까지 절단 ② 빌더 레인 `_theme_patch`도 동일 상한 ③ `concept_universe._select`의 MAX_SIZE(30)·MIN_SIZE 완화 중단 경계가 동점 그룹 한가운데를 심볼순으로 가름(같은 근거 점수인데 번호 빠른 종목만 잔존 — 근거 기반 선정 위반). 수정: 유니버스는 조회 전체 사용(파싱·빌더 레인 상한 제거 — 안내문 나열만 10곳+«외 N곳» 축약, `theme_label`은 synthesize_prompt 재파싱용 전체 이름 유지), `_select` 크기 경계 동점 완결(동점 전체 포함, 경계 밖 저점수는 기존대로 제외). E2E 실측: 동일 질의 36곳 전체 반영. 회귀 3(`test_select_size_bounds_do_not_split_ties`·`test_all_theme_companies_applied_without_truncation`·`test_theme_patch_uses_all_companies_without_truncation`) — 백엔드 2,783 전체 통과. SRS FR-STR-071 ④·FR-STR-072 ② 갱신 | ✅ 완료 |
| 다종목 지정 리밸런싱 되묻기 — 기본값 침묵 확정 폐지 (2026-07-28) | 스크린샷 사고: '모바일솔루션 관련주' 테마 전략(지정 23종목)의 리밸런싱이 질문 없이 기본값 '설정 안 함'으로 요약 카드에 확정 표시. 원인: 최소 조건 게이트의 단독 종목 면제가 '지정 종목 존재 여부'로 판정돼(백엔드 `_missing_backtest_conditions` is_single_asset·프론트 `getNextMissingBacktestCondition` isSingleAsset) 테마 유니버스 다종목까지 리밸런싱 질문이 생략 — 코드 주석의 의도("단독 종목은 교체가 없어 제외")는 1종목에만 유효. 수정 3곳: ① 면제=지정 종목 정확히 1개(백·프론트 동일 규칙), 다종목은 리밸런싱 되묻기+칩에 '리밸런싱 안 함' 추가(사용자 결정) ② 명시 거부 재질문 방지 — `detect_incomplete_backtest_conditions`에 user_prompt 관통(`_mentions_rebalancing_negation` 인지, primary.py planner 게이트 2곳도 배선), 누적 프롬프트 재파싱 무한 반복 차단 ③ 요약 카드(`builderProgressPresentation`) 다종목은 답 전 기본값 확정 표시 금지(1종목·명시 답변만 표시). 회귀: 백엔드 2(다종목 되묻기+거부 비반복, 기존 칩 계약 갱신)+프론트 5(readiness 2·표시 게이트 3) — 백엔드 2,784·프론트 1,210 전체 통과·tsc 클린. SRS FR-STR-068 ④ 개정. **후속(같은 날): '최대 보유' 카드-실행 정합** — 같은 카드의 "최대 보유 10종목"도 기본값 표시였는데, 지정 종목 모드 실행은 변환기가 max_positions=지정 종목 수 균등(FR-STR-068 ①, ranking off)으로 덮어써 카드와 실행값이 불일치. `builderProgressPresentation`이 지정 종목 모드에서 '최대 보유 N종목' 대신 파싱 카드와 동일한 FR-STR-068 ⑧ 표기("단일 종목 집중 투자"/"지정 종목 N개 균등 투자", 진행 패널 라벨 '포트폴리오'=완료)를 쓰도록 통일(유니버스 전략 표기 불변). 회귀 3 추가 — 프론트 1,213 전체 통과·tsc 클린. SRS FR-STR-068 ⑧ 확장 | ✅ 완료 |
| classify_universe 섹터 근사 vs 정본명 구분 — '태양광' 과대 유니버스 사고 (2026-07-28) | 사용자 제보: "태양광 관련 투자 전략" 요청이 업종 칩 '에너지/원자력'(원자력·풍력·석유·가스 전부 포함)로 확정 — `_classify_universe`가 `normalize_sector`를 카탈로그 테마 판정보다 먼저 검사해, NL_SAFE_TERMS 근사('태양광'→'에너지/원자력', MAPPING_RULES 키워드 버킷에서 파생)와 정본명 자체("반도체"→"반도체") 매치를 구분 없이 즉시 SECTOR 확정. 2026-07-27 'AI/인공지능' 사고와 동일 근본원인이나 그때는 `_SECTOR_SYNONYM_OVERRIDES`에서 그 용어만 손으로 빼는 개별 대응이었음 — 사용자 요청("케이스 바이 케이스 대응 금지, 일반화된 설계")에 따라 구조적으로 재설계. 수정: `universe_pit.is_narrow_sector_approximation()` 신설 — 표현이 정본 섹터명 문자열 안에 그대로 들어있으면("은행"→"은행/금융지주", 이름 표기 차이) False, 정본명 밖의 이질적 키워드 버킷에서 온 근사면("태양광"→"에너지/원자력", 원자력·풍력·석유가 한 섹터로 뭉뚱그려짐) True. `_classify_universe`는 True인 경우에만 `catalog_theme_candidates`로 더 구체적인 카탈로그 테마 존재 여부를 먼저 확인, 있으면 CONCEPT(되묻기 체인)로 넘기고 없으면 기존대로 SECTOR 확정 — 새 근사 용어가 추가돼도 자동으로 이 경로를 타 개별 화이트리스트 유지가 불필요. 회귀 검증: 기존 65개 섹터 동의어(NL_SAFE_TERMS+`_SECTOR_SYNONYM_OVERRIDES`) 전수 스윕 — 은행·보험·통신·원자력·조선·철강 등 정본명 포함 동의어는 SECTOR 유지, 태양광·풍력·수소·위성·항공기 등 버킷형 근사만 CONCEPT로 전환(2차전지·배터리·제강·인터넷 등 일부는 표기 변이로 인해 보수적으로 CONCEPT로 전환 — 실패 모드는 조용한 과대 확정이 아니라 되묻기 1회 추가뿐이라 안전). 테스트: `test_planner_first.py`에 회귀 3건 추가(태양광→CONCEPT, 은행/원자력→SECTOR 불변) — 백엔드 전체(2,784+) 통과 | ✅ 완료 |
| 값-대기 조건 요약 표시 + planner 팩터 구 오라우팅 백스톱 — '당기순이익' 사고 (2026-08-03) | 실사용 사고: "당기순이익과, 영업이익률이 높은 종목에 투자하는 전략" — 인터프리터는 두 조건을 정확히 해석(net_income_growth·operating_margin, 값 MISSING)하고 되묻기까지 발행했으나 화면은 "첫 조건부터 하나씩"(빈 요약)+유니버스 질문만 노출돼 '이해 못함'으로 읽힘. 원인 2겹: ① 값 미정 조건은 컴파일에서 드롭(무단 확정 금지)돼 `parsed`에 없는데 요약(`buildBuilderTurnPresentation`)은 parsed만 봄 ② 프론트 explicit 게이트의 유니버스 질문이 백엔드 값 되묻기보다 우선(설계 유지 — pending_ask로 보존돼 뒤 턴에 복귀). 수정: `compile_partial`이 값-대기 조건 구조화 목록 반환 → 응답 `pending_conditions` [{role,label,source_text}] 신설(NLParseResponse·apply_primary_meta 이월) → 프론트 요약이 매수/매도 조건 행에 "순이익증가율(값 미정)" 표기, 원문 표현과 다른 지표로 매핑됐으면 "'당기순이익과' → 순이익증가율(값 미정)"로 치환 고지(비교 입력은 둘 다 LLM 구조화 출력). 부수 결함: planner가 팩터 구 전체를 유니버스 표현으로 `classify_universe`에 넘겨 CONCEPT 판정 → KG 조회·ground_term 검색 학습까지 돌다 턴 예산 소진(실측 10.7초, 어휘집 오염은 없음 확인). 2겹 수정: 프롬프트 Universe-first 절에 "지표 조건 구는 유니버스 표현 아님" 명시+`classify_universe`에 결정론 백스톱(`contains_factor_term` — 한글 4자 이상 레지스트리 별칭 포함 시 NOT_UNIVERSE 종결, 입력은 planner LLM이 뽑은 표현이라 계약 적합. 러너는 CONCEPT 외 타입을 종결로 취급해 호환). 테스트: 백엔드 5(compile_partial 구조화·primary 페이로드·NOT_UNIVERSE 2·기존 유니버스 불변)+프론트 5(빈 요약 해소·확정+대기 병기·치환 고지·매도 행·무페이로드 불변) — 백엔드 3,418·프론트 1,375 전체 통과. AgentsTab planner 흐름도 갱신. **2차 수정(같은 날, 실서비스 재발 2건)**: ① 백엔드는 pending_conditions를 실었는데 **SSE 프록시 화이트리스트**(`route.ts` parsed_final)에서 떨어져 요약이 여전히 빈 전략으로 보임(priority 마커·pending_ask 누락과 동일 함정, 세 번째 실사고) — 화이트리스트 추가+프록시 보존 테스트 ② NOT_UNIVERSE로 planner가 예산 안에 성공하자 parsed만 보면 매수 슬롯이 공백(값-대기 조건은 드롭)이라 열린 질문("어떤 조건에서 매수할까요?")이 채택돼 검증 리포트의 **기준값 질문**을 덮음 — `_planner_first_ask`에 값-대기 슬롯 ask 거부 가드(`pending_value_conditions`) 추가, 폴백 기준값 질문에 `clarification_priority="pending_values"` 마커(사용자 결정 "숫자를 물어봐야지" — 기준값 질문이 프론트 유니버스 explicit 게이트보다 선행). 회귀 3(planner ask 거부·primary 마커·프록시 보존)+AgentsTab 가드 문구 — 백엔드 3,426·프론트 1,378 전체 통과. **3차: 한 턴에 한 질문(2026-08-03 사용자 결정 — 기준값 2개+청산을 한 버블에 묶어 묻던 것 폐지)**: `_build_clarification`을 질문 단위 항목(`_clarification_items` — {question, chips, topic, metric})으로 분해(병합 출력은 기존 규칙 보존 — 수정 레인 무변화). 초기 파스 폴백에서 질문이 여러 개면 **첫 질문만** 발행하고 나머지는 `pending_ask.queue`로 이월(무상태 에코 — 첫 질문 결속 실패 시 큐 유실 방지 위해 종전 병합 방식 폴백). 답이 반영되면 칩 레인(run_chip_answer)·수정 레인(run_primary_modification)이 재계획 대신 `_next_ask_from_queue`로 큐의 다음 질문을 발행 — 칩 결속은 표면화 시점 parsed로 재계산, **이미 반영된 항목은 스킵**(조건 임계값=metric이 재무 필터에 존재, 슬롯=_is_filled_slot_topic — 자유 서술로 앞서 답한 경우 재질문 방지), 우선순위 pending_values로 프론트 게이트 선점 방지. unexplained_drops 대조에 큐 질문 포함(이월 질문의 조건에 '미반영' 안내 오발 방지). 회귀 3(초기 분할+큐 구조·칩 답변 후 다음 질문 발행·기충족 스킵)+AgentsTab 해석기 되묻기 노드 갱신 — 백엔드 3,428·프론트 1,378 전체 통과 | ✅ 완료 |
| 당기순이익 절대 금액 팩터 + 재무 팩터 상위 N 랭킹 (2026-08-03) | 사용자 요청 2건. **① fundamental.net_income(억원)**: fetcher가 성장률 재계산 컴포넌트로만 쓰고 버리던 `_net_income`(순이익률×매출액)을 `net_income`으로 저장 승격(`ANNUAL_FUNDAMENTAL_KEYS` 추가 → FUND_COLS 경유 파케이 인리치 자동) — signals `FUNDAMENTAL_LABELS`/`FUNDAMENTAL_AMOUNT_CIDS`(억원 배지)+`FundamentalFilter` Literal+metric 별칭+레지스트리(`당기순이익` 별칭, recommended 100억)+`fundamental-factors.json`+`condition_builder` 패턴(`당기\s*순이익` — 순이익률/증가율과 구분)+프론트 `METRIC_LABELS`·`formatEokAmount` 배선. 주의: 기존 재무 JSON 캐시(90일 TTL)에는 값이 없어 재수집부터 채워진다(prod는 `enrich_all_fundamentals.py` 재실행으로 즉시). **② 재무 팩터 랭킹**('영업이익률 상위 20종목', 'PER 낮은 상위 10종목'): `ParsedStrategy.ranking_metric`을 Literal["return"]→`RankingMetricLiteral`(return+재무 cid, trading_value 제외 — 파케이 컬럼 아님)로 확장+`ranking_direction`(top/bottom, top=미저장으로 기존 strategy_id 불변) 신설. 엔진: `_process_symbol`이 랭킹 지표 컬럼 수집(`all_fund_rank_values`, pbr/roe 블렌드와 같은 경로) → 새 분기에서 as-of ffill+next_open 1일 shift(look-ahead 방지)+pct rank(NaN=자연 배제)+선정=진입 풀(대형주·유동성 마스크 재결합, momentum C4 계약)+매수 사유("영업이익률 상위 X%")+데이터 전무 시 경고(조용한 0거래 방지). 검증기: 랭킹 지표 허용을 ranking.*+fundamental.*로 확장, ETF×재무 랭킹=오류+제거(조건 검사와 동일 계약). 컴파일러/디컴파일러 라운드트립+수정 이력 라벨(`랭킹 방향`)+인터프리터 프롬프트(지원 지표 절+예시 4-a)+프론트 `getRankingLabel`("영업이익률 상위"/"PER 낮은 순 상위"). **함정 수정**: `_apply_prompt_overrides`의 레드팀 13-1 가드("재무 정성 표현의 '상위'는 랭킹이 아님")가 '재무 랭킹 미지원' 전제로 랭킹을 전부 비우던 것을 `ranking_metric=='return'` 오귀속 전용으로 좁힘 — 안 좁히면 신기능이 결정적 보정에서 소거된다. 슬롯 판정 픽스처(`slot-judgments.json`) 재수출. 테스트: 백엔드 신규 10(compile top/bottom·엔진 risk 전달·디컴파일 라운드트립·ETF 차단·모멘텀 불변·13-1 가드 생존·fetcher net_income·NOT_UNIVERSE 유지 등)+프론트 신규 3(랭킹 라벨 top/bottom·당기순이익 억원 배지) — 백엔드 3,425·프론트 1,377 전체 통과 | ✅ 완료 |
| Phase 4 후속: 다중 턴 State 반영 → 대화 전체 확대 | ① 결정적 추출이 못 푸는 칩(자기완결 미준수 맨값 칩)의 topic 힌트 인터프리터 주입 ② validate/compile 노드 실제 실행 배선(Phase 5 판단: 러너 이중 실행은 레인 결정론 경로와 분기 위험 — 레인이 실행하고 DAG는 구조 계약 유지) ③ dev 실사용+QA 하니스(빌더 퍼징·레드팀) 게이트 | ⬜ 예정 |
| KG 시각화 테마 레벨 기본 화면 — 카탈로그 확장 후 헤어볼 대응 (2026-07-27) | 사용자 제보: 테마 카탈로그 편입 후 그래프가 노드 3,050·엣지 9,410(상장사 2,386=78%) 규모가 되어 렌더가 감당 못 하고 아무것도 안 보임. `KnowledgeGraphView` 수정 — ① **기본=테마 레벨**: 종목(company) 노드는 기본 비활성(SimNode.active), 개념·섹터·학습·ETF ~660노드만 시뮬레이션·렌더 ② **선택 시 펼침**: 노드 클릭·검색 선택 시 그 이웃 종목만 활성화, 처음 펼쳐지는 종목은 연결 노드 곁에서 등장(placed 플래그 — 스파이럴 원점 낙하 방지), 선택 해제 시 다시 접힘 ③ **전체 표시 토글**: 범례 '상장사' 칩이 토글 겸용('선택 시 표시'↔'전체 표시', resetKey 재배치에도 ref로 유지) ④ **반발력 O(n²)→공간 그리드 근사**(셀 80px — 인접 9칸 정확 계산+원거리 칸 무게중심×개수, 컷오프 400px 유지) — 전체 표시 3천 노드에서도 프레임 유지 ⑤ 라벨 줌 비례 차수 임계값(k<0.55→차수 40 이상만 등, 학습 용어는 항상)+노드 크기 sqrt 차수 스케일(카탈로그 테마가 선형 상한에 몰리는 문제). 테스트: 토글 신규 1(`KnowledgeGraphTab.test.tsx`) — 프론트 1,203 전체 통과·tsc 선재 에러 외 클린. SRS FR-STR-070c ② 갱신 | ✅ 완료 |
| 관련 기업 엣지 뉴스→네이버 분류 전환 + 자동 등록 (2026-07-27) | 사용자 지시: 학습 용어의 관련주 목록을 뉴스 검색(동시언급)이 아니라 네이버 증권 검색으로 만들고 자동 등록 — 발단 '다이어트' 학습 목록에 삼성SDI·신한지주·KB금융 등 무관 종목 21개 pending(뉴스 기사 스침 노이즈). FR-STR-071 ① 개정 — ① `_propose_company_edges`(뉴스 동시언급) 폐기, `_naver_company_edges` 신설: 검색 레인의 네이버 분류 목록(④a 표기 정합과 1회 수집 공유, `_naver_groups_for_learning` 심 — search_fn 주입 시 None 실네트워크 가드)에서 LLM이 이름 닫힌 목록 선택(최대 3, 목록 밖·스코프 제외 드롭) → 수록 종목 결정적 수집(`naver_theme_live.fetch_group_stocks` 추출 리팩터링, `lookup_and_ingest`에 groups 파라미터) → **자동 verified**(콘솔 사후 반려 가능), 대응 없음·수집 실패=기업 엣지 없음(뉴스 폴백 없음) ② 과확장 가드 2겹(dry-run 실측 교정): 개별 상장사명 결정적 차단('삼성전자'→'반도체 대표주' 12종목 방지)+단일 과제 LLM 산업 판별 `_naver_term_is_industry`('이재명'→반도체·로봇 280종목, '리센느'(걸그룹)→조선, 'BTS'→엔터 31종목 차단 — 매핑 프롬프트에 규칙을 섞으면 소형 모델이 무시하는 실측, 판별 분리로 4건 전부 스킵 확인) ③ 기존 10항목 마이그레이션 `scripts/rebuild_learned_company_edges.py`(멱등, --dry-run/--only): pending 뉴스 엣지 제거+verified/rejected 보존(콘솔 결정·rejected 부활 금지)+네이버 편입 — '다이어트' 21개(20 pending)→86 전부 verified(비만치료제+건강기능식품+건강관리기술), 'LCD 부품' 66, '유리기판' 17, 인물·그룹 4건 편입 0. 테마 유니버스 왕복 확인(theme_listed_companies 86곳). 테스트: 신규 3(네이버 분류 자동 verified·상장사명 차단·산업 판별 게이트)+검색 레인 순서·분류 목록 공유 개정 — 백엔드 2,740·프론트 1,203 전체 통과. SRS FR-STR-071 ① 개정 | ✅ 완료 |
| 학습 검토 탭 접기/검색 정비 (2026-07-27) | 관련 기업 엣지 자동 등록 후 '다이어트' 86엣지 등으로 목록이 길어져 사용자 요청(탭 삭제 검토 → 반려·pending 승인·용어 삭제가 이 탭에만 있어 유지 결정, 대신 UI 정비). `KnowledgeTab` — ① 용어 박스 기본 접힘: 헤더(▸/▾ 토글 버튼)에 용어·업종 칩·학습 시각·엣지 수·검토 대기 배지(amber, pending>0만), 정의·수동 엣지 추가·엣지 목록은 펼침 시만 ② 검색 입력: 용어명·정의·엣지 대상 종목명(normKey 부분일치 — 종목→테마 역조회) 필터+검색 중 일치 항목 자동 펼침+'일치하는 용어가 없습니다' ③ 안내 문구를 새 계약(네이버 분류 자동 검증 등록·사후 반려)으로 갱신. 테스트: 신규 2(기본 접힘·배지·토글 왕복 / 검색 필터·자동 펼침·무일치 안내)+픽스처 확장 — 프론트 1,205 전체 통과·tsc 클린. SRS FR-STR-070b ⑤ 갱신 | ✅ 완료 |
| 운영 콘솔 Agents 탭 — AI 파이프라인 설계 구조 시각화 (2026-07-29) | 사용자 요청: 플랫폼의 모든 agent 설계 구조를 운영 콘솔에서 agent별 서브탭으로 시각적으로 확인, 용어는 내부 변수명이 아닌 운영자 친화 명칭. `components/admin/AgentsTab.tsx` 신설(정적 스냅샷 데이터 — 파이프라인 변경 시 함께 갱신) — 9개 agent(전략 해석기·대화 플래너·질문 분류기·전략 빌더·전략 수정기·전략 검증 도우미·AI 리포트·테마 학습기·종목 질문 도우미)를 서브탭으로 전환, 각 agent는 세로 흐름도(노드+화살표+분기)로 렌더. 노드 유형 7종 색상 범례(입력/AI 판단/자동 규칙/지식·데이터/안전장치/사용자 확인/결과물)로 "의미 해석=LLM, 검증·컴파일=결정론" 역할 분담이 한눈에 보이게 구성, agent별 운영 메모(폴백 금지·보존 코드 등 함정)와 구현 위치 병기. `AdminConsole.tsx` Agents 탭 배선(Knowledge와 Audit Logs 사이). API 불필요(정적 데이터). 테스트: `AgentsTab.test.tsx` 신규 3(서브탭 목록·기본 선택 렌더/탭 전환/분기 라벨) — 프론트 1,216 전체 통과·`npm run build` 클린 | ✅ 완료 |
| 채워진 슬롯 재질문 결정론 가드 — '매수 조건' 두 번 묻기 사고 (2026-07-29) | 스크린샷 사고: 매수 조건(부채비율·ROE)을 칩으로 답해 요약 카드·진행률(4/8)에 모두 반영됐는데 planner가 "어떤 조건에서 매수할까요?"를 **다시** 물음. 원인: '채워진 슬롯은 다시 묻지 않는다'가 **프롬프트 지시로만** 존재하고(dag_planner 시스템 프롬프트 규칙+`_dag_state_summary`의 결정론 `filled_slots` 주입), 출력측에는 대응 검증이 없어 9B가 지시를 어기고 예시 DAG를 패턴매칭해 **풀 8슬롯 골격(ask_entry부터)을 재발행**하면 러너가 첫 ready ask를 그대로 표면화. 수정: ask 표면화 지점(`dag_planner.plan_strategy_dag`)에 결정론 가드 — ask 노드의 `topic`을 `filled_slots`와 공백 무시 비교해 일치하면 건너뛰고(충족 처리) 다음 빈 슬롯 ask를 표면화, 전부 채워졌으면 기존 무진전 폴백(None→레인의 기존 질문 유지). 판정은 표기 정규화뿐(의미 판단 없음 — 계약 § 판정 기준). 계약 정본 `docs/planner_dag_contract.md`·운영 콘솔 Agents 탭 흐름도 동기화. 테스트: 신규 2(`test_filled_slot_ask_skipped_surfaces_next_empty_slot`·`test_all_asks_filled_falls_back_without_reask`) | ✅ 완료 |
| 되묻기 provenance 채널 전환 — 프론트 원문 정규식 폐지 (2026-07-29) | 스크린샷 사고 2건이 같은 원인이었다: 프론트 게이트가 사용자 원문을 정규식으로 재분석해 '말했나'를 스스로 판정(`hasExplicit*` 5종). **미탐** — '최대 보유 종목은 10개'를 못 잡아 진행률 미체크·요약 누락; **오탐** — '거래대금 20억 원'을 초기 자본 명시로 오인해 되묻기를 삼킴(2026-07-28). 사용자 지적('그건 자연어 해석에 관여한다는 뜻 아니야?')에 따라 어휘를 넓히는 대신 채널 자체를 교체했다(계약 § 판정 기준). ① **provenance는 LLM 구조화 출력에서만** — `strategy_conversation/response/provenance.py`가 `StrategySpec`의 필드 유무로 `explicit_fields`(universe/max_positions/rebalancing/backtest_period/initial_capital)를 판정 ② **기본값 물질화 제거** — `UniverseSpec.markets` 기본값 `["KOSPI200"]`을 컴파일러로 이전(LLM이 기본값을 지어내면 출력에서 provenance가 지워진다), 프롬프트 v2.1 ③ **무상태 에코 누적** — `previous_explicit_fields`(pending_ask와 동형 계약), SSE 화이트리스트 프록시에 배선 ④ **프론트 정규식 0** — `hasExplicit*` 5종+`AMOUNT_FILTER_PHRASE` 삭제, `isExplicit(field, explicitFields, parsed)`로 대체(지정 종목은 그 자체가 유니버스 명시) ⑤ **칩·빌더·복원·돌아가기 4경로 배선** — 칩 답변은 백엔드 왕복이 없어 로컬 기록(없으면 같은 질문 무한 반복), 빌더 슬롯은 그 자체가 답변 기록(`BUILDER_SLOT_EXPLICIT_FIELDS`), 세션 스냅샷에 저장·복원, '돌아가기'는 되돌린 필드의 provenance도 함께 되돌린다(안 하면 되돌아온 질문을 답한 것으로 보고 건너뜀). ⑥ 파스 응답 핸들러에서 **게이트 계산이 provenance 갱신보다 먼저** 실행되던 순서 버그 수정(항상 이전 턴 값을 봄). 실서버 확인: 명시 프롬프트→`['universe','max_positions']`, 미명시→`[]`(값은 KOSPI200·10으로 채워져 있어도). 부수 효과: 빌더 단독 진입(파스 없음)은 기간·초기 자본 provenance 출처가 없어 이제 묻는다 — 종전엔 원문 정규식이 질문을 막고 엔진 기본값으로 조용히 확정했다. 테스트: 프론트 목 픽스처를 '프롬프트가 실제로 말한 것'으로 재작성, 신규/개정 다수 — 백엔드 2,797·프론트 1,221 전체 통과 | ✅ 완료 |
| 전략 파스 지연 근본 수정 — planner 재계획 제거 + prefill 워밍업 (2026-07-29) | **사용자 제보**: "Strategy parse stream proxy error: The operation was aborted due to timeout". 프록시 타임아웃은 120초인데 캐시 미스 파스가 70~146초를 오가며 그 경계에 걸쳤다. **계측** — 파스 1회를 몽키패치로 분해하니 테마·KG 조회는 전부 합쳐 74ms(0.0%)였고 **100%가 LLM**이었다. 다시 호출별로 쪼개니 planner 1턴이 233자 출력에 24.7초(2.4 tok/s) — 생성이 아니라 **prefill이 병목**. 인터프리터 system 프롬프트가 20,470자(~8,900 tok)였고, 콜드 43.6초 vs 캐시 적중 **0.4초**(109배). 추가로 warm 파스 계측에서 planner가 한 파스에 **6회** 호출되는 것을 발견 — `_plan_first`가 턴 예산 4를 소진해 None을 반환하면 elif 체인의 다음 분기가 planner를 **처음부터 다시** 돌리고 있었다(148초 + 84초). **수정** — ① 재계획 분기 제거(예산 소진은 실패가 아니라 고정 질문 폴백 — `_dag_planner_clarification` 자체는 칩 답변 턴 재계획이 계속 사용) ② 턴 예산 4→2(사용자 결정, 롤백 `STRATEGY_DAG_PLANNER_MAX_TURNS=4`) ③ startup에 고정 system 프롬프트 prefill 워밍업 추가(`_kick_system_prompt_prefill` — 모델 가중치 적재와 별개 비용, 실측 63.4초→0.7초/0.5초). LLM 호출 7→3회(첫 파스)·4→3회(warm). 벽시계 검증은 머신 부하 load 90 상태라 보류 — 부하 안정 후 재측정 필요. 백엔드 전체 통과. SRS FR-STR-019o | ✅ 완료 |
| 칩=값 결속 계약 — 우리가 낸 선택지를 우리가 못 알아듣던 자기모순 수정 (2026-07-29) | **사용자 제보**: 카지노 관련주 전략 대화에서 우리가 제시한 칩 '거래량 급감(전일 대비 1/2 이하) 시 매도'를 클릭했더니 "요청을 전략 조건으로 해석하지 못했어요". 원인 2층 — ① planner LLM이 칩 문구를 자유롭게 지어내는데 capability 검사가 없어, registry에 `_unsupported`인 `volume_multiple`과 아예 존재하지도 않는 거래량 **하락**을 선택지로 노출 ② 칩 값이 결속돼 있지 않아 클릭할 때마다 문구를 **다시 해석**(결정적 추출 → 실패 시 수정 LLM)했다. 사용자 지적대로 칩은 우리 agent가 만든 열거형 옵션이므로 값은 보여주는 순간 이미 알아야 한다. **수정** — ① `primary._bind_chips`: 조건 슬롯 칩을 발행 시점 State에 적용해 `{필드: 값}`으로 결속하고 `pending_ask.chip_bindings`로 에코, 결속 실패 칩은 `clarification_suggestions`에서도 제거(전량 탈락이면 질문만 남기고 자유 서술) ② `run_chip_answer`: 결속값을 그대로 적용 — 칩 문구 재추출·LLM 호출 0 ③ `description`만 달라진 것을 '반영'으로 세지 않도록 수정(무변경을 "칩 답변 확정"으로 오보고하던 구멍 — 실측 확인) ④ `output_guard`가 규제 가드 통과 후 살아남은 칩의 결속만 남겨 키 어긋남 방지 ⑤ 유니버스 범위 칩은 카탈로그 표기라 결속이 이미 보장돼 제외(테마 상장사 조회 N회 반복 회피). 프론트는 `pending_ask` blob을 열지 않고 그대로 에코(타입만 확장). 회귀 4종 신규 — 백엔드 2,858·프론트 1,284 전체 통과. AgentsTab '선택지 값 결속 검사' 노드 추가. SRS FR-STR-019n | ✅ 완료 |
| 빈 슬롯 판정 단일 정본 통합 (2026-07-29) | **사용자 지적**("빈 슬롯 체크는 한 곳에서 하는 게 아니야?") — 실제로 네 곳이었고 서로 답이 달랐다. 빈 전략 하나를 넣으면 planner State는 '4/8 완료'(기본값 물질화), 백엔드 게이트는 최대보유·기간·자본을 검사조차 안 함, 프론트는 '0개 완료'. 이 갈라짐이 2026-07-28·07-29 사고 3건의 공통 원인이었다. ① **정본 신설** `backend/engine/strategy_slots.py` — 판정 단위(필드 9)와 진행 골격(슬롯 8)을 분리해 어휘 불일치를 제거(리스크 관리=손절·익절 **둘 다**), 되묻기 문구·칩도 같은 모듈에 배치 ② **소비자 이관** — `_missing_backtest_conditions`(범위 인자)·`_dag_state_summary.filled_slots`(provenance 인자)가 정본에서 파생, 차이는 판정이 아니라 인자로만 표현 ③ **가려져 있던 결함 수정** — planner State가 기본값 물질화를 '채워짐'으로 봐 유니버스·최대보유·기간·자본을 영영 묻지 않던 것(빈 전략 4/8→0/8) ④ **이관 중 테스트가 잡은 것** — '리밸런싱 안 함'을 provenance 쪽에 두면 require_explicit=False 레인이 무시해 무한 반복 → '이미 결정된 필드'로 분리 ⑤ **프론트 고정** — 칩 답변은 백엔드 왕복이 없어 로컬 판정을 없앨 수 없으므로, 정본이 생성한 계약 픽스처(`scripts/export_slot_judgments.py`, 24케이스)로 parity를 강제(프론트 parity 테스트 + 백엔드 픽스처 최신성 테스트). 허수 아님을 뮤테이션으로 확인(프론트 술어 1개 훼손 → 해당 케이스만 실패) ⑥ 빌더(`required_missing`)는 상태 모델이 달라 제외(슬롯 라벨만 공유). 테스트: SOT 계약 14 + parity 25 신규 — 백엔드 2,817·프론트 1,246 전체 통과. SRS FR-STR-019m | ✅ 완료 |
| planner-first ask 채택의 슬롯 대조 (2026-07-29) | 스크린샷 사고: 매수 조건이 '20일 고점 돌파'로 반영돼 요약 카드에 있는데 "박스권 돌파 시 매수할까요?"가 뜸. 원인: 채택 관문(`_planner_first_ask`)이 `detect_incomplete_backtest_conditions`에 **"어딘가 비었나"만** 물어, 리밸런싱·기간이 비었다는 이유로 매수 조건 ask가 통과. planner-first는 파스보다 먼저 계획하므로 자기 `filled_slots`를 볼 수 없어 planner 내부 가드(07-29 ①)로는 막히지 않는다. 수정: 파스 결과가 존재하는 채택 시점에 topic↔슬롯 라벨을 대조해 채워진 슬롯 ask를 거부(`_is_filled_slot_topic`). 실서버 재현·검증(같은 프롬프트 → 재질문 소멸, 첫 빈 슬롯인 리밸런싱 질문). 회귀 1건 | ✅ 완료 |
| 종목명 오타 되묻기 term-in 이관 (2026-07-29) | 위 수정으로 재질문이 걷히자 그 뒤에 가려져 있던 결함이 드러남: `detect_symbol_typo_clarification`이 원문의 3자 이상 한글 토큰을 전부 종목 마스터에 자모 근접 매칭해 '넘기는'→**삼기**, '안으로'→**알트**로 오탐하고, 칩으로 사용자 문장을 통째로 오염시켜 되돌려줬다. 섹터/테마는 § 11-3에서 term-in으로 옮겼는데 종목명만 남아 있었다. 수정: ① `terms=` 인자 신설 — LLM이 `universe.symbols`로 뽑았는데 리졸버가 못 푼 표현만 후보 ② primary 레인은 term-in 경로(`_symbol_typo_term_in`)가 소유, 원문 스캔은 레거시 레인 전용 ③ 원문에 토큰이 없으면 치환 없는 원문 대신 종목명만 칩으로(같은 질문 반복 방지). 실측: 오탐 소멸 + 진짜 오타는 그대로 검출('삼서전자'→'삼성전자'). 회귀 3건. 계약서 § 11-7 | ✅ 완료 |
| (동시 수정) '최소 보유 기간'이 '최대 N일 보유 후 매도'로 뒤집힘 (2026-07-29) | 같은 스크린샷: '최소 보유 기간은 3개월'이 매도 조건 '최대 63일 보유 후 매도'로 표기 — **하한↔상한 반전**(그 전엔 팔지 않기 ↔ 만료 시 강제 청산). `hold_period_days`는 상한만 표현하므로 하한을 뒤집어 확정하는 것은 조용한 오해석. 수정 4겹: ① `_MIN_HOLD_PERIOD_PATTERN` 공유 상수 신설(보유 동사·'보유 기간' 명사 동반 형태만 — '최근 3개월 이상 상승' 모멘텀 룩백 오탐 방지) ② `_extract_hold_period_days`가 하한 구간을 지운 뒤 추출(같은 문장의 상한 표현은 보존) ③ 추출만 막으면 침묵 누락이므로 미지원 개념 `min_hold_period`로 등재 — 규칙 파스는 LLM 위임(None)하고 `build_unsupported_concept_notice`가 안내(FR-STR-023d 확장) ④ 인터프리터 프롬프트에 같은 계약 명시(하한=`unsupported_features`), PROMPT_VERSION 1.9→2.0. 예시 카드 '부채비율·ROE 보유 조건' 문구도 '최대 보유 기간'으로 정정(엔진이 표현 가능한 형태). 아울러 잦은 신호 경고가 사용자에게 "최소 보유기간 설정을 고려해 주세요"라고 **미지원 레버를 권하던** 자기모순 문구 2곳(`stock_question_templates.py`·`single_asset_review.py`)을 '조건을 좁히는 것'으로 교정. 테스트: 신규 2+기존 3 갱신 — 백엔드 전체 통과 | ✅ 완료 |
| 신규 상장(IPO) 유니버스 (2026-07-29) | 사용자 요청 — "'2026년 신규 상장 종목 투자 전략'을 처리할 수 있게". 종전에는 개념이 없어 빈 전략으로 나가 유니버스부터 되물었다. ① **상장일 확보** — 상폐 종목은 FDR KRX-DELISTING이 상장일을 함께 주지만 현행 상장 종목은 목록에 상장일 컬럼이 없어 전부 null이었다. FDR `KRX-DESC`(KIND 상장법인목록, 무료·무키)에서 백필(`backfill_listing_dates.py` 멱등 + `build_stock_master.py`가 재빌드 시 직접 채움) — 현행 보통주 2,642종목 확보, 미커버 126은 우선주 113 + KIND 미등재 구종목 13. KRX Open API `LIST_DD`는 서비스 미승인(401)이라 미채택 ② **최초 상장일 = min(상장일, 로컬 데이터 시작일)** — KIND 상장일은 '현재 시장 상장일'이라 이전상장·재상장(지에프씨생명과학: 상장일 2025-06-30인데 2022-12-23부터 거래)이 신규 상장으로 둔갑한다 ③ **코호트 의미론** — 사용자 2차 지적("여전히 코스피·코스닥 전체로 잡힌다")으로 롤링('상장 후 N일 이내') 마스크를 폐기하고 **상장일이 구간에 속하는 종목 집합**으로 재구현. 상장일 하나로 결정되니 정적 심볼 필터면 충분하고(섹터 필터와 같은 자리), 코호트 소속은 만료되지 않는다 ④ **백테스트 창 클램프** — 같은 지적("백테스트 기간이 2022년부터 잡혔다"): 2026년 상장 종목이 존재하지도 않던 구간을 테스트할 수 없으므로 `enforce_strategy_minimums`가 창 시작을 상장 하한으로 끌어올리고 안내한다. 연도는 상장 시기이지 검증 기간이 아님을 프롬프트에 명시하고, 프론트 기간 배지도 명시 날짜가 있으면 실제 창을 보여준다 ⑤ **개념/구간 분리** — "신규 상장 종목"엔 시기가 없어 `new_listing_only`(개념)와 `listing_from`/`listing_to`(구간)를 나눴다. 개념만 있으면 대상 시기를 되묻고(칩: 올해/작년 상장·최근 1년/3년 내 상장) 구간 확정 전까진 엔진에 아무것도 넘기지 않는다 ⑥ **빌더 레인 관통** — 빌더는 `BuilderState`로 슬롯을 모아 DSL을 직접 조립하는 별도 레인이라 `apply_parsed_seed`가 이어받지 않으면 제한이 증발한다. 유니버스 다음에 `listing_period` 스텝 신설(전용 파서 — 공통 파서로 흘리면 '3개월'이 모멘텀 룩백으로 오귀속), custom 유형은 합성 문장으로 재파싱 복원, 지정 종목·테마·ETF는 배제 ⑦ **확정된 창 재질문 금지 + 프론트 슬롯 술어 통합**(사용자 3차 지적 — "백테스트 기간이 자동으로 채워졌는데 캐치하지 못하고 다시 묻는다", 4차 지적 — "진행률 박스에 체크가 안 된다"): 원인은 **판정 축의 부재**였다. 신규 상장 코호트는 창을 시스템이 확정하는데 SOT의 축이 "값이 있나"·"사용자가 말했나" 둘뿐이라 그 값이 영원히 '미언급'으로 남았다 → `_decided`(질문이 끝난 필드)로 이동. 이어 **프론트에 사본이 둘**이었던 것이 재발 경로로 드러났다 — 게이트(`backtestReadiness`)만 고치고 진행률 패널(`builderProgressPresentation`)이 낡은 채 남았다. 프론트 술어를 `isSlotFilled` 하나로 합치고 두 소비자가 그것만 부르게 했다. 통합 과정에서 패널의 기존 드리프트 3종이 함께 드러나 수정: 손절 배지만으로 '매도 조건' 완료 표기, 손절·익절 중 하나만으로 '리스크 관리' 완료 표기, 리밸런싱 '안 함' 결정을 패널이 입력으로 받지 못해 미완료 표기(호출부 7곳에 플래그 배선). 계약 픽스처는 '첫 빈 슬롯'만 내보내던 것을 **슬롯별 정답**까지 내보내도록 확장 — 슬롯별로 표시하는 소비자에게 대조할 정본이 없었던 것이 드리프트가 오래 살아남은 이유다. 뮤테이션 검증: 술어 규칙을 하나씩 훼손하면 게이트·패널 양쪽에서 해당 케이스만 실패. ⑧ **가드** — 상장일 미상 제외+경고, 공집합 fail-fast, ETF 명시적 미지원, 시장 미언급 기본값은 양시장. 재현 검증: 빌더 대화 왕복 후 코스피+코스닥 2,605종목 → **2026년 상장 20종목**, 백테스트 시작일 2026-01-01로 자동 조정, 첫 매매 2026-03-03. 테스트: 신규 60 — 백엔드 2,851·프론트 1,284 전체 통과, 빌더 퍼징 QA 0실패. SRS FR-STR-073 |
| 인터프리터 프롬프트 정리 + 크로스오버 기간 소실 수정 (2026-07-30) | 사용자 요청 — "인터프리터 system 프롬프트 중 필요 없는 프롬프트를 제거". 판정 기준은 취향이 아니라 **파이프라인이 실제로 읽는가**로 뒀다. ① **죽은 출력 채널 3개 제거** — `status`(`run_validation`이 오류·누락으로 재판정해 `report.status`만 쓰임), `missing_fields`(`validate_completeness`가 결정론 산출, LLM 값은 소비자 0), `assumptions`(소비자 0 — recall 검사도 명시적 제외). 형태·규칙 8·예시 7곳의 관련 지시를 함께 제거했고, `clarification_questions`는 수정·되묻기 경로(`primary.py`)가 읽으므로 유지 ② **중복 정리** — 규칙 5-2-1이 5-3과 동일 내용이라 5-3에 접어 넣되 '돌파' 어휘를 함께 이전(안 옮기면 규칙 5-4가 '돌파'를 `>=` 임계값으로 가져간다), 5-2/5-3/6-0 번호 충돌 해소, ETF 재무지표 금지 3회 반복 중 1회 제거. 20,470자→19,441자 (FR-STR-019o의 prefill 병목과 같은 축) ③ **검증 중 기존 버그 발견·수정** — 실제 9B A/B에서 "20일선을 깨고 내려오면 매도"·"20일선이 60일선을 골든크로스"가 1차 출력에서 `parameters=null`로 나와 **사용자가 말한 기간이 사라지고** 시스템이 "단기 기간을 몇으로 할까요?"라고 되묻고 있었다(HEAD에서도 재현 — 이번 정리와 무관한 기존 결함). 원인은 `_OUTPUT_SHAPE`의 조건 예시가 재무 조건 하나뿐이라 **`parameters` 키가 형태에 아예 없었던 것** — `etf_theme`(07-27)과 같은 실패 방식으로, 규칙 5-3이 아무리 상세해도 형태를 이기지 못한다. 수정: 형태에 `parameters`를 채운 크로스오버 조건 추가 + `parameters:null`→`{}` 형식 정규화(종전엔 dict_type ValidationError로 출력을 통째로 버려 복구 재요청 1회를 무조건 태웠다) + 예시 3-1 신설·예시 4-2에 크로스오버 파라미터 명시(단일 이동평균 문장에서 말하지 않은 60을 지어내던 것 차단). 실측: 5문장×3회 15/15 통과, `repairs=0`(재요청 소멸), 기간 되묻기 소멸, 비-MA 전략에 유령 크로스오버 조건 유입 없음 ④ 회귀 4건(형태 계약 2·죽은 채널 무시 1·null 정규화 1) — 백엔드 2,862 전체 통과. `docs/nl_interpretation_contract.md`(출력 계약 SOT)·`software_architecture.md` 동기화 | ✅ 완료 |
| 커밋 전 QA 게이트에서 발견 — clarification_questions 예시 삭제가 5개 예시를 통째로 파괴 (2026-07-30) | 커밋·푸시 전 필수 확인 절차로 `qa_template_detect.py --category 기술분석 --refresh`(20예시)를 처음 돌려보니 치명 5개 — 모두 `유니버스=KOSPI200 · max_pos=10` **동일한 고정값**이라 프롬프트 내용과 무관, 폴백/스키마 거부 신호로 판단해 추적. 원인: 위 프롬프트 정리에서 예시 1의 clarification_questions worked example(`{"field":"strategy.entry_conditions[0].value", ...}`)을 지웠는데, 그 예시가 프롬프트 전체에서 ClarificationQuestion 객체 형태(field 키 필수)를 보여주는 **유일한** 자리였다(형태 자체는 원래도 빈 배열이라 스키마를 못 가르침) — 9B가 되묻기 항목을 낼 때 field를 빠뜨려 검증 실패→복구도 실패→InterpreterError로 "20일 고점을 넘기는 날 매수"처럼 완전히 파싱 가능한 입력까지 전략 전체가 버려졌다. 수정: 형태의 clarification_questions에 field 채운 예시를 다시 실음(parameters 사고와 같은 교훈 — FR-STR-019p 확장). **진단 중 별도 함정 발견**: 인터프리터를 직접 스크립트로 호출하는 검증은 `.env`를 로드하지 않는다(`load_dotenv()`는 main.py 임포트에만 걸림) — STRATEGY_INTERPRETER_MODEL이 비어 조용히 qwen3:8b(운영 모델과 다름)로 폴백해, 세션 초반 "9B로 검증됨"이라 보고한 것이 실제로는 다른 모델 검증이었다(사용자에게 정정 보고). STRATEGY_INTERPRETER_MODEL을 명시 export하거나 HTTP 엔드포인트로 재검증해 바로잡음. **부수 발견**: 이 커밋에 포함된(세션과 무관한 기존 백로그) backtest_engine.py·universe_pit.py 변경이 engine-version-guard CI를 걸려 실패시킴 — ENGINE_VERSION 7.3→7.4, CHANGELOG 추가(신규 상장 유니버스는 listing_from/to 미지정 기존 전략에 결과 영향 없는 opt-in 필터라 MINOR). 검증: 수정 후 재기동한 서버로 5개 치명 전부 해소 확인(HTTP), 실제 9B 크로스오버 5문장×3회 15/15 재확인, `test_backtest_engine.py` 실패 2건은 356e0b50(백로그 이전)에서도 동일 재현 — pre-existing, 미수정(범위 밖) | ✅ 완료 |
| CI 배포 게이트 + 프롬프트 형태 불변식 가드 (2026-07-30) | 회귀가 프로덕션까지 나간 원인 두 가지를 각각 막았다. ① **배포 게이트** — `deploy` 잡이 `needs: [frontend, backend]`만 요구해 `engine-version-guard`가 빨간불이어도 배포가 그대로 나갔다(실측: c0f4eb31에서 가드 실패에도 `deploy=success`, 배포 스크립트가 `git reset --hard origin/main`이라 "배포는 됐는데 CI는 실패"가 조용히 정상처럼 보였다). `needs`에 `engine-version-guard` 추가. ② **형태 불변식 가드** — 같은 사고(형태에 없는 키를 9B가 안 채움)가 `etf_theme`(07-27)·`parameters`(07-30)·되묻기 `field`(07-30) 세 번 반복됐으므로, 개별 필드 회귀 테스트가 아니라 불변식으로 세웠다: `test_output_shape_objects_expose_all_live_fields`가 형태에 **구체적 객체로** 등장하는 6개 모델의 스키마 필드가 전부 노출되는지 검사하고, 의도적 누락은 `_SHAPE_OMISSIONS`에 이유와 함께 등록하도록 강제한다. 검사 범위를 구체적 객체로 한정한 근거는 실측 — `ranking: []`처럼 빈 배열 자리는 잘못된 키 집합을 각인시키지 않아 규칙만으로 정상 동작하고, 위험한 것은 **일부 키만 보여준 객체**다. 이 분석이 곧바로 `max_position_weight` 미노출을 짚었고 확인 결과 엔진 미지원 필드라 의도적 누락이 맞아 사유와 함께 등록(노출하면 오히려 오류 출력을 유도). 뮤테이션 검증: `UniverseSpec`에 신규 필드를 주입하면 실패, 원복하면 통과 — LLM 없이 도는 유닛 테스트라 CI에서 상시 작동한다 | ✅ 완료 |
| 전략 파싱 전면 타임아웃 — 워밍업 num_ctx 불일치 (2026-07-30) | 사용자 신고: 전략 입력이 전부 `Strategy parse stream proxy error: The operation was aborted due to timeout`. 재현 실측 — `/strategy/parse-stream` 1회 **480초**(planner 240s + 인터프리터 240s, 둘 다 응답 0바이트로 클라이언트 타임아웃), 프론트 프록시 예산은 120초라 사용자에겐 항상 에러. 원인은 파싱 로직이 아니라 **Ollama 러너 컨텍스트 불일치**였다: startup 워밍업(`_ollama_preload_model`·`_ollama_prefill_system_prompt`)이 `num_ctx` 없이 `keep_alive=-1`로 모델을 적재해 러너가 모델 최대 컨텍스트(**262144**)로 **영구 고정**되고, 이후 추론 호출(`num_ctx=16384`)은 러너 교체를 기다리는데 고정된 러너는 만료되지 않아 무한 대기했다. 격리 실측: 같은 모델·같은 질문이 `num_ctx` 생략 시 **0.8초**, `num_ctx=16384` 지정 시 **240초+ 무응답**(러너 CPU 0%, 신규 러너 미기동); 언로드 후 `num_ctx=16384`로 새로 적재하면 5.2초. 수정: 두 워밍업 호출에 추론과 동일한 `_OLLAMA_NUM_CTX`를 실어 러너를 같은 컨텍스트로 띄운다 — `parse_validator._VALIDATION_NUM_CTX`가 이미 명문화한 규칙(추론 본경로와 num_ctx를 맞출 것)을 07-30 신설 prefill이 어긴 것으로, `keep_alive=-1` 고정 때문에 결과가 '콜드 페널티'가 아니라 **완전 정지**로 악화됐다. 검증: 수정 후 동일 요청 **480초 → 19.9초**, 재기동 시 러너 ctx=16384 확인, 회귀 테스트 `test_ollama_warmup_uses_same_num_ctx_as_inference` 추가 — 백엔드 2,866 전체 통과 | ✅ 완료 |
| 테마 유니버스 교체 불능 — 수정 레인 지식 조회 이관 (2026-07-30) | 사용자 신고: 토스 관련주 6종목 전략에 "쿠팡 관려주로 수정해줘"를 넣었는데 전략이 토스 그대로 유지됐다. 인터프리터 로그는 의미를 제대로 읽고 있었고(MODIFY_STRATEGY, source_text="쿠팡 관려주로") KG에도 쿠팡 테마가 상장사 21곳으로 있었는데(`catalog_theme_candidates('쿠팡')` 확인) **조회조차 되지 않았다**. 원인 3겹 — ① **수정 레인에 지식 조회 체인 자체가 없음**: 생성 경로는 planner가 `classify_universe`→`list_concept_candidates`→`kg_theme_companies`→`ground_term`을 태우고 관찰값을 병합하는데, `run_primary_modification`은 `decompile→인터프리터→patches→검증→컴파일`뿐이라 테마 표현이 KG에 도달할 경로가 없다. 그래서 모델이 종목코드를 스스로 알아내야 하는 처지가 되어 초안의 토스 코드 6개를 그대로 복사한 **무변경 패치**를 내고 "쿠팡 관련주 종목 코드가 무엇인가요?"를 되물었다(지식 조회를 사용자에게 떠넘김 — 계약 § 3-2 위반). 자기 의심 게이트는 그 산출물을 되묻기로 돌린 마지막 단계일 뿐 원인이 아니다 ② **테마 출처 소실**: `apply_theme_companies`가 종목만 남기고 테마명을 지워(`sector=None`) 초안에 "이 종목들이 어디서 왔는지"가 없었다 — 무엇을 비워도 되는지 판정할 근거 부재 ③ **되묻기 소실**: 무변경 되묻기에 `clarification_priority`가 없어 프론트가 자기 게이트 질문("다음으로 어떤 조건에서 매수할지 정해볼까요?")으로 덮어써, 요청이 반영되지 않은 사실이 화면에서 증발했다. 수정 3겹 — ① `ParsedStrategy.theme_universe`+`UniverseSpec.theme`로 출처를 수정 초안까지 왕복(라운드트립 가드 유지) ② `primary._resolve_theme_change` — 이번 턴이 새로 넣은 미해결 유니버스 표현을 **검증기에 넘기기 전에 떼어내** 생성 경로와 같은 계약의 체인에 넘긴다(후보 2개 이상=범위 되묻기 / 1개=정본 표기 확인 칩(자동 확정 금지) / 0개=KG 직접→검색 학습→되묻기). 떼어내는 이유는 실측: 미지 테마를 그대로 넘기면 capability_validator가 '지원 섹터 목록에 없습니다' **오류**로 판정해 수정 레인 전체가 폴백하고 요청이 무변경으로 끝난다. 적용은 신규 `nl_parser.replace_theme_universe` — 이전 **테마에서 온** 종목만 비우고 재조회, 사용자 직접 지정 종목은 불가침(기존 가드 유지), 조회 실패 시 원상복구 ③ 무변경 되묻기 4분기에 `clarification_priority` 부여 ③ **설계 1차안 폐기(실측 근거)**: LLM이 `/universe/theme`를 패치하게 하려 했으나 실제 9B는 테마 교체를 `replace /universe/sectors=['쿠팡']`로 낸다(생성 규칙 6-0-2와 같은 형태 — 형태에 없는 키는 채우지 않는다는 07-30 교훈의 재확인). 트리거를 sectors로 옮기고 `theme`은 시스템 전용 출처 표기로 남겨 `_SHAPE_OMISSIONS`에 사유 등록. **부수 수정**: 정본 섹터로 바꾸는 턴('2차전지 업종으로')도 이전 테마 종목이 남아 새 업종을 삼키던 같은 계열 버그가 함께 해소됐다(지정 종목이 섹터 필터보다 우선하므로). 실제 9B 검증: 사고 입력 재현 → '쿠팡(coupang)' 확인 칩 제시(전략 무변경) → 칩 클릭 → 21종목 교체 확인, '2차전지 업종으로' → sector=이차전지·종목 해제 확인. 회귀 6건 추가 + `AgentsTab` 수정기 흐름도·`slot-judgments.json` 픽스처 동기화 | ✅ 완료 |
| 네이버 분류 전면 우선 + KG 미스 라이브 편입 (2026-07-27) | 사용자 지시 2건: "KG 데이터는 네이버 증권이 주달보다 우선" + "우리 KG에 없으면 네이버를 항상 우선 검색해서 KG에 넣어줘". 발단: '온디바이스 AI'가 네이버 금융 테마(24종목)에 있는데 우리 카탈로그엔 부재 — 원인은 수집 누락이 아니라 **시드 우선 가드**(시드 `on-device-ai` 노드와 이름 충돌로 스킵, 시드 직접 엣지는 2곳뿐). 수정 3겹: ① **수집** — `ingest_naver_themes.py` 시드 중복 가드 폐지 후 재수집(248→285테마·엣지 6,405, 온디바이스 AI 24종목 편입; 스캔 인식은 여전히 시드 우선이라 taken 계약 불변) ② **읽기 경로** — `theme_listed_companies` 카탈로그 표기 정합 우선을 학습 앵커 한정에서 **전 앵커**로 확장(정확 일치만: 온디바이스 AI=네이버 24곳이 시드 2곳 대체, 표기 불일치 HBM은 시드 큐레이션 6곳 유지) ③ **라이브 편입** — `engine/naver_theme_live.py` 신설(배치 수집과 파서·스코프 가드 공유, 스크립트가 엔진 모듈을 임포트하도록 역전): KG 미스 용어의 검색 레인(`term_grounding` ④a)이 뉴스 검색 학습 전에 네이버 테마·업종 목록을 라이브 조회, 표기 정합(원명·괄호 본체·슬래시 변형 정확 일치) 시 수록 종목을 카탈로그에 병합 저장 → 그래프 mtime 재로드로 즉시 결정적 해석(정합 없음·수집 실패는 기존 뉴스 학습 폴백, search_fn 주입 시 스킵으로 테스트 실네트워크 차단). 테스트: 신규 7(`test_naver_theme_live.py` 정합·병합·가드·검색 레인 순서 + `test_knowledge_graph.py` 시드 앵커 카탈로그 우선) — 백엔드 2,738·프론트 1,202 전체 통과 | ✅ 완료 |

| 워크플로 제어 축 추가 — 멈춤·취소·초기화·되돌리기 (2026-07-30) | State-Aware Strategy Agent 설계 스펙 § 4(Conversation Mode / Workflow Effect 분리) 구현. 이전에는 "이 발화가 진행 중인 전략 작성을 **어떻게 제어하는가**"를 표현할 자리가 없어 "잠깐 멈춰"·"그만할래"·"처음부터 다시"·"아까 바꾼 거 되돌려"가 전부 일반 전략 발화로 흘러 조건 수정으로 해석되거나 조용히 무시됐다. **축은 늘리되 레인은 늘리지 않았다** — 스펙의 conversation_mode 8종 중 4종(TASK/EXPLANATION/CASUAL/UNSUPPORTED)은 이미 `QueryIntent`와 중복이라 새 필드로 받지 않는다(같은 원문을 두 축으로 판정하면 `intent=OFF_TOPIC`+`mode=TASK` 같은 모순 조합 조정 규칙이 필요해진다). 실제로 없던 것은 `workflow_effect` 하나이고 라벨과 직교하므로(한 발화가 전략 요청이면서 동시에 취소일 수 없다) 중복이 생기지 않는다. ① **판정** — 기존 의도 분류 LLM의 **출력 형태에 키 1개 추가**(`intent/interpreter.py`), LLM 호출 증가 0회·원문 정규식 0개 유지. `/query/classify` max_tokens 120→180(필드 증가로 JSON 절단 시 UNKNOWN 실패로 떨어짐) ② **성립 검증(결정론)** — `classifier._resolve_workflow`: LLM은 제안만 하고 성립 여부는 코드가 정한다(스펙 § 18). 규제 게이트 라벨 9종은 제어 거부(제어가 정형 안내를 삼키지 못하게), 진행 중인 전략이 없으면 PAUSE/CANCEL/RESTART/ROLLBACK 불성립, 직전 상태가 PAUSED가 아니면 RESUME 불성립 — 불성립은 거부가 아니라 **NONE 강등**이라 제어가 사라져도 기존 흐름이 그대로 이어진다 ③ **상태 보관** — 백엔드 무상태 유지, `workflow_status`를 프론트가 매 요청에 에코(`previous_explicit_fields`·`pending_ask`와 같은 계약). 분류 실패 시에도 값을 잃지 않는다(실패가 사용자의 '멈춤'을 조용히 해제하지 않게) ④ **실행** — 프론트 `decideConversationTurn` → `action:"control_workflow"`. CANCEL/RESTART만 전략 초안을 비우고(`clearStrategyDraft` — `handleReset`과 달리 대화 기록·화면 유지), PAUSE는 보존, RESUME은 진행, ROLLBACK은 미실행 ⑤ **스펙 내부 모순 1건 해소** — 스펙 § 4 예시는 "PER이 뭐야?"를 PAUSE로 적었으나 같은 스펙 § 21은 "부가 질문은 워크플로를 유지한다"고 규정한다. 설명마다 멈추면 명시적 RESUME 없이 진행이 안 되므로 § 21을 따랐다(PAUSE는 명시적 요청에만) ⑥ **ROLLBACK은 감지하되 미실행** — 변경 이력(Event Sourcing, 스펙 § 19) 미구현이라 되돌릴 대상을 특정할 수 없다. 거절 대신 지원 가능한 가장 가까운 형태를 안내(스펙 § 28), § 19 구현 시 전이표+프론트 실행부만 배선하면 됨. 회귀: 백엔드 11건(규제 게이트 우회 차단 9라벨 파라미터 포함)·프론트 4건 — 백엔드 3,070·프론트 1,298 전체 + `npm run build` 통과. `nl_interpretation_contract.md` § 11-9·`AgentsTab` 분류기 흐름도 동기화. SRS FR-SA-007 | ✅ 완료 |

| 필드 상태 축 — '해당 없음'과 '완료'의 분리 (2026-07-30) | State-Aware Strategy Agent 설계 스펙 § 5(Field Status 7종) 구현. 진행 골격 판정이 `filled: bool` 하나뿐이라 **서로 다른 셋을 같은 값으로 뭉갰다**: ① 사용자가 말한 값 ② 기본값이 물질화된 미확인 값 ③ 물을 대상이 아닌 항목. 특히 ③이 완료로 표시돼 **단일 종목 전략의 리밸런싱 칸에 체크가 켜져 있었다**(진행률이 실제보다 높게 보임). `strategy_slots.py`의 도입 배경 주석이 이미 같은 진단을 남겨 뒀다 — "판정을 한 곳에 모으는 것만으로는 부족하고, 그 곳이 표현할 수 있는 축이 실제 사례를 모두 덮어야 한다". ① **스키마를 감싸지 않았다** — 스펙은 모든 필드를 `{value, status, source, ...}`로 감싸라고 하지만 그러면 컴파일러·디컴파일러·patch_applier·엔진 변환기·프론트가 전부 깨진다. 값 표현은 그대로 두고 상태만 옆에 다는 **사이드카**로 만들었다 ② **새 판정을 만들지 않았다** — UNKNOWN/CONFIRMED/PROVISIONAL/NOT_APPLICABLE은 기존 3축(`_decided`·`_has_value`·`_explicit_ok`)을 그대로 재사용하고, INVALID/NOT_APPLICABLE(조건)은 검증 후 spec에서 구조적으로 재판정하며, CONFLICTED만 `conflict_validator`가 판정한 자리에서 슬롯을 함께 기록한다(`ValidationReport.conflicted_slots` — 오류 문장만으로는 어느 필드가 모순인지 알 수 없다). 지표 미지원(INVALID)과 ETF×기업 재무지표(NOT_APPLICABLE)를 나눈 이유는 해결책이 다르기 때문이다 — 전자는 지표를 바꾸고 후자는 유니버스를 바꾼다 ③ **`filled` 판정은 한 줄도 바뀌지 않았다** — 상태 축은 표시 전용이고 되묻기 게이트·백테스트 실행 버튼·planner의 `filled_slots`는 이전과 동일하다. 계약 픽스처(`__fixtures__/slot-judgments.json`)를 재생성해 **무변동** 확인(회귀 없음의 근거). `status_overrides`도 상태만 덮고 값이 없는 필드(UNKNOWN)는 덮지 않는다 ④ **소비자는 진행률 카드 하나** — '해당 없음'을 분모에서 빼고(`countProgress`) 흐리게 표시한다. 백엔드 `field_states` → SSE 프록시 화이트리스트 → `attachFieldStates`로 렌더 직전 부착(호출부 8곳에 인자를 늘리지 않음) ⑤ **미구현(스펙 대비)**: source·confidence·updated_at·dependencies·invalidated_by 메타데이터, INFERRED 산출(열거형 정의만 — 슬롯 단위로 롤업할 소비자가 없어 미리 만들지 않음). 회귀: 백엔드 23건(상태 축 12·조립기/앵커 11)·프론트 7건 — 백엔드 3,093·프론트 1,305 전체 + `npm run build` 통과. `nl_interpretation_contract.md` § 11-10·`AgentsTab` 해석기 흐름도 동기화. SRS FR-STR-019q | ✅ 완료 |

| 되묻기 결속 소실 — 질문↔답변 연결 복구 (2026-07-31) | 사용자 신고 7종(직전 질문과 답변의 연결 소실, 이미 결정한 값 재질문, 수정 시 흐름 깨짐, ETF·단일종목·코스피에 같은 질문, 매번 새 Intent로 분류, 최신 문장 과의존, Action 추적난)의 원인을 실측으로 특정했다. **원인은 실행 엔진이 아니라 `pending_ask` 발행 체인**이다 — 멀티턴 13턴 실측에서 `clarification_priority=dag_planner`(플래너 ask 채택) 턴은 결속 **5/6**, 고정 파이프라인 폴백 턴은 **0/7**로 완전히 갈렸다. LangGraph 도입은 검토 후 반대로 결론(Action DAG·NodeStatus·`invalidated_by_state_change`는 `planner/dag.py`에 이미 있고, 아래 원인 넷은 전부 프레임워크가 대체하지 않는 도메인 코드다). ① **`_build_clarification`이 추천값을 버렸다** — 인터프리터는 포트폴리오·리스크·청산 슬롯에도 `recommended_value`를 냈는데(종목 수 10, 리밸런싱 monthly, 손절 8) 칩 생성이 **조건 임계값 질문에만** 있어 전부 탈락했고, 칩이 0개면 `_pending_ask_payload`가 None을 낸다 → 그 슬롯 질문은 구조적으로 영원히 결속 불가. 슬롯별 칩 빌더 `_SLOT_CHIP_BUILDERS` 추가 — **표기는 `_bind_chips` 결속이 실증된 것만** 쓴다(지어낸 문구는 발행 시점에 탈락해 무효). ② **폴백이 결속을 잃었다** — `_is_filled_slot_topic` 가드가 플래너의 결속 가능한 ask를 거부하면(`gate=ask_rejected:filled_slot`) 폴백인 검증 리포트 질문에는 결속이 없었다. 가드 판단은 옳다 — 잃지 말아야 할 것은 폴백의 결속이다. 초기 파스 + 수정 경로 3곳(`_modify_clarification`)에 발행 배선. ③ **완결성 검증이 유니버스를 안 봤다** — KOSPI·ETF·단일 종목에 **바이트 동일한** 질문을 냈다('삼성전자만으로 전략'에 "상위 몇 종목을 선택할까요?"). 지정 종목이면 종목 수를 묻지 않는다(FR-STR-068과 같은 계약, 리밸런싱은 복수 지정에 성립하므로 유지). ④ **네 번째 질문 생산자** — 백테스트 최소 조건 게이트(`main._build_parse_result`)가 칩을 이미 갖고도 `pending_ask: None`을 하드코딩하고 있었다. 슬롯 라벨을 topic으로 실어 결속(`next_incomplete_backtest_slots` 신설). 질문과 결속이 어긋나지 않게 `apply_primary_meta`가 질문을 덮어쓸 때 결속도 함께 옮긴다. **관찰 계층**: `observability.agent_trace.ask_binding_gate()` — 결속이 어느 게이트에서 끊겼는지 이름 붙인다(ok/planner_off/planner_failed/ask_rejected:*/no_chips/chip_binding_failed/path_without_binding). 이 이름이 원인 특정을 만들었다(LangSmith는 `.env` 키 부재로 전 계층 no-op이었다 — 켜면 같은 계측이 Trace 트리로 보인다). **하니스**: `scripts/qa_multiturn_binding.py` — 프론트 무상태 에코 계약을 흉내낸 멀티턴 QA. 기존 QA 하니스가 전부 한 턴짜리라 턴 **사이** 증상이 재현되지 않던 공백을 메운다. ⑤ **plannerX칩 결속 실패 폴백(2026-08-01)** — LangSmith 활성 후 Trace가 마지막 1건의 정체를 바로잡았다: `no_chips`가 아니라 **`chip_binding_failed 칩=0/3`**이었다(플래너가 낸 매도 칩 3개가 전부 엔진이 표현할 수 없어 탈락). 칩 개수만 보면 "칩이 있으니 정상"으로 지나가지만 결과는 칩 0개와 동일하다 — 판정 기준을 "칩이 있나"에서 **"결속이 됐나"**로 바꾸고, 실패 시 진행 골격 슬롯 SOT(`strategy_slots.suggestions_for_topic` 신설)의 **결속 실증된** 칩으로 재시도한다(`_bound_ask_with_slot_fallback`). 이 과정에서 발행 지점을 2개 더 찾았다 — 수정 경로(`_modify_clarification`)와 재계획(`_replan_next_question`)에 게이트 span이 없어 Trace에서 modify 7턴이 통째로 공백이었고(create 7턴만 잡힘), 수정 레인은 설계상 플래너를 안 돌리는데 `planner_failed`로 오라벨돼 `lane` 축을 추가했다. 실측 전후: 지적 **12건 → 0건**, 결속 **5/13 → 14/14**. 회귀: 신규 31건. 백엔드 3,334 전체 통과. `AgentsTab` 해석기 흐름도 동기화. LangSmith는 APAC 리전(`LANGSMITH_ENDPOINT` 불일치 시 전 요청 403 — `.env.example`에 함정 명시) | ✅ 완료 |
| 되돌리기 — 변경 이력 + 대상 판정 (2026-07-30) | 설계 스펙 § 19(Event-Sourced State Management) 구현. § 4가 `ROLLBACK`을 **감지만 하고 실행하지 않던** 것을 닫았다("아까 바꾼 거 취소해"·"ETF로 바꾸기 전으로"·"PER 조건 지운 것만 되돌려"). ① **이벤트 소싱의 전체 구현이 아니다** — 상태 재구성(replay)이 아니라 **스냅샷 되감기**다. 각 턴의 ParsedStrategy 전체가 이미 스냅샷이라 이벤트를 되감아 상태를 만들 필요가 없다(문서에 '이벤트 소싱'이라 적지 않는 이유) ② **레인 분리** — 변경 산출은 결정론(`change_log.changed_field_names`: 값이 달라진 최상위 필드 **이름**. 기존 `_diff_fields`는 "max_positions: 10 → 5" 로그 문장이라 대상으로 못 쓴다), 보관은 프론트+세션 스냅샷(백엔드 무상태 계약 유지 — `pending_ask`·`explicit_fields`·`workflow_status`와 같은 에코), 대상 판정은 LLM(`/strategy/rollback/resolve` — 원문 해석), 대조는 결정론, 복원은 스냅샷을 들고 있는 프론트(`rollback.ts`) ③ **임의 보정 금지가 이 기능의 핵심** — 지어낸 턴 번호를 '가장 최근 턴'으로 떨어뜨리면 사용자가 의도하지 않은 변경이 조용히 사라진다. 되돌리기는 작업을 지우는 동작이라 폴백이 다른 레인보다 보수적이어야 하며, 모든 실패(LLM 미가용·출력 불량·없는 번호·그 턴에 없는 필드)는 되묻기로 끝난다 ④ **provenance도 함께 되돌린다** — 남기면 되돌아온 질문을 이미 답한 것으로 보고 건너뛴다(조건 옵션 되돌리기 `previousStepState`가 겪은 함정). 필드 단위는 되돌린 필드의 provenance만 맞추고 나머지는 유지한다 ⑤ **실측이 설계를 두 번 고쳤다**(로컬 Ollama): **모델 슬롯** — 분류기와 같은 4B로 시작해 **1/7**이었다. 라벨 분류가 아니라 이력 목록 위의 추론이라 9B(인터프리터 슬롯)로 옮겨 5/7 → 최종 **7/7**(4B도 아래 수정 후 5/7까지 올랐으나 슬롯은 9B 유지 — 잘못 고른 턴은 전략을 지운다). **필드 라벨** — 영문 필드명만 실었더니 "손절 바꾼 거"가 `stop_loss_pct`와 이어지지 않아 9B가 재무 조건 턴을 골랐다. 이력을 `stop_loss_pct(손절)` 형태로 싣는 결정론 매핑 추가. **대상 없는 요청** — "되돌려"에 임의의 중간 턴을 고르던 것을 "가리키는 대상이 없으면 가장 큰 번호"로 명시(Ctrl+Z 의미) ⑥ 필드 단위 복원은 전략이 새 조합이라 `/strategy/compile`로 백테스트 요청을 재생성한다(턴 단위는 스냅샷의 요청을 그대로 복원). 회귀: 백엔드 19건·프론트 13건 — 백엔드 3,112·프론트 1,318 전체 + `npm run build` 통과. `nl_interpretation_contract.md` § 11-11·`AgentsTab` 분류기 흐름도 동기화. SRS FR-SA-008 | ✅ 완료 |

| 개념↔종목 관계 근거·관련도 배선 (2026-07-30) | 설계 스펙 § 8.5("관계에는 반드시 근거와 관련도를 저장", "직접적인 사업 관계와 단순 테마성 관계를 구분") 구현. **대부분 이미 있었고 런타임에 도달하지 못하고 있었다** — 조사 원장(`data/kg-research/*.json`, 129건)에 `relation_type`·`relevance`·`relevance_score`·`reason`·`business_evidence`·`sources`·`verified`가 이미 적혀 있는데, 시드 그래프로 옮길 때 관계 종류(엣지 타입)와 한 줄 `note`만 남고 사라졌다(`grep kg-research engine/` = 0 — 원장은 런타임에서 한 번도 읽히지 않았다). ① **원장 로더** `engine/kg_research.py`(mtime 캐시) → 그래프 빌드가 시드 엣지에 `relation` 부착(원장에 없으면 부착하지 않음 — 근거를 지어내지 않는다) → `listed_companies`가 `relation`·`direct`·`evidence_source` 전달 ② **어휘를 정하고 데이터를 맞추지 않았다** — 처음엔 스펙의 10개 유형을 그대로 상수로 적었으나 원장 전수 확인 결과 실제 어휘는 `Producer 104·Supplier 15·Related 6·Investor 3·Infrastructure 1`이라 목록을 데이터에 맞춰 고쳤다(원장이 정본). 목록 밖 유형도 버리지 않고 `relation_known=False`로 표시만 한다 ③ **§ 8.5 핵심 구분은 `direct` 하나로** — Producer·Supplier만 직접 사업 관계, Investor·Infrastructure·Related는 사실이되 직접 생산·공급이 아니다. 출처는 `evidence_source`(research/seed/catalog/learned)로 나누며 **빌드 시점에 표기**한다(읽는 시점에 추론했더니 근거 없는 시드 엣지 HBM이 카탈로그로 잘못 표기됨) ④ **문자열 되파싱 제거** — `concept_universe`가 note에서 정규식으로 `"(Core 95)"`를 긁어 점수를 만들던 것을 원장의 `relevance_score` 직접 사용으로 교체(원장 없는 개념은 기존 되파싱 유지) ⑤ **[규제 안전] '정책 수혜 가능성' 미도입** — 스펙이 나열한 관계 유형 중 이것만 미래 전망이라 근거로 표기하는 순간 객관적 데이터 표시가 아니라 전망 제공이 된다. 회귀 테스트가 전망성 어휘(Policy·Beneficiary·Expected·Outlook·Forecast) 유입을 막고, 별도 테스트가 배포된 원장의 유형이 전부 사실 유형인지 상시 확인한다 ⑥ **관련도 기반 절단·정렬은 넣지 않았다** — "테마 유니버스 종수 상한 절단 금지"가 선 사용자 결정. 회귀 16건 — 백엔드 3,128 전체 통과. `nl_interpretation_contract.md` § 11-12 동기화. SRS FR-STR-070d | ✅ 완료 |

| 정정(CORRECT) + Action 메타데이터·상태 (2026-07-30) | 설계 스펙 § 20(사용자 정정)과 § 12.1·12.2(Action 메타데이터·상태) 구현. ① **정정** — `workflow_effect`에 `CORRECT` 추가. ROLLBACK과의 경계는 **올바른 지시가 함께 있는가**다("아까 바꾼 거 취소해"=되돌리고 끝 / "아니 ETF로 바꾸라는 게 아니라 관련 ETF를 후보에 추가하라는 거야"=되돌린 자리에 새 해석 적용). 되돌릴 지점은 **LLM에 묻지 않는다** — 정정은 언제나 방금 한 해석을 겨냥하므로 직전 변경으로 결정론이 정해진다(과거 어느 지점이든 가리킬 수 있는 ROLLBACK과 다른 점). 스펙 § 20 "잘못 해석한 내용을 변명하지 마라"에 따라 사과·해명 문구를 붙이지 않는다(분류기에 CORRECT canned 문구 없음 — 재해석 결과가 그대로 답). 실측(4B): CORRECT·ROLLBACK·UPDATE 경계 포함 제어 축 17/17 ② **Action 메타데이터** — `requires`/`produces`/`invalidated_by`를 노드에 추가하되 **LLM에 묻지 않는다**: "kg_theme_companies가 무엇을 만들고 언제 무효가 되는가"는 도구의 정적 성질이지 이번 턴의 판단이 아니다. 프롬프트 출력 형태에 필드를 늘리면 9B가 잡음을 내고 prefill 예산만 먹으므로(FR-STR-019o·019p) `dag._TOOL_EFFECTS` 정적 표가 채우고, LLM이 실어 보내도 알려진 도구면 표가 이긴다 ③ **Action 상태 8종** — 완료 집합만으로는 "왜 이 노드가 실행되지 않았나"(의존 미완료/무효/실패)를 구분할 수 없었다. `node_statuses`가 PENDING/READY/RUNNING/COMPLETED/BLOCKED/INVALIDATED/FAILED/SKIPPED를 계산하고, **무효 노드는 지우지 않고 INVALIDATED로 남긴다**(지우면 무엇이 왜 취소됐는지 추적 불가 + LLM이 같은 노드 재발행) ④ **무효화 씨앗은 이미 완료된 노드뿐** — 실행 전 노드까지 씨앗으로 삼으면 정상 선행 실행이 무효로 잡힌다(`classify_universe`가 `universe.type`을 만들면 그 값에 기대는 `kg_theme_companies`가 시작도 전에 무효). 무효화는 의존 방향으로 연쇄한다 ⑤ **`preconditions`는 미구현(판단)** — 스펙의 `"universe.type == etf"` 평가에는 표현식 미니 DSL이 필요한데 LLM이 문법을 지어낼 여지가 크고 평가 실패가 전부 '무시'로 떨어져 장식용 필드가 된다. 같은 제약은 `depends_on` 사슬과 `validate_intent`/`compile_strategy` 게이트가 이미 구조로 강제한다 ⑥ **한계**: DAG는 파스 1회 안에서만 산다(턴 간 영속 아님) — 무효화가 다루는 것은 한 파스 안에서 도구 관찰이 앞선 관찰의 전제를 깨는 경우다. 회귀: 백엔드 13건·프론트 3건 — 백엔드 3,141·프론트 1,321 전체 + `npm run build` 통과. `nl_interpretation_contract.md` § 11-13·`AgentsTab` 동기화. SRS FR-SA-009 | ✅ 완료 |

| 확정(CONFIRM) — 값이 아니라 상태를 바꾸는 답 (2026-07-30) | 설계 스펙 § 7(State Patch 연산 9종) 구현. **6종을 다 만들지 않았고, 그 판단이 이 작업의 핵심이다** — 이 코드베이스에서 새 능력인 것은 `CONFIRM` 하나다. `INVALIDATE`·`MARK_CONFLICT`·`MARK_NOT_APPLICABLE`은 매 턴 전략 **전체**에 재실행되는 검증기가 이미 산출하고(`validate_capability`·`validate_conflicts`·`field_state.slot_status_overrides`), `REVALIDATE`는 파이프라인이 무조건 재검증하므로 지시할 대상이 없으며, `ROLLBACK`은 § 19 작업에서 턴·필드 단위로 구현됐다. 상태를 패치로 **저장**하면 같은 판정이 두 곳에서 갈라져 `strategy_slots`를 SOT로 모은 이유를 되돌린다(`field_state.py` 머리주석) — 스펙이 `MARK_*`를 요구하는 것은 스펙의 State가 상태를 저장하기 때문이고, 계산하는 구조에서 그 등가물은 "값 패치 → 상태 재산출"로 이미 매 턴 돈다. **CONFIRM만 다른 이유**: 확정은 값에서 유도되지 않는다(물질화 기본값 10과 사용자가 고른 10은 값이 같고 상태만 다르다). ① **실측 결함** — 확정 경로가 없어 `_bind_chips`가 현재값과 같은 칩을 "표현할 수 없어 노출 제외"로 **탈락**시키고 있었다: "최대 몇 종목?"의 `최대 10종목`, "초기 자금?"의 `1,000만원`, "어느 기간?"의 `최근 5년 데이터` — 우리가 물어놓고 화면에 보여준 값을 사용자가 선택할 방법이 없었다 ② **결정론 레인** — 값이 안 바뀌는 칩의 두 종류(표현 불가 vs 현재값 지시)를 **프로브**로 구분한다(그 필드를 현재값이 아닌 값으로 바꿔 둔 State에 칩을 적용해 현재값으로 되돌아오는가). "패치가 비었으니 topic의 확정"으로 추정하지 않는다 — 그 추정은 아무 뜻도 결속되지 않은 칩을 사용자 확정으로 둔갑시켜 되묻기를 삼킨다. 확정 칩은 `pending_ask.chip_confirms`로 값 결속과 **채널 분리**(섞으면 무변경 패치가 되어 '반영 없음'으로 떨어진다) ③ **LLM 레인** — `CONFIRM_RECOMMENDATION`은 `IntentType`과 프롬프트에 **이미 있었으나 어디서도 처리되지 않던 라벨**이라 "응 그걸로"가 patches 없는 의도로 떨어져 "해석하지 못했어요"로 끝났다. 확정 판정은 LLM이 하고 **무엇을 확정했는지는 묻지 않는다** — 확정은 언제나 직전 질문에 대한 답이므로 `pending_ask.topic`으로 결정론이 정한다(§ 20 정정이 되돌림 지점을 묻지 않는 것과 같은 이유). 물어본 적이 없으면 임의로 고르지 않고 폴백 ④ **확정 가능 필드 4개**(최대 보유·리밸런싱·백테스트 기간·초기 자본) — 기본값이 없는 필드엔 확정할 대상이 없고 `universe`는 여러 속성의 합이라 '그 값 그대로'가 하나로 안 정해진다 ⑤ **잔여**: `리밸런싱 안 함` 칩은 결정적 추출기가 문구를 인식 못해 여전히 탈락 — 인식시키려면 **사용자 원문**에 쓰이는 `_extract_rebalancing_period`의 어휘를 넓혀야 하므로 금지(대원칙 1). 올바른 해법은 planner가 칩 발행 시 값을 함께 선언하는 구조다. 회귀: 백엔드 9건 — 백엔드 3,150·프론트 1,321 전체 통과. `nl_interpretation_contract.md` § 11-14·`AgentsTab` 동기화. SRS FR-SA-010 | ✅ 완료 |

| 하이브리드 상태 모델 — 영속·계산·산출물 분리 (2026-07-30) | 사용자 결정: **스펙을 그대로 구현해 Field Status를 전부 영속화하지 않는다.** 상태를 세 종류로 나누고 정본을 각각 지정했다 — ① Persisted User State(`ValueStatus` 4종, 정본=`ParsedStrategy`+`explicit_fields`) ② Derived Runtime State(`DerivedStatus` 4종, **저장 안 함**, 정본=`pipeline.py`→`field_state.py`→`strategy_slots.evaluate`가 매 턴 계산) ③ Persisted Artifact State(`ArtifactStatus` 4종, 정본=신설 `conversation/artifacts.py`, 근거만 저장). **나누는 기준은 재계산 비용**이다 — 파생 상태는 전략만 보면 공짜로 다시 나오지만(실측 0.12ms) Artifact는 KG 조회·검색이 필요해 "아직 맞나"를 재실행으로 확인할 수 없어 `source_key`를 남기고 대조한다. ① **가역성이 시험대** — ETF로 바꾸면 PER 조건이 NOT_APPLICABLE로 계산되지만 원본 값은 보존되고, 코스피로 되돌리면 **역방향 패치 없이** APPLICABLE로 복귀한다(저장했다면 그 되돌림을 LLM이 발행해야 하고 빠뜨리면 멀쩡한 조건에 '적용 불가'가 영구히 남는다). 회귀 테스트로 고정 ② **타입 분리** — 기존 `FieldStatus` 7종은 두 축이 섞여 "값은 확정인데 지금 유니버스에서 못 쓴다"를 표현할 수 없었다. `SlotStatus`가 두 필드를 갖고 `field_states` 페이로드는 `{value, derived}`. `NodeStatus`(실행)와 `ArtifactStatus`(유효성)도 분리. 계약 픽스처 재생성 **무변동**이 `filled` 불변의 증거 ③ **파이프라인 불변조건** — 파생 상태 계산이 레인 2곳(초기 파스·수정 성공)에만 있어 칩 답변·확정·유니버스 칩·설명·되묻기 레인에서는 프론트가 **직전 턴 사본을 계속 쓰고 있었다**(전략이 바뀐 턴엔 틀린 표시). 모든 반환 지점이 지나는 `_finalize_parse_result` 한 곳으로 승격 — provenance 확정 → 파생 상태 → 메타데이터 → Artifact 순서(값 축이 explicit_fields를 입력으로 쓰므로 순서가 중요) ④ **Patch 허용목록** — JSON Patch wire format 유지(개명은 수정 RAG 코퍼스·프롬프트·9B 레인 재검증을 요구하므로 별도 마이그레이션). `MARK_*`·`REVALIDATE`는 **없는 것이 계약**이며 `ALLOWED_PATCH_OPS`+`_reject_state_ops`가 코드에 남긴다. `REVALIDATE`는 파이프라인이 무조건 하는 일이라 필드를 만들면 LLM이 **빠뜨릴 수 있게** 되어 없을 때보다 나빠진다 ⑤ **비권위 메타데이터** — `field_metadata`(source·updated_at·confidence)는 저장하되 판정에 안 쓴다. `explicit_fields`와 채널을 섞지 않은 이유는 권위 축에 넣으면 언젠가 판정에 샌다는 것이며, 판정 경로 4개 파일에 이름이 없음을 테스트가 확인한다. **confidence는 필드별 producer가 없어** '이 필드를 마지막으로 바꾼 해석의 확신도'로만 해석하도록 주석·문서에 명시 ⑥ **`INFERRED`는 producer 없음** — 스키마만 유지(새 추론 기능 추가는 이번 목표가 아님) ⑦ **구현 중 오탐 발견** — Artifact STALE 대조가 미지 테마('쿠팡 관련주')에서 `parsed.sector=None`이라 비교 상대가 없는데도 VALID로 단정하고 있었다. `basis_verified` 플래그로 '확인함'과 '반증 없음'을 구분(드러내지 않으면 검증되지 않은 산출물이 검증된 것처럼 보인다). 회귀: 백엔드 27건 — 백엔드 3,166·프론트 1,323 전체 통과. `nl_interpretation_contract.md` § 11-15·`AgentsTab` 동기화. SRS FR-SA-011 | ✅ 완료 |

| 검색 목적 구조화 — 관계 근거 검증 상태 노출 (2026-07-31) | 사용자 지시: 8.3(ETF 재무지표 되묻기)는 하지 말 것(ETF는 재무지표 자체가 성립 안 함 — 버그 아니라 설계), § 16(검색 목적 구조화)만 시작. 유일한 실제 검색 경로(`engine/term_grounding.py`, 823줄)를 분석한 결과 §16이 요구하는 검증 단계 대부분이 **이미 도메인 특화 형태로 있었다**: 결과를 바로 CONFIRMED로 안 씀(`normalize_sector` 닫힌 목록 게이트), 관계 근거·중복 검증(`_propose_edges` 교차지지 2건 이상만 verified — pending은 그래프 빌드 시점에 아예 제외), 사실 vs 테마성 추정 구분(`_naver_term_is_industry`), 최신성(TTL+`first_known_date` 시점 편향 notice). **실제로 비어 있던 칸 하나**: `theme_listed_companies()`가 반환하는 회사별 관계 근거(§8.5 kg_research의 `relation_type`·`direct`·`verified`·`source_count`)가 `apply_theme_companies`에서 `target_symbols = [c["symbol"] for c in companies]`로 **평탄화되며 통째로 버려지고 있었다** — §8.5에서 어렵게 나눠 둔 "직접 사업 관계로 교차검증됨"과 "테마 성격의 간접 연관·근거 미검증"의 구분이 사용자 안내 문구에서는 "등록 관계·공시·검색 출처 근거"라는 균질한 한 문장으로 뭉개졌다. **의도적으로 하지 않은 것**: `search_goal`/`queries`를 LLM이 매 검색마다 새로 정하게 바꾸지 않았다 — 고정 4쿼리 템플릿(FR-STR-069 실측 튜닝값)을 LLM에 맡기면 지연 증가·회귀 위험만 지고 얻는 게 없다(사용자 결정으로 범위를 검증 상태 노출로 한정). **구현**: `_relation_evidence_disclosure(companies)`(`engine/nl_parser.py`)가 새 판정 없이 kg_research가 이미 계산한 `direct`/`verified`만 읽어 "사업 관계가 확인된 N곳 · 테마 성격의 간접 연관이거나 근거가 아직 검증되지 않은 M곳"으로 안내 문구를 가른다. 관계 원장이 없는 종목(카탈로그 공식 분류·시드 큐레이션)은 다른 경로로 신뢰가 이미 확립돼 있어 disclosure를 붙이지 않는다(원장 미가입=미검증 오판 금지). 전부 직접·교차검증이면 구분해 얻을 정보가 없으므로 문구를 늘리지 않는다. **남은 격차**: `search_goal`/`queries`/`required_evidence` 구조의 명시적 타입화, ETF 후보 검색(§16 워크드 예시)처럼 코드베이스에 없는 신규 검색 유형 — 둘 다 이번 범위 밖. 회귀: 백엔드 4건 — 백엔드 3,170 전체 통과. `nl_interpretation_contract.md` § 11-16 동기화. SRS FR-SA-012 | ✅ 완료(부분) |

| 종목 선정 범위 — 지정 vs 후보군 (2026-07-31) | 설계 스펙 § 6 `universe.selection_scope` 구현. **스펙 항목이 실제 버그를 가리킨 사례.** `target_symbols`에는 성격이 다른 둘이 같은 모양으로 들어간다 — 사용자가 지목한 종목과 테마 조회가 채운 관련 상장사. 변환기가 `if target_symbols:` 하나로 "지정 모드"를 판정해(`ranking_enabled=False`, `max_positions=len()`) **"이차전지 관련주 중 최근 60일 수익률 상위 10종목"이 랭킹 없이 36종목 전부 매수로 나갔다** — 사용자가 말한 랭킹과 "10종목"이 동시에 증발(실측 `ranking_enabled=False`, `max_positions=36`, `position_size=2.78%`). ① **신설 `engine/selection_scope.py`** — UNIVERSE/CANDIDATE_POOL/EXPLICIT 3종을 **저장하지 않고 계산**(FR-SA-011 ② 파생 상태와 같은 계약). 구분의 근거는 이미 State에 있던 `theme_universe`(종목 출처 기록)다 ② **테마 유래여도 랭킹이 없으면 EXPLICIT 유지** — 선정 기준이 없으면 36곳 중 무엇을 기준으로 자를지 아무도 말하지 않은 것이고, 임의 절단은 '비만치료 관련주' 사고(2026-07-28)의 결정을 뒤집는다. 5개 케이스 중 버그 케이스만 바뀌고 나머지(테마+랭킹 없음·사용자 지목 2종목·단일 종목·유니버스 전략)는 전부 기존 동작 유지 확인 ③ **프론트 배지 동반 수정** — `getPositionLabel`이 `target_symbols.length > 1`만 보고 "지정 종목 36개 균등 투자"를 표시하고 있었다. 백엔드만 고치면 **화면이 거짓말을 한다**(배지 36개 균등 vs 엔진 랭킹 10개). `getSelectionScope`는 백엔드 판정의 미러임을 주석에 명시하고 양쪽 테스트가 같은 조합을 쓰게 했다 ④ **`goal`은 미구현(판단)** — 소비자가 없다. `description`(사용자 원문)과 빌더 `strategy_type`이 이미 그 자리이고, 유일한 소비자 후보였던 § 10(질문 우선순위 동적화)은 사용자가 하지 않기로 결정했다. 소비자 없는 필드는 만들지 않는다(§ 7 `MARK_*` 판단과 동일) ⑤ **부수 확인** — 전체 스위트 1회차에서 `test_format_results_does_not_call_norm_dt_per_row` 실패했으나 월클럭 0.5초 단언의 부하 플레이크였다(해당 테스트는 `req`를 직접 만들어 변경 경로를 타지 않음). 재실행 통과 확인. 회귀: 백엔드 12건·프론트 7건 — 백엔드 3,182·프론트 1,330 전체 + `npm run build` 통과. `nl_interpretation_contract.md` § 11-17 동기화. SRS FR-SA-013 | ✅ 완료 |

| 변경 영향 범위 — 내부 출력 잔여 칸 (2026-07-31) | 설계 스펙 § 30(Planner 내부 출력)과 § 8(변경 영향) 구현. **§ 30의 7개 블록 중 6개는 이미 있었다** — `interpretation.workflow_effect`(§ 11-9)·`operations`/`state_patch`(허용목록 § 11-15)·`user_question`·`unknown_terms`·`conflicts`(§ 11-10)·`validation`(형태까지 일치)·`dag_changes`(NodeStatus 8종, § 11-13)·`next_action`. 실제로 비어 있던 것은 **`impact` 하나**. ① **왜 유일한 갭인가** — `changed_fields`(§ 19)는 *값이 달라진 필드*를 답하지만, 유니버스를 ETF로 바꾸면 값이 바뀐 건 universe 하나인데 영향은 기존 PER 조건까지 번진다. 게다가 파생 상태는 **저장하지 않으므로** 현재 값만 보면 "원래부터 안 되던 것"과 "방금 안 되게 된 것"이 구분되지 않는다 — 전이는 직전 턴 계산 결과와 대조해야만 관측된다(입력=`previous_field_states` 무상태 에코) ② **산출 3종** — affected(값 변경)·invalidated(APPLICABLE→NOT_APPLICABLE/INVALID/CONFLICTED)·revalidated(그 역방향). **재유효화를 함께 내는 이유는 되돌림의 증거가 여기에만 남기 때문**이다: 파생 상태를 저장하지 않기로 한 대가로 "ETF→코스피로 되돌려 PER이 다시 유효해졌다"가 어디에도 기록되지 않는데, 두 계산 결과의 차이가 그것을 복원한다 ③ **재검증 목록은 만들지 않았다** — 매 턴 전체를 재검증하므로(§ 11-15 ⑤ 불변조건) 그 목록은 항상 전부라 정보가 0이다 ④ **사용자 문구를 새로 만들지 않았다** — ETF×재무 안내는 capability validator가 이미 한다. 스펙 § 30 자체가 "사용자가 요청하지 않는 한 노출하지 않는다"고 규정한 내부 추적 기록이다 ⑤ **`response_plan`은 묶지 않았다** — acknowledgement/summary/warning/question 채널이 이미 4개로 분리돼 있어 한 구조로 모으는 것은 동작 이득 없는 리팩터다. 회귀: 백엔드 6건 — 백엔드 3,188·프론트 1,330 전체 + `npm run build` 통과. `nl_interpretation_contract.md` § 11-18 동기화. SRS FR-SA-014 | ✅ 완료(부분) |
| 볼린저 전략 수정 전면 불능 + 파생 상태 dict 무력화 (2026-07-31) | 사용자 신고: 볼린저 상/하단 전략에 "코스닥으로 유니버스를 변경해줘"를 넣었더니 **"요청을 전략 조건으로 해석하지 못했어요"**. 원인 2건(무관하게 겹침) — ① **LLM이 입력을 보지도 못했다**: 볼린저는 방향을 `operator`가 아니라 `signal_type`으로 표현하는데(엔진 `signals.py`: buy=하단 터치, sell=상단 터치) `strategy_decompiler`가 그것을 `operator=None`으로 되짚어, 진입·청산이 둘 다 "값 없는 같은 팩터"가 되고 `StrategySpec._drop_mirrored_valueless_exits`가 청산을 삼켰다 → 라운드트립 불일치(표현 불가) → `run_primary_modification`이 인터프리터를 부르기도 전에 폴백 → `llm_first`에는 레거시 수정 폴백이 없으므로 해석 실패 되묻기. **그 가드는 원래 이 짝을 지키려 했다**("볼린저 하단 매수/상단 매도는 서로 다른 신호"라는 예외 조항이 주석까지 달려 있었는데, 예외가 요구하는 방향 표기를 되짚기가 안 만들어 줘서 발동하지 못했다). 수정: decompiler가 `signal_type`에서 방향을 결정론적으로 복원(buy→`crosses_below`/sell→`crosses_above`). 컴파일러는 볼린저의 operator를 무시하고 역할로 방향을 정하므로 **백테스트 결과 불변**. 2026-07-27 etf_theme 소실과 같은 계열(되짚기 공백이 수정 레인 전체를 죽인다) ② **`field_states`가 인터프리터 밖 모든 레인에서 비어 있었다**: 응답 payload의 `parsed`는 `model_dump()` 결과(dict)인데 `_ensure_field_states`가 그대로 `derive_field_states`에 넘겨 되짚기가 `AttributeError`로 죽었고(로그에만 남음), 거기서 끝나지 않고 **값 축까지 전 슬롯 UNKNOWN으로 무너졌다**(실측: 유니버스 CONFIRMED→UNKNOWN, 최대 보유 PROVISIONAL→UNKNOWN 등). 기존 테스트는 `ParsedStrategy` 객체를 직접 넘겨 못 잡았다. 수정: `derive_field_states` 진입부에서 dict를 `model_validate`로 정규화. 회귀 2건(볼린저 진입/청산 라운드트립 보존+수정 반영, dict·객체 입력 동일 결과) — 백엔드 3,190·프론트 1,330 전체 통과 | ✅ 완료 |
| 전략 재진술 첫 문장 제거 (2026-07-31) | 사용자 결정: 첫 응답의 "…전략이군요." 한 줄(2026-07-24 도입)을 삭제한다 — 바로 아래 '현재까지 이해한 전략입니다' 카드가 같은 내용을 필드별로 보여주므로 정보값이 없고 읽는 시간만 든다. 제거 범위: `app/analytics/new/strategyRestatement.ts`(+테스트 13건) 삭제, `page.tsx`의 import·`ChatMessage.restatement` 필드·`finalizeParse` 합성·렌더 블록(닷+산문 단락). 대체 문구를 넣지 않는다(요약 카드가 그 자리를 이미 채운다). `chatSurfaceDesign.test.ts`의 산문 표면 단언은 재진술 전용이라 제거하고, 대신 재도입 방지 단언(`strategy-restatement`·`buildStrategyRestatement` 미등장)으로 교체. `UI_GUIDELINES.md` 표면 표에서 '재진술' 삭제. 프론트 1,319 전체 + `npm run build` 통과 | ✅ 완료 |
| 조건 교체 수정 전면 실패 — 환각 게이트 판정 단위 (2026-07-31) | 사용자 신고: "매주조건을 per 50이하로 변경해줘"가 **"요청을 전략 조건으로 해석하지 못했어요"**로 끝남. 로그에는 `✓ 패치 수락 replace /entry_conditions/0/operator='<='; replace /entry_conditions/0/value=50`이 찍혀 있어 수락된 것처럼 보였지만, **그 수락이 곧 실패의 원인**이었다. 원인 2건(둘 다 단독으로 치명): ① **게이트 판정 단위** — 인터프리터가 낸 패치 3개(`factor`=fundamental.per / `operator`=`<=` / `value`=50)는 조건 하나를 통째로 갈아끼우는 한 덩어리인데, `_patch_provenance_supported`가 **필드 단위로 개별 판정**했다. factor 패치의 `source_text`만 원문과 한 글자 어긋나(사용자 '매주' → LLM 인용 '매우') 인용 대조에 실패하고 값이 `fundamental.per`이라 수치 대조 근거도 없어 그것만 거부 → 나머지 둘이 적용돼 `technical.ma_crossover`에 `<= 50`이 붙은, **LLM이 제안한 적 없는 조건**이 생성 → capability_validator가 "'이동평균 크로스오버'에 연산자 '<='은(는) 허용되지 않습니다"로 오류 1건 → `report.errors`가 비어있지 않아 되묻기 분기를 못 타고 레거시 경로로 폴백 → 미해석 안내. 수정: `_patch_group_key`가 같은 조건 객체를 겨냥한 형제 패치를 묶고, 그룹 안에 출처가 확인된 패치가 하나라도 있으면 함께 수락한다(§ 3-1 대조의 단위를 필드가 아니라 조건으로 — 근거 없는 그룹은 그대로 거부, 그룹 키는 조건 리스트의 **필드 경로**에만 부여해 슬롯 단위로 넓히지 않음). **사용자 결정**: 그룹 AND(전량 거부·안전) 대신 그룹 OR(근거 전파·요청 반영) 채택. ② **factor 교체 시 잔여 파라미터** — ①을 고쳐 3개를 전부 적용해도 이전 지표의 `short_period`/`long_period`가 조건에 남아 "'PER(주가수익비율)'에 알 수 없는 파라미터" 오류 2건으로 **같은 폴백이 재발**했다. `patch_applier._drop_stale_parameters`가 factor가 실제로 바뀐 조건에 한해 새 factor의 registry spec에 없는 파라미터 키를 떨어낸다(입력이 LLM 출력이고 판정 근거가 registry 조회뿐이라 결정론 정규화 — 원문 해석 아님). 수정 후 동일 입력 `status=READY errors=0`. 회귀 3건(`test_modify_primary_sibling_condition_patches_share_provenance`, `test_patch_factor_replacement_drops_stale_parameters`, `test_patch_value_change_keeps_parameters`) 추가. 백엔드 3,193 통과 + 프론트 1,319 통과. AgentsTab 게이트 설명(판정 단위) 동기화. SRS FR-STR-019f ③ | ✅ 완료 |
| 부가 발화가 되묻기를 삼킴 — "안녕" 한 마디로 질문 소실 (2026-07-31) | 사용자 신고: 리밸런싱 되묻기가 떠 있는 상태에서 "안녕"을 입력했더니 인사 응답만 남고 **전략 진행이 달라졌다** — 인사에 인사로 답한 것은 맞지만 리밸런싱은 여전히 물었어야 했다. 원인: 되묻기 블록은 `isLastAssistant(i) && msg.clarification` 조건으로 **마지막 assistant 메시지에만** 렌더되는데, 분류가 GREETING이면 `decideConversationTurn`이 안내 문구만 담은 `respond` 턴으로 끝내 새 메시지 하나가 붙는 순간 질문과 선택지가 화면에서 통째로 사라졌다(설계 스펙 § 21 "부가 질문은 워크플로를 유지한다"는 FR-SA-007에서 PAUSE 억제로만 구현돼 있었고, 화면 쪽은 비어 있었다). ① **범위는 부가 발화 전체**(사용자 결정) — 같은 분기에 묶인 5개 라벨(인사·역할 밖·미제공 기능·맞춤 조언·실계좌 매매)과 용어·지식 질문(`answer_general`)이 증상이 동일하다. 종목 안내(`respond_stock`)는 안내문 자체가 입력을 유도해 질문이 겹치므로 제외 ② **판정을 새로 만들지 않았다** — 분류 LLM 라벨로 이미 갈린 분기에 `preservesOpenQuestion` 표시만 붙였다(원문 재분석 0). 자기 질문을 던지는 `respond` 턴(익절 값·보유 기간)에는 붙이지 않는다 ③ **복원 대상은 화면 상태뿐** — `openClarificationRef`에 되묻기 스냅샷(질문·선택지·요약 카드·되돌아가기 상태)을 두고 그대로 되붙인다. 파스 재실행 없음(회귀 단언), 칩 클릭의 결정론 귀속(`clarificationSuggestions` 일치)과 `pending_ask` 에코도 그대로 — `infoSuggestions`로 대충 되살렸다면 칩이 결정론 경로를 잃고 자유 발화로 새었을 것 ④ **요약 카드 이중 렌더 방지** — 안내문 블록과 되묻기 블록이 같은 `builderPresentation`을 각각 그리므로, 되묻기 쪽에 `!msg.infoText` 가드를 넣어 한 번만 그린다. 회귀 2건(인사·용어 질문) 추가 — 프론트 1,321·백엔드 3,193 전체 통과. AgentsTab 분류기 흐름 동기화. SRS FR-SA-015 | ✅ 완료 |
| 후속 질문의 다음 할 일 — 진행 골격 순서가 정한다 (2026-07-31) | 사용자 신고 2건 연속. ① 익절만 남은 전략에서 "어떻게 해야 할까?"에 '전략 검증' 말풍선 한 줄("익절 조건을 입력해 주세요.")만 뜨고 **진행률 박스·옵션 박스가 없었다** ② 1차 수정(검증 문구를 되묻기 질문으로 승격)을 넣자 **질문은 '익절', 칩은 '리밸런싱'** 으로 어긋났고 "어떻게 해야 할까?"마다 익절만 물었다 — "state 확인 후 action 결정 프로세스가 잘 작동 안 하는 것 같다". 원인은 같다: 이 발화는 분류기까지 가지 않고 프론트 `isAdvisorFollowUpPrompt`(레거시 원문 정규식)에 걸려 `answer_follow_up`으로 가는데, 그 턴이 **상태를 읽지 않고** 검증 agent 응답에 화면을 맡겼다. 검증 agent는 미완성 전략이면 어떤 후속 질문에도 자기 순서의 "X 조건을 입력해 주세요"만 돌려주므로 진행 골격 순서와 어긋난다 — 1차 수정은 질문만 그 문구로 채우고 칩은 상태에서 뽑아 **출처를 둘로 갈랐다**(어긋남의 직접 원인, 내 오판). ① **최종: 질문·선택지·진행률을 `getNextMissingBacktestCondition` 한 판정에서 만든다**(`nextConditionClarification`) — 진행 골격 순서대로 아직 정하지 않은 조건을 묻고, 세 요소가 항상 같은 항목을 가리킨다 ② **정할 것이 남아 있으면 검증 agent를 호출하지 않는다** — 답이 상태에 있으므로 LLM 왕복 0(응답 지연도 감소). 정할 것이 없으면(전략 완성) 그때는 진단이 곧 답이라 기존 '전략 검증' 말풍선 경로 유지 ③ **되묻기는 `openClarificationRef`에 기록**돼 부가 발화(FR-SA-015)가 들어와도 살아남고, 칩 클릭은 기존 결정론 귀속(`applyDeterministicConditionChoice`)을 그대로 탄다. 회귀 2건(리밸런싱 차례엔 리밸런싱 질문+칩·검증 호출 0 / 익절 차례엔 익절 질문+칩+진행률) — 프론트 1,323 전체 통과. AgentsTab 검증 agent 흐름 동기화. SRS FR-SA-016 | ✅ 완료 |
| 턴 중재 구조화 — 상태 평가 후 액션 선택 (2026-07-31) | 사용자 지적: "매 턴 State를 재평가하고 실행 가능한 Action을 고르는 구조가 맞나?" **절반만 그랬다.** 상태 재평가는 그 구조가 맞지만(파생 상태 매 턴 계산), 액션 선택은 `decideConversationTurn`의 고정 순서 원문 술어 if 체인이었고 **슬롯 상태를 입력으로 받지조차 않았다**(`ConversationContext`에 플래그 4종뿐, `getNextMissingBacktestCondition` import 없음). 직전 사고 3건(인사가 되묻기를 삼킴 / 후속 질문에 진행률·선택지 누락 / 질문과 칩 어긋남)이 전부 이 결손의 증상이었고, 그때의 수정은 분기 안에서 상태를 읽게 한 **국소 처방**이었다. ① **상태 주입** — `ConversationContext.slots`(다음에 정할 조건). 판정은 정본 술어 하나(`isSlotFilled`)로만 하고 중재자는 결과만 본다(순수 함수 유지) ② **액션 계층 명시** — L0 워크플로 제어 / L1 진행 중 하위 대화 / L2 발화 지목 규칙 / L3 라벨 / L4 상태 기본 액션(`ask_next_condition` 신설) / L5 파싱 폴백. **사용자 결정: L2 > L4**(지목한 질문을 진행 순서가 덮어쓰지 않는다). **L4가 L5를 가로채지 않는다**(새 조건 발화까지 되묻기로 흡수하면 방금 말한 조건이 사라진다 — "새 정보인가"의 판정자는 파서 LLM) ③ **응답 조립기 일원화**(신설 `turnMessage.ts`) — 분기별 수작업 조립을 없애고 계약으로 고정: 카드 항상 동반, 되묻기 칩은 결정론 귀속 채널로만, 부가 발화는 열린 되묻기 복원(자기 질문 턴은 제외). 칩 채널 둘은 클릭 의미가 달라 합치지 않는다 ④ **핸들러 단일화** — 자리표시자 유무(append/patch)가 분류 전/후로 핸들러를 두 벌 만들었고 그래서 '안녕' 수정도 한쪽만 고쳤다. `emitAssistant`가 차이를 흡수해 액션당 구현 1개(14분기, 중복 0). 미처리 액션이 조용히 로딩 버블을 남기던 끝단도 오류 안내로 닫음 ⑤ **L2 원문 정규식은 부채로 남김** — 계층으로 드러내되 새 규칙 추가 금지(LLM 레인 이관은 별도 작업). 회귀 12건 추가(중재 계층 5·조립 계약 7) — 프론트 1,335 전체 통과. SRS FR-SA-017 | ✅ 완료 |
| 되묻기 판정 LLM 레인 부분 이관 — clarify_target (2026-07-31) | 대원칙 1 부채 상환. "바꿀 대상은 말했는데 값이 없다"를 프론트 정규식 3종이 원문을 읽어 판정하고 있었다(`getModificationClarification` 15패턴 · `buildTakeProfitPercentagePrompt` · `buildFundamentalFactorPrompt` 16패턴). **사용자 결정: 부분 이관** — 되묻기 성격 3종만 옮기고 기간 하한·실행 확인·연구 지표·기간 비교는 즉답 경로로 남긴다(이관하면 분류 왕복이 새로 생기므로). ① **축 1개 추가** — `workflow_effect` 선례 그대로 기존 분류 호출 출력에 `clarify_target` 키만 더해 LLM 호출 증가 0회(`max_tokens` 180→220 — 필드 증가로 JSON 절단 시 UNKNOWN 실패) ② **닫힌 목록** `intent/clarify_targets.py`(설정 9·영역 7·재무 지표 키 26) — 지표 키 정본은 `data/fundamental-factors.json` 하나이고 프롬프트 목록도 거기서 생성해 목록이 갈라지지 않게 함 ③ **성립 검증은 결정론**(`_resolve_clarify_target`) — 규제 게이트 라벨 9종·전략 없음이면 None 강등(거부가 아니라 기존 흐름 유지) ④ **문구는 LLM이 짓지 않는다** — 라벨을 키로 기존 표에서 고른다(`clarificationForTarget`). 사용자에게 보이는 표현 무변경이 요구사항 ⑤ **순서 제약 1건** — 되묻기 판정이 분류 이후에만 가능해 후속 질문 분기도 분류 뒤로 내렸다. 그러지 않으면 '영업이익률을 추가해 볼까?'를 진행 순서가 가로챈다(이관 전 주석이 예고했던 충돌이 실제로 재현돼 테스트가 잡음) ⑥ **테스트 12건은 입력만 새 레인으로 옮겼다** — 검증 대상(어떤 질문·어떤 칩)은 그대로. 백엔드 회귀 24건 추가. 백엔드 3,217·프론트 1,335 전체 통과. `nl_interpretation_contract.md` § 11-20·AgentsTab 분류기 흐름 동기화. SRS FR-SA-018 | ✅ 완료(부분) |
| 전략 유지 턴의 안내 — 사실 + 상태가 답하는 다음 행동 (2026-07-31) | 사용자 요청: 요청을 반영하지 못해 전략을 유지하는 턴이 "똑같은 전략만 다시 보여주는" 것으로 끝나지 않게 안내를 붙이자. **사용자 선택: 사실 한 문장 + 상태 기반 다음 행동**(대안 지표 제시안·최소 문구안은 탈락 — 전자는 미지원→대안 매핑 표를 새로 유지해야 하고, 후자는 "그래서 뭘 하지"가 여전히 남는다). ① **안내는 사실까지만** — "'수급' 조건은 지원하지 않아 전략에 넣지 못했어요. 나머지 조건은 그대로입니다." 다음 행동은 진행 상태가 답한다(다음 조건 되묻기 / 완성이면 실행 안내). 안내에 다음 행동을 써넣지 않는 이유는 같은 말이 두 곳에서 갈라지기 때문 ② **렌더 결함 동반 수정** — 안내 카드가 요약 블록(`!clarification`) 안에만 있어 **되묻기가 뜨는 턴에서는 미반영 사유가 통째로 사라졌다**. 독립 렌더로 분리(회귀 테스트가 수정 전 실패 확인) ③ **발화 전체 인용 차단** — 인터프리터가 `unsupported_features`에 발화를 통째로 담는 오라벨이 실재한다(사용자 로그: `미지원=['어떻게 해야 할까?']`). 그대로 인용하면 "'어떻게 해야 할까?'은(는) 반영할 수 없어요"가 나간다. LLM 출력과 입력의 대조로 감지해 조건 이름 없이 사실만 말한다(원문 해석 아님) ④ **부수 확인** — 그 로그의 "어떻게 해야 할까?"는 오늘 턴 중재 변경(FR-SA-016·017) 이후 이 분기에 도달하지 않는다. 이 수정의 대상은 실제 미지원 요청(FCF·수급·뉴스)이다. 회귀 2건(백엔드 오라벨 인용 차단·프론트 안내+되묻기 공존) — 백엔드 3,218·프론트 1,336 전체 통과. SRS FR-SA-019 | ✅ 완료 |
| 유지/변경 체크박스 선택 (2026-07-31) | 사용자 요청: 인터프리터가 낸 "…유지하시겠습니까?" 5줄을 체크박스로 만들어 유지할 것만 고르게 하고, 고르지 않은 것은 다시 묻고, **진행률 박스도 언체크해 싱크**를 맞춰 달라. ① **그 5줄은 LLM 자유 텍스트였다** — 수정 레인의 `CLARIFY_STRATEGY`(패치 없음)에서 `_build_clarification`이 이어붙인 것이고 줄별 필드 결속도 LLM이 채운 값이다. 그 문자열을 파싱해 체크박스로 만들면 LLM 문장을 정규식으로 해석하는 구조(대원칙 1 위반)가 되므로, 목록을 **전략 상태에서 결정론으로 생성**(`strategyItems.ts` 신설)했다. 라벨은 요약 카드 포매터 재사용(같은 값이 두 곳에서 다르게 보이지 않게) ② **사용자 결정: 트리거는 조건 변경 메타 요청**(`clarify_target=condition`) — 기존 영역 칩 5개 자리를 대체한다. 그 로그의 "어떻게 해야 할까?"는 오늘 턴 중재 변경 이후 이 경로에 오지 않는다 ③ **사용자 결정: 체크 해제 = 값 비우기 + 순서대로 재질문** — 진행률 언체크가 같은 술어로 자동 성립한다(요청하신 싱크). 비우는 방식은 슬롯 판정을 따라 둘로 나뉜다: 값이 곧 완료인 항목은 값 삭제, 기본값 물질화 슬롯은 `explicit_fields` 삭제(값을 0/""로 만들면 백엔드 스키마와 충돌) ④ **재질문 대기열** — 진행 골격 순서·슬롯 단위 중복 제거. **물어보는 순간 소모**하며, 답하지 않아도 그 슬롯은 비어 있어 상태 기본 액션이 나중에 데려간다(질문 소실 없음) ⑤ **기본은 전부 체크** — 그대로 제출하면 전략 무변경(파괴적 방향을 기본값으로 두지 않음) ⑥ 백엔드 왕복 0회(화면의 값을 사용자가 직접 고른 것이라 재해석할 원문이 없음). 회귀 3건(목록 표시·해제 후 재질문+진행률 언체크·전부 유지) — 프론트 1,339·백엔드 3,218 전체 통과. SRS FR-SA-020 | ✅ 완료 |
| 열린 질문에 대한 답이 인사로 오분류 (2026-07-31) | 사용자 신고: 되묻기("어떻게 하지?라는 표현이 무엇을 의미하는지…")에 **"아니야"**라고 답했더니 "안녕하세요. 오늘은 어떤 전략을 연구해 볼까요?"가 나왔다 — "지난 질문에 대한 대답인 걸 이해 못한 것". 원인 2건이 겹쳤다: ① **되묻기가 분류 맥락에서 누락** — `selectClassifierHistory`가 assistant 메시지에서 `infoText ?? coachText ?? clarification` 중 **앞의 하나만** 골랐는데, FR-SA-015로 한 메시지가 안내문+되묻기를 함께 싣게 되면서 방금 던진 질문이 히스토리에서 사라졌다(내 기능 추가가 다른 기능의 입력을 조용히 없앤 상호작용). 있는 것을 모두 싣도록 수정 ② **"답을 기다리는 질문"이라는 사실 미전달** — 히스토리에 섞이는 것과 명시하는 것은 다르다. `active_strategy`·`workflow_status`와 같은 무상태 에코로 `pending_question`을 넘기고(출처=`openClarificationRef`), 프롬프트 규칙 4-1로 "그 답으로 보이는 짧은 발화는 GREETING·OFF_TOPIC이 아니다"를 명시 ③ **프론트 결정론 보정은 넣지 않았다** — "짧은 부정 답변이면 인사가 아니다"는 원문 의미 판정이라 정규식이 LLM을 재심하는 구조가 된다(대원칙 1). 재료만 주고 판정은 LLM에 맡긴다 ④ **잔여**: 부정 답변의 후속 처리는 별도 축 — 지금은 파싱 레인으로 흘러 "해석하지 못했어요"+열린 질문 유지로 끝난다(인사보다는 정직하나 최선은 아님). 긍정 확정(CONFIRM)의 대칭인 거절 축은 미도입. 회귀 4건 — 백엔드 3,221·프론트 1,340 전체 통과. AgentsTab 분류기 입력 동기화. SRS FR-SA-021 | ✅ 완료 |
| 유니버스 되묻기에서 '직접 입력' 칩 제거 (2026-07-31) | 사용자 지적: 유니버스를 물을 때는 우리가 제시한 시장 범위(코스피200·코스피·코스닥·코스피+코스닥)가 **선택지의 전부**라 '직접 입력' 칩이 없는 여지를 만든다. 빌더 칩 경로(`withBuilderNavigationSuggestions`)는 이미 유니버스 단계에서 이 칩을 떼고 있었으나, 되묻기(clarification) 렌더는 선택지에 칩이 없으면 **무조건** '직접 입력' 버튼을 덧붙여 같은 질문이 경로에 따라 다르게 보였다. 판정 근거를 슬롯으로 옮겼다 — `backtestReadiness.isClosedChoiceSlot(field)`(선택지가 닫힌 슬롯 = 유니버스)을 정본으로 두고, 되묻기 메시지에 `clarificationField`(이 되묻기가 채우는 골격 슬롯)를 함께 실어 렌더가 그 값으로 판정한다. 질문 문구는 `makeBuilderQuestionFriendly`가 치환하므로 문구 매칭은 근거가 못 된다. 칩 생산 경로 4곳(결정론 칩 답변·파스 스트림·빌더 확정·`turnMessage`의 `ask_next_condition`)과 열린 되묻기 스냅샷(`openClarificationRef`)에 필드를 배선. 되묻기 칩이 떠 있는 동안 입력창이 숨겨지는 기존 규칙(FR-SA-002c)과 합쳐져 유니버스 질문은 네 칩 중 하나만 고를 수 있다 — 빌더 경로와 동일한 동작이다. 회귀 2건 + 기존 단언 1건 갱신, 프론트 1,341·백엔드 3,221 전체 통과. SRS FR-SA-002c | ✅ 완료 |

| 되묻기 답변이 같은 질문으로 되돌아옴 — '직접 입력' 3억원 (2026-07-31) | 사용자 신고: 초기자금 되묻기에서 '직접 입력'으로 **"3억원"**을 입력했는데 같은 질문이 다시 나왔다. **원인은 문맥 부재였다** — 질문은 우리가 던졌는데, 그 답을 해석하는 쪽에는 질문이 전달되지 않는다. ① **되묻기 레인이 답을 가로챘다** — 값이 실린 답에도 분류 LLM은 `clarify_target`을 그대로 낸다(실측 4/4: '3억원'→initial_capital, '초기자금 3000만원으로 변경'→initial_capital, '손절 -8%로 바꿔줘'→stop_loss, '최대 5종목으로 변경'→max_positions). 그 축은 대상만 알고 **'값이 함께 왔는가'는 알지 못한다.** 이관 전 정규식 경로에는 `explicitPattern`(값이 있으면 통과) 게이트가 있었으나 FR-SA-018 이관에서 사라졌고, 그 불변식을 지키던 테스트는 이제 아무도 호출하지 않는 `getModificationClarification`을 검증하고 있어 초록으로 남았다(죽은 레인을 지키는 테스트). **사용자 결정: 되묻기가 열려 있으면 항상 차단**(분류는 유지 — 규제 게이트가 그 턴에도 걸려야 한다) ② **질문을 파스 레인에 에코한다** — `pending_ask`·`previous_coach_text`와 같은 무상태 계약으로 `pending_question`을 넘겨 인터프리터가 귀속을 판단한다(프론트가 원문에서 필드를 정하지 않는다). 실측 증명: 같은 답 '10%'가 손절 질문에서는 `/risk_management/stop_loss`, 익절 질문에서는 `/risk_management/take_profit`으로 갈린다(질문 없으면 손절로 고정) ③ **열린 되묻기의 기록처를 단일화** — L2' 되묻기 턴이 `openClarificationRef`에 질문을 남기지 않아 다음 턴이 답인 줄 몰랐다(`respond` 액션은 `infoText` 채널을 쓴다). `opensClarification` 표시로 조립기 계약을 유지한 채 기록만 남긴다 ④ **부수 발견 — 3억원이 3천만원으로**: 되묻기를 통과시키자 9B가 `initial_capital=30000000`(10배 축소)을 냈고 **수치 반영 대조가 그것을 통과시켰다** — 패치의 `source_text="3억원"`에서 숫자 3이 추출돼 앵커 '3억'의 후보 3과 맞았다(조건 배열에서는 이미 `source_text`를 빼고 있었는데 패치는 빠져 있었다). 인용 제외로 검사를 정직하게 만들고, 값 자체는 프롬프트 규칙 11-2(금액 단위 환산표)로 LLM 레인에서 교정 — 결정론 보정은 넣지 않았다(임의 보정 금지). 실측: 3억원·3억·5억원·1억5천만원·2억5000만원 전부 정확, 종단 확인 `initial_capital=300000000`+다른 필드 보존 ⑤ **차단 범위의 대가** — 되묻기 중 값 없는 **다른** 필드 요청('손절도 바꾸고 싶어')은 무변경 파스 후 다음 조건 질문으로 흐른다. 회귀 8건(프론트 5·백엔드 3, 종단 1건 포함) — 프론트 1,348·백엔드 3,226 전체 통과. AgentsTab 분류기 가드·수정기 입력 동기화. SRS FR-SA-022 | ✅ 완료 |

| '직접 입력' 자유 답변 QA — 86케이스 실측·교정 (2026-07-31) | 사용자 지시: 매수 조건~초기 자본의 '직접 입력'을 입력 가능한 모든 형태로 넣어 제대로 응답하는지 확인. 슬롯 8종 × 표현 43종 × 되묻기 질문 2계열(진행 골격/수정) = **86케이스** 하니스(`scripts/qa_free_input.py`) 실행. **1차 70 PASS / 16 FAIL**, 다른 슬롯 침범 0건(FR-SA-022의 질문 에코가 귀속을 담당). 실패 원인 4갈래를 전부 교정: ① **조건 객체 패치의 JSON 붕괴** — 3단 중첩(패치→조건→parameters)에서 9B가 닫는 중괄호 누락, 1회 복구에도 동일 출력(2/2) → 청산 조건 답변 전량 해석 실패. 닫는 괄호 삽입만으로 설명되는 붕괴를 형식 정규화로 복구(`_close_unbalanced_containers`). **절단은 복구하지 않는다** — 잘린 조건을 완성하면 사용자가 말하지 않은 전략이 된다 ② **인용문 자리가 둘** — `source_text`는 패치(`PatchOp`)와 조건(`StrategyCondition`) 양쪽에 있는 필드인데 환각 게이트가 패치 쪽만 읽어, 조건 안에 정확히 인용한 '데드크로스 나오면 팔아'가 근거 없음으로 거부됐다(숫자가 없어 수치 대조로도 구제 불가). 두 자리를 모두 대조 — 지어낸 인용은 여전히 거부 ③ **없는 인덱스 필드 패치** — 빈 배열에 `replace /exit_conditions/0/factor`. 같은 인덱스를 겨냥한 형제 패치를 조건 추가 하나로 승격(LLM이 이미 낸 필드만 모으고, factor 없으면 승격 안 함) ④ **버킷 밖 기간 표기** — '전체 기간'→`"all"`, '10년'→`"10y"`가 Literal 탈락으로 패치 전량 폐기. 뜻이 같은 표기는 정본 값으로 정규화하고, 버킷 아닌 연수·개월은 **가장 가까운 버킷으로 올리지 않고** 명시 날짜 창으로 변환(버킷으로 올리면 사용자가 말한 적 없는 창) ⑤ **미반영 수치 안내를 수정 레인에도 배선** — 초기 파스에만 있어 값 오차가 조용히 확정됐다('60일 신고가'→lookback 300, '최근 1년'→5y 유지). 값을 코드가 만들어 채우는 것은 금지이므로 남는 선택지는 정직하게 알리는 것 ⑥ **되묻기는 실패가 아님** — '볼린저밴드 상단'의 기준 기간, 'RSI 30 이하'의 RSI 기간을 묻는 것은 정상 동작이라 판정을 분리(PASS/FAIL/되묻기). **결과 79 PASS · 4 되묻기 · 3 실패**(남은 3건은 모델 샘플링 흔들림, 2건은 ⑤로 사용자에게 노출). 회귀 5건 추가 — 백엔드 3,232·프론트 1,347 전체 통과. AgentsTab 수정기 게이트·보정 단계 동기화. SRS FR-SA-023 | ✅ 완료 |
| LangSmith 관찰 계층 도입 (2026-07-31) | Agent 실행(Planner → Action DAG → Tool → State → Responder)을 LangSmith Trace로 추적·평가하는 **관찰 전용** 계층 신설(`backend/observability/`). **기존 Agent 동작·아키텍처 무변경이 계약** — 실행 경로·분기·되묻기 조건·폴백 판정·반환값·예외 전파 중 어느 것도 건드리지 않는다. ① **계측은 기존 단일 통로 5곳만** — 루트 `main.py::_run_nl_parse`, Tool `tools/base.py::call`(도구 전부가 지남), LLM `_default_ollama_chat`(공유 `ChatFn` 계약), Planner `plan_strategy_dag`, Interpreter `interpret`. 각각 본체를 `_*_traced`/`_plan_strategy_dag`/`_interpret`으로 분리하고 래퍼가 span만 연다(계측을 코드 전반에 흩지 않는다) ② **기본 OFF** — `LANGSMITH_TRACING`이 참이 아니면 완전한 no-op이고 langsmith를 import조차 하지 않는다(외부 전송·오버헤드 0). 켜면 사용자 원문·전략 State·LLM 프롬프트 전문이 외부로 나가므로 prod 활성화는 별도 결정 ③ **스레드 경계가 핵심 함정** — langsmith는 contextvar로 부모를 찾는데 contextvar는 스레드를 건너지 않는다. shadow planner 2종과 SSE 후행 검증이 각자 스레드라 그대로 두면 **span이 조용히 고아 Trace가 된다**. `current_parent()`를 스레드로 넘기고 `use_parent()`로 복원 — 대조군 테스트까지 회귀로 고정 ④ **없는 값은 지어내지 않는다** — `NLParseRequest`에 `user_id`가 없고 요청 스키마를 늘리는 건 실행 경로 변경이므로 `user_id=None`. 대화는 `session_id(턴 N) == strategy_id(턴 N-1)` 사슬로 잇는다. Cost는 self-hosted라 단가가 없어 미수록(토큰 수는 Ollama 응답의 `prompt_eval_count`/`eval_count`를 읽어 기록 — 종전엔 버려지던 값) ⑤ **Dataset 21개 + 결정론 evaluator 6축**(LLM judge 없음 — 채점이 비결정적이면 회귀 테스트로 못 쓴다). Dataset에 정답 전략을 두지 않는다: **되묻기는 실패가 아니라 정상 동작**이라 정답을 못 박으면 계약을 어기는 쪽이 통과한다. 같은 이유로 evaluator는 `SKIPPED`를 낭비로 세지 않고, 판정 근거가 없으면 `score=None`(집계 제외) ⑥ **테스트가 외부로 나가는 것을 확인하고 차단** — 추적을 켜는 테스트가 실제로 `api.smith.langchain.com`에 POST했다. `LANGSMITH_ENDPOINT`를 루프백으로 고정 ⑦ AgentsTab 미갱신 — 파이프라인 단계·순서·분기·되묻기·가드가 하나도 바뀌지 않았다(관찰 래퍼뿐). 신규 40건 — 백엔드 3,272 전체 통과. docs/observability.md 신설. SRS FR-OBS-001 | ✅ 완료 |

| 미지원 예시 15개 삭제 + 미지원 안내 정리 (2026-08-01) | 사용자 지적: 백테스트 입력 예시 카드가 **엔진이 표현할 수 없는 조건**을 담고 있어 안내 두 줄과 함께 반쪽 전략이 나갔다('PBR 1.3 이하 + 영업활동현금흐름 흑자 + 시장 대비 상대 수익률'). ① **예시 전수 점검** — 96개를 레지스트리 UNSUPPORTED 목록과 결정론 게이트(`_UNSUPPORTED_CONCEPT_PATTERNS`) 두 축으로 스캔하고 캐시된 실제 파싱과 대조해 **15개 삭제**(최소 보유 기간 하한 2·거래량 배수 3·현금흐름 수준 1·분할 익절 1·변동성 3·이격도 1·정배열(3중) 1·섹터 중립 2·현금 비중 2 — 중복 포함). 삭제된 제목을 참조하던 프론트 테스트 3곳 교정(첫 카드 카테고리가 가치투자→기술분석으로 바뀌어 뱃지 색 단언도 함께) ② **게이트 오탐 2건은 예시가 아니라 게이트가 문제였다** — '영업활동현금흐름 **증가율** 10% 이상'(`ocf_growth` 지원)과 '20일 EMA가 60일 EMA 위'(두 선 비교로 표현 가능)가 반영됐는데도 미지원 안내가 나갔다. `concepts_expressed_in_strategy` 신설 — **컴파일 결과가 그 개념을 실제로 표현했으면 안내에서 뺀다**(섹터·배당의 조건부 제외와 같은 계약). 판정 입력은 컴파일 결과와 입력 **수치**뿐이라 원문 어휘를 다시 읽지 않는다: 현금흐름 증가율은 임계값이 입력 수치에 있을 때만 제외해 '흑자'를 `ocf_growth>=0`으로 바꾸는 유사 대체는 안내를 유지한다 ③ **인터프리터 `unsupported_features` 인용 안내 폐지**(파싱 경로, 사용자 판단) — LLM 자유 서술 채널이라 내부 사정('unsupported_features에 기록합니다')·지원되는 필드명(`risk_management.stop_loss`·`portfolio.hold_period_days`)·발화 조각이 그대로 노출됐고, 미지원 안내는 결정론 게이트가 이미 낸다. 조용한 누락 방지는 제외 조건·미반영 수치 안내(결정론 대조)가 계속 담당하며 수정 경로 안내(FR-SA-019)는 유지 ④ **알려진 한계** — 세 선 이상 정배열의 부분 표현은 ②의 술어가 구분하지 못한다. AgentsTab 미갱신(안내 오탐 수정일 뿐 단계·분기·되묻기·가드 불변). 라이브 재검증 3건 + 회귀 4건(신규 3·기존 1 전환) — 백엔드 3,337·프론트 1,347 전체 통과. SRS FR-STR-023d | ✅ 완료 |
| 로컬 Ollama 미기동을 startup에서 알림 + 서비스 등록 (2026-08-01) | 사용자 신고: 전략 예시 카드가 **"해당 주제에 대한 일반적인 설명을 준비하지 못했습니다"**로 답했다("해석을 못 하게 됐다"). 코드 회귀가 아니라 **`ollama serve`가 죽어 있었다** — 백엔드는 Ollama를 **기동하지 않고** 이미 떠 있다고 가정해 워밍업(`_kick_local_ollama_model_preload`·`_kick_system_prompt_prefill`)만 하는데, 둘 다 실패를 "첫 호출 시 lazy 로드"로 무시하므로 **LLM 없는 백엔드가 조용히 기동**했다. 그 결과 `/query/classify`가 `intent=UNKNOWN`(0.0초 — 호출조차 못 함) → 프론트가 `answer_general`로 라우팅 → 일반답변 LLM도 미가용이라 폴백 문구. 분류·파싱·일반답변 세 레인이 같은 원인으로 동시에 죽는데 사용자에게는 파싱 회귀로 보인다. ① **서버 생사 확인을 워밍업과 분리** — `_local_ollama_reachable`(GET `/api/tags`, 3초)이 실패하면 적재·prefill을 건너뛰고 조치 안내(`brew services start ollama`)를 startup 로그에 낸다. 적재 실패(비치명적, lazy 로드로 복구)와 **서버 부재**(복구 경로 없음)는 다른 사건이다 ② **부팅 자동 기동** — postgres·redis와 달리 ollama는 brew 서비스로 등록돼 있지 않아(`brew services list`에서 `none`) 수동 기동에 의존했다. `brew services start ollama`로 LaunchAgent 등록 ③ 진단 순서를 메모리에 고정: 11434 응답 → `reason`이 0.0초에 오는지 → 그다음이 `/api/ps` num_ctx(FR-STR-019o ⑥). 회귀 2건(`test_startup_model_preload.py`) — 백엔드 3,339 전체 통과. SRS FR-STR-019o ⑦ | ✅ 완료 |
| 미반영 수치 안내 폐지 + 시총 배지 단위 표기 (2026-08-01) | 사용자 지적 2건. ① **"'1, 20일' 수치는 조건으로 반영하지 못했어요" 안내 폐지** — 대조(`recall_validator`)가 **크기만 보는 수치 비교**라 안내가 맥락 없는 숫자 나열이 되고, 정작 걸리는 것은 '월 1회 리밸런싱'(→`monthly`)·'20일 평균 거래대금'(→`trading_value>=50`)처럼 **표현형이 달라 숫자가 남지 않았을 뿐 이미 반영된** 조건이다. 사용자가 무엇을 다시 말해야 하는지 알 수 없으므로 정보값이 없다(사용자 판단). 초기 파스·수정 두 레인의 안내를 걷어내고 로그(`△ 미반영(안내 없음)`)로만 남긴다 — **재요청 증거로서의 쓰임은 그대로**다(`_recall_gap` → 인터프리터 재생성 1회는 계속 돈다. 폐지된 것은 재요청 후에도 남은 잔여를 사용자에게 알리는 마지막 자리뿐). **대가**: 진짜로 값이 조용히 틀리는 경우('60일 신고가'→lookback 300)가 사용자에게 안 보인다 — 조용한 누락 금지의 마지막 자리를 뗀 것이라 파스 정합은 `parse_fidelity_validator`·되묻기에 남는다 ② **시총 배지 단위 누락** — '시가총액 3000억 원 이상 3조 원 이하'가 요약 카드에 `시총 >= 3000 · 시총 <= 30000`으로 단위 없이 표시됐다. 원인은 **프론트가 단위를 원으로 오해**한 것: 시총 필터의 정본 단위는 **억원**인데(`indicator_registry` market_cap `"억원"`, 엔진 `data_resolver`가 `(close × shares) / 1e8`) `formatMarketCapValue`가 원 단위 가정으로 `< 1억`이면 원본을 그대로 반환해, 현실적인 모든 시총 값이 변환 없이 날것으로 나갔다(기존 테스트도 `10_000_000_000 → "100억"`으로 같은 오해를 고정하고 있었다). 억원 전용 `formatEokAmount` 분리 — 시총 필터는 이것을, 초기자금(원 단위)은 기존 `formatMarketCapValue`(→ 내부에서 위임)를 쓴다. 결과 `시총 >= 3,000억 · 시총 <= 3조` ③ AgentsTab 수정기 흐름도의 '미반영 안내' 출력 노드를 '재생성 요청(안내 없음)' 가드로 교체. 라이브 재검증(스크린샷 원문: notices 0건, market_cap 3000/30000 억원 확인) + 회귀 갱신 2건(백엔드 1·프론트 1) — 백엔드 3,339·프론트 1,347 전체 통과. SRS FR-STR-019j ⑤·FR-SA-023 ⑤·FR-STR-023d | ✅ 완료 |
| 명시적 백테스트 창이 엔진에 닿지 않던 스키마 누수 (2026-08-01) | 사용자 신고: '최근 10년'으로 답했는데 실제 실행이 **2022-01-03 ~ 2026-07-31**(약 4.6년)이었다. **파싱은 정상이었다** — `backtest_start_date=2016-08-01`·`backtest_end_date=2026-08-01`이 붙었고, 요약 카드도 '백테스트 2016~2026'으로 맞게 보였으며, `to_backtest_request`도 `startDate`/`endDate`를 실었다. 유실 지점은 마지막 한 칸: **`backend/schemas.py::BacktestRequest`에 두 필드 선언이 없어** `request.model_dump()`가 조용히 버렸고(`extra=ignore`), 엔진이 `startDate`를 못 받아 `period="5Y"` 폴백 창으로 실행했다(`backtest_engine`: `Timestamp(year=ref_date.year - 4, month=1, day=1)` = 2022-01-01 → 첫 거래일 **01-03**, 신고된 날짜와 정확히 일치). `ranking_metric` 0거래 사고와 **동일한 함정**이며, 같은 파일의 주석이 `backtest_mode`·`sector`·`etf_theme`·`listing_from/to`에 대해 세 번 경고해 둔 것이다 — 스키마는 전송 계약이므로 엔진이 읽는 필드는 전부 선언돼 있어야 한다. `/backtest`·`/strategy/backtest-stream` 두 엔드포인트가 같은 모델을 쓰므로 한 곳 수정으로 둘 다 닫힌다. 라이브 재검증: 같은 요청이 수정 전 2022-01-03 시작 → 수정 후 **2016-08-01 ~ 2026-07-31**(2,452봉, 616거래). 회귀 2건(`test_backtest_request_schema.py` — 창 보존·미지정 시 None) — 백엔드 3,341 전체 통과. SRS 데이터 사전 `backtest_start_date`/`backtest_end_date` 항목 | ✅ 완료 |
| 설정 패널 기간 ↔ 엔진 창 표현 정리 (2026-08-01) | 위 스키마 누수를 고치고 나서 드러난 후속 불일치 — **설정 패널의 기간 어휘와 엔진 요청의 기간 어휘가 서로 달라 양방향으로 어긋났다.** ① **표시** — 패널 버튼 id는 대문자(`"5Y"`)인데 요청의 period는 소문자(`"5y"`)라 `period === p.id`가 어긋나 **어느 버튼도 선택되지 않았고**, 명시 창(2016~2026)으로 파싱된 전략은 그 창이 화면 어디에도 없었다(패널은 `period === "custom"`일 때만 날짜 입력을 연다) ② **권위** — 패널에서 기간을 바꿔도 요청에 남아 있던 이전 명시 창이 그대로 실려 나갔다. 엔진은 `startDate`를 상대 기간보다 우선하므로 **사용자가 방금 고른 기간이 조용히 무시된다**(위 스키마 수정 전에는 날짜가 애초에 안 갔으므로 드러나지 않던 결함이다). 정리: 규칙을 하나로 세웠다 — **화면에 보이는 기간이 곧 실행되는 창이다**. 순수 함수 2개로 분리(`app/analytics/new/backtestOptions.ts`): `backtestConfigOptions`(요청 → 패널 초기값. 명시 창이 있으면 '직접 입력'으로 열어 그 창을 보여주고, 없으면 period를 패널 id 표기로 맞춘다)와 `applyRunWindow`(패널 선택 → 요청. '직접 입력'이면 고른 창을 싣고, **상대 기간이면 이전 명시 창을 떼어낸다**). 설정을 만드는 자리 2곳(파스 확정·빌더 확정)과 실행 자리 1곳에 배선. ③ **패널이 표현 못 하던 정본 버킷 보강** — 파싱 정본은 `1y/3y/5y/full` 넷인데 패널에는 3년·전체 버튼이 없어 그 기간의 전략은 열어도 선택된 것이 없었다. 두 버튼 추가('전체'는 창을 계산하지 않는다 — 데이터 전 구간이라 창이 없다) ④ 프론트 `StrategyBacktestRequest` 타입에 `startDate`/`endDate` 선언 — 타입에 없으면 요청을 다루는 코드가 창의 존재를 모른 채 지나간다(기존 `tsc` 에러 3건도 이 누락이 원인이었다: 11건 → 6건). 신규 8건(`backtestOptions.test.ts`) — 프론트 1,355·백엔드 3,341 전체 통과 | ✅ 완료 |
| 전략 요약 배지에 창의 길이 표기 (2026-08-02) | 사용자 지적: '최근 10년간'이라고 답했는데 요약 카드가 `백테스트 2016~2026`으로만 보여 **말한 기간이 반영됐는지 알 수 없다**. 원인은 표현 계층의 정보 손실 — 버킷 밖 기간(`10년`)은 `BacktestSpec._relative_period_to_dates`가 명시 날짜 창으로 변환해 저장하고(`backtest_period` Literal은 `1y/3y/5y/full` 넷뿐이라 `10y`를 담을 수 없다), 배지는 그 창만 표기했다. 수정: `explicitWindowSpanLabel(from, to)` 신설 — 창의 길이가 **딱 떨어지면**(시작·종료의 일(日)이 같아 개월 수가 정수) 그 길이를 앞세운다(`백테스트 10년 (2016~2026)` / 목록형은 `10년 (2016-08-01 ~ 2026-08-01)`). ① **길이 계산은 날짜 산술이지 해석이 아니다** — 원문을 다시 읽지 않고 저장된 두 날짜만 본다 ② **딱 떨어지지 않는 창은 뭉개지 않는다** — 직접 지정한 연도 범위("2002년부터 2005년까지" → 2002-01-01~2005-12-31)는 정수 개월이 아니라 null을 돌려 기존 창 표기를 그대로 쓴다(길이로 바꾸면 사용자가 지정한 경계가 사라진다). 종료일 없는 창(신규 상장 코호트)도 그대로다 ③ 배지 두 곳(요약 카드 `page.tsx::backtestPeriodLabel`, 목록·진행률 `lib/strategy-summary.ts::formatBacktestPeriodLabel`)이 같은 술어를 공유한다 ④ **요약 카드에서 자기 행으로 분리**(사용자 지시) — 백테스트 기간이 '포트폴리오' 행의 칩 하나로 묻혀 있었다. 포트폴리오 구성(종목 수·보유·리밸런싱·초기자금)이 아니라 **실행 조건**이므로, 진행 상황 표시(`백테스트 기간  3년`)와 같은 라벨로 독립 행을 만든다. 라벨이 6자로 길어져 행 라벨 열을 `w-14`(56px) → `w-20`(80px)로 넓히고 `whitespace-nowrap`을 달았다(전 행 공통 — 정렬 유지). 값에서는 중복되는 '백테스트' 접두를 뺀다(행이 라벨을 달고 있다). ⑤ **초기 자본도 같은 이유로 분리**(재지적) — ④에서 **지목된 항목만 옮기고 같은 성격의 초기 자본을 포트폴리오 행에 남겨** 같은 지적이 반복됐다. 판정 기준은 '포트폴리오 구성인가'다: 종목 수·보유 기간·리밸런싱은 구성이고, 백테스트 기간·초기 자본은 **실행 조건**이라 각자 행을 갖는다(라벨은 진행 골격의 `SLOT_LABELS`와 동일 — '백테스트 기간'·'초기 자본'). 남은 칩 전수 확인: 포트폴리오 3칩·리스크 3칩 모두 해당 그룹이 맞다. ⑥ **청산 신호와 리스크의 값 중복 제거** — 손절·익절·트레일링·보유 기간이 '청산 신호'와 '리스크'(·'포트폴리오')에 **같은 값으로 두 번** 실려 있었다. 리스크·포트폴리오를 따로 보여주는 화면에서는 청산 신호에 지표 신호만 싣는다(`getSignalExitLabels` 신설). 진입/청산 두 칸뿐인 **결과 화면 배지는 위험 청산까지 실어야 하므로** `getDisplayExitLabels` 계약은 그대로 두고, 두 화면이 각자 필터링해 다시 갈리지 않도록 술어를 하나로 공유한다 — 전략 요약 카드와 진행 상황 카드(`매도 조건`/`리스크 관리`) **양쪽 모두** 같은 중복을 갖고 있었다(한쪽만 고치면 같은 지적이 또 반복된다). 지표 청산이 없는 전략은 해당 행 자체가 생략되며 값은 리스크 행에 남는다. 신규 4건 — 프론트 1,361 전체 통과. 신규 2건 — 프론트 1,357 전체 통과 | ✅ 완료 |
| 수정 턴 provenance 판정 근거 교정 (2026-08-02) | 사용자 신고: 초기자금을 10억으로 입력했는데 요약에 반영되지 않는다. 원인은 **provenance 드리프트** — 백테스트 기간만 답한 턴에서 `initial_capital`이 '사용자 명시'로 올라가(실측 2/2) **초기 자금을 아예 묻지 않게 되고** 기본값 1천만원이 조용히 확정됐다. 그 상태에서 사용자가 스스로 `10억`만 입력하면 결속할 질문이 없어 그 발화가 아무 표시 없이 버려진다(`초기자금 10억`처럼 필드를 붙이면 정상 — 실측). **메커니즘**: `explicit_fields_from_spec`는 spec에 값이 있으면 사용자가 말한 것으로 판정하는데, 수정 턴의 spec은 LLM이 발화에서 뽑은 것이 아니라 **이전 전략을 디컴파일한 초안 + 패치**다. 디컴파일러가 물질화 기본값(`initial_capital=10,000,000`)을 채워 넣으므로 값의 존재가 근거가 될 수 없다(provenance 모듈 docstring이 이미 경고하던 "왕복이 provenance를 지운다"의 정확한 발현). 수정: 수정 턴의 근거를 **환각 게이트를 통과한 패치**로 옮긴다(`explicit_fields_from_patches` — 경로 표기만 보는 정규화, 원문 무관여). 최초 파스는 그대로 spec에서 판정한다(그 spec은 발화에서 뽑은 것이라 근거가 맞다). 이전 턴 에코와의 합집합 누적은 불변. **되묻기는 추가하지 않는다**(사용자 판단: 질문이 정상적으로 나가면 '직접 입력' 값은 그 질문에 결속되므로 되물을 이유가 없다). 라이브 검증: 기간만 답한 턴에서 `initial_capital` 미표시(수정 전 표시), 실제 변경 4종(초기자금·종목 수·리밸런싱·유니버스)은 그대로 표시. AgentsTab 미갱신(되묻기 게이트의 **입력**을 고친 것으로 단계·순서·분기·가드는 불변). 신규 3건 — 백엔드 3,344·프론트 1,357 전체 통과. SRS FR-STR-019k ⑥ | ✅ 완료 |
| 초기 자금 상한 100억원 (2026-08-02) | 사용자 신고: 초기 자금 **100조**로 실행한 백테스트가 "유동성 기준 미달(거래대금 부족)"로 대부분의 종목을 매매하지 못했다. 버그가 아니라 **입력이 시장 유동성을 초과**한 것 — 엔진은 1회 매수 금액(초기 자금 ÷ 최대 보유 종목 수)이 **전일 거래대금의 10%**(`liquidity_limit_pct`)를 넘으면 그 종목의 진입 신호를 통째로 지운다(`engine/loader.py::check_liquidity` — 시장에 없는 물량을 체결한 것처럼 만들지 않는 안전장치). 신고 사례(10조·최대 12종목)는 1회 매수 8,333억 → 통과에 필요한 전일 거래대금 **8.3조/일**이라 통과 가능한 국내 종목이 사실상 없다. 수정: 초기 자금에 상한 **100억원**(`MAX_INITIAL_CAPITAL`)을 건다. ① **보정하지 않고 값을 버린다**(하한 100만원은 종전대로 클램프) — 100억으로 깎아 주면 사용자가 말한 적 없는 금액을 시스템이 확정하는 것이다(`enforce_initial_capital_bounds`, 모든 파싱 경로 공통 진입점) ② **provenance도 함께 떼어낸다**(`main._drop_rejected_provenance`) — 값만 버리고 `explicit_fields`의 `initial_capital`을 남기면, 되돌아온 기본값 1천만원이 '사용자 확정'으로 판정돼 **설정하지 못했다는 안내를 읽고도 말한 적 없는 금액으로 백테스트가 실행된다**. 떼어내면 기존 되묻기 게이트가 "초기 투자 자금을 얼마로 설정할까요?"를 칩과 함께 다시 낸다(FR-STR-019k 계약 재사용 — 새 되묻기 경로를 만들지 않는다). 파생 상태(`field_states`)도 무효화해 재계산 ③ **설정 패널의 직접 입력도 같은 상한**(`BacktestConfig` — 대화 레인만 막으면 패널이 그대로 우회로가 된다): 초과 시 실행 버튼을 막고 "최대 100억원까지 설정할 수 있습니다. 금액을 다시 선택해 주세요" 안내. 상한값 자체(100억)는 허용한다 ④ 설정 기본값 질의 답변(`platform_defaults`)에 상한 문구 추가, AgentsTab 해석기 흐름도에 '설정값 범위 게이트' 가드 노드 추가. 신규 7건(백엔드 5·프론트 2) — 백엔드 3,349·프론트 1,363 전체 통과. SRS FR-STR-023e ⑥ | ✅ 완료 |
| 인용이 값의 자릿수 오류를 덮던 환각 게이트 구멍 (2026-08-02) | 위 상한 기능 검증 중 사용자 발견: **1000억원**을 요청했는데 요약에 **100억원**이 들어가고 상한 안내도 뜨지 않았다. 상한 게이트는 정상이었다 — 값이 애초에 1000억으로 도착하지 않았다. 9B 인터프리터가 `value=10000000000`(1e10, **10배 오차**)과 `source_text="1000억원"`을 함께 냈고, 그 값이 공교롭게 상한(100억)과 정확히 같아 게이트가 통과시켰다. **세 겹의 방어가 모두 비켜갔다**: ① 수치 반영 대조(`recall_validator`)는 **정확히 잡아냈고**(`⟳ 수치 누락 재요청 미반영: 1000억`) 재요청까지 돌렸지만 9B가 같은 값을 되풀이했고, 잔존 미반영은 **로그로만 남기고 그대로 확정**된다(안내 폐지 2026-08-01의 설계 — 값 확정을 막는 장치는 아니었다) ② 환각 게이트는 인용(`source_text`)이 입력에 실재하면 **수치 대조 전에 통과**시킨다 — 인용은 원문 조각이라 언제나 실재하므로 값이 틀려도 통과 ③ 상한 게이트는 1e10을 정상값으로 본다. 수정: **인용이 수치 대조를 대신 통과시키지 않게 한다**(`_quote_contradicts_value`) — 인용문에 숫자가 있고 패치 값과 **10의 거듭제곱 배수**만큼 어긋나면 그 인용은 근거가 아니라 오류의 증거다. 입력을 해석하지 않고 **LLM 출력 두 조각(인용↔값)만 대조**한다(대원칙 1 준수). `recall_validator._reflected_numbers`가 같은 이유로 인용을 제외하며 같은 유형의 사고("3억원"→3천만원)를 이미 기록해 두었는데, 그 교훈이 환각 게이트에는 적용돼 있지 않았다 — `_patch_value_numbers`도 값 안의 `source_text`를 제외하도록 함께 고쳤다(인용이 값 안에 오면 자기 자신과 대조돼 검사가 침묵). **10의 거듭제곱으로 좁힌 이유**: 단위 환산에는 관례 차이가 있다 — "최근 3개월"을 9B는 `lookback_days=90`(달력일), 환산표는 63(거래일)로 잡으며 둘 다 옳다(전면 대조로 만들었을 때 실제로 이 회귀가 났다: `test_complete_patch_survives_other_slot_completeness_question`). 결과: 자릿수가 어긋난 패치는 거부돼 전략 무변경 + 미해석 안내, 초기 자금은 explicit이 붙지 않아 되묻기 게이트가 다시 묻는다 — **틀린 값으로 확정하느니 다시 묻는다.** 라이브 재검증: "1000억원"→거부(1천만원 유지), "50억원"→정상 적용(5e9). 신규 3건 — 백엔드 3,352 전체 통과. SRS FR-STR-019f ③ | ✅ 완료 |
| 백테스트 창 = 보유 데이터 구간 강제 (2026-08-02) | 사용자 질문에서 출발한 점검: 입력한 기간이 실제로 테스트 가능한 구간인지 검사하는가. **과거 방향은 안내만 있고 미래 방향은 검사가 아예 없었다.** ① `2030~2035` (전 구간 미래)·`1980~1990`(전 구간 데이터 이전)은 그대로 통과해 사용자가 전략을 완성하고 실행 버튼을 누른 **뒤에야** 엔진의 "분석 가능한 유효한 데이터가 없습니다" 예외로 알게 됐다 ② `2024~2035`(부분 미래)가 가장 나빴다 — 엔진(`ref_date = to_datetime(end_date_req)`, 오늘로 클램프하지 않음)은 오늘까지만 돌리는데 요약 카드·결과 배지는 **2035년까지 돌린 것처럼 표시**되는 조용한 절단이다(FR-STR-023d '화면에 보이는 기간이 곧 실행되는 창이다' 위반) ③ 설정 패널의 `<input type="date">`에 `min`/`max`가 없어 직접 입력으로도 미래 날짜가 들어갔다. 수정(`enforce_backtest_window_bounds`, 사용자 결정): (a) 시작일만 데이터 이전 → **종전 유지**(날짜 보존 + 커버리지 안내) (b) 종료일 미래 → 오늘로 **절단 + 안내**('2035년까지'의 의도는 "가능한 데이터까지") (c) 창 전체가 데이터 밖 → **창 폐기 + 기간 되묻기**(초기 자금 상한과 같은 계약 — `reask_fields`로 explicit provenance까지 떼어내 게이트가 재질문). 데이터 구간 정본은 상수 유지 + 상한 추가(`DATA_FLOOR_DATE=1996-01-01` ~ `data_ceiling_date()`=오늘) — 파케이를 읽지 않아 파싱 경로에 파일 I/O가 없고, 실측 범위(1996-01-03~2026-07-31)와도 맞으며, 오늘과 마지막 거래일의 차이는 엔진이 흡수한다. 패널에도 같은 경계를 걸어 실행 차단. 회귀 발견: `_DummyParsed` 스텁에 `backtest_end_date`가 없어 파스 캐시 테스트 2건이 깨졌다(스텁이 실제 타입을 따라가지 못한 것 — 스텁 보강). 신규 8건(백엔드 4·프론트 4) — 백엔드 3,356·프론트 1,367 전체 통과. SRS FR-STR-023e ④ | ✅ 완료 |
| 백테스트 종료일 당일 봉 누락 수정 — 엔진 v9.0 (2026-08-02) | 파케이 `date` 컬럼 타입이 파일마다 갈리는 것(us 5,066 · ns 1 · String 1)을 조사하다 발견한 **별건이자 더 큰 버그**. 창 필터가 타임스탬프를 통째로 문자열화해 비교한다: `date_col = pl.col("date").cast(pl.Utf8)` → `date_col <= "2024-12-30"`. 그런데 `"2024-12-30 00:00:00.000000" <= "2024-12-30"`은 **거짓**이다(접두가 같고 더 긴 쪽이 크다) → **명시 종료일 당일 봉이 매번 통째로 빠졌다.** 삼성전자 실데이터 재현: `endDate=2024-12-30` 요청 시 마지막 봉이 **2024-12-27**(12-30 봉은 파일에 존재). 시작 경계는 같은 규칙이 우연히 맞는 방향이라(`>=`는 더 긴 쪽이 커서 통과) **끝에서만** 하루가 사라지는 비대칭이었고, ① 기본 경로는 종료일=오늘이라 오늘 봉이 아직 없어 티가 안 나고 ② 종료일이 휴장일이면(2024-12-31 연말 폐장) 증상이 가려져 오래 남았다. 수정: 날짜 부분(YYYY-MM-DD)만으로 비교하는 `_date_key()` 공유 술어 — 창 필터와 워밍업 사전 절단 두 자리가 같은 술어를 쓴다. **날짜 캐스팅이 아니라 문자열 절단**을 택한 이유는 `date` 컬럼 타입이 파일마다 갈려 Date 캐스팅이 타입을 가리기 때문이다(us/ns/String 세 타입 모두 회귀로 고정). 회귀 2건: `_date_key` 양끝 포함(3타입)과 엔드투엔드(요청 종료일 봉이 실행 창에 포함) — **수정 전 실패 확인 완료**(`['2024-01-02','2024-01-03']`로 01-04가 빠짐). **결과값이 바뀌는 변경이므로 `ENGINE_VERSION` 8.0 → 9.0(MAJOR)**: 기간을 명시한 모든 백테스트가 마지막 거래일 하나를 더 포함하게 돼 수익률·MDD·거래 건수가 달라질 수 있다. 백엔드 3,358 전체 통과. `tests/test_backtest_engine.py`의 상장폐지 관련 2건은 **clean HEAD에서도 동일하게 실패**(stash 대조 확인)해 이번 변경과 무관한 기존 실패다. SRS FR-BT-010e | ✅ 완료 |
| 로컬 Agent Trace — LangSmith 동급 로컬 로그 (2026-08-02) | 전략 agent가 요청 하나를 어떻게 처리했는지 LangSmith 없이 로컬에서 보게 하는 관찰 기록처 추가(FR-OBS-002). 기존 LangSmith 관찰 계층(FR-OBS-001)의 span 파사드가 chokepoint 5곳에서 이미 수집하던 것(계층·입출력·메타데이터·소요 시간·오류·성능 지표·토큰)을 **파사드 뒤에서만** 분기해 `observability/local_trace.py`가 ① 콘솔 `[AGENT-TRACE]` span 트리(값은 raw JSON 한 줄이 아닌 `key = value` 컬럼 — `_flatten_json_columns` 선례)와 ② `backend/logs/agent_traces/YYYY-MM-DD.jsonl`(Trace 하나=한 줄, 트리 구조 보존)로 남긴다 — 실행 계층·chokepoint 호출부 무변경. 외부 전송이 없으므로 **기본 켜짐**(opt-out `AGENT_TRACE_LOCAL=0`, 저장 위치 `AGENT_TRACE_DIR`), LangSmith는 종전대로 기본 꺼짐 — 두 sink 독립, 둘 다 꺼져야 span no-op. 스레드 경계는 `current_parent()/use_parent()`가 로컬 부모 노드도 함께 실어 나르고, SSE 후행 검증처럼 **루트 방출 뒤** 도착하는 span은 같은 trace_id의 별도 레코드(`late_attach`)로 남긴다(방출된 트리 소급 수정 금지). 테스트 스위트는 conftest가 기본 꺼짐(span마다 콘솔·파일 소음 방지). AgentsTab 미갱신(관찰 전용 — 파이프라인 구조 불변). 신규 10건(`test_local_trace.py`) — 백엔드 3,385 전체 통과. SRS FR-OBS-002, docs/observability.md § 2b | ✅ 완료 |
| Agent Architecture Audit — 원문 정규식 가로채기 제거 + 유니버스 확인 소멸 안내 (2026-08-02) | Claude Code 감사(Planner→Action DAG→State→Tool→Context→Response, 로컬 Ollama 실제 대화 실행+`backend/logs/agent_traces` 트레이스 근거)에서 발견한 두 결함 수정. ① **[대원칙 1 위반]** `intent/condition_builder.py::clarification_for_add`를 `main.py`가 수정 턴마다 `request.prompt`(사용자 원문)에 직접 호출해 정규식 cue(`추가|넣|더해|...`)+`detect_metric`이 매칭되면 인터프리터를 **한 번도 호출하지 않고**(LLM 0회, 7ms) 되묻기를 확정했다 — "ESS 종목 중에서 거래대금 상위만 넣어줘"가 "ESS"(테마 전환)·"상위만"(랭킹)을 통째로 무시하고 "거래대금 몇억 이상?"만 반환. 이 호출을 제거했다 — 값 없는 조건 추가는 `validate_intent`→`validate_completeness`가 인터프리터의 구조화 출력을 보고 이미 동일한 모양의 되묻기를 낸다(중복 로직 제거, 새 판정 추가 아님). `full_rewrite_clarification`(전면 재작성 요청 감지, QA 19-4)은 같은 유형이나 라이브 재현 증거가 없고 제거 시 그 회귀가 되살아날 위험이 있어 이번 범위에서 **의도적으로 보존**(후속 과제로 남김 — 인터프리터 프롬프트에 동등한 처리를 추가한 뒤에만 제거). ② **[INVALIDATED가 실행에 배선되지 않음]** `planner/dag.py`의 `NodeStatus.INVALIDATED`(§ 12.2 설계 의도)는 `_trace_final_statuses`를 통해 trace 관측에만 쓰이고 사용자 응답에는 닿지 않았다 — 유니버스 범위 확인 질문("ESS로 바꿀까요?")이 대기 중일 때 다음 턴이 무관한 화제로 넘어가면 그 확인이 재질문·안내 없이 소멸했다(sector는 이전 값에 고정). `main._flag_unresolved_universe_ask`(모든 반환 지점이 지나는 `_finalize_parse_result` 마지막 단계)가 최소 보정 — 직전·이번 턴의 `pending_ask.topic`(유니버스 여부)과 유니버스 관련 필드 동일성만 비교해(원문 재해석 없음) notices로 알린다. 슬롯 완결성 재질문(매도조건이 매 턴 반복되는 것 등)은 대상이 아니다(서로 다른 진행 골격 슬롯이 독립적으로 비어 있는 정상 동작). **감사에서 기각한 항목**: 완결성 검증의 다중 질문 병합(`_build_clarification`, "RSI 임계값?"+"리밸런싱 주기?"가 한 문자열에 병합되고 칩은 한 슬롯분만 나오는 것)은 `test_only_one_slot_supplies_chips_per_turn`이 이미 의도적으로 검증하는 별개 계약이라 결함이 아님(dag.py의 "질문 병합 금지"는 DAG planner `ask` 노드 전용 계약). 지연시간(턴당 5~30초, Planner 최대 2회+Interpreter 1회 LLM 순차 호출)은 Planner가 도구 관찰을 봐야 다음 노드를 결정하고 Interpreter 출력이 있어야 Planner가 다음 질문을 판단하므로 **순서 자체가 정합성 요구사항** — 병합은 Planner/Interpreter 관심사 분리(각자 시스템 프롬프트가 명시)를 깨므로 보류, `think:false`·`num_ctx`·GPU 상주는 이미 정상이라 안전한 코드 레벨 단축 경로를 찾지 못했다(Ollama `OLLAMA_NUM_PARALLEL` 등 서버 설정 튜닝은 자원 트레이드오프가 있어 별도 결정 필요 — 코드 변경 아님). 신규 4건(`test_modify_roundtrip_migration.py`) — 백엔드 3,389 전체 통과. SRS FR-STR-019r | ✅ 완료 |
| Agent Architecture Audit #3 — 결함 8건 일괄 수정 (2026-08-02) | 멀티턴 에코 하니스(프론트 무상태 계약 재현, 9시나리오 25턴+분류 7건 실측, `backend/logs/agent_traces` 트레이스 근거) 감사가 찾은 결함 전량 수정. 공통 주제: **LLM은 옳았는데 하류가 결과를 버리고 원인을 위장했다**. ① **[Critical] 유니버스 전환 불능+오보고** — 코스피+PER→ETF 수정에서 인터프리터 패치는 정확했으나 capability 오류가 레인 전체 폴백→"해석하지 못했어요". llm_first에서는 전략 무변경+검증기 오류 문장을 그대로 되묻기로 전달(`_capability_conflict_clarification`, 새 판정 없음). 해소 칩("PER 조건을 빼고 ETF로 바꿔줘")은 검증기 unsupported 표기+패치된 State에서 결정론 조립하되 **pending_ask 없이** 내보낸다 — 결속 프로브가 복합 의미("제거+전환")의 추출 가능한 절반만 결속시켜 칩 클릭이 결정론 레인에서 부분 적용(ETF만, PER 잔존)되는 실측 사고를 라이브 검증에서 잡았다. 복합 의미 칩의 실행자는 LLM뿐 ② **[Critical] "초기 자금 5천만원" 미반영** — 환각 게이트 `_NUMBER_RE`가 "5천만"을 "5천"(5,000)으로 절단해 정당한 5e7 패치를 자릿수 모순으로 거부. 환산표에 천만·백만·십만 추가(표기 변환 — 자릿수 오류 검출력 유지 회귀 고정) ③ **[High] PAUSE/RESTART 소실** — "잠깐 멈춰"→LIVE_TRADING, "처음부터 다시 만들자"→STRATEGY_PICK 오분류로 규제 게이트의 제어 거부가 제어를 삼키고 동문서답 안내. 분류 프롬프트 규칙 4-2 추가 — 실측 15/15+게이트 대조군 4/4 ④ **[High] planner 턴 예산이 관찰 폐기** — 예산 2가 CONCEPT 흐름(LLM 3턴 필요)을 항상 소진, 관찰된 카탈로그 테마 60곳 대신 폴백 레인이 시드 앵커 2곳 적용. 진전 시 +2턴 연장(예산이 막는 것은 무진전 반복이지 생산적 도구 사슬이 아니다)+**후보 1개면 정본 표기 테마 조회는 결정론 에필로그**(ground_term 선례, 후보 2개 이상은 종전대로 범위 ask) — 실측 'ESS' 60곳 적용 확인 ⑤ **[Medium] Artifact 레인 사망** — `evaluate_artifacts`·`_ensure_field_metadata`가 getattr로 읽는데 라이브는 model_dump dict를 넘겨 FR-SA-011이 25턴 전부 null(인스턴스만 주입하는 테스트는 초록). dict 수용+라이브 모양 회귀 ⑥ **[Medium]** 비-SSE `/strategy/parse` 응답 모델에 `field_states` 추가(response_model이 잘라내 에코 계약 성립 불가) ⑦ **[Low] 미반영 턴 질문 소실** — notices-only 응답(설명·미지원·전량 거부)이 열려 있던 되묻기를 지움(FR-SA-015의 파스 레인판). `_reattach_open_question`이 에코된 pending_ask를 되붙임 ⑧ **[Low] 오타 골든크러스→1/20** — worked example(예시 3-0)로 정본 5/20 고정(FR-STR-019p: 형태·예시가 규칙보다 강하다), 실측 3/3. 라이브 재검증: B1(ETF 전환 3단 왕복)·C1(5천만원+열린 질문 유지)·D1(ESS 60곳+artifacts 기록)·W 배터리 전부 통과. 회귀: `test_agent_audit3_fixes.py` 10건+`test_dag_planner.py` 4건 — 백엔드 3,400 전체 통과. `nl_interpretation_contract.md` § 11-22·`planner_dag_contract.md` 안전 계약·AgentsTab(수정기 분기·플래너 예산) 동기화. SRS FR-STR-019s | ✅ 완료 |
| 뉴스 LLM 시작 프리로드 제거 (2026-08-03) | 뉴스 서비스(구 `news/` 파이프라인) 미사용 결정에 따라 서버 기동 시 `main.py`가 백그라운드 스레드로 Qwen3.5-4B GGUF를 llama-cpp로 미리 적재하던 `_start_news_llm_preload_thread` 제거 — 기동 로그의 `llama_context: n_ctx_seq (1024) < n_ctx_train (262144)` 메시지 출처였다. `news/llm_extractor.py` 모듈 자체는 보존(코치 보존 선례 — lazy-load라 뉴스 API를 호출하지 않는 한 적재되지 않음), news_v2는 별개 시스템으로 무변경. 백엔드 3,403 전체 통과 | ✅ 완료 |
| 의도 분류 bare enum JSON 파손 수리 + 4B preload 복원 (2026-08-03) | 사용자 신고: "면역항암제 관련주 투자 전략"이 전략 대신 **정의 설명**으로 답변. 근본 원인은 오분류가 아니라 **형식 결함** — 분류 LLM(4B 슬롯, `NL_OLLAMA_MODEL`)이 `"workflow_effect": NONE`처럼 enum 값을 **따옴표 없이** 간헐 출력 → `json.loads` 실패 → `intent/interpreter.py::extract_json_object` None → UNKNOWN → 프론트 `conversationDecision`이 "UNKNOWN+전략 없음"을 `/query/general`(어휘집 정의 주입 일반답변)로 라우팅. LLM의 의도 판정 자체는 매번 STRATEGY_ADVICE로 정확했다(재현 실측 실패 6/20). 수정: `extract_json_object`에 2차 파스 — 값 자리의 **대문자 bare 토큰만** 따옴표로 감싸 재시도(`_BARE_ENUM_VALUE`, 입력이 LLM 출력이므로 형식 정규화 레인 소관·대원칙 1 합치). **전수 조사**: KG 테마 카탈로그 449개 전 테마 "X 관련주 투자 전략" 분류 — 444 STRATEGY_ADVICE·해석 실패 0(수정 후), **152개(34%)가 수리 필요**로 이 결함은 전 테마의 1/3에 걸린 구조적 문제였음. 잔여 관찰 2건(미수정): ① 해외기업명 테마 5건(애플·두나무·화이자·모더나·쿠팡)이 STOCK_PICK으로 분류 ② UNKNOWN이 프론트에서 일반 정의 답변으로 위장되는 라우팅. **후속(같은 날)**: 분류 레인이 여전히 4B를 쓰는데 preload가 없어(07-27 미적재 결정) 5분 유휴 뒤 첫 분류가 ~5.5초 콜드 로드를 떠안음 — `_local_preload_models`가 인터프리터 슬롯(9B) 뒤에 파서 슬롯(4B)도 적재(사용자 결정, 07-27 결정 대체. system 프롬프트 prefill은 인터프리터 슬롯에만). 실측: 두 모델 상주(9B 6.1GB+4B 3.2GB, num_ctx=16384 공존), 웜 분류 1.2~1.4초. 회귀: `test_intent_interpreter.py` 2건+`test_startup_model_preload.py` 개정 3건 — 백엔드 3,406 전체 통과 | ✅ 완료 |
| LLM 전 슬롯 9B 단일화 — 4B 폐기 (2026-08-03) | 비용 검토("9B만 쓰면 prod 비용 절감?")에서 시작 — **비용은 근거가 아님을 먼저 확인**: prod LLM은 Modal L4 컨테이너 1개가 두 모델을 같이 서빙하고 청구는 컨테이너 warm GPU-초 기준이라 모델 수를 줄여도 절감이 거의 없다(레버는 scaledown_window·호출 횟수·GPU 티어). 대신 **품질 실측이 단일화를 정당화**: 9B 분류는 bare enum 0/20(4B 34%)+해외기업명 테마 5건(애플·두나무·화이자·모더나·쿠팡) 전부 STRATEGY_ADVICE 정분류(4B는 STOCK_PICK 오분류), 웜 지연 +0.3초뿐. 변경: ① `.env`/`.env.production.example` `NL_OLLAMA_MODEL`→9B ② `modal_ollama.py` `MODELS`에서 4B 제거 ③ `llm_backend.py` `OLLAMA_MODEL_4B` 상수 삭제+주석 "9B 하나뿐"으로 개정, `nl_parser`·`build_modify_corpus` 기본값 9B(잘못된 기본값=조용한 오검증 사고 방지, FR-STR-019p ⑤) ④ 같은 날 넣었던 4B 동반 preload 원복(슬롯이 전부 9B라 사어 — `_local_preload_models` 단일 슬롯) ⑤ bare enum 형식 수리는 안전망으로 존치. 라이브 검증: 4B 언로드 후 분류가 4B를 재적재하지 않음(9B 단독 서빙 증명), 웜 분류 1.55~1.58초. prod 반영 순서(deployment.md): 앱 env 교체(9B는 이미 서빙 중이라 즉시 동작) → `modal deploy` → `remove_model`로 볼륨의 4B 정리. MLX 슬롯(`NL_MLX_MODEL`, opt-in dev 전용)은 이번 결정 범위 밖으로 불변. 백엔드 3,405 전체 통과 | ✅ 완료 |
| 해석 실패 UNKNOWN의 정의 답변 위장 제거 (2026-08-03) | bare enum 사고의 구조 잔여분 수정 — 분류가 **해석 실패**(LLM 미가용·구조화 출력 파손)로 UNKNOWN을 반환하면 프론트 `conversationDecision`이 "UNKNOWN+전략 없음"을 `/query/general`로 보내 실패가 무관한 정의 설명으로 위장됐다(계약 § 8-1 "폴백은 실패 보고" 위반 상태). 수정: ① `IntentResult.interpretation_failed` 플래그 신설 — classify의 두 실패 경로(LLM 미가용·구조화 출력 해석 실패)만 True, **LLM이 스스로 판단한 UNKNOWN 라벨과 구분**(그쪽은 종전대로 일반 답변 경로 유지) ② 프론트는 실패+전략 없음일 때 정직한 실패 안내("해석하지 못했어요, 다시 시도/다르게 표현")로 응답하고 열린 되묻기를 유지(`preservesOpenQuestion`) ③ 실패+전략 있음은 종전대로 파스 레인(9B 인터프리터가 자체 해석) — 동작 불변. AgentsTab 분류기 흐름(형식 수리 항목+실패 안내 노트) 동기화. 회귀: 백엔드 3건(`test_intent_interpreter.py` — 실패 플래그·LLM 미가용·LLM 판단 UNKNOWN 구분)+프론트 3건(`conversationDecision.test.ts`) — 백엔드 3,407·프론트 1,370 전체 통과(tsc 기존 에러 6줄은 무관 파일, stash 대조로 확인) | ✅ 완료 |
| 코스닥 유니버스 변경이 되묻기로 빠짐 + 다중 기술적 진입 조건 AND 소실 (2026-08-03) | 사용자 신고 2건. **① 되묻기 오분류**: "코스닥으로 변경해줘"처럼 유니버스 값이 이미 명시됐는데도 `intent/interpreter.py`의 대상 판단 프롬프트가 숫자 값 예시만 들어 LLM이 "값 없음"으로 오판, `clarify_target=universe`로 칩 되묻기가 떴다. 수정: 규칙 10에 "값은 숫자만이 아니다 — 시장명·업종명도 값이다" 예시("코스닥으로 변경해줘"→null) 추가. 회귀: `test_prompt_clarifies_that_enumerated_values_count_as_values`(프롬프트 문구 고정). **② 다중 기술적 진입 조건 AND 소실(더 심각, 실측으로 확인)**: 사용자가 "RSI 50 돌파하면서 MACD 골든크로스 동시에"를 요청하자 LLM은 두 조건을 정확히 추출했지만, `engine/strategy_converter.py::to_backtest_request`가 만드는 `entry` 딕셔너리에 `logic` 키가 전혀 없어 `SignalEngine.generate_signals`(`engine/signals.py`)의 기본값 `OR`로 조용히 실행됐다 — "동시에"가 "또는"이 되는 사고. 실측: 합성 데이터로 OR=26/50봉, 강제 AND=0/50봉 확인. `entry_filters`(빌더 전용 AND 게이트)는 LLM 경로에서 한 번도 채워지지 않는 죽은 채널이라 우회 불가. 원인은 `StrategySpec`(LLM 스키마)·`ParsedStrategy`·`schemas.ConditionGroup` 어디에도 결합 방식을 표현할 필드 자체가 없었던 것. 수정: `entry_logic`(Literal AND/OR, 기본 AND) 필드를 4곳에 신설·배선 — `strategy_conversation/interpreter/models.py`(LLM 출력, `_OUTPUT_SHAPE`에도 노출해야 9B가 채움)·`engine/nl_parser.py`(`ParsedStrategy`)·`strategy_conversation/compiler/strategy_compiler.py`(전달)·`strategy_conversation/compiler/strategy_decompiler.py`(수정 라운드트립 보존, 누락 시 OR 전략이 다음 턴에 조용히 AND로 되돌아감)·`engine/strategy_converter.py`(`to_backtest_request`가 `logic` 항상 명시)·`schemas.py`(`ConditionGroup.logic` 필드 추가, 미선언 시 model_dump가 조용히 버리는 기존 함정과 동일). 프롬프트(`prompts.py`)에 "동시에·그리고·쉼표 나열=AND(기본), 또는·둘 중 하나=OR" 규칙 4-2 추가. `to_canonical_strategy_dsl`은 entry_signals가 2개 이상일 때만 `entry_logic`을 해시에 반영(0~1개 전략의 기존 strategy_id 불변). `scripts/export_slot_judgments.py` 재실행으로 프론트 계약 픽스처(`slot-judgments.json`) 동기화. 회귀 4건(`test_intent_interpreter.py` 1건, `test_strategy_conversation.py` 2건 — 기본 AND·명시적 OR 전파, `test_strategy_converter_strategy_id.py` 1건 — SignalEngine 실제 계산까지 AND 확인) — 백엔드 3,411·프론트 1,370 전체 통과 | ✅ 완료 |

| PCR(주가현금흐름비율) 정식 지원 승격 (2026-08-03) | 사용자 질문("pcr, psr도 가지고 있나?")에서 발견 — `fundamental_fetcher.py`가 PCR(시가총액/영업활동현금흐름)을 계산해 parquet에 저장하고 있었지만(삼성전자 2,511일치 실측) 어느 소비 지점에도 배선되지 않은 죽은 데이터였다. 사용자 지시로 3계층 배선: ① `engine/signals.py` `FUNDAMENTAL_LABELS`에 pcr 등록(제네릭 filter 평가는 컬럼명=조건 id라 자동) ② `indicator_registry.py`에 `fundamental.pcr` 스펙(valuation·ratio·추천 10·범위 0~500, 영업현금흐름<=0 결측 note)+별칭(pcr·주가현금흐름비율) → `supported_factor_lines()`로 인터프리터 프롬프트 **자동 반영** ③ 정본 JSON(`data/fundamental-factors.json`)에 pcr 추가 — 이 JSON을 읽는 `condition_builder`(_PATTERNS["pcr"] 필수, 없으면 KeyError)·`clarify_targets.factor_targets()`(되묻기 대상 목록)·프론트 `parsedStrategyMerge.ts`가 함께 갱신됨. 부수 배선: `nl_parser.py` FundamentalFilter Literal+설명+레거시 프롬프트 예시, `_default_operator_for_metric`(<=), ETF 충돌 라벨, `_MODIFY_FIELD_CUES`(수정 어휘차감 — psr과 동열), `parse_validator.py` metric 목록, 프론트 라벨 3파일(strategy-summary·strategy-type·parsedStrategyMerge). **미지원 목록 처리(개념 구현 시 목록 제거 원칙의 적용 판단)**: `condition_builder._UNSUPPORTED`의 PCR 안내("아직 데이터셋에 없어")는 거짓이 되므로 **제거**+pcr 지표 인식으로 대체. 반면 `nl_parser._UNSUPPORTED_CONCEPT_PATTERNS`의 cash_flow 큐(pcr 포함)는 **유지** — 결정적 추출기는 PCR을 추출하지 못하고(원문 정규식 어휘 추가 금지 — 대원칙 1) 큐가 있어야 규칙 기반 레인이 자신을 불신하고 LLM 폴백으로 위임한다(제거하면 침묵 누락). 대신 `_CONCEPT_EXPRESSED_PREDICATES.cash_flow`에 pcr을 추가해 LLM이 pcr 필터로 반영하면 "미지원" 안내를 뺀다(2026-08-01 ocf_growth 오탐 수정과 동형). 라벨 "FCF/PCF 등"→"FCF 등"(PCF≒PCR). 실측: 9B 실모델로 "PCR 10 이하+부채비율 100% 이하" → `[('pcr','<=',10.0),('debt_ratio','<=',100.0)]` READY·안내 없음·entry logic=AND 확인. 회귀 4건(supported 승격+큐 유지, 안내 억제, condition_builder 승격, registry→컴파일→백테스트 요청 끝-끝) — 백엔드 3,415·프론트 1,370 전체 통과(tsc 기존 에러 3줄=무관 파일, stash 대조) | ✅ 완료 |

| 당기순이익 전 종목 캐시 재수집 + 미러 pull 스톨 근본수정 (2026-08-04) | 사용자 신고: "당기순이익 >= 0억, 영업이익률 >= 0" 전략에서 유니버스 대부분이 "미해결 데이터 — 검증 불가 제외". 원인: `net_income`은 08-03 신설된 fetch 시점 파생 필드(순이익률×매출액)인데 `fetch_fundamentals`가 90일 캐시를 재계산 없이 반환하고, 캐시 저장 전 `_revenue`를 pop해 기존 캐시(3,218개 전부 net_income 0개)로는 복원 불가 — KIS 재조회 필수. 조치(코드 변경 없는 데이터 작업): 정본=프로덕션 원칙대로 prod parquet pull(3,807파일)로 통일 → `backfill_fundamentals.py --force` 전 종목(5,074 parquet, 약 3.5h — enriched 2,724·market_cap_only 1,574·no_data 776·오류 0) → 백필이 수정한 parquet 4,298+재수집 캐시 5,074만 `rsync --files-from` 스코프 push(전체 push는 무관 drift 오염 위험 — 미러 함정 2). 결과: 상장 일반주 당기순이익 커버리지 0%→93.5%(영업이익률 81%→93.8%), 신고 화면 종목 11개 중 10개 해소. 미커버 잔여는 은행·금융지주·스팩 — KIS 손익계산서에 매출액 항목이 없어 재계산 불가(구조적, 예: 케이뱅크·카카오뱅크·우리종합금융). **주의: 파생 필드를 또 추가하면 그때도 전량 재수집 필요**(캐시에 `_revenue` 없음). **부수 발견·수정**: 첫 pull이 30분 0바이트 정지 — 로컬 스케줄러의 08-02 21:15 일일 pull이 SSH 행으로 30시간 좀비로 남아 이후 pull 전부 막힘(로컬 3,807파일 낙후의 원인). `mirror_data.py::build_rsync_cmd`에 `--timeout=120`(무전송 중단)+SSH keepalive(`ServerAliveInterval=15`×4)를 키 유무 무관 항상 포함으로 근본수정 — 스케줄러는 스크립트를 서브프로세스 실행하므로 재시작 없이 적용. 회귀 `test_mirror_data.py::test_stall_timeouts_always_present` — 백엔드 3,429·프론트 1,379 전체 통과 | ✅ 완료 |
| parquet 재작성 컬럼 소실 근본수정 — 이월 화이트리스트 → 블랙리스트 (2026-08-04) | 사용자 질문("우리는 배당주 데이터를 가지고 있나?")에서 발견. **증상**: 프로덕션 5,074 parquet 중 1,276종목(25%)에 `dividends` 원천 컬럼이 없고 배당 지표 3종이 전부 NaN — 하필 삼성전자·SK하이닉스·현대차 등 대형 배당주가 여기 포함돼, 배당수익률 조건 전략이 이들을 조용히 탈락시켰다(프로덕션·로컬 수치 완전 동일 — 미러 유실 아님). **오진 2회 후 규명**: ① "08-03 재수집이 덮었다"→ mtime 대조로 반증(같은 시각 갱신분 2,601개는 컬럼 보유) ② "KIS 배당 API 실패"→ 미백필 30종목 직접 호출로 반증(27종목 DPS 정상·3종목은 주식배당만·**실패 0**, 삼성전자 dry-run 23 ex-dates 정상). **진짜 원인**: `backend/scripts/resync_kis_adjusted.py::_merge_fundamentals`가 이월 컬럼을 `_FUND_COLS` **화이트리스트 5개**(sector/eps/bps/roe_or_gpa/debt_ratio)로 열거 — KIS 深과거 백필(`backfill_ohlcv_history.py`가 이 함수를 재사용)이 parquet을 통째로 재작성하며 목록 밖 컬럼을 전부 버렸다. 미백필 1,276개 중 1,016개가 `.kis_backfill_done.json` 처리 목록에 포함되고, 두 그룹의 최초 데이터 중앙값이 1996년 vs 2019년(深과거 백필 대상=구 KOSPI 대형주)으로 일치. 다른 보강 컬럼(roa·net_income·market_cap 등)도 같이 날아갔지만 이후 펀더멘털 백필이 복구했고, **배당만 그 뒤로 재수집된 적이 없어** 지금까지 남았다(두 그룹 컬럼 차이=`dividends` 단 하나). **수정**: 이월을 **뺄 것만 정하는 블랙리스트**로 전환 — `_PRICE_COLS`(KIS 정본 가격 6종)+`_CLOSE_DERIVED_COLS`(per/pbr/psr/pcr/market_cap/배당지표 3종)만 제외하고 나머지 전부 이월. 종가 파생을 **떼어내는** 이유는 펀더멘털 백필이 `combine_first`로 결측만 채우므로, 옛 종가 기준 값을 남기면 낡은 기준이 영구 고착되기 때문(per/pbr은 이 함수가 새 종가로 재계산, 나머지는 결측→다음 백필이 재계산, 배당 3종은 `dividends` 원본 보존만으로 `data_resolver._resolve_dividend_metrics`가 런타임 복원). 전진충전 예외 `_NO_FFILL_COLS`=sector(상수 문자열)+**dividends**(ex-date 이벤트 시리즈 — 전진충전하면 배당 한 건이 이후 전 구간으로 번진다). 회귀 신규 `test_resync_merge_fundamentals.py` 6건(컬럼 생존·배당 값 비오염·연간 전진충전 유지·종가 파생 배제·가격 정본·신규 종목 no-op) — **수정 전 구현에 돌려 3건 실패 확인**(가드 실효성 검증). 백엔드 3,443 전체 통과. **미완(별건)**: 소실된 1,276종목 배당 재백필과 `--end` 기본값 2026년 확장은 데이터 작업으로 미실행 | ✅ 완료 |
| 재무 available_from 정정공시 오염 수리 — PIT 원공시일 클램프 (2026-08-05) | 사용자 검증 요청("2022-02-03 매매 종목들이 실제 흑자였나")에서 발견. **원인**: DART `fnlttSinglAcntAll`의 rcept_no는 정정공시가 있으면 **정정본**을 가리킴 → 캐시 `available_from`이 원공시일(예: 2021-03) 대신 정정 접수일(최대 수년 뒤)로 기록 → PIT 병합이 그 구간에서 낡은 연도 재무를 참조(실사고: 유성티엔에스 FY2018~2021 af=2023-03 → 2022-02-03 백테스트가 FY2017 재무로 매수 판정). 전수 스캔: 결산+120일 초과 3,390레코드/1,628종목(available_from 없는 레코드=결산+90일 폴백, 정상). **수정 3종**: ① `fundamental_fetcher._fetch_dart_original_filing_dates`(공시검색 list.json, A001, last_reprt_at=N, 12월 결산만 매핑 — 3월 결산은 괄호연도≠bsns_year라 오클램프 위험, 미매핑=안전한 현행 유지) 신설, `_fetch_cash_flow_from_dart`가 available_from을 min(기존, 원공시일)로 클램프 — 향후 재수집이 재오염되지 않는 근본 수정 ② `fundamental_backfill.rebuild_fundamental_columns` — 교정 캐시 우선(fresh wins)/캐시 밖 과거 이력 보존/PER·PBR·PSR 분모 정합 재계산(기존 merge_fundamentals의 기존값-우선 combine_first는 오염된 날을 못 고침), ROE 유도는 `_fill_roe_from_eps_bps`로 공유 추출 ③ `scripts/repair_fundamental_available_from.py` — 오염 종목만 DART 1회/종목 조회로 캐시 클램프+parquet 재구축, idempotent, 쿼터(020) 감지 시 exit 3 재개형, `--manifest`로 변경 파일 기록. **실행**: DART 일일 쿼터가 당일 net_income 전량 재수집으로 소진돼 백그라운드 waiter가 08-05 00:05(리셋 직후) 자동 실행 — 1,611종목·4,309레코드 클램프, 오염 3,390→62(잔여=실제 지연공시, 미확인 9종목은 안전 미변경). **prod 반영(함정 2개)**: 로컬 parquet push는 프로덕션(정본) 최신 봉 유실 위험(실측: 로컬 024800이 08-03까지) → 캐시 JSON 1,611개만 스코프 rsync push 후 재구축을 프로덕션 컨테이너 현지 실행(행수·최대날짜 불변 가드). 1차 실행은 prod 배포 코드의 `ANNUAL_FUNDAMENTAL_KEYS`가 29키(net_income 없음)라 net_income만 stale 잔존 → 로컬 키 30개+PIT 채움 로직을 통째로 임베드한 자기완결 v2(로컬에서 엔진 결과와 전 컬럼 일치 검증 후)로 재실행. 테스트: fetcher 클램프 2·재구축 3·수리 스크립트 3 신규 — 백엔드 3,437·프론트 1,379 전체 통과 | ✅ 완료 |
| 배당 시계열 배치 근본 수정 — 연말 1점 → 실제 기준일 (2026-08-04) | 위 컬럼 소실 수리에 이어, 소실 종목 1,276개 배당 백필을 실행하려다 **종료일 상수와 배치 방식 두 결함**이 드러났다. ① **종료일 상수 박기** — `backfill_dividends.py`의 `--end` 기본값이 `20251231`로 고정돼 **2026년 배당 전량이 KIS에 요청조차 되지 않았다**(실측 누락: 삼성전자 746원·SK하이닉스 2,250원·KB금융 3,903원·신한지주 2,360원·현대차 7,500원). `_today()`(실행일)로 교체 — 상수를 박으면 해가 바뀔 때마다 당해 배당이 조용히 사라진다. ② **연도 단위 배치가 TTM을 부풀림**(단순 확장이 위험했던 이유) — `build_dividend_series`가 연도별 **합계**를 '그 해 마지막 거래일' 한 점에 몰아 찍어, 진행 중인 해의 부분 배당이 직전 연말 배치와 몇 달 간격으로 들어가 252거래일 TTM 창에서 겹쳐 세졌다(삼성전자 실측: TTM 1,668원 → **2,414원, 45% 과대**). 원인은 KIS 응답에 **건별 기준일(`record_date`)이 이미 있는데** `_parse_kis_dividends`가 `int(rd[:4])`로 연도만 남기고 월·일을 버린 것. **수정**: 파서·provider 반환을 `{연도: DPS}` → `{기준일 "YYYYMMDD": DPS}`로 바꾸고(`annual_dps_from_kis`→`dps_by_record_date_from_kis`, `annual_dps_from_pykrx`→`dps_by_year_end_from_pykrx` — 후자는 pykrx가 건별 기준일을 주지 않아 12-31 키로 종전 동작 유지), 배치 규칙을 **기준일 이하의 마지막 거래일**로 일반화. 연말 결산 배당은 이 규칙이 곧 '그 해 마지막 거래일'이라 완결 연도 배치는 사실상 불변이고, 분기·중간 배당만 제 날짜로 흩어진다. 같은 거래일로 떨어지면 덮어쓰지 않고 **합산**(구현은 `=`이라 조용히 하나를 잃었다). **마지막 봉 이후 기준일 가드(1차 구현 오류를 실데이터가 잡아냄)**: `searchsorted` 배치는 기준일이 마지막 봉보다 뒤여도 마지막 봉으로 끌어와 찍는다. 1차 구현은 이를 '실행일 이후만 제외'로 막았는데, 전량 재백필 후 검증에서 **배당수익률 40% 초과 289종목**(구 데이터 24종목)이 잡혔다. 공정 비교(프로덕션에도 배당이 있던 3,532종목, 최대 배당수익률 변화 중앙값 **0.00%p**·평균 +1.22%p로 대다수는 불변)로 좁히자 **17종목만 0~2% → 100~150%로 악화**. 정체는 **스팩·상장폐지 종목의 청산 분배금**으로, 기준일이 마지막 거래일 **+82~+454일**이었다(460280·441330·394350 +454일, 스팩 207720 +82일, 0001S0 +2일). 금액이 주가와 맞먹어(청산=원금 반환: 460280 13,426원 vs 종가 8,915원) 마지막 봉에 찍히면 유령 고배당주가 된다. 구 연도 매칭 코드는 '그 해에 봉이 없으면 skip'이라 **우연히** 걸러내고 있었다. 엔진은 상폐 시 강제청산하므로 이 분배금은 실제로 받지 못한다 → 가드를 `record_date > dates[-1]` 제외로 교정(예정 배당 lookahead도 같은 조건이 함께 막아 `now` 주입 파라미터는 폐기 — 가드 하나로 충분). **실측 검증**: 삼성전자 배당 이벤트 23건→66건(분기 분산), 최종일 TTM DPS 1,682원=최근 4개 분기(370+566+372+374) 정확 일치·배당수익률 0.70%, KB금융 4,598원(2.71%)·현대차 10,000원(2.54%) 전부 현실값. **부수 발견·수정 — 액면가 조정 기준 오염(기존 결함)**: 위 검증에서 남은 이상치 33종목의 최악값을 파고들어 별건 결함을 찾았다. 분할 역조정은 `DPS × (최신 액면가 / 당시 액면가)`인데, '최신'을 **전체 레코드 중 최근**으로 잡아 **상장폐지 이후 레코드의 비정상 액면가**가 기준이 됐다 — 002005(한국유리공업우)는 폐지 후 레코드가 액면가 500,000원(정상 배당기 5,000원)이라 과거 배당이 **100배**로 부풀어 배당수익률 1,069%(002000은 619%). **1차 수정은 틀렸고 검증이 잡아냈다** — 후보를 '배당이 있는 레코드 중 최신'으로 좁히자 002005/002000은 고쳐졌지만 이상치가 33→35로 **늘었다**. 새로 깨진 001080·002420·006345는 **마지막 배당 이후 액면분할**한 종목으로(1,000→100 / 5,000→500), 최신 배당 레코드가 분할 전 액면가라 역조정이 사라져 배당이 10배로 남았다. 무배당 레코드도 '현재 액면가'는 정확히 준다 — 문제는 무배당이 아니라 **값의 오염**이었다. 근거 확보를 위해 액면가 분포를 실측(120종목 표본·배당 레코드 1,369건): 관측값은 **{100, 200, 500, 1000, 2500, 5000} 6종뿐이고 5,000원 초과 0건**. 최종 규칙은 '**정본 집합에 속하는 가장 최근 액면가**'(`_VALID_FACE_VALUES`, 정본 밖은 무조정 처리). 실측 확인: 002005 82,500→825원, 001080 200→20원, 002420 1,000→100원, 006345 150→15원, 삼성전자·001130 불변. 회귀 2건 추가(오염 액면가 배제 / 마지막 배당 이후 분할 역조정). 회귀 `test_backfill_dividends.py` 개정+신설 33건(기준일 배치·중간배당 분산·부분연도 TTM 비중첩·예정 배당 제외·**상폐 후 청산 분배금 제외**·**무배당 레코드 액면가 배제**·동일 거래일 합산·종료일 기본값 추적) — 백엔드 3,451 전체 통과. **운영 주의**: `_kis_dividend_records`가 네트워크 예외를 삼키고 빈 리스트를 반환해 **일시적 타임아웃이 그 종목 배당을 0으로 덮어쓴다**(실제 발생: 244820, 로그로 검출해 개별 재실행 복구). 대량 백필 후 로그의 `fetch failed` 검색이 필수. **프로덕션 반영 완료**(2026-08-04 15:31 KST, `mirror_data.py --push` 5,074파일 — dry-run 선행, 스케줄러 21:00 이전). prod 직접 검증: 컬럼 누락 0·전부 NaN 0·배당수익률>0 3,329종목·2026년 반영 1,121종목, 삼성전자 66건 TTM 1,682원(0.70%)·현대차 40건 10,000원(2.54%)·신한지주 39건 3,500원(3.41%) | ✅ 완료 |

| 값-대기 조건을 '미지원'이라 안내하던 모순 제거 (2026-08-04) | 배당 데이터 정비 후 사용자 질문("'고배당률 종목 투자 전략'이라고 입력하면 백테스트 할 수 있나?")을 라이브로 실측하다 발견. 파이프라인은 정상 동작했다 — `고배당률`→**배당수익률**로 인식해 `pending_conditions`에 담고 "기준값을 얼마로 할까요?(3%)"를 칩(`chip_bindings`: `dividend_yield>=3.0`)과 함께 되물었고, 칩 답변→청산 규칙 답변 3턴이면 백테스트까지 실행됐다(실측: KOSPI200 5년 월간 리밸런싱, PIT 유니버스 870종목 15.4초 완주). 문제는 **그 되묻기와 같은 응답에 "'배당 조건'은(는) 아직 직접 지원되지 않아요"가 함께 나간 것** — 서로 모순이고 사실도 아니다(배당수익률은 2026-07-14 지원 승격). 원인은 구조적 사각지대: 미지원 개념 게이트의 억제 술어 `concepts_expressed_in_strategy`가 **컴파일된 parsed만** 보는데, 값 미정 조건은 계약상 parsed에 없고 `pending_conditions` 별도 채널에만 있다(FR-STR-019 '말하지 않은 값을 기본값으로 확정 금지'의 부작용). 수정: `concepts_covered_by_pending(pending_conditions)` 신설 — 값 대기 조건의 **레지스트리 정본 라벨**(display_name)을 미지원 개념 패턴에 대조해 억제 대상에 더한다(판정 입력이 사용자 원문이 아니라 정본 표기라 결정론 코드 소관 — 대원칙 1 합치, 라벨 매칭이라 새 팩터 추가 시 별도 매핑 유지 불필요). `_build_parse_result`에 `pending_conditions` 인자를 추가해 primary가 이미 산출한 값을 넘긴다. **과잉 억제 방지 확인**(라이브): "고배당률 종목 중에 베타 낮은 것" → 배당 안내는 사라지고 베타 안내는 유지, 값 대기 조건이 무관 지표(부채비율)면 배당 안내 그대로. 라이브 재검증: 같은 입력의 `notices`가 `[]`로 바뀌고 질문·칩·pending_conditions는 불변. 회귀 3건(`test_fundamental_metrics_extraction.py` — 억제·과잉억제 방지·빈/불량 입력) — 백엔드 3,455 전체 통과. AgentsTab 미갱신(단계·분기·되묻기·가드 구성 불변, 기존 게이트의 판정 입력 보정). **후속(같은 날): 내부 식별자 노출 제거** — 위 실측에서 함께 발견된 별건. 미지원 팩터의 값-대기 안내가 `"'technical.beta' 조건은 값 확인 전까지 전략에 반영되지 않았어요."`처럼 내부 식별자를 그대로 노출했다. 원인은 `compile_partial`의 `label = spec.display_name if spec else cond.factor` — Registry에 없는 팩터(LLM이 만들어 낸 미지원 지표)는 정본 표시명이 없어 식별자로 폴백했다. `_condition_label()` 신설: 정본 표시명 → **사용자가 실제로 말한 표현(`source_text`)** → 네임스페이스 접두를 뗀 팩터명 순으로 내려간다. 라벨이 source_text와 같아도 프론트 요약은 중복 표기하지 않는다(`formatPendingCondition`이 이미 처리). `compile_strategy`(비-partial)는 미지원 팩터에서 예외를 던져 라벨을 만들지 않으므로 무영향. 라이브 확인: `'technical.beta'` → `'베타 낮은 것'`, 내부 식별자 노출 0. 회귀 2건(`test_strategy_conversation.py` — source_text 폴백·접두 제거 폴백). **후속 2(같은 날): 드롭 안내를 원인별로 분리** — `compile_partial`의 `dropped`가 원인 둘을 섞고 있었다(① 값 미정 = `pending_conditions`에도 실림 ② 컴파일 불가 = 미지원 지표·역할 불가). 한 문구로 묶은 탓에 ②에까지 "값 확인 전까지"가 붙어 **값을 주면 해결될 것처럼** 읽혔다(지원되지 않는 '베타'에 "값 확인 전까지 반영되지 않았어요"). `pending_conditions`의 라벨 집합으로 갈라 값 미정은 기존 문구, 컴파일 불가는 "'X' 조건은 전략에 반영하지 못했어요."로 분리 — 원인 설명은 결정론 게이트의 미지원 개념 안내가 담당하고 여기서는 '어느 표현이 빠졌는지'만 알린다(조용한 누락 방지 유지). 원문 재해석 없이 **드롭 원인**만으로 갈라 정규식을 새로 도입하지 않았다. 라이브 확인: "고배당률 종목 중에 베타 낮은 것" → `'베타(시장 민감도) 조건'은 아직 직접 지원되지 않아요` + `'베타 낮은 것' 조건은 전략에 반영하지 못했어요`(값 문구 사라짐), "고배당률 종목 투자 전략" → 안내 0. 회귀 1건 추가. 백엔드 3,458 전체 통과 | ✅ 완료 |

| 현금흐름 3분류(영업·투자·재무) 수집 (2026-08-05) | 사용자 질문("우리는 종목의 현금흐름표 데이터를 가지고 있나?" → "영업활동, 투자활동, 재무활동별 데이터를 받아 올 수 있나?" → "공공데이터에서 얻어 올수 없나? KIS나?")에서 출발. **현황 파악**: 현금흐름표 전체가 아니라 영업활동현금흐름(OCF)·CAPEX 두 계정만 수집 중이었고(파생: PCR·FCF·ocf_growth·fcf_growth), 로컬 캐시 3,220종목 중 OCF 보유 2,501(77.7%)·CAPEX/FCF 2,365(73.4%), 연도 2015~2025(`_DART_YEAR_FLOOR`). **대체 출처 전수 확인(실측)**: ① KIS 재무제표 그룹 7개 엔드포인트를 전수 호출 — balance-sheet/income-statement/financial-ratio/profit-ratio/other-major-ratios/stability-ratio/growth-ratio는 200이지만 `finance/cash-flow`·`cashflow`는 **HTTP 404**(엔드포인트 부재). 부수 확인: income-statement에 `depr_cost`(감가상각비)가 있어 OCF 근사는 가능하나 운전자본 변동이 빠져 대체재 불가, 응답이 23개 기간이라 DART(2015~)보다 이력이 깊다 ② 공공데이터포털 금융위원회 기업재무정보(`GetFinaStatInfoService_V2`)를 레포의 기존 `PUBLIC_DATA_SERVICE_KEY`로 직접 호출 — `getSummFinaStat_V2`(요약재무제표)·`getIncoStat_V2`(손익 계정 5종, 2015~2025)만 200이고 `getCashFlowStat_V2`/`getCshflStat_V2`/`getCashFloStat_V2` 등 현금흐름 계열은 **전부 400**. 금감원 정기보고서 재무정보(다중회사 주요계정)도 재무상태표·손익계산서 주요계정만 → **OpenDART `fnlttSinglAcntAll.json`이 유일 출처**(이미 호출 중인 그 엔드포인트). **계정ID 실측(11종목 × 2024, 삼성전자·SK하이닉스·현대차·카카오·셀트리온·신한지주·SKT·포스코인터내셔널·클래시스·엘브이엠씨홀딩스·삼양식품)**: `ifrs-full_CashFlowsFromUsedInInvestingActivities`·`...FinancingActivities`가 **11/11 전부** 등장(금융업·외국계 포함, 편차 우려는 기우). account_nm은 "…현금흐름 / …으로인한현금흐름 / …순현금흐름" 3표기로 갈림. **함정 발견**: 포스코인터내셔널에 `ifrs-full_CashFlowsFromUsedInOperations`("영업활동에서창출된현금흐름" = 이자·법인세 차감 **전** 소계, 1,205,694,724,000)가 총계(876,881,370,000)와 **별도로 존재** — 계정명만으로 고르면 총계로 오인한다(기존 코드는 계정ID 우선이라 이미 안전, 회귀로 고정). **구현**: `_parse_dart_operating_cash_flow`의 중복 로직을 `_parse_dart_activity_cash_flow(rows, account_id, names)`로 일반화(계정ID 일치 우선 정렬 계약 보존, 기존 함수는 래퍼로 시그니처 유지)하고 투자·재무 총계를 같은 `rows`에서 파싱해 record에 추가 — **추가 API 호출 0**(회귀로 `fnlttSinglAcntAll.json` 호출 1회 단언). `ANNUAL_FUNDAMENTAL_KEYS`에 `investing_cash_flow`·`financing_cash_flow` 추가(raw 원 단위 — PCR이 `market_cap×1e8/ocf` 기준이라 억원 환산 금지). 해당 활동이 없는 제출본은 키 자체를 생략(0으로 날조 금지). 부수 수정: OCF 계정명 폴백 집합에 실측 표기 `영업활동순현금흐름` 누락분 추가(계정ID가 빈 제출본 대비 안전망 — DART 구조화 출력의 계정명 정규화라 대원칙 1 무관). **end-to-end 라이브 검증**: 삼성전자 2024 = 영업 729,826억/투자 -853,817억/재무 -77,972억, 신한지주 2024 = 46,263/1,485/-1,826억 — 실측 프로브 값과 일치. 회귀 5건(3분류 파싱·소계 오인 방지·순현금흐름 이름 폴백·한 응답 3분류 동시 수집+호출 1회·결측 키 생략) — 백엔드 3,463 전체 통과. **범위 제한**: 데이터 수집만이며 전략 조건 지표 승격은 미포함(`unsupported.cash_flow` 유지). **전 종목 백필 완료(2026-08-05, 사용자 승인 '전 종목 전 기간을 나눠서 하자')**: 신규 `scripts/backfill_cash_flow_activities.py`(재개 가능·쿼터 분할). **호출량 감축** — 3분류가 한 응답에서 나오므로 **OCF 보유 연도만** 재조회하면 되고(OCF 없는 연도는 그 응답에 CF 총계가 없었다는 뜻), 22,694 (종목,연도)로 산정해 초기 추정 5.5만에서 절반 이하로 줄였다. 분할 장치: `--max-calls` 예산, status 020 감지 시 진행분 저장 후 종료코드 3(재실행 재개), 재개 근거 이중화(progress 파일 + 캐시 `pending_years` 스캔 — 프로세스 강제 종료에도 성립). parquet은 `rebuild_fundamental_columns`(캐시 우선)가 아니라 **`merge_fundamentals`(기존 값 우선)**를 써서 두 컬럼만 신규 추가 — 000020 실주행 백업 대조로 신규 컬럼 2개·삭제 0·행수 불변·기존값 변경 0 확인(배당 3종의 결측 2행 채움은 설계된 gap-fill, 일일 스케줄러와 동일 경로). **실행 결과**: 2,486종목 처리, DART 26,856 호출로 **쿼터 중단 없이 1회 완주**(≈1.5시간 — 일일 한도가 사전 추정 2만보다 높음이 실측으로 확인됨). 커버리지 영업 2,501 → 투자 2,500 / 재무 2,499, 연도별 2015~2025 각 1,715~2,291 레코드. **결측 3건은 데이터 부재이지 실패가 아님**: 0115H0(FY2025 OFS 응답에 영업·재무만 존재, 투자활동 항목 자체가 없음)·025270·066270(재무활동 없음) — 키를 생략하고 0으로 날조하지 않는 설계가 정확히 작동. 검증: 캐시↔parquet 불일치 0건(표본 300), 삼성전자 parquet 값이 라이브 프로브와 일치(729,826/-853,817/-77,972억). **검증 중 잠재 버그 발견·수정**: `by_year` 키를 연도 4자리로 잡아, 같은 해에 결산월이 다른 레코드가 함께 있으면(KIS 유래 2025-09-30 + DART 유래 2025-12-31) OCF가 없는 쪽에 값이 실릴 수 있었다 — 실제 충돌 사례는 전수 스캔 0건이었으나 OCF 보유 레코드로만 키를 만들도록 수정하고 회귀 추가. 테스트 신규 9건 — 백엔드 3,472 전체 통과. **프로덕션 반영 완료(2026-08-05)** — 스코프 push 직전 사전 검사에서 **행 소실 사고를 발견해 절차를 바꿨다**: 2,501종목 중 **1,777개(71%)에서 프로덕션 parquet이 로컬보다 앞서 있었다**(로컬 2026-08-03 / 프로덕션 2026-08-04 — 백필 중 프로덕션 일일 스케줄러가 돌았다). `rsync --files-from`으로 스코프를 좁혀도 **파일 단위 덮어쓰기라 행 손실은 막지 못한다**(2026-07-21 선례가 막은 것은 '무관 종목' 오염이지 '같은 종목의 뒤진 내용'이 아니다 — mtime 기준 `--update`도 무력, 로컬이 더 최신이었다). 안전 절차로 대체: ① 스코프 **pull**(정본=프로덕션)로 최신 행 회수 → 새 컬럼은 사라짐 ② 신규 `--remerge-only` 모드로 **DART 호출 0**의 캐시→parquet 재병합(캐시 `data/fundamentals`는 미러 대상이 아니라 3분류가 보존돼 있다는 점을 이용) ③ 전수 검증(프로덕션 대비 뒤진 종목 0, 행 보존 2,501/2,501, 컬럼 누락 0) ④ push. 결과: parquet 2,501 + 캐시 2,501 반영, 재-dry-run 차이 0건, 프로덕션 컨테이너에서 값 확인(삼성전자 as-of 2026-08-04 = FY2025 공시일 2026-03-10 기준 투자 -685,122억·재무 -134,780억으로 전진충전, 행수 7,679 보존). 프로덕션 캐시 커버리지도 로컬과 일치(3,220종목 중 투자 2,500·재무 2,499). **오늘 밤 스케줄러 안전성 확인**: 일일 증분(`scripts/sync_data.py::update_ohlcv_incremental`)은 `df_old.columns` 기준으로 스키마를 맞춰 미지 컬럼을 보존하고, `merge_fundamentals`는 기존 parquet을 copy로 시작하므로 **이미 반영된 과거 값은 지워지지 않는다**. 다만 프로덕션 코드에는 아직 새 파서가 없어(배포 커밋 `ef87baa` 기준 `_DART_INVESTING_CASH_FLOW_ACCOUNT_ID` 부재) **신규 거래일 행의 투자·재무는 코드 배포 전까지 null**로 남는다. **미실행**: 코드 배포(커밋·main push→CI 배포)는 명시 지시 대기. SRS FR-BT-052e | ✅ 완료 (코드 배포 대기) |

| 현금흐름 3분류 조건 지표 승격 (2026-08-05) | 위 수집에 이어 사용자 지시("조건 지표로 승격해야지")로 전 계층 배선. **핵심 결정 — 단위**: 저장값이 DART 원천 그대로 raw 원이라 승격하면 "1,000억 이상"이 **1억 배** 어긋난다(코드베이스 관례는 `market_cap`·`net_income`처럼 금액=억원). raw 컬럼은 PCR(`market_cap×1e8/ocf`)·FCF 계산 기준이라 손대지 않고 **억원 파생 컬럼 3종**(`operating_cf_amount`/`investing_cf_amount`/`financing_cf_amount`)을 신설해 그것만 승격했다 — 컴파일 시점 임계값 환산(대안 B)은 "제네릭 eval(get_col(cid))" 계약을 깨고 배지·검증·랭킹·프론트 전 지점에 같은 환산을 중복해야 해 누락 시 조용한 1e8 오차가 나므로 배제. 부호는 보존한다(투자·재무는 자산 취득·차입 상환으로 통상 음수 — 절댓값·부호반전 금지). **배선 8계층**: ① `fundamental_fetcher._compute_derived_annual_metrics` 억원 환산 + `ANNUAL_FUNDAMENTAL_KEYS` ② `signals.FUNDAMENTAL_LABELS`(엔진 SOT — 제네릭 filter 평가는 컬럼명=조건 id라 자동)+`FUNDAMENTAL_AMOUNT_CIDS`(억 배지) ③ `indicator_registry` 스펙 3종(category=cashflow, 단위 억원)+별칭 14개 → `supported_factor_lines()`로 인터프리터 프롬프트 **자동 반영** ④ 정본 `data/fundamental-factors.json`(이 JSON을 읽는 `condition_builder._PATTERNS`는 키 누락 시 **KeyError로 임포트 자체가 실패** — 실제로 재현 후 추가) ⑤ `nl_parser` FundamentalFilter/RankingMetric Literal·필드 설명·ETF 충돌 라벨·`_MODIFY_FIELD_CUES` ⑥ `parse_validator` metric 목록 ⑦ `_CONCEPT_EXPRESSED_PREDICATES.cash_flow` 확장(3분류 반영 시 미지원 안내 억제) ⑧ 프론트 `strategy-summary.ts`(라벨+`formatEokAmount` 대상)·`parsedStrategyMerge.ts`·`strategy-type.ts`(가치투자 분류에 `cf_amount`). **절대금액 vs 증가율 잠식 방지**: `_PATTERNS`에 lookahead(`(?!\s*(?:증가율|성장))`)를 둬 "영업활동현금흐름 1000억"→`operating_cf_amount`, "…증가율 10%"→`ocf_growth`로 갈리는 것을 회귀로 고정. **미지원 목록 처리**(개념 구현 시 제거 원칙의 적용 판단): `unsupported.cash_flow`는 **제거하지 않고** 명칭을 "현금흐름 배율(FCF/PCF) 조건"으로 좁히고 alternatives를 3분류로 교체 — 어느 분류인지 특정되지 않은 맨 '현금흐름'은 결정적으로 고를 수 없어 LLM 위임 신호가 여전히 필요하다(PCR 승격 때와 같은 판단). **데이터 반영**: 승격 이전에 쓰인 캐시에는 억원 파생본이 없어 parquet 컬럼이 전부 null이 되는 것을 발견 — `--remerge-only`가 `_compute_derived_annual_metrics`를 재계산해 캐시에 반영하도록 보강(295종목 사전 대조로 **순수 가산**임을 확인: 추가 3키·기존 값 변경 0). 로컬 2,501종목 재병합 완료. **라이브 실측(9B)**: "영업활동현금흐름 1000억 이상이고 부채비율 100% 이하" → `[(operating_cf_amount,>=,1000),(debt_ratio,<=,100)]` 단위 억원·안내 0, "투자활동현금흐름이 0보다 작은 기업 중에 ROE 10% 이상" → `[(investing_cf_amount,<,0),(roe_or_gpa,>=,10)]`. 엔진 스크리닝 실측: 표본 506종목 중 `operating_cf_amount>=1000억` 통과 105. 테스트 신규 7건(레지스트리 승격·증가율 비잠식·엔진 SOT·억원 파생·패턴 분리·캐시 파생 백필 등) — 백엔드 3,480·프론트 1,390 전체 통과(tsc 에러 3건은 stash 대조로 기존 확인). AgentsTab 미갱신(지표 추가일 뿐 단계·분기·되묻기·가드 불변). SRS FR-BT-052f | ✅ 완료 (프로덕션 반영 대기) |
| 지배주주순이익 지표 추가 (2026-08-06) | 사용자 질문("우리는 지배주주순이익을 계산할 수 있나?")에서 출발. **현황 확인**: 못 하고 있었다 — 기존 `net_income`은 KIS 순이익률×매출액이라 **비지배지분이 섞인 연결 전체** 당기순이익이다(삼성전자 2023 대조: 우리 값 154,843억 = DART 지배 144,734 + 비지배 10,137). **출처 결정**: 이미 종목·연도마다 부르던 `fnlttSinglAcntAll.json` 응답 안에 계정이 들어 있어 **추가 API 호출 0**으로 파싱 가능(FR-BT-052e와 같은 패턴). 12종목 2023년 CFS 실측에서 12/12 등장. **핵심 결정 — 계정ID 정확 일치, 이름 폴백 금지**: `account_nm` 표기가 회사마다 갈리는데(지배기업의 소유주에게 귀속되는 당기순이익(손실)/지배기업소유주지분/지배기업소유주/지배주주순이익) 같은 CIS 섹션의 **총포괄손익 귀속** 행이 사실상 같은 이름을 쓴다(SK하이닉스: 둘 다 "지배기업(의) 소유주지분") — 이름으로 잡으면 포괄손익을 순이익으로 오인한다. 기존 DART 파서들이 이름 폴백을 갖고 있는 것과 반대 방향의 판단이며, 그 폴백이 다음 함정을 가리고 있었다. **함정 — IFRS 택소노미 접두 2벌**: 2018년 사업보고서까지 `ifrs_`, 2019년부터 `ifrs-full_`. 신형만 보고 1차 구현했더니 삼성전자 2015~2018이 조용히 null이었다(다른 파서들은 이름 폴백이 있어 이 차이가 드러난 적이 없다). 두 접두를 모두 인정하도록 수정 후 2015~2025 **11개 연도 전부 수집**. 섹션도 IS/CIS 두 곳으로 갈려(실측 IS 5 / CIS 7) 둘 다 본다. **단위**: DART raw 원 → 억원 파생(`market_cap`·`net_income`·`cf_amount` 3종과 같은 관례), 부호 보존(적자면 음수 — SK하이닉스 2023 -91,124억). **배선 6계층**: ① `fundamental_fetcher` DART 파서+억원 환산+`ANNUAL_FUNDAMENTAL_KEYS` ② `signals.FUNDAMENTAL_LABELS`+`FUNDAMENTAL_AMOUNT_CIDS` ③ `indicator_registry` 스펙+별칭 8개 → `supported_factor_lines()`로 인터프리터 프롬프트 자동 반영, `net_income` notes에 "연결 전체" 명시해 오선택 방지 ④ `nl_parser` FundamentalFilter/RankingMetric Literal·필드 설명·ETF 충돌 라벨 ⑤ `parse_validator` metric 목록 ⑥ 프론트 `strategy-summary.ts`(라벨+`formatEokAmount`)·`parsedStrategyMerge.ts`. **의도적 미배선 2곳**: `data/fundamental-factors.json`+`condition_builder._PATTERNS`(키 추가 시 원문 정규식을 새로 써야 해 대원칙 1 위반 — 라우트 미배선 모듈이라 누락해도 깨지지 않는다), `nl_parser._MODIFY_FIELD_CUES`(같은 이유). **라이브 실측(9B)**: "지배주주순이익 1000억 이상인 코스피 종목" → `[(owner_net_income,>=,1000)]`, "지배주주 순이익이 5000억 넘고 부채비율 100% 이하" → `[(owner_net_income,>,5000),(debt_ratio,<=,100)]`, 맨 "당기순이익 1000억 이상" → `[(net_income,>=,1000)]`(비잠식 확인). 검증·컴파일·랭킹 경로 통과(`risk.ranking_metric=owner_net_income`), PIT 전진충전 확인(available_from 이전 봉은 NaN). 엔진 버전 9.2→**9.3**(순수 가산, 기존 전략 결과 불변). 테스트 신규 13건 — 백엔드 3,510·프론트 1,391 전체 통과(tsc 에러 3건은 기존). AgentsTab 미갱신(지표 추가일 뿐 단계·분기·되묻기·가드 불변). **검산 폴백 확장(2026-08-07)**: 1차 백필(1,527종목) 후 `no_owner_data` 235건을 90종목 표본으로 원인 분류 — **연결재무제표 미제출 76%(정상 결측)**, 나머지는 ① 귀속 행 미기재(비지배 0) ② 계정ID 미사용(`-표준계정코드 미사용-`) ③ 계속영업손익 계정. *중간 보고에서 ③이 주범이라고 했던 것은 오진이었다(표본 필터가 계정명에 '순이익'이 든 행만 봐서 ①②를 못 봄) — 90개 중 ③은 1건, ①이 16건으로 최다.* 사용자 승인(A안)에 따라 **단일 검산 규칙**(지배+비지배=`ifrs-full_ProfitLoss`)으로 세 원인을 함께 구제: 비지배 행이 없으면 0으로 놓고 단독 검산, 귀속 행이 전무하면 BS의 비지배지분 0(또는 자본총계=지배지분) 확인 후에만 당기순이익 전액 채택. 검산 실패 시 결측 유지 — 045660 2025는 계정ID 없는 "지배기업소유주지분/비지배지분" 쌍의 합이 당기순이익과 어긋나(총포괄 귀속) **거부**됐고 정상 연도는 채택됐다(연도 단위 판정). 실측 10건 전부 기대값 일치, 회귀 9건 추가. **데이터 반영 완료**: 2차 백필로 2,500종목 전량 처리(누적 DART 32,294 호출) → **2,191종목 / 16,954개 연도 레코드**(87.6%). `npm run pull-data`로 컬럼이 사라지는 것을 실제 확인하고 `--remerge-only`(DART 0회)로 2,191종목 복원 — 미러 왕복 절차 검증 완료. **스크리닝 실측(연간 기준)**: 지배주주순이익 ≥1,000억 통과 195종목, 두 지표가 10% 이상 갈리는 종목 495(26.0%), 1,000억 필터 통과 여부가 뒤집히는 종목 18. 괴리 상위는 전부 지주형(HD현대 3.68조→0.96조, SK 3.56조→1.60조, 한화 1.99조→0.37조) — 지표 신설 목적과 정확히 일치. **발견한 기존 결함 2건**: (가) `net_income`에 KIS 분기 레코드가 섞여 최근 시점에 분기 값이 전진충전됨 (나) `net_margin`(소수 2자리 반올림)×매출 재계산이라 저마진 연도 절대금액 오차가 큼 — 둘 다 사용자 지시로 아래 'FR-BT-052h' 행에서 수정했다. **프로덕션 반영 완료(2026-08-08)**: 로컬 캐시(`data/fundamentals`, 미러 비대상)를 rsync로 올리고 현지에서 `--remerge-only` 재구축 — **DART 호출 0건**으로 예정했던 4만 조회·이틀을 대체했다(로컬 parquet push 금지 원칙은 유지). 프로덕션 실측: 컬럼 2,228종목/값 2,170, 지배주주순이익≥1,000억 통과 188. SRS FR-BT-052g | ✅ 완료 (프로덕션 반영 완료) |

| 분위(퀀타일) 그룹 비교·비율 선정 (2026-08-06) | 사용자 요청("PER 가장 낮은 종목부터 정렬 → 종목 수 동일 10개 그룹 → 1그룹=최저 10%, 10그룹=최고 10% 편입"을 처리할 수 있나 → a·b 둘 다 + 결과 페이지 그래프·테이블)에서 출발. **선정 계약 2종 신설**: ① 비율 선정 `max_positions_pct`("상위 10% 편입") — 시뮬레이터가 리밸런싱일마다 그날 후보 수 기준 `max(1, round(n×pct/100))`로 동적 산정, 있으면 개수(max_positions) 무시 ② 분위 밴드 `ranking_band=[g,G]` — 랭킹 내림차순 후보를 종목 수 기준 G등분(`select_ranked_targets`, round 경계로 서로소·전체 커버 보장). 두 모드 모두 순수 리밸런싱(from_orders)·커스텀 루프(reconstitution) 양 경로 지원(커스텀 루프는 슬롯 상한·동일가중 비중을 리밸런싱일마다 갱신). **분위 그룹 실행**: `ranking_quantile_groups=G`(2~10)면 엔진이 rank_df·신호를 1회만 계산하고 그룹별 시뮬레이션만 G회 반복 — 메인 결과=1그룹(랭킹 최상위 구간, 사용자 SL/TP 유지), `quantileGroups`에 그룹별 요약(총수익률·CAGR·MDD·샤프·승률·거래수·최종자산+다운샘플 자산곡선 ≤300pt — 전체 format은 신호 목록까지 G배가 되어 응답·저장 페이로드 폭증)을 싣는다. 그룹 비교는 순수 리밸런싱 기준(손절/익절/보유기간 미적용 — 동일 규칙 비교)임을 경고로 고지, 랭킹 없음·리밸런싱 없음이면 조용히 빼지 않고 경고. **해석 레인**: RankingSpec.quantile_groups·PortfolioSpec.selection_percent 신설, _OUTPUT_SHAPE에 selection_percent 노출(형태에 없는 키는 9B가 안 채움)+규칙 2줄+예시 4-b(사용자 원문 그대로), 완결성 검증기가 편입 규모 기정의(지정 종목·비율·분위) 시 "상위 몇 종목?" 되묻기 억제, 파라미터 검증기 범위(비율 0<x≤100, 그룹 2~10), 컴파일러/디컴파일러 왕복(누락 시 수정 턴 전체가 레거시 레인 폴백). **함정 처리**: schemas.py RiskManagement·BacktestResponse 필드 선언(미선언=model_dump 조용한 소실, ranking_metric 0거래 사고 동일 함정), canonical DSL은 None 제거로 기존 strategy_id 해시 불변, 슬롯 판정 픽스처 재생성(export_slot_judgments.py). **프론트**: `QuantileGroupsSection` 신설 — 그룹별 막대 그래프(CAGR/총수익률/MDD 토글, 수익/손실 의미색 — dataviz 검증기 통과, 값 라벨은 텍스트 토큰)+지표 테이블+메인 그룹 강조, BacktestDashboard 배선, 매퍼/BacktestService에 quantileGroups 보존(누락=섹션 조용히 실종), getPositionLabel이 분위/비율 전략을 "최대 10종목"(물질화 기본값)으로 오표시하지 않게 분기. AgentsTab 완결성 검사에 되묻기 억제 항목 추가. 엔진 v9.3→**9.4**(순수 가산 — 새 파라미터 없는 기존 전략 결과 불변). 테스트 신규 20건(선정 헬퍼 분할 불변식·엔진 그룹 실행·비율 편입·해석 레인 왕복·매퍼·컴포넌트) — 백엔드 3,541·프론트 1,396 전체 통과(tsc 에러 3건은 stash 대조로 기존 확인). SRS FR-BT-060 | ✅ 완료 |
| 분위 그룹 전용 되묻기 + 그룹당 보유 상한 (2026-08-06) | 라이브 실측 후속 2건. **① 진행 카드 누락**: "10개 그룹으로 나눠 달라"가 정상 파싱됐는데 '현재까지 이해한 전략입니다' 카드에 그룹 내용이 없어 이해 못한 것처럼 읽힘 — builderProgressPresentation 요약 목록에 '분위 그룹' 행(그룹 수·메인 1그룹, cap 답변 시 '그룹당 N종목' 병기)과 '편입 비율' 행 추가(분위/비율 필드는 물질화 기본값이 없어 값 존재=사용자 발화, 명시 판정 불필요). **② 상황에 안 맞는 되묻기**: 분위 전략에도 일반 "포트폴리오에 최대 몇 종목?"(칩 5/10/20)이 나감 — 사용자 확인(AskUserQuestion)으로 의미를 **그룹당 N종목**(각 그룹이 자기 구간의 랭킹 상위 N만 보유, 전 그룹 동일 적용 = 비교 규칙 동일)으로 확정하고 전용 되묻기 신설: 질문 "각 분위 그룹에 최대 몇 종목을 담을까요?", 칩은 그룹 수(10) 이상에서 시작(그룹당 10/20/30종목, 사용자 지시). `ranking_group_cap` 전 계층 배선(ParsedStrategy·컴파일러 selection_count→cap·컨버터·schemas·시뮬레이터 band [:cap]) — cap은 물질화 없음이라 값 존재=답변(provenance 불요), 디컴파일러는 분위 모드 selection_count를 max_positions(물질화 10)가 아닌 cap에서 취해 라운드트립 보존(안 하면 모든 분위 수정이 레거시 폴백). 질문·칩·판정은 백/프론트 SOT 쌍(strategy_slots._QUANTILE_MAX_POSITIONS_QUESTION ↔ backtestReadiness.QUANTILE_MAX_POSITIONS_PROMPT) + 칩 답변 미러 2곳(_apply_prompt_overrides·applyDeterministicConditionChoice — 추출된 값의 자리 배정, 새 원문 해석 아님), 슬롯 픽스처 재생성 2회. 테스트 신규 15건 — 백엔드 3,535·프론트 1,404 전체 통과(tsc 에러 3건 기존). SRS FR-BT-060b | ✅ 완료 |

| 지표 온톨로지 Phase A — 전략 언어 계약 그래프 + 프롬프트 계층 어휘 + 콘솔 시각화 (2026-08-06) | LLM 의미 이해 안정화를 위한 지식 계층 논의에서 출발 — 범위는 "세상 모든 금융 지표"가 아니라 **엔진 지원 어휘의 계약 그래프**(잎 정본=IndicatorRegistry `_SPECS`, 재정의 금지). 신규 시드 `data/indicator-ontology.json`(git 추적, 수정만으로 성장·mtime 자동 재로드) + 로더 `strategy_conversation/registry/concept_ontology.py`: ① is_a 분류 계층 — 클래스 25종(이동평균/오실레이터/추세/밸류에이션/수익성 … 루트 class.indicator)에 전 잎 69종 완전 분류(미지원 18종 포함 — 라우팅 노드) ② 합성 개념 4종(golden_cross/dead_cross/price_vs_ma/macd_cross)의 전개 선언(expands_to factor·operator·정본 기본 파라미터 5/20, requires) — Phase C(전개 위임)의 사전 선언. 무결성은 로드 시 issues 채널(미존재 참조·순환·미분류 잎·전개의 허용 연산자/파라미터 위반·고아 클래스) + `test_concept_ontology.py` 8건이 CI 단언(새 지표를 _SPECS에 추가하면 '미분류 잎'으로 잡혀 시드 등록 강제). **프롬프트 배선(PROMPT_VERSION 2.7→2.8)**: 평면 supported_factor_lines를 온톨로지 생성 계층 어휘(`ontology_prompt_sections` — 분류 헤더+동일 잎 줄 표기)와 합성 개념 표기 정본(`concept_prompt_lines` — 규칙 5-3과 정합, 온톨로지가 SOT)으로 교체, class.*를 factor로 쓰지 말라는 가드 명시(Phase A는 출력 계약 불변 — 클래스 되묻기 Phase B·전개 위임 Phase C는 QA 게이트 후). **콘솔**: 지식 탭에 '지표 온톨로지' 서브탭 신설 — `IndicatorOntologyView`(포스 레이아웃 캔버스, 분류=파랑 다이아/지원 잎=청록/미지원 잎=회색/개념=주황 — KG 뷰 팔레트·도형 2차 인코딩 관례, 노드 98·엣지 97 규모라 전쌍 반발력), 이름·canonical ID·별칭 검색→카메라 포커스, 선택 노드 관계 패널("RSI –is_a→ 모멘텀/오실레이터")·지원 배지·연산자/단위, issues 배너. API: `/ontology/graph`(intent_routes, 읽기 전용)+`/api/admin/ontology/graph`(requireAdmin 404 은닉 프록시). 라이브 9B 스모크 3케이스(PER+포트폴리오+손절/사용자 기간 20/60 골든크로스 보존/배당 ETF+가격 vs 한 선 1/20) 전부 정상 파싱. 테스트: 백엔드 3,543·프론트 1,406 전체 통과(tsc 에러 3건은 기존 — stash 대조 기확인분). AgentsTab 미갱신(흐름 구조 불변 — 어휘 생성 교체+읽기 전용 뷰) | ✅ 완료 |

| 지표 온톨로지 Phase B — 클래스(계열) 발화 되묻기 (2026-08-06) | 사용자가 "모멘텀 지표 하나로 매수"처럼 **구체 지표 없이 계열만** 말하면, 종전에는 LLM이 임의 지표를 확정하거나 '알 수 없는 지표' 오류로 떨어졌다. **프롬프트 2.9 계약**: 계열 발화는 온톨로지 분류 ID(class.*)를 factor로 출력(구체 지표 무단 확정 금지, 예시 1-1), 잎을 말했으면 잎 ID(과사용 금지 문구 병기). **검증 레인 4곳**: ① capability_validator — class.*는 오류·미지원이 아니라 **선택 대기**로 통과 ② completeness_validator ③-0 — `.factor` 누락 필드 + 되묻기 질문("'모멘텀 지표' — 진입 조건에 어떤 모멘텀/오실레이터 지표를 사용할까요? (RSI, 스토캐스틱, …)", 역할 명시=답변 패치의 배열 귀속 근거, 선택지=온톨로지 정본 class_choice: 직속 지원 잎 표시명, 중간 분류는 자식 분류명) ④ compile_partial — 기존 `.factor` 정규식 매치로 pending_conditions 제외(라벨=source_text, 없으면 한글 분류명 — 내부 식별자 노출 방지 _condition_label 확장) ⑤ field_state — INVALID(엔진 실행 불가)가 아니라 정상 축(해결책=되묻기 답변, INVALID/NOT_APPLICABLE 판정 기준 준수). **칩은 내지 않는다** — 지표 선택 칩은 값 결속 계약(_bind_chips=_apply_prompt_overrides)이 성립하지 않아 노출 금지, 질문만 나가고(pending_question 에코로 귀속) 자유 서술 답변은 수정 인터프리터 레인이 처리. **답변 턴 계약(규칙 10-4)**: 고른 지표의 잎 ID로 조건 add 패치, 말하지 않은 임계값은 null(라이브 실측: 규칙 없이는 9B가 class ID 유지+값 30 날조 — 규칙 추가 후 잎 ID+null 정상), 선택지 표시명 답변("이동평균 크로스오버로")도 잎 ID 매핑(분류명 유사성 오매핑 실측 후 예시 보강, 재질문 루프 방지). 라이브 9B 검증 7케이스: 계열 발화 2(oscillator·moving_average)→분류 ID+선택지 질문, 잎 발화 1(RSI 30 이하)→과사용 없음, 답변 턴 4(RSI/스토캐스틱 20 이하/크로스오버/EMA)→전부 잎 ID·값 계약 준수. AgentsTab 전략 해석 흐름도 갱신(완결성 검사에 계열 되묻기 항목). 테스트 신규 12건(test_class_factor_clarification.py — 헬퍼·검증 4곳·라벨 폴백·잎 회귀 가드·프롬프트 계약) — 백엔드 3,555·프론트 1,406 전체 통과 | ✅ 완료 |

| 지표 온톨로지 Phase C — 합성 개념 결정적 전개 (2026-08-06) | 골든/데드크로스 관용 표현의 조립(연산자 crosses_above/below + 정본 기간 5/20)을 LLM이 매번 수행하던 것을 온톨로지 전개 선언으로 이관 — 연산자 표기 드리프트("golden_cross"·"above", 예시 4-7이 경고하던 사고류)와 파라미터 드리프트(2026-07-30 사고류)가 LLM 손을 떠난다. **시드 `llm_output` 플래그**: 개념별로 "LLM이 개념 ID를 factor로 출력하는 계약"을 선언(golden/dead cross만 on) — 무결성 검증이 플래그 개념의 전개 연산자 선언을 강제(비면 물질화가 방향을 지어내야 하므로 금지). **프롬프트 3.0**: 규칙 5-3 골든/데드 항목=개념 ID 출력(기간을 말했으면 그 값만 parameters에, 안 말했으면 비움 — 5/20 직접 채우기 금지), 합성 개념 섹션이 llm_output 여부로 계약 줄/표기 정본 줄을 나눠 렌더링(온톨로지 SOT), 예시 3·3-0·10-3(수정 턴) 갱신. **전개 지점=capability_validator 최선두**(수정 턴 patches도 validate_intent 경유라 동일 적용): factor→잎 치환, 연산자=선언 정본이 LLM 출력을 덮어씀(드리프트 정규화), 파라미터=사용자 값 우선·빈 자리만 정본 채움, 전개 후 일반 잎 경로(canonical 정규화·지원 판정) 계속. 가격 vs 한 선(short_period=1)·MACD는 현행 잎 표기 유지(이번 계약 대상 아님). 라이브 9B 검증 5케이스: 무기간+오타('골든크러스')→개념 ID+params 비움→5/20 물질화, 기간 명시(20/60)→사용자 값 보존+READY, 가격 vs 한 선·MACD 회귀 없음, 수정 턴 "데드크로스 나오면 팔아"→concept.dead_cross 패치→전개. **별건 발견(기존 드리프트, 미수정)**: "MACD 골든크로스"에 9B가 fast/slow/signal 12/26/9 파라미터를 방출 — 커밋본 2.7 프롬프트 주입 대조로 기존 동작 확인(이번 회귀 아님). parameter_validator가 '알 수 없는 파라미터' 오류 3건을 내지만 missing_fields가 없어 질문 없는 NEEDS_CLARIFICATION이 됨(컴파일은 정상) — MACD 골든/데드크로스의 llm_output 개념화가 자연스러운 후속 해법. 테스트 신규 8건(test_concept_expansion.py 6 — 정본 물질화·사용자 기간 우선·연산자 덮어쓰기·청산 역할·부분 기간·미지 개념 오류 / 온톨로지 2 — 계약 줄 렌더링·플래그 무결성) — 백엔드 3,562·프론트 1,406 전체 통과 | ✅ 완료 |

| MACD 골든/데드크로스 개념 승격 + 고정 기간 파라미터 정리 게이트 (2026-08-06) | Phase C 라이브 QA에서 발견한 별건(기존 드리프트, 2.7 대조 확인) 해소 — "MACD 골든크로스"에 9B가 fast/slow/signal 12/26/9를 습관적으로 방출해 parameter_validator '알 수 없는 파라미터' 오류 3건+질문 없는 NEEDS_CLARIFICATION이 되던 문제. **개념 승격(프롬프트 3.1)**: `concept.macd_cross`(정보용, 방향 미선언)를 방향별 llm_output 개념 2개(`concept.macd_golden_cross`/`concept.macd_dead_cross`, crosses_above/below 선언)로 분리 — llm_output은 전개 연산자 선언 필수라는 무결성 규칙 준수. 정본 기간이 없는 개념의 프롬프트 계약 줄은 "parameters는 항상 비움"으로 렌더링(concept_prompt_lines 분기), 예시 4-6 갱신(12/26/9 직접 채우기 금지 명시). **고정 기간 정리 게이트**: 시드 `fixed_parameters`(12/26/9) 신설 — 전개가 대상 잎에 선언되지 않은 이질 파라미터를 정리하되, 값이 고정값과 **같으면**(9B echo 드리프트) 의미 손실 0이라 조용히 정리하고, **다르면**(사용자 커스텀 기간) 조용히 버리지 않고 "커스텀이 지원되지 않아 표준 설정으로 실행됩니다" 안내(warnings→notices, 침묵 왜곡 방지). 라이브 9B 검증 3케이스: 맨 MACD 골든크로스→개념 ID+빈 params→**READY**(질문 없는 NEEDS_CLARIFICATION 해소), 재무+MACD 진입/청산 혼합→양방향 전개 READY, "MACD를 5, 35, 5 기간으로"→정리+커스텀 안내 정확 발화. 테스트 신규 4건+기존 2건 갱신 — 백엔드 3,566·프론트 1,406 전체 통과 | ✅ 완료 |

| 지표 자연 방향(polarity) + 랭킹 방향 기본값 교정 (2026-08-07) | 사용자 설계 지적("방향성이 없으면 팩터 합성 때 부호가 틀려 전략이 뒤집힌다")에서 출발. 조사 결과 **부호 지식이 엔진 표현식 한 줄에만 존재**했다 — 합성 랭킹(ranking_weight_value/quality)의 `1.0 - pbr_df.rank(pct=True)`(가치=낮을수록 좋음)와 `roe_df.rank(pct=True)`(퀄리티=높을수록 좋음)이 PBR/ROE 고정 하드코딩이라, 다른 지표로 확장하면 부호를 매번 손으로 맞춰야 했다. 더 직접적인 사고 경로도 확인: `RankingSpec.direction`이 `default="top"`이라 **LLM이 방향을 말하지 않은 것**과 사용자가 높은 순을 지정한 것이 구별되지 않았고, 'PER 기준 20종목'처럼 방향이 빠진 요청이 조용히 top으로 떨어져 저평가 전략이 '가장 비싼 종목 선정'으로 뒤집혔다(물질화 기본값이 명시로 둔갑하는 것과 같은 함정). **시드 polarity**: 지원 잎 51개 **전수 명시** 선언(lower_better 8·higher_better 25·none 18) — 무결성 검증이 미선언·유령키·값 오류를 CI에서 잡고, `none`도 명시 선언이라 침묵과 구별된다. **none을 억지로 채우지 않은 것이 설계의 핵심**(틀린 방향은 방향 없음보다 나쁘다): 시가총액(대형/소형=선호지 우열 아님), 배당성향(배당↑ 재투자↓), 투자·재무활동 현금흐름(성장기업은 음수가 정상 — Registry 주석과 정합), 오실레이터 전부(과매도 매수 vs 과매수 추종이 정반대 전략). **소비자 2곳**: ① 컴파일러 — `direction`을 Optional화해 미언급을 감지하고 `natural_ranking_direction`으로 채움(명시 방향은 재심 없이 보존 — polarity는 침묵을 채우는 장치이지 LLM 판정을 뒤집는 안전망이 아니다, 대원칙 1), top은 엔진 기본값이라 미저장(방향 미지정 기존 전략 strategy_id 불변 계약 유지) ② 프롬프트 3.2 — 어휘 줄에 `[낮을수록 선호]`/`[높을수록 선호]` 병기(none은 미병기, 어휘 비대 방지)+"direction은 사용자가 정렬 방향을 말했을 때만" 규칙. **해시 영향**: `ranking_direction`은 canonical DSL에 포함되므로 방향이 채워지면 그 전략의 strategy_id가 달라진다 — 신규 전략은 무해, 저장된 전략은 저장값을 그대로 실행하므로 영향 없음(의도된 교정). 라이브 9B 4케이스: 방향 미언급 'PER 기준 20종목'→9B가 병기를 보고 직접 bottom 출력(컴파일러 폴백은 2차 방어로 잔존), 'PER 낮은 상위'→bottom, 'PER 높은 순'→top 보존, '영업이익률 상위'→top. 테스트 신규 10건(무결성 4·방향 기본값 5·프롬프트 계약 1) — 백엔드 3,585·프론트 1,406 전체 통과. AgentsTab 완결성 검사 항목 갱신 | ✅ 완료 |
| 연간 재무 레코드 기간 정합 3종 수정 (2026-08-07, 엔진 v10.0) | 지배주주순이익 검증 중 "95%가 어긋나고 지배주주순이익이 당기순이익보다 크다"는 말이 안 되는 결과가 나와 추적하다 **기존 결함 3건**을 발견, 사용자 지시("1,2,3 순서대로", "3번째 결함도", "그것도 고쳐")로 전부 수정. **① KIS 분기 행 혼입**: KIS가 연간(`FID_DIV_CLS_CODE=0`)을 요청해도 최신 분기 한 행을 맨 앞에 끼워 보낸다(실측 확인 — `0`은 202603+202512+202412…, `1`은 전 분기). 그 행의 비율은 연환산돼 정상인데 유량만 1/4이라(현대차 ROE 89%·부채비율 101% vs EPS 25%·영업이익 22%·EBITDA 23%·당기순이익 25%) **최근 구간에서 PER 4배·순이익증가율 -75%**가 찍혔다. 3,220종목 중 2,150종목(67%) 해당. **판정 규칙을 두 번 고쳤다**: 1차 "결산월 최빈값과 다른 레코드 전부 삭제"는 결산기 변경 회사의 이력을 통째로 날려 테스트가 잡았고, 2차 "최신 한 행 + 월 비교"는 3월 결산 회사에서 **DART 레코드가 12-31로 잘못 라벨돼** 간격이 3개월로 보이는 바람에 정상 연간 21건을 오탐했다(적용 직전 눈으로 발견). 최종은 **최신 한 행 + 직전 레코드와의 간격 11개월 미만**. 수리 스크립트는 판정 시퀀스를 KIS 유래 레코드로만 만들고 DART 유래는 삭제 대상에서 제외한다. 2,278종목 3,168 레코드 제거 → 분기 최신 레코드 2,150 → 0. 현대차 PER 45→11.3, 순이익증가율 -75%→-21.6%(실제 YoY 일치). **② net_income을 DART 원값으로 교체**: KIS 순이익률(소수 2자리 반올림)×매출 재계산이라 저마진 연도에 절대금액 오차가 컸다(중앙값 1.1%, 순이익 10억 규모에서 수백 %). 검산용으로 이미 파싱하던 `ifrs-full_ProfitLoss`를 승격 — 같은 손익계산서라 `지배주주순이익 ≤ 당기순이익`도 정합. 2015년 이전·별도재무제표 구간은 KIS 재계산본 유지. parquet 반영은 **교체**라 `merge_fundamentals`(기존 값 우선)가 아니라 `rebuild_fundamental_columns`(캐시 우선)를 써야 한다. **③ DART 결산일 라벨**: `year_end`를 `{bsns_year}-12-31`로 고정해 비12월 결산 회사(23종목)의 DART 값이 엉뚱한 날짜에 붙어 KIS 값과 갈라졌다 — ①의 오탐을 만든 장본인. DART 전체재무제표 응답엔 기간 필드가 없어(`thstrm_dt` 없음, "제 41 기"만) 기업개황 `acc_mt`를 정본으로 쓰고, `bsns_year`=결산기가 끝나는 연도임을 실측 확정(효성오앤비 2023→KIS 2023-06 12.4억 일치, 금비 2024→2024-09 59.7억 일치). 결산월은 파일 캐시(`data/dart_fiscal_month.json`). 23종목 212 레코드 이동(대응 KIS 레코드가 있으면 병합, 없으면 라벨 교체). **④ 공시일 클램프 12월 하드코딩**(추가 지시): `사업보고서 (YYYY.12)` 정규식이라 비12월 결산 회사가 정정일 오염 보정에서 통째로 빠져 있었다("안전한 미클램프"로 주석돼 있었으나 실제론 그 회사들만 미보정). 결산월로 패턴 조립, `[기재정정]`도 걸리지만 연도별 min()이 원공시를 고르는 것을 회귀로 고정. 24종목 재클램프(097870 2023: 정정일 09-26 → 원공시 09-19). **엔진 9.4→10.0(MAJOR)**: ①이 최근 구간의 재무 필터·랭킹 통과 종목과 PER 기반 결과를 바꾼다(과거 이력은 전부 연간이라 불변, 저장 전략의 과거 결과는 재현 불가). **⑤ 연도별 결산월(이어서 지시)**: ③을 acc_mt(현재 결산월 하나)로 구현했더니 결산기를 변경한 회사의 변경 이전 연도가 여전히 틀렸다(유유제약 2015·2016은 당시 3월 결산인데 12-31에 남아 KIS 3월 레코드와 갈라짐). 사업보고서 이름이 연도마다 그 해 결산월을 달고 있어(`사업보고서 (2016.03)`) 이를 정본으로 승격 — 마침 ④의 원공시 접수일 조회가 같은 `list.json`이라 **두 정보를 한 번에** 얻도록 통합(`_fetch_dart_annual_report_periods`, 추가 호출 0). 조회 구간을 `_DART_YEAR_FLOOR+1`→`_DART_YEAR_FLOOR`로 넓혔다(6월 결산은 같은 해 9월 제출이라 이듬해부터 훑으면 FY2015가 빠진다). acc_mt는 공시 목록에 없는 연도의 폴백으로 강등. 13종목 58 레코드 추가 이동(유유제약 2015~2017이 KIS+DART 한 레코드로 병합), 해당 종목 available_from 재클램프. 남은 DART 단독 레코드 4건은 KIS가 아직 연간을 안 낸 최신 연도라 정상. 테스트 신규 28건, 백엔드 3,618 통과. **프로덕션 반영(2026-08-08)**: 잔여 838종목 백필 완료(2,501종목 전량, 누적 DART 약 40,300) 후 캐시를 프로덕션에 올려 현지 재구축. 재구축을 세 번 돌렸다 — ①은 배포된 옛 스크립트라 `owner_net_income` 보유 종목만 처리해 1,029종목을 건너뛰었고(분기 행 제거는 그 지표가 없는 종목에도 걸린다), 조건을 "캐시가 있는 모든 종목"으로 넓혀 재배포 후 ②, 그 사이 야간 동기화가 새 봉을 붙여 ③으로 메웠다. **스크립트 수정을 먼저 배포했어야 했다.** 프로덕션 실측: 현대차 PER 45→**11.19**, 순이익증가율 -75%→**-21.7%**. 부수 발견 → 아래 야간 보강 행. SRS FR-BT-052h | ✅ 완료 (프로덕션 반영 완료) |

| 벤치마크 오배정 수정 + 상장 이전 구간 뒤채우기 제거 (2026-08-07, 엔진 v11.0) | "백테스트 결과에 초과수익률을 보여줄까" 논의에서 출발 — 표시에 앞서 비교 대상 자체를 점검했더니 **벤치마크가 시장을 제대로 따라가지 않고 있었다.** ⓐ *오배정(값이 바뀜)*: `benchmark_for_universe`가 `universe_id`의 시장 토큰만 봤기 때문에, 지정 종목·테마 유니버스처럼 `universe_id`가 `None`인 백테스트(strategy_converter가 `target_symbols`가 있으면 None으로 지운다)는 **전부 기본값 KODEX 200**과 비교됐다 — 코스닥 종목만 담긴 전략도 마찬가지. 이제 보유 심볼의 실제 시장을 마스터 `market` 필드로 다수결 판정해(`universe_pit.dominant_market`, 동수는 KOSPI) 고른다. 또 코스피+코스닥 혼합 유니버스가 코스닥을 먼저 검사하는 순서 탓에 KODEX KOSDAQ 150과 비교되던 것을 KODEX 코스피로 교정(전 종목 지수가 대형주 200종목 지수보다 가깝다). 해당 백테스트들은 비교 지수가 달라져 `buyAndHoldReturn`이 바뀐다. ⓑ *0% 뒤채우기 제거(곡선이 바뀜)*: 벤치마크 정렬의 `.bfill()`이 지수 ETF 상장 이전 구간에 첫 가격을 뒤채워, 수익곡선에 초기자본에서 평탄한 가짜 선이 그려졌다(존재하지도 않던 지수). 이제 채우지 않고 `benchmark_equity`에 `null`로 내보낸다(schemas·types 원소 타입 확장). **검증 중 확인한 사실**: 뒤채우기 구간은 수익률이 0%라 누적곱이 커버리지 구간만 곱한 것과 같아 **`buyAndHoldReturn` 값 자체는 종전과 동일하다** — 왜곡은 값이 아니라 곡선과 *기간 불일치*(벤치마크는 자기 존재 구간만, 전략은 전체 구간 복리)에 있고, 이는 데이터로 메울 수 없어 경고 문구를 정확하게 고쳐 공시한다. ⓒ 프론트 `benchmarkLabelForResult`가 `universeId`로 라벨을 재추정하던 것을 제거 — 엔진 `benchmark_label`이 정본(ⓐ의 심볼 기반 판정과 어긋남 방지). **전략 자체의 매매·손익은 어느 쪽도 바뀌지 않는다.** FR-BT-020d 신설. 테스트 신규 12건(`test_benchmark_selection.py` 9 — 시장 매핑·혼합 순서·심볼 추론·명시 우선·폴백·다수결/동수/판정불가 / `test_result_handler.py` 3 — 커버리지 null·covered-window 수익률·전 구간 커버) — 백엔드 3,639·프론트 1,407 전체 통과(tsc 에러 3건은 기존 — stash 대조 확인). 초과수익률 표시 자체는 미착수(후속) | ✅ 완료 |

| 초과수익률 결과 표시 + KOSDAQ150 벤치마크 배선 (2026-08-08) | 벤치마크 정정(v11.0) 후속 3단계. ⓐ *KOSDAQ150 오배정*: 직전 커밋(`0401734a`)이 배선한 `kosdaq150` 유니버스 토큰을 벤치마크 선택이 몰라 **KODEX 200과 비교**되고 있었다(방금 고친 것과 같은 종류의 오배정, 실측 확인). 코스피200과 달리 코스닥150은 별도 지수 ETF를 쓰지 않고 코스닥 전체와 같은 상품이 벤치마크라 코스닥 계열로 묶었다. ⓑ *초과수익률 카드*: 결과 화면 '리스크 및 성과 분석' 첫 행, **최종 자산 오른쪽**에 `전략 총수익률 - 벤치마크 총수익률`을 %p로 표시(FR-BT-020e). CAGR 기준이 아닌 이유는 엔진이 벤치마크 CAGR을 산출하지 않고, 두 값을 다른 기간 환산 규칙으로 계산하면 잣대가 어긋나기 때문. 색은 같은 행 다른 지표와 동일한 무채색 — 전략·벤치마크가 모두 음수일 때 양수 초과수익률이 초록으로 뜨면 손실이 성과로 보이는 문제를 구조적으로 회피(툴팁에 "'덜 하락'이지 이익이 아니다" 명시, 규제상 평가 표현·우열 판단·정렬 키 사용 금지도 함께 명문화). ⓒ *비교 불가 시 숨김*: 엔진에 `benchmark_partial` 플래그 신설(result_handler → schemas 2곳 → types → 매퍼 5곳: backtestResultMapper· BacktestService·analytics/[id]·RunAllTestsModal·backtestCache) — true면 숫자 대신 `-`. 벤치마크가 구간 일부만 덮으면 두 수익률의 기간이 달라 차이가 비교값이 아니고, 경고 문구로 대체하면 사용자는 숫자만 읽는다. ⓓ *별건 수정(스크린샷 제보)*: 최종 자산·초기 자본 금액이 "7,175,050원 원"으로 표시됐다 — `formatKRW`가 이미 '원'을 붙이는데 셀이 `sub: "원"`을 또 붙였다. 테스트 신규 8건(백엔드 3 — kosdaq150 매핑·partial true/false / 프론트 5 — 카드 위치·%p·양쪽 손실·partial 숨김·'원 원' 회귀)+기존 1건 갱신(변동성 위치 +1→+2, 초과수익률이 사이에 들어옴) — 백엔드 3,660·프론트 1,417 전체 통과, tsc 신규 에러 0 | ✅ 완료 |
| 백테스트 결과값 전수 감사 + 지표 계산 정정 (2026-08-10, 엔진 v12.0) | "백테스트 결과 값들이 정확하게 계산되고 있는지" 요청으로 실데이터(8종목·2019~2024·141거래) 백테스트를 돌린 뒤 모든 결과값을 자산곡선·거래기록에서 교과서 정의로 재계산해 대조했다. **정확했던 것**: 체결가(시가×(1+슬리피지))·수량(floor(NAV×비중÷체결가) 정수주)·수수료·증권거래세·PnL이 원 단위까지 일치하고 `sum(거래 PnL) − totalProfit = 0.00원`, next_open 신호 1일 shift로 룩어헤드 없음, 마지막 봉 강제청산이라 미실현손익 미혼입. **고친 것 7가지**: ① *CAGR 연수*: '봉 수 ÷ 252'가 KRX 실제 거래일(2010~2024 평균 246.5일)보다 분모가 커서 연수를 2% 적게 세고 CAGR을 과대계상(실측 3.579% → 3.499%) → 달력 경과일 ÷ 365.25. ② *연환산 계수·표준편차*: √252 → KRX 실측 √246, 모집단(ddof=0) → 표본(ddof=1) — 종전은 변동성 과소·샤프 과대(18.934% → 18.714%, 0.2802 → 0.2768). ③ *1년 미만 CAGR*: 연환산하지 않은 총수익률을 CAGR 칸에 넣던 것(121봉 13.11%)을 정의대로 연환산(29.24%)하고 잡음 증폭 경고 추가 + 며칠짜리 퇴화 구간의 float 발산(OverflowError)을 표시 상한으로 차단. ④ *손익비 0 표시*: 손실 거래 0건이면 vbt가 inf를 주는데 `safe()`가 0.0으로 뭉개 **전승한 전략이 손익비 0(최악)·빨간색**으로 표시됐다(실측 재현) → `null`(표시 ∞). ⑤ *켈리 항상 0%*: 백엔드가 아예 계산하지 않아 프론트 `raw.kelly ?? 0`이 0을 채웠고 그 0이 AI 리포트 프롬프트에 "켈리 기준: 0.00%"로 사실처럼 주입됐다(계산 코드는 미사용 죽은 파일 `lib/backtest-engine.ts`에만 존재) → f* = W − (1−W)/R (R = 평균수익률÷평균손실률)로 신규 산출, 한쪽 표본 없으면 null. ⑥ *종목별 CAGR 분모 불일치*: vbt `annualized_return`(포트폴리오 초기자본 + 365일 연환산)을 써서 같은 행 totalReturn(종목 누적 진입원가 기준)과 분모가 어긋났다(005930: totalReturn 2.79% vs cagr 2.86%, 후자가 함의하는 총수익 17.97%) → 같은 분모로 연환산(0.46%). ⑦ *최대 연속패*: `1 - is_win`이라 손익 0 거래를 패로 셌다 → `pnl < 0`. **null 전파**: `?? 0`으로 되살아나지 않도록 타입(`profitFactor: number | null`)·매퍼 4곳·저장 경로 4곳(backtestCache 2·save-with-backtest·backtest-history)·점수/정렬 4곳·표시 5곳을 `lib/format-profit-factor.ts`(formatProfitFactor/profitFactorForRanking)로 일원화. **죽은 코드에서 발견해 함께 수정**: 마운트되지 않는 `BacktestStatsSummary.tsx`의 α가 `cagr − buyAndHoldReturn`(연율 − 6년 누적 = −48.5%p, 올바른 값 −29.2%p)이었고 `benchmarkPartial`을 무시했으며 지수 ETF 수익률에 "바이앤홀드" 라벨을 붙였다 → 셋 다 교정. FR-BT-020d-1/020d-2 신설. 테스트 신규 21건(백엔드 10 — time_base 달력/퇴화·1년 미만 연환산·PF null/유한·kelly 산출/null·종목별 CAGR 분모·본전 거래 연속패·ddof1×√246 / 프론트 11 — format-profit-factor 5·매퍼 3·StatsSummary 5). **후속 전수 재감사(같은 날)에서 null 미처리 소비처 5곳 추가 수정**: ① `/backtest` 디버그 로그가 PF null을 `:.2f`로 서식하다 TypeError → 광역 except가 'Engine error' 500으로 둔갑 — **무손실 백테스트가 로그 한 줄에 죽던 실장애**(`format_pf_for_log`로 우회) ② 배치 랭킹 스냅샷(batch-runs route)이 null→0(최악) 저장 → 999 상한 접기(클라이언트 스냅샷과 동일 규약) ③ AI 리포트 종합 점수(summarize.calculate_score)가 null=50점, 같은 공식의 프론트 3곳은 999→100점 — 키 부재(모름=50)와 명시 null(∞=상한)을 구별해 정합 ④ 리서치 최소 손익비 게이트(PrescreenGates)가 `or 0`으로 전승 전략을 탈락시킴 → inf 통과 ⑤ 최적화 리포트 표가 null을 0.00으로 표기 → ∞. 부수: 대시보드 툴팁 3곳의 √252 문구를 √246으로, 구버전 결과용 프론트 폴백 계산(변동성·소티노)도 √246·ddof=1로 엔진과 정합. FR-BT-020d-2에 소비처 계약(숫자 서식은 문자열 우회·점수/랭킹은 상한 접기) 명문화. 회귀 테스트 +8(백엔드 7·프론트 1) — 백엔드 3,688·프론트 1,431 전체 통과, tsc 신규 에러 0(기존 3건 stash 대조). **2차 후속(같은 날)**: 마지막 봉 청산 라벨을 날짜 도장(마지막 날짜=전부 "백테스트 종료")에서 실제 사유 우선으로 정정 — 시뮬레이터 확정 사유(exit_reason_overrides)·전략 신호 사유는 보존하고, 사유 없는 기말 강제 정산('데이터 종료' 포함)만 "백테스트 종료"로 표기(마지막 날 발동한 손절·리밸런싱 편출이 가려지던 문제, FR-BT-015b 보강). 수익률-근접 추론은 기말 정산과 우연 일치가 잦아 마지막 봉에서 비채택. 회귀 테스트 +3 — 백엔드 3,691·프론트 1,431 전체 통과. **매매·손익은 불변, 요약 통계만 바뀐다** — 저장된 과거 백테스트의 지표는 재현되지 않는다 | ✅ 완료 |

| 야간 보강이 새 봉의 null을 방치하던 문제 (2026-08-08) | 위 프로덕션 반영을 검증하다 삼성전자 최신봉만 재무값이 전부 null인 것을 발견해 추적. OHLCV 갱신(`sync_data.sync_symbols`)은 새 봉을 붙일 때 재무 컬럼을 null로 맞추는데(pykrx 응답에 없어 기존 컬럼 기준 `pl.lit(None)`), 뒤따르는 보강 단계의 스킵 판정이 `df["roa"].notna().any()`라 **한 행이라도 값이 있으면 영구 스킵**됐다. 그래서 그 null이 캐시 만료(90일) 전까지 채워지지 않았고, 최근 구간의 재무 필터·랭킹이 종목에 따라 통째로 비었다(캐시를 새로 올리면 만료 시계가 초기화돼 90일간 자가 복구가 안 걸린다는 점에서 이번 반영이 증상을 오히려 연장할 뻔했다). 판정을 **마지막 행** 기준으로 바꿔 매 동기화가 그날 붙인 봉을 그 자리에서 메우게 했다 — 보강은 결측만 채우므로(`merge_fundamentals`=기존 값 우선) 반복해도 기존 값을 덮지 않는다. 판정을 `needs_fundamental_enrichment()`로 분리해 회귀 4건 고정(새 봉 null=보강 / 끝까지 채워짐=스킵 / `roa` 컬럼 부재=보강(신규 팩터 배포 계약) / 캐시 만료=보강). **비용**: 종전 대부분 스킵되던 보강 단계가 매일 실제로 돈다 — 외부 API 호출은 없고(캐시 히트) 디스크·CPU라 3,220종목 기준 약 10분이 야간 배치에 추가된다. 백엔드 3,672 통과. SRS FR-BT-052i | ✅ 완료 (배포 완료, 다음 야간 동기화 로그로 최종 확인 예정) |
| 지표 온톨로지 사용 추적 로그 (2026-08-09) | "agent가 온톨로지를 어떻게 쓰는지"가 코드를 읽어야만 보이던 상태 해소 — 동작 변경 없이 관찰 채널만 신설. `concept_ontology.logger`(`console_logger`, 태그 `[ONTOLOGY]`)를 모듈에 두고 소비 지점이 가져다 쓰게 해 **한 태그 grep으로 한 요청의 온톨로지 개입 지점이 순서대로** 보이게 했다. 로그 지점 6종: ① 시드 로드·재로드(분류/잎/개념/LLM출력/polarity 개수+무결성 위반 — 위반은 WARNING 개별 출력) ② 프롬프트 어휘 주입(`ontology_prompt_sections` — 분류 섹션 수·잎 줄 수·섹션명 목록) ③ 프롬프트 개념 주입(`concept_prompt_lines` — 개념 줄 수·LLM 출력 계약 개념명) ④ 개념 전개(capability_validator — 개념명→잎 factor/연산자/파라미터, **LLM 원출력 병기**로 덮어쓴 값과 사용자 값을 구별, 커스텀 기간 드롭 여부) ⑤ 분류 발화 경로(capability 통과=선택 대기 / class_choice 선택지 조회 / completeness 되묻기 생성 / field_state 정상 축 / compile 표시명 폴백) ⑥ 랭킹 방향(`natural_ranking_direction` polarity→direction + 컴파일러 최종 확정 — 사용자 명시 여부와 저장값 병기, PER 방향 뒤집힘류 사고의 사후 추적점). 고빈도 조회(`is_class_id`·`concept_spec`)에는 로그를 달지 않았다 — 조건마다 3개 레인에서 호출돼 miss가 대다수라 노이즈만 남는다(효과가 발생한 지점에서만 기록). 스모크로 6종 출력 확인(골든크로스 전개 5/20 물질화·class.oscillator 선택지 6개·PER polarity→bottom). 동작·계약 불변이라 AgentsTab 미갱신. 테스트: 백엔드 3,672·프론트 1,417 전체 통과 | ✅ 완료 |

| 변동성 지표 지원 승격 + 의도 분류 오판 수정 (2026-08-10, 엔진 v13.1) | 사용자 신고: "변동성이 낮은 종목에 투자하는 전략"이 이해되지 않고 빈 빌더로 흘렀다. 원인 2겹: ① **의도 분류 흔들림** — 9B가 같은 문장을 10회 중 6회 STRATEGY_PICK(열린 추천)으로 오판해 정형 안내+빈 빌더가 나갔다('변동성'이 프롬프트 예시 지표 목록에 없어 "구체적 유형"으로 인정받지 못함). 분류 프롬프트에 "종목을 고르는 기준이 하나라도 명시되면(지표명이든 정성 표현이든, 지원 여부와 무관하게) STRATEGY_ADVICE" 규칙 추가 → 재현 4케이스×10회 전부 기대 라벨(변동성 문구 10/10, 기존 열린 추천 10/10 유지). ② **변동성 자체가 미지원** — 표준편차는 계산 가능하지만 엔진 지표·랭킹 배선이 없어 레지스트리 UNSUPPORTED였다. 승격(FR-BT-061): ⓐ technical `volatility` 필터 — N일(기본 60) 일수익률 롤링 표준편차×√246(결과 통계 v12.0과 동일 KRX 실측 계수 — 결과 화면 'Volatility'와 같은 눈금)×100, 매수 기본 `<=`(저변동성), NaN 워밍업 구간 신호 금지(indicators/signals/converter/nl_parser Literal) ⓑ `ranking_metric='volatility'` 저변동성 랭킹 — 모멘텀과 같은 계약(순위=진입·달력 리밸런싱·마스크 보존), **방향 미지정 기본 bottom**(무언의 top은 고변동성 선정으로 반전), 컴파일러는 온톨로지 polarity(lower_better)로 bottom을 채우되 **명시적 top은 None으로 접지 않고 저장**(엔진 기본이 bottom이라 재무 분기 규칙 그대로면 top이 삼켜짐 — 구현 중 발견) ⓒ 레지스트리 technical.volatility/ranking.volatility SUPPORTED + 별칭('변동성'→technical, '저변동성'→ranking) + 온톨로지 members/polarity ⓓ nl_parser '변동성' 큐는 **의도적으로 존치**(결정적 추출기가 표현 불가 → LLM 위임 신호, PCR 선례) + `concepts_expressed_in_strategy` volatility 술어로 반영 시 미지원 안내 억제 ⓔ 프론트 types IndicatorType·strategy-summary 라벨(변동성 N% 이하 배지·랭킹 라벨 기본 bottom 미러)·parse_validator 스키마 문서. E2E: 9B가 ranking.volatility/bottom으로 해석(unsupported 0). 테스트 신규 11건(`test_volatility_indicator.py` — 연환산 값·저/고변동 신호·컴파일 방향 계약 top 저장·표현-제외 술어) — 백엔드 3,707·프론트 1,433 전체 통과, tsc 신규 에러 0(기존 3건 stash 대조). 라이브 랭킹(가상계좌 live_signal_utils)은 'return'만 지원하는 기존 상태 유지(재무 랭킹과 동일 스코프). **후속(같은 날) — 기간·편입 규모 질문 검증 중 백분위 드리프트 발견·수정**: '200일 변동성'은 lookback_days=200으로 정상이나, '변동성 하위 10%만 편입'은 9B가 10을 portfolio.selection_percent가 아니라 랭킹 조건 value(unit percentile)로 실었고 그 조건은 검증기의 랭킹 이동에서 소거되어 **편입 규모가 조용히 사라졌다**. 이중 수정: ① 프롬프트 ranking.volatility 규칙에 비율 편입→selection_percent 명시 ② capability_validator 랭킹 이동에 결정적 백스톱 — unit이 percentile로 명시된 값만, 편입 규모(count·percent)가 비어 있을 때만 selection_percent로 자리 이동(맨 값은 연환산 % 임계값과 구별 불가라 미이동). E2E 2형상 재검증 + 회귀 3단언 추가 — 백엔드 3,708 통과. **후속 2(같은 날) — 산정 기간 되묻기 추가**(사용자 요청: N일 변동성을 고를 수 있게): 변동성 랭킹에서 기간 미지정 시 기본 60일을 조용히 물질화하지 않고 "변동성 산정 기간을 며칠(거래일)로 할까요?"를 되묻는다(completeness_validator ④-0) + 칩 60/120/200일(_SLOT_CHIP_BUILDERS, topic 매수 조건). 칩 결속은 _apply_prompt_overrides의 정본 표기 에코 인식('변동성산정기간N일')으로 성립 — 미지원 큐 r"변동성"이 칩을 노출 금지시키는 충돌은 '산정기간' lookahead 제외로 해소(발견 경위: 칩 전수 결속 회귀 테스트가 잡음). 모멘텀 랭킹은 기존 계약 유지(스코프=변동성만). AgentsTab 검증 흐름 항목 추가(되묻기 조건 추가라 동기화 대상). 회귀 +3(되묻기 발생/기간 명시 시 미발생/칩 에코 결속). **후속 3(같은 날) — 질문이 화면에 안 나오던 원인 수정**: 백엔드는 질문을 정상 발행했지만(라이브 curl 검증) 우선순위 마커 없는 백엔드 질문은 프론트 explicit 게이트(시장 질문)가 삼킨다(page.tsx presentedClarification 순서). 값-대기 조건 질문의 기존 계약(pending_values, 2026-08-03)에 산정 기간 질문을 편입 — 첫 질문 field가 strategy.ranking[0].lookback_days면 마커를 붙여 게이트에 밀리지 않게 함. 라이브 재검증(priority=pending_values) + 회귀 1건(test_primary_volatility_lookback_question_gets_priority) — 백엔드 3,713 통과. **후속 4(같은 날) — 매매 검증 요청이 backfill 오염 발견(엔진 v13.2)**: 사용자 요청('매매 전날 실제로 변동성 하위였는지 검증')으로 2022-07-01 매수 10종목의 120거래일 변동성을 전 종목 재계산 대조. 9종목은 실제 하위 0.6~1.7%로 정상이나 ① 상장 21일째 마스턴프리미어리츠가 매수됨(120일 변동성 정의 불가) ② 표시 백분위 6~7%가 재계산(0.6~1.7%)과 불일치. 원인: 변동성 랭킹이 ffill+**bfill**된 price_df로 계산 — 상장 전 구간이 첫 가격으로 평평하게 뒤채워져 수익률 0 → 신규 상장 종목이 가짜 초저변동으로 위장 선정되고 하위권을 채워 백분위도 부풀림. 수정: bfill 전 raw_price_df에 ffill만 적용하는 annualized_volatility_panel(engine/indicators.py) 신설·배선, 관측 120개 미만은 NaN(후보 배제). 실데이터 대조로 수정 전(오염 근사=마스턴 포함)/후(마스턴 제외) 재현 확인. 모멘텀 'return' 랭킹도 같은 bfill 패널 사용(상장 후 실수익률 계산이라 성격 다름) — 범위 밖으로 보류·기록. 회귀 1건(backfill 위장 재현+엄격 패널 NaN) — 백엔드 3,714 통과 | ✅ 완료 |
| 값 없는 발화("리스크 관리")의 임의 값 확정 4중 사고 수정 (2026-08-10) | 사용자 신고: 전략 작성 재개 후 "리스크 관리"라고 조건 주제만 말했는데 익절 8%가 임의 확정됨. trace 추적으로 4중 원인 확정 — 재개 시 익절 되묻기(pending_ask)가 상태에 살아 있는데 화면에는 일반 안내만 나갔고, "답이면 값만 말했더라도 패치로" 프롬프트 압박에 9B가 초안의 손절 8을 복사한 take_profit=8.0 패치를 냈고, 첫 출력의 자기 의심 질문("익절 기준을 의미하는 것인가요?")은 절단 JSON 수리 재요청이 지워 자기 의심 게이트가 침묵했고, 환각 게이트는 발화 전체 인용("리스크 관리")의 실재만으로 통과시켰다(무숫자 인용이 숫자 값을 대신 통과). 4중 수정: ① 프론트 RESUME 턴이 열려 있던 되묻기를 선택지와 함께 재표시(page.tsx control_workflow — 부가 발화 질문 복원 § 21과 같은 원칙, 일반 안내 "다음으로 정할 조건을…"은 질문 없을 때만) ② 수정 프롬프트(3.3) 값 없는 답 규칙 — 값을 지어내지 말고 초안의 다른 필드 값 복사 금지, intent=CLARIFY_STRATEGY+clarification_questions로 질문 유지(기존 primary_modify_clarify 경로가 표면화) ③ 수리 재요청 내용 보존 — 수리 프롬프트에 patches·clarification_questions 삭제 금지 지시 + 수리 성공 후 질문이 비면 원출력에서 배열만 형식 추출해 결정적 병합(salvage_clarification_questions, 스키마 재검증 통과 시에만 — EOF 절단의 조용한 완성 금지 계약은 불변) ④ 환각 게이트 숫자 근거 규칙 — 숫자 스칼라 패치는 인용 또는 입력에 숫자가 실재해야 통과(조건 객체 dict의 내장 기본 파라미터는 대상 아님 — '데드크로스' 구제 유지), 전량 거부 시 기존 계약대로 전략 유지+열린 질문 재부착. AgentsTab 수정 파이프라인 환각 게이트 항목 갱신. 기존 테스트 1건 픽스처 조정(PatchError 폴백 테스트의 값이 우연히 숫자 스칼라 — 목적 보존 위해 문자열로). 회귀 테스트 +7(프론트 1 — RESUME 질문 복원 / 백엔드 6 — 프롬프트 규칙 2·salvage 추출·수리 프롬프트 계약·질문 복원 병합·게이트 숫자 근거) — 백엔드 3,719·프론트 1,434 전체 통과, tsc 신규 에러 0(기존 3건 stash 대조) | ✅ 완료 |

| 손절·익절 '안 함' 선택지 추가 (2026-08-10, FR-BT-062) | 사용자 지시: "리스크 관리 물어볼 때 익절·손절 창에 '안 함' 옵션칩을 추가". 종전에는 손절·익절이 백테스트 최소 조건 게이트의 필수 슬롯이라 **값을 넣어야만 실행 버튼이 나왔다** — 손절 없이 리밸런싱으로만 회전하는 전략을 만들 수 없었다. 표현 방식 결정: 값 센티널(0)은 `enforce_strategy_minimums`가 "비율은 0%보다 커야 한다"로 이미 거부하는 값이라 쓰면 그 가드를 무력화해야 한다 → **리밸런싱 '안 함'과 같은 거부 상태 채널**을 택했다(스키마 null은 "아직 안 물었다"와 구분 불가). 배선: ⓐ **판정 정본**(engine/strategy_slots.py) — `DECLINABLE_FIELDS`(리밸런싱·손절·익절) + `evaluate(declined_fields=)`, `_decided ②`가 거부를 CONFIRMED로 확정(해당 없음이 아니다 — 물을 수 있었지만 사용자가 안 하기로 정한 것). **값이 있으면 값이 이긴다**(거부 후 값 입력 시 화면과 판정이 어긋나지 않게, 프론트도 같은 순서) ⓑ **거부 칩 정본표** `DECLINE_CHIP_FIELDS`('손절 안 함'·'익절 안 함') + 슬롯 질문 칩에 추가 ⓒ **칩 결속 3번째 채널** — 거부 칩은 값을 바꾸지 않아 `_apply_prompt_overrides` 값 대조로는 영원히 탈락(=노출 금지)하므로 `chip_declines`로 결속(확정 칩 `chip_confirms` 선례), output_guard도 같은 계약으로 생존 칩만 남김 ⓓ **거부 칩 클릭 레인** `run_chip_answer` → `primary_chip_decline`(전략 값 불변, 거부 목록에 기록 후 다음 질문 재계획) ⓔ **무상태 에코** `previous_declined_fields`/`declined_fields` + `merge_declined_fields`(explicit_fields와 **분리** — "말한 값이 있다"와 "값이 없는 게 결정이다"는 다른 축이라 한 목록에 담으면 값 유무 판정이 둘을 구분 못 한다), 거부를 만들지 않은 턴은 이월 ⓕ 게이트·플래너 state_summary·`_is_filled_slot_topic`·수정 레인 재계획까지 관통(한 곳만 모르면 그 경로가 다시 묻는다) ⓖ **프론트**: SLOT_PROMPTS 칩 '안 함', `isSlotFilled` 거부 분기, `declinedFieldsRef`(세션 스냅샷·에코·되돌리기 복원), 요약 카드 '손절 안 함' 표기(값이 없다고 항목이 사라지면 답한 것이 사라진 것처럼 보인다), 누적 프롬프트에는 자기완결 문구("손절 안 함")로 기록. **원문 정규식은 늘리지 않았다** — 리밸런싱 거부의 레거시 원문 판정(`_mentions_rebalancing_negation`)을 손절·익절로 확장하는 대신 칩 클릭이 만든 사실을 구조화 채널로 나른다(대원칙 1). 계약 픽스처 3케이스 추가·재생성(거부 1개·2개·거부 후 값)으로 백엔드 정본과 프론트 게이트 일치 검증. 테스트 신규 15건(백엔드 8 — 슬롯 판정 4·칩 결속/클릭/누적/게이트 4 / 프론트 7 — 거부 칩 4·게이트 판정 3) + 기존 기대값 4건 갱신(칩 목록에 '안 함' 추가) — 백엔드 3,728·프론트 1,448 전체 통과, tsc 신규 에러 0 | ✅ 완료 |

| 되묻기 두 질문 병합 버블 수정 + 질문 문구 평이화 (2026-08-10) | 사용자 신고: "상대 모멘텀 효과를 이용한 투자 전략" 파스에서 랭킹 지표 선택 질문과 청산 질문이 **한 버블에 함께** 나갔다("한 번에 한 가지만 물어봐야 한다") + "뭘 물어보는지 모르겠다, 설명이 너무 어렵다". **원인(병합)**: 한 턴에 한 질문 분할(2026-08-03)은 첫 질문의 pending_ask 결속이 성립할 때만 동작했다 — 첫 질문이 무칩(지표 선택 되묻기는 칩 결속 계약상 칩을 내지 않음)이면 `_pending_ask_payload`가 None을 내고, 큐를 실을 곳이 없다는 이유로 전체 질문 병합 폴백이 한 버블에 2~3개를 내보냈다. **수정**: 무칩 ask(`chips: []`)를 큐를 나르는 그릇으로 허용 — ① primary 분할 분기: 결속 실패 시 병합 폴백 대신 무칩 ask+queue 발행(답변은 자유 서술로 수정 레인이 받고 그 턴이 큐 소비) ② `_next_ask_from_queue`: 큐 중간의 무칩·결속 탈락 항목에서도 남은 큐를 잃지 않게 동일 계약 ③ output_guard `finalize_user_response`: 칩 0개면 ask를 통째로 지우던 관문 완화(질문이 살아 있으면 유지 — 지우면 큐가 함께 소실). **문구 평이화**(사용자가 본 두 질문만, 규칙 10-4의 진입/청산 키워드 보존): 지표 선택 질문 역할 라벨 "진입"→"매수(진입)"(청산도 동일)·선택지를 "…중에서 고를 수 있습니다" 문장으로, 청산 질문 "청산 규칙이 없습니다"→"매수한 종목을 언제 팔지(청산 규칙)가 아직 정해지지 않았습니다"+방식 예시를 일상어로(종목 교체(리밸런싱)·손실/이익에서 매도(손절/익절)). AgentsTab 되묻기 항목·분류 되묻기 인용 문구 동기화. 회귀 +1(`test_primary_chipless_first_question_still_asks_one_at_a_time` — 무칩 첫 질문 단독 발행+큐 이월+칩 노출 금지 유지) + 기존 문구 단언 3건 갱신 — 백엔드 3,728·프론트 1,448 전체 통과(프론트 1회 플레이키 후 재실행 전건 통과), tsc 신규 에러 0(기존 2건 무관 테스트 파일) | ✅ 완료 |

| 열린 추천 안내문·빌더 이해 복창 동시 노출 수정 (2026-08-10) | 사용자 신고: "상대 모멘텀 효과를 이용한 투자 전략"에 열린 전략 추천 안내문("어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만…")과 빌더의 시드 이해 ack("좋아요. 모멘텀 전략(으)로 이해했어요")가 **함께** 나갔다 — "안내문은 추천을 요청받았을 때만, 이해했으면 필요 없다. 둘 중 하나만". **원인**: 분류 LLM이 구체 설계 요청을 STRATEGY_PICK(열린 추천)으로 오판 → 프론트 start_builder 분기가 안내문을 **빌더 실행 전에 무조건** 내보내고, 빌더는 시드에서 모멘텀을 이해해 ack를 또 냈다. 분류 재심(정규식)은 금지(대원칙 1)이므로 **이해 여부의 정본인 빌더 판정을 표시 근거로 배선**: ① `StepResult.seed_recognized` 신설 — 시드 적용 직후 상태로 `_seed_summary` 판정(초기 ack와 동일 판정), JSON·SSE 두 라우트 동일 계약, 시드 턴에만 실림 ② 프론트 start_builder: STRATEGY_PICK 안내문(reason=classified_strategy_pick)은 즉시 내보내지 않고 빌더 첫 응답을 본 뒤 결정 — seed_recognized=true면 생략(ack만), false(진짜 열린 요청)면 첫 질문 버블 앞에 병합해 표시(호출 실패 시엔 종전대로 표시). STOCK_PICK·ONBOARDING 안내는 기존 동작 유지(스코프=사용자 지시 범위). 부수: 열린 요청 케이스의 안내문이 별도 버블→질문과 한 버블로 합쳐져 스크롤 테스트 2건의 정확 일치 단언을 부분 일치로 갱신. AgentsTab 빌더 진입 노드 갱신. 회귀: 백엔드 +4(`test_builder_step_stream.py` — 구체 시드 true·열린 시드 false·후속 턴 미적재·SSE 계약)+프론트 +2(`page.strategy-pick-notice.test.tsx` — 이해 시 안내 생략·미이해 시 안내+질문) — 백엔드 3,732·프론트 1,450 전체 통과, tsc 신규 에러 0 | ✅ 완료 |

| '상대 모멘텀 효과' = 기존 모멘텀 랭킹으로 직결 해석 (2026-08-10, 프롬프트 3.4) | 사용자 판정: "'상대 모멘텀 효과를 이용한 투자 전략'은 우리가 이미 알고 있는 모멘텀 전략이다 — 새로 만들지 말고 원래 모멘텀 전략 프로세스를 이용하라". 종전에는 9B 인터프리터가 이 발화를 계열 발화(class.ranking)로 격하해 "어떤 랭킹 지표를 사용할까요?"를 되물었다(옵션칩 노출 검토 중 방향 전환 — 칩 설계 불필요해짐). 수정: 인터프리터 프롬프트 랭킹 규칙에 "'모멘텀 전략'·'상대 모멘텀 (효과)'·'모멘텀 투자'처럼 **전략 자체를 이름으로** 말한 입력은 class.*가 아니라 ranking.return"(플랫폼의 모멘텀 전략=기간 수익률 랭킹 하나로 정해져 있어 되물을 필요 없음) 명시 + "모멘텀 지표 하나 골라줘"(오실레이터 선택)와의 구분 병기. 정규식 추가 없음(대원칙 1 — 의미 판정은 LLM 레인에서 수정). E2E 9B 실측: '상대 모멘텀 효과를 이용한 투자 전략' 2/2 → ranking.return(60일)+「상위 몇 종목을 선택할까요?」(기존 모멘텀 흐름·확정 칩 결속), '모멘텀 지표를 하나 써서'는 종전대로 class.oscillator 되묻기 유지. 관찰(기존 동작·미수정): '모멘텀 전략으로 백테스트 해줘'는 intent=RUN_BACKTEST로 파스 대상에서 제외됨(규칙 0 회색지대). 회귀 +1(`test_prompt_declares_momentum_strategy_name_is_ranking_return` — 프롬프트 계약 고정) — 백엔드 3,733·프론트 1,450 전체 통과 | ✅ 완료 |

| 모멘텀 산정 기간 60일 강제 폐지 — 되묻기+칩 (2026-08-10) | 사용자 지시: "60일이라고 강제하지 말고 사용자가 고를 수 있게 해줘. 옵션칩과 직접입력칩을 보여줘". 종전에는 ① 인터프리터 프롬프트 랭킹 규칙이 ranking.return 예시에 lookback_days:60을 박아 두어 기간을 말하지 않아도 LLM이 60을 물질화했고 ② 프론트 요약 라벨(`getRankingLabel`)도 `?? 60` 폴백으로 "60일 수익률 상위"를 표시했다. 변동성 산정 기간 되묻기(같은 날 후속 2)와 **완전히 같은 계약으로 모멘텀을 합류**: ⓐ 프롬프트(랭킹 규칙) — 기간 미언급 시 lookback null 명시("임의로 60을 채우지 마세요"), 명시된 예시 4·4-3(60일 언급)은 그대로 ⓑ completeness ④-0을 가격 산출 랭킹 공통(변동성·수익률 라벨 분기)으로 확장 — "수익률 산정 기간을 며칠(거래일)로 할까요?"+추천 60 ⓒ 칩은 지표별 문구가 달라 `_SLOT_CHIP_BUILDERS` 표에서 `_clarification_items` 직접 생성으로 이동(변동성 60/120/200일·수익률 60/20/120일, topic 매수 조건, +프론트 자동 직접 입력 칩) ⓓ 칩 정본 표기 에코 인식을 `(?:변동성\|수익률)산정기간N일`로 확장(nl_parser — 어휘 확장이 아니라 칩 자리 배정) ⓔ 우선순위 마커(pending_values)는 field 기준이라 그대로 모멘텀 포함 ⓕ 프론트 라벨 — 기간 null이면 "수익률 상위(산정 기간 미정)"(60일 표시=조용한 확정으로 읽힘), 변동성도 동일. E2E 9B 실측: '상대 모멘텀 효과를 이용한 투자 전략' → lookback null+「수익률 산정 기간을 며칠(거래일)로 할까요?」+칩 3개 전부 값 결속+후속 질문(종목 수·리밸런싱) 큐 이월. 기존 테스트 2건 조정(모멘텀 60 물질화 전제·READY 컴파일 픽스처에 기간 명시). 회귀 +4(completeness 수익률 되묻기/기간 명시 시 미발생/재무 랭킹 제외·수익률 칩 에코 결속·primary 우선순위+칩+결속·라벨 미정 표시) — 백엔드 3,734·프론트 1,451 전체 통과, tsc 신규 에러 0 | ✅ 완료 |

| 모멘텀 랭킹 상장 전 backfill 오염 수정 (2026-08-11, 엔진 v13.3) | 사용자 요청("이 종목들이 실제로 매매 전날 수익률 상위였는지 확인")으로 2023-12-01 매수 10종목을 전 종목 재계산 대조. **검증 결과**: 유니버스가 코스피 전용임을 확인한 뒤 KOSPI 804 후보 재계산 상위 10 = 매수 10종목 집합 완전 일치(표시 백분위 8/10 정확 일치, 2건은 반올림 경계+상폐 포함 수·배당 보정·창 시작일 미세 차이). 단 **상장 10거래일째 에코프로머티·40거래일째 두산로보틱스의 '60거래일 수익률'은 실제로는 상장 이후 수익률** — 모멘텀 랭킹이 ffill+bfill된 price_df의 pct_change로 계산돼 상장 전 구간이 첫 가격으로 뒤채워진 것(v13.2에서 변동성만 고치고 모멘텀은 '성격 다름'으로 보류했던 잔여분). 사용자 지시("일괄 적용 — 다른 곳에서 같은 문제 안 나오게")로 수정: `engine.indicators.lookback_return_panel` 신설(bfill 전 raw_price_df에 ffill만, annualized_volatility_panel과 같은 계약) + 엔진 'return' 분기 배선 — 상장 후 lookback 봉 미만은 NaN → valid 마스크가 후보 배제. **일괄 점검**: 변동성 랭킹=v13.2 기수정, 재무 팩터 랭킹=조회 기간 없음(해당 없음), 라이브 신호(live_signal_utils)=자기 봉 수 검사(`row_index-lookback>=0`)로 원래 안전, 조건식 지표(technical.volatility 등)=종목별 자기 데이터 계산이라 무관 — 백테스트 모멘텀 랭킹이 유일한 잔존 오염 경로였다. 수정 후 재계산: 에코프로머티·두산로보틱스 제외, 한국단자공업·종근당 편입(상위 10 재구성). 관측 미달 신규 상장이 편입되던 모멘텀 전략은 매매·통계가 바뀐다(저장된 과거 결과 재현 안 됨). 회귀 +2(`test_momentum_ranking_guard.py` — bfill 위장 재현+엄격 패널 NaN·관측 충족 시 정의) — 백엔드 3,736·프론트 1,451 전체 통과 | ✅ 완료 |
| '소형주 전략 만들어줘' 오분류·고아 스피너 수정 (2026-08-11) | 사용자 보고 2건 동시 수정. **① 고아 '분석 중...' 스피너**: 08-10 안내문 보류 변경(STRATEGY_PICK 안내를 seed_recognized 확인 뒤로 미룸)이 분류 자리표시자의 유일한 소비자(emitAssistant)를 건너뛰게 만들어, startStrategyBuilder가 두 번째 로딩 버블을 새로 붙이고 첫 버블이 로딩 상태로 영원히 남았다. start_builder 디스패치가 안내문을 즉시 내보내지 않은 턴엔 자리표시자를 빌더 첫 질문으로 재사용(`reuseExisting: placeholderShown && !introEmitted`). 회귀: `page.strategy-pick-notice.test.tsx` 2케이스에 스피너 부재 검증 추가(수정 제거 시 2건 실패 확인) **② 추천 불가 안내문 오출력**: 9B 분류가 '소형주 투자 전략을 만들어줘'(4/5)·'중소형주 전략 하나 만들어줘'(5/5)를 STRATEGY_PICK으로 오분류 — 시총 규모 표현을 종목 선별 기준으로 인식 못 함. 분류 프롬프트에 "대상 범위를 좁히는 표현(시장·업종·테마·시총 규모)도 기준" 명시 → 실측 60/60 정답(통제군 열린 요청 3종은 STRATEGY_PICK 유지). 라이브 회귀 게이트 `scripts/qa_intent_open_pick_scope.py` 신설 **③ 백스톱 확대**: seed_recognized가 ack 요약(_seed_summary) 전용이라 유니버스만 이해한 시드('코스피 전략 만들어줘')도 안내문이 나가던 모순 — 유니버스 인식을 시드 이해로 인정(ack에는 미포함, 첫 질문 생략으로 드러남). 회귀 +1(`test_builder_step_stream.py`), AgentsTab 열린 추천 전환 desc 동기화 — 백엔드 3,737·프론트 1,451 전체 통과 | ✅ 완료 |
| '소형주'=시가총액 조건 이해 + 임계값 선택지 되묻기 (2026-08-11) | 사용자 지시("소형주=시총 작은 종목, 작은 시가총액을 옵션으로 보여줘 고를 수 있게"). 종전엔 LLM 인터프리터가 '소형주'를 몰라 빈 전략+산발적 되묻기("특정 종목인가요? 업종인가요?")로 조건이 조용히 소실. **① 인터프리터 프롬프트 규칙 2-1 신설**: '소형주'·'중소형주'·'시가총액이 작은' 등 시총 규모 표현 → `fundamental.market_cap <= null` 조건(임계값 지어내기 금지, universe.markets 금지, '무슨 뜻인지' 되묻기 금지). '대형주'=KOSPI200 지수 매핑은 유지. 라이브 실측: 소형주·중소형주 모두 market_cap 조건+값 되묻기로 해석 **② 시총 상한 임계값 되묻기 칩 다중화**(`_clarification_items`): 추천값 1개 칩 → "시가총액 5000/1000/3000억원 이하" 3개 제시(사용자 선택), 기존 정본 표기 그대로라 값 결속(_bind_chips) 3/3 성립 — 시총 하한(이상)은 종전 단일 칩 유지. 전구간 라이브 검증: run_primary_parse('소형주 투자 전략을 만들어줘') → 질문+칩 3개 결속(ask_gate=ok)+pending_conditions('시가총액'/소형주) 확인. 회귀 +2(test_slot_clarification_chips 26건) + 평가 데이터셋 parse_cases.json small-cap 2건(missing_value_factors 게이트) — 백엔드 3,739·프론트 1,451 전체 통과 | ✅ 완료 |
| 이월 큐에서 슬롯 질문 제외 — 기존 슬롯 되묻기로 잇기 (2026-08-11) | 사용자 보고: '소형주' 시총 기준값 칩을 고른 뒤 **큐에 실려 있던 청산 슬롯 질문이 전용 문구+전용 칩(매월/분기 리밸런싱·20일 보유·손절 -10%)으로 새 박스를 만들었고, 그 칩을 골라도 슬롯이 채워지지 않음** — "그 다음부턴 우리가 이미 가지고 있는 걸 보여주면서 슬롯을 채우면 돼. 원래 있던 걸 사용해줘". 원인: 검증 리포트의 슬롯 질문(청산·종목 수·리밸런싱·손절 등)이 값-대기 질문과 함께 pending_ask.queue에 실려, 칩 답변 뒤 `_next_ask_from_queue`가 pending_values 우선순위로 표면화 → 프론트 explicit 게이트의 정본 슬롯 박스를 덮어씀(같은 슬롯 되묻기 두 벌). 수정: `_clarification_items`에 slot 표식 추가, 큐 구성에서 슬롯 질문 제외 — 큐가 나르는 것은 진행 골격이 묻지 않는 질문(조건 기준값·파라미터)뿐. 슬롯 되묻기는 답 반영 후 기존 기제가 정본 문구·칩으로 잇는다(main 최소 조건 게이트 gate_pending_ask 결속 칩·재계획 planner의 슬롯 SOT 폴백·프론트 explicit 게이트). 나를 큐가 없으면 무칩 ask도 생성하지 않음(08-10 무칩 ask=큐 운반용 계약의 자연 귀결). 라이브 확인: T1 시총 질문 큐 없음 → 칩 클릭 → 질문 없음 → 게이트가 정본 슬롯 박스 발행. 회귀: test_strategy_conversation 슬롯 비이월 +1, 08-10 무칩 큐 테스트를 새 계약으로 갱신. AgentsTab 이월 큐 desc 동기화 — 백엔드 3,740·프론트 1,451 전체 통과 | ✅ 완료 |
| 분류 레인 계측 + 커버리지 프로브 (2026-08-11) | 사용자 질문("무슨 뜻인지 알아듣는 힘을 길러 예상 못한 질문에 대응하고 싶다")에서 출발. 전략 파싱 레인은 Trace가 완비돼 있었으나 **분류·일반답변 레인(`api/intent_routes.py`)에는 span이 하나도 없어**, 예상 못한 질문이 어느 라벨로 떨어지는지 사후 조회가 불가능했다. ① `/query/classify`에 루트 span(라벨·근거·`workflow_effect`·인식 종목·해석 실패 여부), `generate_general_answer`에 `root=False` span(`source`=platform_defaults/llm/none, `grounded`) 추가 — 관찰 계층 계약대로 실행 경로 불변. chokepoint 5→7. ② 읽기 전용 조회 스크립트 `backend/scripts/report_intent_coverage.py`(라벨 분포·게이트에 끊긴 발화·못 알아들은 발화). ③ 합성 커버리지 프로브 `backend/scripts/qa_intent_coverage_probe.py` — 11유형 42문항, **정답 라벨을 적지 않고 유형만 붙여** 실제 라벨 분포를 관측(작성자 추측이 데이터로 위장되는 것 방지). 첫 실행 결과: 정형 안내로 끊김 15/42, 못 알아들음 5/42, 해석 실패 2건 — 종목 사실 조회 6건이 판단 요청 3건과 같은 `STOCK_ANALYSIS` 거절로 묶이는 것(규제상 허용 범위인데 막힘)과, 사전에 예상하지 못한 **결과 해석·대화 메타 유형의 라벨 부재**를 발견 | ✅ 완료 |
| 읽기 전용 라벨 신설 — 진행 상태 되묻기·결과 수치 설명 (2026-08-11, FR-SA-002c-8) | 커버리지 프로브가 찾은 구멍. **원인 규명**: "해석 실패"로 보고되던 2건은 JSON 파손이 아니라 **고를 라벨이 없어서** 9B가 라벨 자리에 제어값을 넣은 것(`{"intent": "NONE"}`). 8회 반복 실측에서 같은 입력이 `STRATEGY_ADVICE`↔`UNKNOWN`으로 흔들림(5:3, 7:1). ① `QueryIntent.STRATEGY_STATUS`(내가 뭘 정했지·아까 손절 몇 %였지·몇 단계까지 왔어)·`RESULT_EXPLAIN`(MDD -35%면 심해·승률 높은데 왜 마이너스) 신설 + 프롬프트 정의와 경계 규칙 4-3(묻기 vs 바꾸기)·4-4(일반 지식 vs 내 결과)·4-5(읽기 전용). ② **읽기 전용 계약** — 두 라벨을 `_EFFECT_BLOCKED_INTENTS`에 넣어 `workflow_effect`·`clarify_target` 항상 강등(묻기만 한 발화가 ROLLBACK으로 새면 전략이 되감긴다). 규제 게이트가 아니므로 정형 문구는 달지 않음. ③ **진행 상태 답변은 LLM 미사용** — 기존 `currentStrategyPresentation()`의 요약·진행 카드가 답(값 환각 위험 0). ④ **결과 설명은 사실 주입 필수** — `backtestResultFacts.ts`가 실제 수치를 블록으로 만들어 `/query/general`의 새 `facts` 필드로 전달, 백엔드가 `[사실]`로 맨 앞 주입. 값 없는 지표는 줄 생략(0으로 채우면 거짓 사실). 결과 없으면 답변 레인 미호출. ⑤ **[규제 안전]** 전용 프롬프트가 우열·권유·전망·비교 금지, 판단 요구엔 워크포워드·몬테카를로 안내로 대체. 프롬프트만으로 9B가 못 지켜 남는 등급 표현("샤프 1.21은 긍정적인 수준")은 결과 경로 전용 출력 필터 `guardrails.strip_metric_grading`이 문장째 제거(공용 `_FORBIDDEN`은 미변경 — 합치면 AI 리포트 출력까지 바뀜). **재실행 검증**: 못 알아들음 5→0, 해석 실패 2→0, 8문항 전부 새 라벨로, 다른 9유형 회귀 없음. AgentsTab에 '읽기 전용 질문 가드' 노드·라벨 목록·전달 대상 동기화 — 백엔드 3,774·프론트 1,460 전체 통과 | ✅ 완료 |
| 규제 게이트를 라벨과 직교하는 축으로 분리 — 종목 지표 값 조회 (2026-08-11, FR-SA-002c-9) | 커버리지 프로브가 정량화한 '천장 2'. `STOCK_ANALYSIS` 라벨 하나가 **"삼성전자 사도 될까?"(규제상 금지)와 "삼성전자 PER 얼마야?"(CLAUDE.md가 명시적으로 허용하는 객관적 재무 지표 제공)를 같은 거절 문구로** 묶어 사실 조회 6문항이 전부 차단되고 있었다. ① `fact_metric` 축 신설(`intent/stock_facts.py` 닫힌 목록 23종 — PER·PBR·PSR·PCR·EV/EBITDA·ROE·ROA·부채비율·유동비율·영업이익률·순이익률·매출총이익률·배당수익률·배당성향·EPS·BPS·시가총액·매출/영업이익/순이익 증가율·종가·52주 최고저). `workflow_effect`·`clarify_target`과 같은 계약 — LLM은 제안만, 성립은 결정론(라벨=STOCK_ANALYSIS + 지표 정규화 성공 + 국내 종목 매핑 성공, 셋 다 아니면 기존 거절). ② **[규제 안전] 축이 답변 자유도를 열지 않는 것이 안전 근거** — LLM은 "어떤 지표를 물었나"만 고르고 문장은 데이터에서 읽어 정해진 틀에 채운다(값·기준일·"판단/추천은 제공하지 않습니다"). 해석 어휘 없음. 축이 오판해도 최악은 '숫자 표시'이지 '매수 권유'가 아니며, 회귀 테스트가 이 성질을 LLM 없이 고정. ③ 프롬프트 규칙 16(값만 묻는 경우만 — "PER 낮은데 사도 될까?"는 null)·17(스크리닝 조건은 null). 실측: 판단 요청 3·판단 혼합 1·스크리닝 1·평가 요구 1 전부 거절 유지, 해외 종목은 기존 미지원 안내. ④ 데이터 정본은 **백테스트 엔진과 같은 종목별 parquet**(KIS 실시간 아님 — 엔진 결과와 정합해야 하고 외부 호출 실패가 답변을 좌우하면 안 됨). 결측 시 뒤에서부터 유효값 탐색 + 실제 관측일 명시, 52주 최고저는 252거래일 계산 + '기록된 날' 별도 표기, 없으면 지어내지 않고 없다고 밝힘. ⑤ 전략 진행 중 파싱 레인 가로채기는 `factMetric`이면 예외(안 그러면 작성 중 값 질문이 영영 미답변). ⑥ 계측 도구 `_is_gated`가 라벨만 세지 않도록 축 반영(안 하면 분리 효과가 리포트에 안 보임). **프로브 재실행**: 정형 안내로 끊김 15→11, 값 조회로 답함 0→5, 못 알아들음 0 유지. 남은 1건은 샘플링 변동(`temperature=0.3`) — 별건. AgentsTab에 '값 조회' 노드·게이트 축 설명 동기화 — 백엔드 3,794·프론트 1,464 전체 통과 | ✅ 완료 |
| 구조화 출력 LLM greedy 전환 — 어댑터 2갈래 분리 (2026-08-11, FR-SA-002c-10) | 커버리지 작업 중 발견. `api/intent_routes.py`의 LLM 어댑터 하나(`_mlx_llm`)를 성격이 정반대인 두 작업이 공유했다 — **구조화 출력**(의도 라벨·지표 키·빌더 ops JSON·용어 추출: 정답 고르기)과 **산문 답변**(`/query/general`: 설명하기). `temperature=0.3, top_p=0.9`는 산문 쪽에 맞춘 값인데(`nl_parser.chat` 주석 "temperature>0이면 표현이 매번 달라지도록 샘플링한다 — 코치용") 분류가 같은 어댑터를 쓰면서 딸려온 것이지 분류를 위해 고른 값이 아니었다. 같은 코드베이스의 전략 해석기·파싱 검증기는 이미 `temperature=0`이라 **이 모듈만 예외**였다. **실측**: 같은 입력 '코스닥 상장사 수가 몇 개야?'가 5회 중 GENERAL_INVESTMENT↔UNKNOWN으로 갈림 → greedy 전환 후 5/5 고정(서버 경유 재확인 5/5). 라벨 흔들림은 ① 같은 질문에 다른 답 ② QA 하니스 flaky화(회귀 놓침) ③ 버그 재현 불가를 부른다. **수정**: 공통 본체 `_chat(…, temperature, top_p)` 위에 용도가 이름에 드러나는 `_mlx_llm_structured`(0.0/1.0)와 `_mlx_llm_prose`(0.3/0.9)를 둔다. 5개 호출부 중 4개가 structured, 답변 생성만 prose — `generate_general_answer`는 한 함수 안에서 둘 다 쓴다(용어 추출=구조화, 답변=산문). **회귀**: `test_llm_adapter_split.py`가 값이 아니라 **배선**을 고정한다(다시 합쳐지면 증상이 조용히 재발). 검증: ① `qa_intent_open_pick_scope` 6/6(케이스당 5회 반복 일치) ② 커버리지 프로브 42문항 결과 변경 전과 동일(끊김 11·값 조회 5·못 알아들음 0) ③ **레드팀 156발화 라벨 대조**(temp 0.3 vs 0) — 152/156 동일, 갈린 4건 전부 greedy가 0.3의 **최빈값을 고정**한 것('잘 나가는 기업' 0.3=OFF_TOPIC 5:UNKNOWN 3→greedy OFF_TOPIC 등). greedy는 새 답을 만들지 않고 분산만 제거함을 실측으로 확인. 백엔드 3,798·프론트 1,464 전체 통과 | ✅ 완료 |
| 업종·테마 소속 목록 — 추천 요청과 분리 (2026-08-11, FR-SA-002c-11) | 사용자 결정("종목 목록을 보여주는 것으로 작업"). `STOCK_PICK` 라벨 하나가 "뭐 살까?"(열린 추천, 거절·빌더 전환)와 "반도체 업종에 어떤 회사들이 있어?"(소속 질문 = 분류 사실)를 같은 거절로 묶던 것을 `list_scope` 직교 축으로 분리 — fact_metric(FR-SA-002c-9)과 같은 계약. ① LLM은 범위 표기만 원문 그대로 추출('반도체'), 정본 성립은 `intent/stock_lists.resolve_listing`이 판정 — 섹터 사전(동의어 '2차전지'→'이차전지' 포함)→KG 테마(`theme_listed_companies`, **그래프 조회만** — 검색 학습 체인 미진입). 미해석=기존 안내(목록 지어내지 않음). 성립 라벨은 STOCK_PICK·GENERAL_INVESTMENT뿐(STRATEGY_ADVICE에서 열면 스크리닝이 목록으로 새고, 규제 라벨에서 열면 정형 안내 우회). ② **[규제 안전]** 답변=총원+가나다순 회사명(코드)+"매수 추천이 아닙니다"+전략 전환. **정렬 가나다순**(시총순은 순위 암시), 표시 40곳 상한+총원 명시(절단은 표시뿐 — 유니버스 종수 절단 금지와 무충돌), 상폐 제외(현재 상장 기준). 프롬프트 규칙 19("살 만한/좋은 거"=추천이므로 null)·20(조건=전략 설계). ③ 전략 진행 중 파싱 가로채기는 listScope 예외(factMetric과 동일), 계측 `_is_gated` 축 반영. **실측**: 소속 질문 2건 목록 응답('반도체' 77곳·'이차전지' 21곳), "살 만한/좋은 거" 2건 거절 유지, 스크리닝 1건 STRATEGY_ADVICE. 프로브: 끊김 11→9, 값 조회 5→7. 부수 관찰: '코스피200에 몇 종목' 라벨이 GENERAL→UNKNOWN 이동(프롬프트 확장의 경계 이동) — 전략 없음 상태의 UNKNOWN은 같은 answer_general 레인이라 사용자 행동 불변. AgentsTab '소속 목록' 노드 추가 — 백엔드 3,813·프론트 1,467 전체 통과 | ✅ 완료 |
| 시장·지수 소속 종수 환각 수정 — list_scope 축 확장 (2026-08-11) | 사용자 스크린샷 신고: "코스피200에 몇 종목 들어있어?"에 **"약 403개, 과거의 코스피 180보다 확대"**라고 답변 — 전부 환각(코스피 180은 존재하지 않는 지수, 실제 편입 200종목). 원인: UNKNOWN→`/query/general` 산문 레인에 지수·시장 구성 사실이 주입되지 않아 9B가 지어냄(데이터 조회 0회). 수정: `platform_defaults`식 원문 정규식(미이관 부채)을 확장하지 않고 **FR-SA-002c-11 `list_scope` 축을 시장·지수로 확장** — ① `stock_lists._resolve_market_listing`: 코스피200=편입 캐시(`kospi200-cache.json`, 마스터 상폐 대조), 코스피·코스닥=마스터 market 필드. 표기 변형('코스피 200'·'KOSPI200')은 닫힌 사전 정규화(입력=LLM 출력). ② `_LISTING_INTENTS`에 UNKNOWN 추가 — 구성·종수 질문은 라벨이 마땅치 않아 UNKNOWN으로 떨어지는데, 축은 정본 매핑+결정론 목록이라 오판 최악='소속 목록 표시'. ③ **디버깅 교훈 재확인**: 프롬프트에 시장·지수 규칙+예시를 넣어도 추출 실패(0/3) — 출력 형식 줄이 `"<업종/테마 표기>"`로 좁아서였고, `"<업종/테마/시장/지수 표기>"`로 넓히자 즉시 추출(**출력 형태가 규칙보다 강하다**, `project_interpreter_output_shape_authority` 동일 패턴). **실측**: '코스피200에 몇 종목?'→"총 200곳"(403 환각 소멸), '코스닥 상장사 수?'→"총 1,822곳", "살 만한/전략" 배제 유지. 백엔드 3,816·프론트 1,468 전체 통과 | ✅ 완료 |
| 한국어 지표명 매핑 + 종수 질문 목록 생략 (2026-08-11) | 커버리지 잔여 2건 마감. **① '영업이익률' 미추출**(마지막 비의도 차단): 지표 목록이 `operating_margin — 영업이익률`(키 먼저) 순이라 9B가 한국어 표기를 키로 잇지 못함(5/5 미추출, 온도 무관). `영업이익률 → operating_margin`(사용자 표기 먼저)으로 뒤집고 도입부에 명시 예시 추가 → **10/10**(판단 배제 2문항 포함). 회귀가 표기 순서 자체를 고정(SRS c-9 ③-1). **② 종수 질문의 목록 군더더기**: '몇 종목?'에 40개 회사명이 붙던 것 — `list_count_only` 축 추가(출력 형식 줄에 직접 — 출력 형태가 규칙보다 강하다), true면 종수+거절 문구만. '상장사 수' 표현이 scope 미추출로 회귀하자 도입부에 짝 예시('코스닥 상장사 수가 몇 개야?' → '코스닥') 추가로 해소 — **6/6**(목록/종수/추천 배제 전부 정위치). 출력 필드 3개 증가분 절단 방지로 분류 max_tokens 220→280(2026-07-31 선례). **프로브 최종: 끊김 8/42(전부 의도된 거절 — 판단 3·개인 맞춤 2·능력 밖 3) · 값 조회 10/42 · 못 알아들음 0 · 해석 실패 0.** 백엔드 3,819·프론트 1,468 전체 통과 | ✅ 완료 |

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
