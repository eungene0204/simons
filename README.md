# 널스탁 (nullstock.im) — 퀀트 투자 연구·시뮬레이션 플랫폼

자연어로 투자 전략을 설계하고, 과거 데이터 백테스트와 모의 시장 가상매매로 검증하는 풀스택 퀀트 플랫폼.
한국(`/`)과 미국(`/us`) 두 시장 레인을 같은 코드 트리에서 서비스한다.

> 리포지터리 이름(`simons`)은 초기 코드네임이다. 서비스명·사용자 노출 표기는 **널스탁 / nullstock**을 쓴다.

## 규제 포지셔닝

본 서비스는 **투자 연구 및 시뮬레이션 플랫폼**이며 투자 자문·투자 추천·개인 맞춤형 금융 조언을 제공하지 않는다.
시스템은 계산, 백테스트, 시뮬레이션, 객관적인 과거 데이터 표시만 수행하고 모든 투자 판단은 사용자가 직접 한다.
전략/종목/섹터/ETF 추천, 시장 전망, 매수·매도 시점 제안, 개인 맞춤 조언은 **아키텍처 차원에서 지원 대상이 아니다**
(상세: [`CLAUDE.md`](CLAUDE.md) 규제 안전 원칙).

---

## 핵심 기능

- **자연어 전략 설계** — 대화로 전략을 설명하면 LLM이 구조화된 전략(StrategyIntent)으로 해석하고, 빠진 값은 되묻는다
- **벡터화 백테스트 엔진** — vectorbt + Polars 기반. 한국 5,093종목 / 미국 5,978종목 OHLCV parquet 대상
- **전략 검증 도구** — Optuna 베이지안 최적화, 그리드 서치, 워크포워드 분석, 몬테카를로 시뮬레이션, 기간별 리밸런싱 비교
- **AI 시그널 블록** — Transformer + XGBoost 하이브리드(v3), SHAP 기반 설명 가능 AI. 보조 지표로만 사용
- **가상매매** — 실시간 시세 기반 페이퍼 트레이딩. 원화(KST 시계)·달러(ET 시계) 계좌 생명주기 분리
- **지식 그래프 / 테마 유니버스** — 섹터·테마·관련주 정본 매핑(KR·US 별도 그래프)
- **운영 콘솔** — 사용자·전략·백테스트·플랜·에이전트 파이프라인·지식그래프 관리(`/console`)

## 기술 스택

| 영역 | 기술 |
|------|------|
| **Frontend** | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Recharts, visx, lightweight-charts |
| **Backend** | Python FastAPI, Polars, Pandas, vectorbt, stockstats |
| **LLM** | Ollama(Qwen3.5-9B 단일 슬롯) — dev/prod 동일. MLX는 Apple Silicon 옵트인 |
| **AI/ML** | PyTorch(Transformer), XGBoost, SHAP, Optuna, ChromaDB + bge-m3(RAG) |
| **Database** | Supabase Postgres + Prisma ORM(50+ 모델). 뉴스 v2 전용 Postgres 별도 |
| **결제** | 토스페이먼츠(KR 빌링) · PayPal(US 정기구독) |
| **인프라** | Docker Compose(Vultr 1박스) + Modal 서버리스(GPU=LLM, CPU=백테스트) + Caddy TLS |

---

## 아키텍처 개요

```
사용자 자연어 입력
    ↓
LLM 의미 해석            intent/interpreter.py · strategy_conversation/interpreter/
    ↓
제한된 구조화 출력        StrategyIntent JSON
    ↓
형식 검증·정규화          JSON 경계 추출 / enum·단위 표기 정규화
    ↓
Schema 검증              Pydantic
    ↓
Domain 검증              registry/ + validation/ (지표 지원 여부·범위·충돌·완결성 → 되묻기)
    ↓
컴파일                   strategy_conversation/compiler/ → ParsedStrategy
    ↓
백테스트 엔진             Loader → Indicators → Signals → (AI) → Simulator → ResultHandler
```

### 자연어 해석 계약 (프로젝트 대원칙)

> **입력이 사용자 원문이면 그것은 해석이다 → LLM.
> 입력이 LLM 출력이고 표기만 보면 결정 가능하면 그것은 정규화다 → 결정론 코드.**

Regex가 사용자 원문의 의미(지표·업종·의도·수치)를 판정하는 코드는 추가하지 않는다.
Regex는 LLM이 만든 구조화 출력의 **형식**만 검증·정규화한다.
아직 이관되지 않은 위반 지점은 부채로 명시 관리한다 — [`docs/nl_interpretation_contract.md`](docs/nl_interpretation_contract.md), [`CLAUDE.md`](CLAUDE.md).

### 지역 레인 (KR / US)

지역은 **URL 경로**로 가른다. `middleware.ts`가 `/us` 트리를 같은 라우트 트리로 rewrite 하고 지역을 내부 헤더로 실어 준다
(언어 토글·언어 쿠키는 폐지). 표시 언어는 `lib/i18n`의 `t()` 사전, 통화·가격·유니버스·시장 달력은 지역별로 분기한다.

---

## 시작하기

### 1. 환경 변수

`.env` (주요 항목):

```env
# DB — Supabase Postgres (Prisma + Python 백엔드 공용)
DATABASE_URL="postgresql://...pooler..."
DIRECT_URL="postgresql://...direct..."
JWT_SECRET=your_secret_key_here

# LLM — 로컬 Ollama 또는 Modal 서버리스 GPU 엔드포인트
OLLAMA_HOST=http://localhost:11434
MODAL_KEY=            # Modal proxy-auth (원격 Ollama/백테스트 워커 사용 시)
MODAL_SECRET=

# 시세·데이터
KIS_APP_KEY=          # 한국투자증권 (실시간 시세·호가)
KIS_APP_SECRET=
KRX_API_KEY=          # KRX Open API (유니버스 동기화)
ALPHA_VANTAGE_API_KEY=  # 미국 상장폐지·시세 보완
DART_API_KEY=         # 재무 데이터

# 결제
TOSS_SECRET_KEY=      # KR
NEXT_PUBLIC_TOSS_CLIENT_KEY=
PAYPAL_CLIENT_ID=     # US
PAYPAL_CLIENT_SECRET=
PAYPAL_WEBHOOK_ID=
```

`.env.example`에 선택 항목(LangSmith 관찰 계층, 데이터 미러, SMTP, 네이버 검색 그라운딩)의 설명이 있다.

### 2. 설치

```bash
npm install
npm run db:generate          # Prisma Client
npm run db:migrate           # 마이그레이션 (로컬 DB)

cd backend && pip install -r requirements.txt
```

### 3. 실행

```bash
npm run dev          # Next.js (port 3000)
npm run dev:backend  # FastAPI (port 8000)
npm run dev:all      # 프론트 + 백엔드 + 스케줄러 동시
```

### 4. 데이터 미러

정본 데이터(parquet/json)는 프로덕션에 있다. 로컬은 pull 로만 맞춘다.

```bash
npm run pull-data          # 프로덕션 → 로컬 동기화
npm run pull-data:check    # 차이만 확인
```

---

## 프로젝트 구조

```
simons/
├── app/                        # Next.js App Router — 24개 페이지, 119개 API 라우트
│   ├── analytics/              #   전략연구소 (자연어 전략 설계 + 백테스트)
│   ├── backtest/               #   백테스트 이력·상세
│   ├── virtual-account/        #   가상계좌·가상매매
│   ├── stock/[symbol]/         #   종목 상세 (차트·호가·프로파일)
│   ├── research/               #   리서치 콘솔
│   ├── console/                #   운영(관리자) 콘솔
│   ├── pricing/                #   요금제
│   └── api/                    #   Next.js API 라우트 (일부는 FastAPI 프록시)
│
├── backend/                    # Python FastAPI
│   ├── main.py                 #   FastAPI 앱
│   ├── backtest_engine.py      #   백테스트 오케스트레이터
│   ├── backtest_executor.py    #   로컬 / Modal 원격 실행 분기
│   ├── engine/                 #   엔진 (65개 모듈)
│   │   ├── signals.py          #     시그널 평가 (벡터화)
│   │   ├── simulator.py        #     매매 시뮬레이터 (vectorbt)
│   │   ├── indicators.py       #     기술적 지표
│   │   ├── phase1.py / phase1_pool.py / prep_cache.py   # 성능 경로 (결과 불변 계약)
│   │   ├── walk_forward.py / wfa_workers.py / monte_carlo.py
│   │   ├── grid_optimizer.py / optuna_optimizer.py
│   │   ├── universe_pit.py     #     PIT 유니버스 (생존편향 방지, KR·US)
│   │   ├── knowledge_graph.py / us_knowledge_graph.py
│   │   ├── virtual_trader.py   #     가상매매 실행기 (30초 루프)
│   │   ├── market_data.py      #     멀티 Provider 시세 (CircuitBreaker)
│   │   └── providers/          #     KIS · Naver · yfinance · pykrx · KRX …
│   ├── strategy_conversation/  #   전략 대화 파이프라인
│   │   ├── interpreter/        #     LLM 전략 해석 + 출력 복구
│   │   ├── planner/            #     Action DAG 플래너
│   │   ├── registry/           #     지표·유니버스·개념 정본
│   │   ├── validation/         #     능력·파라미터·충돌·완결성 검증
│   │   ├── compiler/           #     StrategyIntent → ParsedStrategy
│   │   ├── conversation/       #     수정 패치·되돌리기·변경 이력
│   │   └── response/           #     출력 가드·근거(provenance)
│   ├── intent/                 #   의도 분류·범위 가드 (KR: scope.py / US: scope_us.py)
│   ├── ai/                     #   AI 엔진·XAI·요약·전략 검증 에이전트
│   ├── stock_analysis/         #   종목 질의 (가드레일·심볼 해석)
│   ├── news_v2/                #   뉴스 수집·분석 (Celery + Postgres)
│   ├── research/ · advisor/ · observability/ · vector_memory/
│   ├── harness/                #   백테스트 회귀 하니스
│   └── tests/                  #   259개 pytest 파일
│
├── components/                 # React 컴포넌트 (strategy · dashboard · admin · virtual-account …)
├── lib/
│   ├── strategy/               #   BacktestService, UniverseResolver
│   ├── i18n/                   #   한국어 원문 = 키, en.ts 표시 사전
│   ├── geo/                    #   지역(region) 해석
│   ├── payment/ · pricing/     #   Toss / PayPal, KR·US 가격
│   └── scheduler.ts            #   장 생명주기 스케줄러
├── data/                       # parquet·json 데이터 (§데이터 레이어)
├── scripts/                    # 백필·동기화·QA 게이트 (97개)
├── docs/                       # 아키텍처·SRS·계약·QA 리포트
├── modal_ollama.py             # Modal 서버리스 GPU (LLM)
├── modal_backtest.py           # Modal 서버리스 CPU (백테스트 워커)
└── prisma/schema.prisma        # DB 스키마
```

---

## 백테스트 엔진

```
DataLoader (parquet)
  → IndicatorEngine (기술적·재무·수급 지표)
  → SignalEngine (벡터화 boolean 평가 + 랭킹/리밸런싱)
  → AIEngine (선택 — Transformer + XGBoost)
  → Simulator (vectorbt · SL/TP/TS/MaxHold · 수수료·세금)
  → ResultHandler (지표·종목별 통계·구조화 경고)
```

- **버전 관리**: `backend/engine/version.py`의 `ENGINE_VERSION`이 유일 기준(현재 `16.5.1`).
  MAJOR=계약·구조, MINOR=결과값 변경, PATCH=결과 불변. CI 가드가 엔진 핵심 파일 변경 시 버전 갱신을 강제한다.
- **성능 경로 계약**: 세션 캐시·Phase1 풀·창 병렬은 *답을 바꾸지 않는다*.
  `python scripts/qa_backtest_equivalence.py --wfa` 로 전수 대조(불일치 0)해야 한다.
- **지표**: 이동평균/RSI/MACD/볼린저/스토캐스틱/CCI/ADX/거래량·돌파 등 기술적 지표,
  PER·PBR·ROE·부채비율·시가총액 등 재무 필터, 기관·외인 수급, `ai_model`·`ai_drop_model`,
  랭킹(모멘텀·재무·복합 합산)과 달력 리밸런싱. 정본은 `data/indicator-ontology.json`(70개 항목).
- **성과 지표**: Total Return, CAGR, MDD, Sharpe, Sortino, Win Rate, Profit Factor, Kelly, 월별·종목별 수익률

### 유니버스

| 지역 | 유니버스 |
|------|----------|
| 한국 | KOSPI · KOSDAQ · KOSPI200 · KOSDAQ150 · 전체 · 섹터/업종 · 테마 · ETF · 지정 종목 |
| 미국 | 전체(us) · S&P 500 · NASDAQ 100 · NASDAQ · DOW 30 · US ETF |

PIT(Point-in-Time) 유니버스로 생존편향을 방지하고, 지수 구성종목은 현행 명부 기준임을 고지한다.
KR·US 혼합 유니버스는 거절한다.

---

## 가상매매 & 스케줄러

- 복수 계좌, 시장가·지정가 주문, 전략 연동 자동매매(`VirtualTrader`, 30초 간격)
- 리스크 관리 자동 적용(손절·익절·트레일링 스탑·최대 보유기간), 수수료·세금 포함 손익 정산
- 매매 사유는 세그먼트(템플릿+인자)로 저장 — KR/US 표시 언어를 프론트 사전에서 조립

| 시각 | 작업 |
|------|------|
| 08:50 KST | 장전 데이터 워밍 |
| 09:00 / 15:30 KST | 한국장 개장·마감 → 원화 auto 계좌 running / paused |
| 09:30 / 16:00 ET | 미국장 개장·마감 → 달러 auto 계좌 running / paused (서머타임 자동 반영) |
| 21:00 KST | 한국 OHLCV 일일 동기화 (`scripts/scheduler.py`) |
| 07:00 KST | 미국 OHLCV 증분 + 12주 주기 전량 재수집 (`scripts/scheduler_us.py`) |

휴장일·조기 종료 판정은 `VirtualTrader`의 시장 달력 게이트가 최종 판단한다.

---

## 데이터 레이어

| 데이터 | 위치 | 규모 |
|--------|------|------|
| 한국 OHLCV | `data/ohlcv/` | 5,093 parquet |
| 미국 OHLCV | `data/ohlcv-us/` | 5,978 parquet |
| 재무(DART·KIS) | `data/fundamentals/` | 5,547 파일 |
| 종목 마스터 | `korea-stocks.json` · `stock-master.json` · `us-etf-master.json` | — |
| 상장폐지 정본 | `delisted-stocks.json` · `us-delisted.json` | 생존편향 방지 |
| 지식그래프·테마 | `knowledge-graph.json` · `kg-theme-catalog.json` · `kg-sector-membership.json` | KR·US |
| 지수 구성 | `kospi200-cache.json` · `kosdaq150-cache.json` · `us-index-membership.json` | — |

정본은 프로덕션이며 로컬은 미러다 — **로컬 parquet을 push 하지 않는다.**

---

## 요금제 · 결제

| 플랜 | KR | US | 가상계좌 | 저장 전략 | 월 백테스트 |
|------|-----|-----|----------|-----------|-------------|
| Free | 0원 | $0 | 1 | 3 | 30 |
| Pro | 25,000원 | $19 | 10 | 50 | 500 |
| Premium | 49,000원 | $39 | 30 | 무제한 | 1,000 |

- 초기 투자금은 **가상계좌 시뮬레이션용 모의 자금**이다(자산·충전·포인트·리워드 표현 금지)
- 한도는 서버에서 재검증한다(클라이언트 게이트만으로는 통과되지 않음)
- KR = 토스페이먼츠 빌링, US = PayPal 정기구독(갱신 주체는 PayPal, 웹훅이 정본)

---

## 테스트

```bash
# 백엔드 (서버/AI 모델이 필요한 4개 파일 제외)
cd backend && pytest tests/ \
  --ignore=tests/test_backtest_engine.py \
  --ignore=tests/test_engine_ai.py \
  --ignore=tests/test_ai_sell.py \
  --ignore=tests/test_api_isolation.py

# 프론트엔드
npm run test:frontend
```

- 백엔드: pytest 259개 파일 (엔진·시뮬레이터·AI·최적화·의도 분류·US 레인·회귀)
- 프론트엔드: Vitest 261개 파일 (컴포넌트·API 라우트·유틸리티)

### QA 게이트 (`scripts/`)

| 게이트 | 목적 |
|--------|------|
| `qa_template_detect.py` | 전략 예시 파싱 검증 — 예시 문구 수정 시 필수(`--source us`, `--lang en` 포함) |
| `qa_backtest_equivalence.py --wfa` | 성능 경로 결과 동일성 전수 대조 |
| `qa_backtest_modal_equivalence.py` | prod ↔ Modal 워커 결과 동일성 |
| `qa_redteam_validation.py` | 규제·시장 경계 레드팀 케이스 |
| `qa_free_input.py` / `qa_multiturn_binding.py` | 되묻기 자유 답변 · 멀티턴 결속 |
| `qa_parse_badges_1000.py` / `qa_complex_llm_parse.py` / `qa_builder_fuzz.py` | 파싱 배지·복합 전략·퍼징 |
| `qa_stock_recognition.py` / `qa_validation_agent.py` | 종목 인식 · 검증 에이전트 |

되묻기는 실패가 아니다 — 값이 빠진 팩터를 묻는 것은 정상 동작이다.

### 백테스트 회귀 하니스

고정 픽스처로 백테스트를 반복 실행해 핵심 기대값이 깨졌는지 확인한다.

```bash
python3 backend/harness/runner.py \
  backend/harness/suites/backtest_smoke.json \
  --output backend/harness/reports/backtest_smoke.latest.json
```

케이스는 `request` + `expect`(`metric_ranges` · `signal_count` · `warnings_include` · `signals_include` …)만 넣으면 추가된다.

---

## 배포

```
Namecheap DNS (nullstock.im)
      ↓
Vultr CPU 박스 1대 — Docker Compose
   caddy(TLS) · web(Next.js) · backend(FastAPI+VirtualTrader) · scheduler · scheduler-us · redis · postgres(news)
      ↓                              ↓
Supabase Postgres (앱 DB)      Modal 서버리스
                                 · GPU: Ollama LLM (scale-to-zero)
                                 · CPU: 백테스트 워커 (오토스케일)
```

- CI/CD: GitHub Actions 단일 워크플로(`.github/workflows/ci.yml`) — 테스트 통과 후 **main push마다 Vultr 자동 배포 + `prisma migrate deploy`**
- Modal 워커는 파이썬·수치 라이브러리 버전을 prod와 **정확히 핀**해 결과 동일성을 지킨다
- 상세: [`docs/deployment.md`](docs/deployment.md)

```bash
npm run build   # prisma generate + next build
npm run lint    # ESLint
npm run db:studio  # Prisma Studio
```

---

## 문서

| 문서 | 내용 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | 대원칙·규제 안전 원칙·필수 작업 규칙 |
| [`docs/software_architecture.md`](docs/software_architecture.md) | 아키텍처 상세 |
| [`docs/nl_interpretation_contract.md`](docs/nl_interpretation_contract.md) | 자연어 해석 계약·코드 리뷰 체크리스트 |
| [`docs/SRS.md`](docs/SRS.md) · [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) | 요구사항·진행 계획 |
| [`docs/coding_rules.md`](docs/coding_rules.md) · [`docs/UI_GUIDELINES.md`](docs/UI_GUIDELINES.md) | 코드·UI 규칙 |
| [`docs/deployment.md`](docs/deployment.md) · [`docs/observability.md`](docs/observability.md) | 배포·관찰 계층 |
| [`docs/knowledge_graph.md`](docs/knowledge_graph.md) · [`docs/planner_dag_contract.md`](docs/planner_dag_contract.md) | 지식그래프·플래너 계약 |
