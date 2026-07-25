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
| 섹터 SOT·정규화 | `engine/universe_pit.py` — `CANONICAL_SECTORS`(39개 — 2026-07-13 '로봇' 신설, korea-stocks.json sector 필드=SOT), `normalize_sector`(동의어: 2차전지→이차전지, 제약→바이오/제약, AI→소프트웨어/플랫폼 등), `filter_by_sector` | ✅ 완료 |
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
| Phase 3 (향후) | prod shadow diff 누적 관찰(불일치 유형·오류율) + dev primary 실사용 후: **prod primary 전환**(주의: 모든 파스가 Modal 경유 — 콜드스타트 시 첫 파스 수십 초~분, warmup 로직 존재. keep-warm 검토) → 자연어 해석용 Regex·어휘집(`_RULE_GUARD_KNOWN_VOCAB`·미지원 개념 목록·Fidelity Validator) 제거 — Registry·Validator·Compiler·형식 검증 Regex는 유지 | ⬜ 예정 |

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
