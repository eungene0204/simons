# Simons — 종합 투자 시뮬레이션 플랫폼 프로젝트 계획서

> **문서 버전:** v2.0
> **최종 갱신일:** 2026-04-10
> **프로젝트명:** Simons (시몬스)

---

## 1. 프로젝트 개요

### 1.1 비전
사용자가 자신만의 주식 투자 전략을 **설계 → 검증 → 최적화 → 실전 시뮬레이션**까지 원스톱으로 수행할 수 있는 종합 투자 시뮬레이션 플랫폼.

### 1.2 핵심 가치 제안
| 가치 | 설명 |
|------|------|
| **AI 대화형 전략 설계** | 자연어 프롬프트로 투자 전략을 설명하면 AI가 자동으로 퀀트 전략으로 변환 |
| **AI 융합** | 자체 개발 Transformer+XGBoost 예측 모델을 전략 블록으로 결합 |
| **과학적 검증** | 과거 데이터 기반 백테스트 + SHAP 기반 설명 가능 AI |
| **가상 실전 매매** | 실시간 시장 데이터 기반 페이퍼 트레이딩으로 전략 실전 검증 |
| **자동 최적화** | Optuna 기반 하이퍼파라미터 튜닝으로 전략 고도화 |

### 1.3 타겟 사용자
- **초급:** 투자에 관심 있지만 체계적 방법론이 없는 개인 투자자
- **중급:** 기술적 분석을 활용하는 트레이더 (전략 검증 니즈)
- **고급:** 퀀트 투자자, 알고리즘 트레이딩 연구자 (AI 모델 결합, 최적화)

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
│  SQLite + Prisma ORM · Parquet Files (4,052 종목)       │
│  AI Model Artifacts (Transformer + XGBoost v2)          │
└─────────────────────────────────────────────────────────┘
```

### 2.2 모듈 구조

```
simons/
├── app/                    # Next.js 페이지 & API 라우트
│   ├── api/               # 60+ REST API 엔드포인트 (17개 도메인)
│   ├── analytics/         # 전략연구소 (프롬프트 기반 전략 생성)
│   ├── backtest/          # 백테스트 이력 & 상세
│   ├── kospi/             # 시장 대시보드
│   ├── stock/             # 종목 상세 (차트, 호가, 시그널)
│   ├── stock-order/       # 수동 주문
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
│   └── tests/             # 38개 테스트 파일 (pytest)
├── components/            # React 컴포넌트
│   ├── strategy/          # 전략 빌더 UI (핵심)
│   ├── dashboard/         # 홈 대시보드
│   ├── stock/             # 종목 차트/상세
│   ├── order/             # 호가/주문
│   ├── portfolio/         # 포트폴리오 분석
│   ├── virtual-account/   # 가상계좌
│   ├── virtual-market/    # 가상매매 패널
│   ├── layout/            # 네비게이션, 사이드바
│   ├── drawer/            # 관심종목/계좌 드로어
│   ├── watchlist/         # 관심종목
│   ├── ui/                # 공통 UI
│   ├── providers/         # React 프로바이더
│   └── __tests__/         # 24개 프론트엔드 테스트
├── lib/                   # 프론트엔드 유틸리티
│   ├── strategy-blocks.ts # 29개 시그널 블록 정의
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
│   └── schema.prisma      #   12개 모델
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
| 2. AI 파싱 | 로컬 LLM이 자연어 → ParsedStrategy 구조 변환 | ✅ 완료 |
| 3. 전략 요약 확인 | 파싱된 유니버스, 필터, 시그널, 포트폴리오 설정 표시 | ✅ 완료 |
| 4. 전략 수정 | 대화형으로 파라미터 점진적 수정 가능 | ✅ 완료 |
| 5. 백테스트 실행 | SSE 스트림으로 진행률 + 결과 실시간 전달 | ✅ 완료 |
| 6. 결과 분석 | BacktestDashboard (수익률, 샤프, MDD, 거래내역, 차트) | ✅ 완료 |

**자연어 파서 (NLStrategyParser):**

| 항목 | 내용 |
|------|------|
| 위치 | `backend/engine/nl_parser.py` |
| 지원 백엔드 | MLX (Apple Silicon 최적, 기본값), Ollama (범용) |
| 기본 모델 | `mlx-community/Qwen2.5-32B-Instruct-4bit` / `qwen2.5:32b` |
| 입력 | 한국어 자연어 전략 설명 |
| 출력 | `ParsedStrategy` (유니버스, 펀더멘탈 필터, 진입/청산 시그널, 리스크 설정) |
| 수정 모드 | `previous_parsed` 전달 시 기존 전략 기반 점진적 수정 |
| 캐시 | 200-item LRU (중복 방지) |

**전략 변환기 (StrategyConverter):**

| 항목 | 내용 |
|------|------|
| 위치 | `backend/engine/strategy_converter.py` |
| 기능 | `ParsedStrategy` → `BacktestRequest` 변환 |
| 종목 로딩 | `/data/korea-stocks.json` 기반 유니버스별 심볼 매핑 (KOSPI, KOSDAQ, KOSPI200) |
| 필터 변환 | 펀더멘탈 필터 → `type="filter"` 조건 블록 |
| 시그널 변환 | 기술적 시그널 → `type="indicator"` 조건 블록 + 파라미터 |

#### 3.1.1-legacy 전략 빌더 (5-Step Wizard) ✅ 완료

> 블록 조합 방식의 전략 빌더. 고급 사용자 전용 또는 프롬프트 파싱 결과의 상세 편집용.

| 단계 | 이름 | 기능 | 구현 상태 |
|------|------|------|-----------|
| Step 1 | 유니버스 선택 | KOSPI/KOSDAQ/NASDAQ 등 투자 대상 선택, 필터 적용 | ✅ 완료 |
| Step 2 | 진입/청산 조건 | 블록 조합으로 매수/매도 시그널 설계 | ✅ 완료 |
| Step 3 | 포지션·리스크 | 포지션 크기, 손절/익절, 최대 보유일 등 | ✅ 완료 |
| Step 4 | 백테스트 설정 | 기간, 초기자본, 수수료, 슬리피지 | ✅ 완료 |
| Step 5 | 결과 리포트 | 수익률, 샤프, MDD, 거래내역, 차트 | ✅ 완료 |

#### 3.1.2 시그널 블록 (29개) ✅ 전체 구현

**기술적 지표 (15개)**
| 블록 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `ma_crossover` | 이동평균 골든/데드크로스 | shortMA, longMA, crossType | ✅ |
| `rsi` | RSI 과매수/과매도 | period, operator, value | ✅ |
| `macd` | MACD 크로스오버 | fastPeriod, slowPeriod, signalPeriod | ✅ |
| `bollinger_bands` | 볼린저밴드 이탈/반등 | period, stdDev, signalType | ✅ |
| `volume_spike` | OBV 기반 거래량 급증 | period, signalType | ✅ |
| `breakout` | 52주 신고가/신저가 돌파 | lookbackPeriod, signalType | ✅ |
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
| 블록 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `trading_value` | 거래대금 필터 | operator, value (억원) | ✅ |
| `market_cap` | 시가총액 필터 | operator, value | ✅ |
| `per` | PER 필터 | operator, value | ✅ (Naver Finance EPS 기반 일별 PER 계산) |
| `pbr` | PBR 필터 | operator, value | ✅ (Naver Finance BPS 기반 일별 PBR 계산) |
| `roe_or_gpa` | ROE/GPA 필터 | metric, operator, value | ✅ |
| `debt_ratio` | 부채비율 필터 | operator, value | ✅ |
| `trading_suspension` | 거래정지 제외 | exclude | ✅ |

**수급 (1개)**
| 블록 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `investor_net_buy` | 기관/외인 순매수 | investorType, period, minAmount | ✅ |

**리스크 (4개)**
| 블록 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `price_limit_exit` | 손절/익절 | stopLossPct, takeProfitPct | ✅ |
| `max_holding_days` | 최대 보유기간 | value | ✅ |
| `trailing_stop` | 트레일링 스탑 | percentage | ✅ |

**AI/ML (2개)**
| 블록 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `ai_model` | AI 상승 예측 | threshold, direction | ✅ |
| `ai_drop_model` | AI 하락 예측 | threshold | ✅ |

#### 3.1.3 리스크 관리 설정

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
- **랭킹:** 다중 종목 동시 시그널 시 스코어 기반 우선순위 배정

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
| 가상 주식시장 엔진 | VirtualTrader 백그라운드 루프, 1분 간격 시그널 평가 | ✅ 완료 |
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
│  (5분 스케줄러)   │     │  (주문 처리/체결)  │
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
| 09:05~15:25 | 1분 간격 시그널 평가 + 자동매매 실행 |
| 15:30 | 장 마감 (자동매매 일시정지) |

**Python 스케줄러 (`scripts/scheduler.py`):**
| 시간 (KST) | 작업 |
|-------------|------|
| 00:00 | 일일 OHLCV 데이터 동기화 |

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
| 몬테카를로 시뮬레이션 | 수익률 분포 확률적 분석 | ✅ 완료 |
| Optuna 최적화 | TPE 베이지안 파라미터 최적화 | ✅ 완료 |
| 그리드 서치 | 순열 기반 파라미터 탐색 | ✅ 완료 |
| 팩터 분석 | Fama-French, 모멘텀, 밸류 팩터 분해 | 🔲 미구현 |
| 상관관계 분석 | 종목 간 상관계수 히트맵 | 🔲 미구현 |
| 섹터 로테이션 | 업종별 동향, 순환 패턴 | 🔲 미구현 |
| 벤치마크 비교 | KOSPI/S&P500 대비 알파/베타 | 🔲 미구현 |

---

## 4. 데이터베이스 설계

### 4.1 현재 스키마 (SQLite + Prisma) — 12개 모델

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
  id (cuid), name, description, settings (JSON), strategyType, createdAt, updatedAt
  → BacktestResult[]
}

-- 백테스트 결과
BacktestResult {
  id (cuid), strategyId→Strategy, stockId→Stock, summary (JSON), trades (JSON), createdAt
}

-- 백테스트 이력 (캐싱 포함)
BacktestHistory {
  id (cuid), strategyName, universe, conditions (JSON), metrics (JSON),
  result (JSON), cacheKey (unique), isVisible, hitCount, createdAt
}

-- 가상 계좌
VirtualAccount {
  id, name, initialCash, currentCash, strategyId, strategyName,
  tradingMode ("manual"/"auto"), createdAt, updatedAt
  → VirtualMarketState, VirtualOrder[], VirtualPosition[]
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

#### 전략 (6개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET/POST | `/api/strategy` | 전략 목록/생성 |
| GET/PUT/DELETE | `/api/strategy/[id]` | 전략 상세/수정/삭제 |
| POST | `/api/strategy/parse` | 자연어 파싱 (MLX/Ollama) |
| POST | `/api/strategy/backtest-stream` | SSE 백테스트 스트림 |
| POST | `/api/strategy/save-with-backtest` | 전략 저장 + 백테스트 원자적 실행 |

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

#### 기타 (5개)
| Method | Endpoint | 기능 |
|--------|----------|------|
| GET/POST | `/api/stocks/names` | 종목 마스터 |
| POST | `/api/stocks/sync` | 종목 동기화 (KRX) |
| GET | `/api/universe/data` | 유니버스 필터 데이터 |
| GET | `/api/universe/history` | 유니버스 동기화 이력 |
| GET | `/api/news/top` | 뉴스 피드 |
| GET | `/api/model/status` | NL 파서 모델 상태 |
| GET | `/api/quick-search` | 통합 퀵 서치 |
| POST | `/api/scheduler` | 스케줄러 배치 (장전/개시/갱신/마감) |

### 5.2 FastAPI Backend 엔드포인트 (15+개)

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
| GET | `/model/status` | NL 파서 상태 |
| POST | `/summarize` | AI 요약 생성 |
| POST | `/sync-stocks` | 유니버스 동기화 |

---

## 6. 개발 로드맵

### Phase 1: 핵심 플랫폼 — ✅ 완료

| 작업 | 상세 | 상태 |
|------|------|------|
| 백테스트 엔진 | 시뮬레이터 바이어스 제거, 결과 정확성 검증 | ✅ 완료 |
| 시그널 엔진 벡터화 | 전체 시계열 벡터화 평가로 성능 최적화 | ✅ 완료 |
| 전략 빌더 V2 | 5단계 위자드 UI/UX | ✅ 완료 |
| 전략연구소 (프롬프트 기반) | 자연어 전략 생성 + 대화형 수정 + SSE 백테스트 | ✅ 완료 |
| Optuna 최적화 통합 | 하이퍼파라미터 자동 최적화 | ✅ 완료 |
| AI 모델 v2 | Conv1D+RoPE+CLS Transformer + 분리 XGBoost | ✅ 완료 |
| 결과 대시보드 | 에퀴티 커브, 월별 수익, 종목별 통계 | ✅ 완료 |
| SHAP 설명 AI | 매매 판단 근거 시각화 | ✅ 완료 |
| AI 요약 생성 | Qwen 7B MLX 기반 자연어 리포트 | ✅ 완료 |

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

### Phase 4: 미구현 기능 (향후)

| 작업 | 상세 | 우선순위 |
|------|------|----------|
| 팩터 분석 | Fama-French, 모멘텀, 밸류 팩터 분해 | P2 |
| 상관관계 분석 | 종목 간 상관계수 히트맵, 최적 분산 포트폴리오 | P2 |
| 리밸런싱 시뮬레이션 | 주기적 리밸런싱 전략 백테스트 | P2 |
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

### 7.1 백엔드 테스트 (38개 파일, pytest)

| 영역 | 파일 수 | 주요 파일 |
|------|---------|-----------|
| 시그널 엔진 | 5 | test_engine_signals, test_signal_robustness, test_or_isolation, test_live_signal_utils, test_specific_exit_reasons |
| 시뮬레이터 | 5 | test_engine_simulator, test_time_exit, test_ranking_logic, test_multi_reasons, test_multi_symbol_reasons |
| AI/ML | 3 | test_ai_code_fixes, test_engine_ai*, test_ai_sell* |
| 최적화 | 2 | test_optuna_optimizer, test_optimizer |
| 데이터/로더 | 3 | test_engine_loader, test_loader_preprocess, test_vbt |
| 시세/Provider | 4 | test_market_data, test_providers, test_kis_realtime_providers, test_market_cap |
| 회귀 | 3 | test_regression_fixes, test_zero_trades, test_kospi200_symbol_handling |
| API/통합 | 3 | test_api_idempotency, test_api_isolation*, test_backtest_engine* |
| 유틸리티 | 6 | test_vi_utils, test_universe_history, test_nl_cache, test_summarize, test_stream_progress, test_sync_data_status |
| 백엔드 통합 | 3 | test_backend, test_backend_v2, test_stream_execution_time |

> `*` 표시: 서버/AI 모델 필요 (일반 실행 시 제외)

### 7.2 프론트엔드 테스트 (24개 파일, Vitest + jsdom)

| 영역 | 파일 수 | 주요 파일 |
|------|---------|-----------|
| 컴포넌트 | 7 | OrderBook, PriceRow, TrackedSymbolRow, TrackedSymbolsSkeleton, SidebarQuickSearch, AnalyticsStrategySummary, StrategyExampleTabs |
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
| 금융 데이터 | 로컬 저장 | 데이터 접근 권한 관리 |

---

## 9. 기능 실현도 요약

### 전체 진행률: **~85%** (핵심 기능 기준)

| 영역 | 구현 상태 | 실현도 |
|------|-----------|--------|
| 전략 설계 (프롬프트 + 위자드) | ✅ 전체 완료 | 100% |
| 백테스트 엔진 | ✅ 전체 완료 | 100% |
| 시그널 블록 (29개) | ✅ 전체 완료 | 100% |
| AI/ML (예측 + XAI + 요약) | ✅ 전체 완료 | 100% |
| 전략 최적화 (Optuna + Grid) | ✅ 전체 완료 | 100% |
| 가상 매매 시스템 | ✅ 전체 완료 | 100% |
| 시장 데이터 (멀티 Provider) | ✅ 전체 완료 | 100% |
| 호가/주문 시스템 | ✅ 전체 완료 | 100% |
| 워크포워드 + 몬테카를로 | ✅ 전체 완료 | 100% |
| 대시보드 & 포트폴리오 | ✅ 대부분 완료 | 90% |
| 관심종목 | ✅ 전체 완료 | 100% |
| 테스트 커버리지 | ✅ 양호 (62개 파일) | 85% |
| 고급 분석 (팩터, 상관관계, 섹터) | 🔲 미구현 | 0% |
| 소셜/마켓플레이스 | 🔲 미구현 | 0% |
| 인프라 (Docker, CI/CD, 모니터링) | 🔲 미구현 | 0% |
| 글로벌 확장 (미국 시장) | 🔲 미구현 | 0% |

---

## 10. 경쟁 분석 & 차별화

| 기능 | Simons | 증권사 HTS | QuantConnect | 뱅크샐러드 |
|------|--------|-----------|--------------|-----------|
| AI 대화형 전략 설계 | ✅ (자연어) | ❌ | ❌ (코딩 필수) | ❌ |
| AI 시그널 블록 | ✅ | ❌ | ⚠️ (직접 구현) | ❌ |
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
| NL 전략 파서 | `backend/engine/nl_parser.py` |
| 전략 변환기 | `backend/engine/strategy_converter.py` |
| 전략 DSL 타입 | `types/strategy.ts` |
| 시그널 블록 정의 | `lib/strategy-blocks.ts` |
| 백테스트 엔진 | `backend/backtest_engine.py` |
| 시그널 엔진 | `backend/engine/signals.py` |
| 시뮬레이터 | `backend/engine/simulator.py` |
| AI 엔진 | `backend/ai/ai_engine.py` |
| AI 요약 | `backend/ai/summarize.py` |
| XAI 엔진 | `backend/ai/xai_engine.py` |
| 최적화 에이전트 | `backend/ai/local_optimization_agent.py` |
| 가상매매 트레이더 | `backend/engine/virtual_trader.py` |
| 시세 데이터 | `backend/engine/market_data.py` |
| KIS Provider | `backend/engine/providers/kis.py` |
| 장 스케줄러 | `lib/scheduler.ts` |
| DB 스키마 | `prisma/schema.prisma` |

---

*이 문서는 프로젝트의 현재 상태와 향후 계획을 반영합니다. 최종 갱신: 2026-04-10.*
