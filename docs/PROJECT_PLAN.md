# Simons — 종합 투자 시뮬레이션 플랫폼 프로젝트 계획서

> **문서 버전:** v1.0
> **작성일:** 2026-03-14
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
│  Next.js API Routes (20개) ←→ FastAPI Backend (2개)     │
├─────────────────────────────────────────────────────────┤
│                    Backend (Python FastAPI)              │
│  Polars/Pandas · vectorbt · stockstats · Optuna         │
│  PyTorch · XGBoost · SHAP                               │
├─────────────────────────────────────────────────────────┤
│                    Data Layer                            │
│  SQLite + Prisma ORM · Parquet Files (4,052 종목)       │
│  AI Model Artifacts (Transformer + XGBoost)             │
└─────────────────────────────────────────────────────────┘
```

### 2.2 모듈 구조

```
simons/
├── app/                    # Next.js 페이지 & API 라우트
│   ├── api/               # 20개 REST API 엔드포인트
│   ├── kospi/             # 시장 대시보드
│   ├── analytics/         # 분석 페이지
│   ├── watchlist/         # 관심종목
│   ├── order/             # 주문 (가상매매)
│   └── virtual-account/   # 가상계좌 관리
├── backend/               # Python FastAPI 서버
│   ├── engine/            # 백테스트 엔진 핵심 모듈
│   │   ├── loader.py      #   데이터 로딩 (Parquet)
│   │   ├── indicators.py  #   기술적 지표 계산
│   │   ├── signals.py     #   시그널 생성 엔진 (벡터화)
│   │   ├── nl_parser.py   #   자연어 → 전략 파서 (MLX/Ollama LLM)
│   │   ├── strategy_converter.py  # ParsedStrategy → BacktestRequest
│   │   ├── simulator.py   #   매매 시뮬레이션 (vectorbt)
│   │   ├── result_handler.py  # 결과 집계·메트릭
│   │   └── optuna_optimizer.py # 하이퍼파라미터 최적화
│   ├── ai/                # AI/ML 모듈
│   │   ├── ai_engine.py   #   Transformer + XGBoost 하이브리드
│   │   ├── xai_engine.py  #   SHAP 설명 가능 AI
│   │   └── local_optimization_agent.py  # Optuna 최적화 에이전트
│   └── tests/             # 32개 테스트 파일 (pytest)
├── components/            # React 컴포넌트
│   └── strategy/          # 전략 빌더 UI (핵심)
├── lib/                   # 프론트엔드 유틸리티
│   ├── strategy-blocks.ts # 29개 시그널 블록 정의
│   └── strategy/          # BacktestService, UniverseResolver
├── model/                 # AI 모델 아티팩트
├── data/ohlcv/            # 4,052개 종목 OHLCV 데이터
├── prisma/                # DB 스키마 & 마이그레이션
└── types/                 # TypeScript 타입 정의
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

#### 3.1.1 전략연구소 (프롬프트 기반 전략 생성)

> **핵심 변경:** 기존 5단계 위자드 방식에서 **자연어 프롬프트 기반** 전략 생성으로 전환.
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

**전략 변환기 (StrategyConverter):**

| 항목 | 내용 |
|------|------|
| 위치 | `backend/engine/strategy_converter.py` |
| 기능 | `ParsedStrategy` → `BacktestRequest` 변환 |
| 종목 로딩 | `/data/korea-stocks.json` 기반 유니버스별 심볼 매핑 |
| 필터 변환 | 펀더멘탈 필터 → `type="filter"` 조건 블록 |
| 시그널 변환 | 기술적 시그널 → `type="indicator"` 조건 블록 + 파라미터 |

**ParsedStrategy 구조:**

```python
ParsedStrategy {
  universe: List["KOSPI" | "KOSDAQ" | "KOSPI200"]
  fundamental_filters: List[FundamentalFilter]  # PBR, PER, ROE, 부채비율, 시총, 거래대금
  entry_signals: List[TechnicalSignal]          # MA, RSI, MACD, 볼린저 등
  exit_signals: List[TechnicalSignal]
  max_positions: int                            # 최대 보유 종목 수
  hold_period_days: int                         # 보유 기간
  rebalancing_period: Optional[str]             # 리밸런싱 주기
  stop_loss_pct: Optional[float]                # 손절선
  take_profit_pct: Optional[float]              # 익절선
  backtest_period: str                          # 백테스트 기간 (예: "1y", "3y")
  initial_capital: int                          # 초기 투자금
}
```

#### 3.1.1-legacy 전략 빌더 (5-Step Wizard, 레거시)

> 기존 블록 조합 방식의 전략 빌더. 향후 고급 사용자 전용 또는 프롬프트 파싱 결과의 상세 편집용으로 활용 가능.

| 단계 | 이름 | 기능 | 구현 상태 |
|------|------|------|-----------|
| Step 1 | 유니버스 선택 | KOSPI/KOSDAQ/NASDAQ 등 투자 대상 선택, 필터 적용 | ✅ 완료 |
| Step 2 | 진입/청산 조건 | 블록 조합으로 매수/매도 시그널 설계 | ✅ 완료 |
| Step 3 | 포지션·리스크 | 포지션 크기, 손절/익절, 최대 보유일 등 | ✅ 완료 |
| Step 4 | 백테스트 설정 | 기간, 초기자본, 수수료, 슬리피지 | ✅ 완료 |
| Step 5 | 결과 리포트 | 수익률, 샤프, MDD, 거래내역, 차트 | ✅ 완료 |

#### 3.1.2 시그널 블록 (29개)

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
| `per` | PER 필터 | operator, value | ✅ |
| `pbr` | PBR 필터 | operator, value | ✅ |
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

**AI/ML (1개)**
| 블록 ID | 이름 | 파라미터 | 상태 |
|---------|------|----------|------|
| `ai_model` | AI 상승 예측 | threshold, direction | ✅ |

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

### 3.2 백테스트 엔진

#### 3.2.1 엔진 파이프라인

```
입력: BacktestRequest (종목, 조건, 리스크, 기간)
  │
  ├─ 1. DataLoader: Parquet → Polars DataFrame
  ├─ 2. IndicatorEngine: 기술적 지표 계산 (8종)
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

---

### 3.3 AI/ML 시스템

#### 3.3.1 하이브리드 예측 모델

```
입력: 17개 기술적 지표 + 로그 수익률
    │
    ├─ Transformer Encoder
    │   ├─ 64차원 임베딩
    │   ├─ 4-Head Multi-Head Attention
    │   ├─ 2 Encoder Layers
    │   └─ 128차원 FFN
    │
    ├─ XGBoost Head
    │   └─ Gradient Boosting (feature importance 기반)
    │
    └─ Ensemble
        └─ 출력: 10일 내 7% 상승 확률 (0~1)
```

#### 3.3.2 설명 가능 AI (XAI)

- **프레임워크:** SHAP (SHapley Additive exPlanations)
- **방법:** TreeExplainer (XGBoost 전용)
- **제공 정보:**
  - 매매별 피처 기여도 (어떤 지표가 매수/매도 판단에 기여했는지)
  - Force Plot (개별 예측 분해)
  - Bar Plot (전체 피처 중요도)

#### 3.3.3 전략 최적화 (Optuna)

- **방식:** TPE (Tree-structured Parzen Estimator) 기반 베이지안 최적화
- **파라미터:** 이산형 리스트 또는 연속형 범위 (min, max, step)
- **제약조건:** 의미적 순서 보장 (예: shortMA < longMA)
- **타겟 메트릭:** CAGR, Sharpe, Profit Factor, Win Rate, Total Return
- **결과물:** 최적 파라미터, Top-N 결과, 파라미터 중요도, 마크다운 리포트

---

### 3.4 가상 매매 시스템 (페이퍼 트레이딩)

> **현재 상태:** 가상 주식시장 엔진 + 자동매매 시스템 구현 완료

#### 3.4.1 기능 명세

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| 가상 계좌 생성 | 초기 자금 설정, 복수 계좌 관리 | ✅ UI 구현 |
| 실시간 호가 조회 | 종목별 매수/매도 호가 표시 | ✅ API 구현 |
| 시장가/지정가 주문 | 매수·매도 주문 입력 | ✅ 완료 |
| 포지션 관리 | 보유 종목, 평균 단가, 평가 손익 | ✅ 완료 |
| 전략 연동 매매 | 백테스트 전략 기반 자동 주문 생성 | ✅ 완료 (자동매매/신호알림 모드 선택 UI + 가상 주식시장 엔진) |
| 거래 내역 | 체결 이력, 수수료 포함 손익 계산 | 🔲 개발 필요 |
| 포트폴리오 리밸런싱 | 비중 조정, 자동 리밸런싱 알림 | 🔲 개발 필요 |
| 실시간 PnL | 시장 데이터 기반 실시간 손익 추적 | 🔲 개발 필요 |

#### 3.4.2 가상 매매 아키텍처 (계획)

```
[사용자 전략]
    │
    ▼
┌──────────────────┐     ┌──────────────────┐
│  Strategy Runner │────▶│  Order Manager   │
│  (시그널 감시)    │     │  (주문 처리)      │
└──────────────────┘     └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
           ┌─────────────┐ ┌──────────┐ ┌──────────────┐
           │ Position Mgr │ │ Risk Mgr │ │ Trade Logger │
           │ (포지션 관리) │ │ (리스크)  │ │ (체결 기록)   │
           └─────────────┘ └──────────┘ └──────────────┘
                    │
                    ▼
           ┌──────────────────┐
           │  Virtual Market  │
           │  (실시간 데이터)   │
           └──────────────────┘
```

---

### 3.5 포트폴리오 관리

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| 포트폴리오 대시보드 | 전체 자산 현황, 수익률 추이 | ✅ 완료 |
| 홈 대시보드 재설계 | 전략/백테스트/가상계좌 허브 (WelcomeSection, StrategyOverview, BacktestHistory, VirtualAccountSummary, MarketSnapshot) | ✅ 완료 |
| 종목별 비중 | 파이차트, 섹터별 분산도 | ✅ 기본 구현 |
| 관심종목 | 종목 추가/삭제, 그룹 관리, DB 영구 저장 (SQLite) | ✅ 완료 |
| 리밸런싱 추천 | 목표 비중 대비 조정 제안 | 🔲 개발 필요 |
| 성과 귀인 분석 | 종목·전략·타이밍별 기여도 | 🔲 개발 필요 |

---

### 3.6 시장 데이터 & 분석

| 기능 | 설명 | 구현 상태 |
|------|------|-----------|
| KOSPI/KOSDAQ 지수 | 실시간 시장 지수 | ✅ 완료 |
| 종목 상세 페이지 | 차트, 재무제표, 기본정보 | ✅ 완료 |
| 종목 검색 | 이름/코드 기반 검색 | ✅ 완료 |
| 실시간 시세 | 현재가, 등락률, 거래량 | ✅ 완료 |
| 금융 뉴스 | 주요 뉴스 피드 | ✅ API 구현 |
| 섹터 분석 | 업종별 동향, 로테이션 | 🔲 개발 필요 |
| 상관관계 분석 | 종목 간 상관계수 히트맵 | 🔲 개발 필요 |

---

## 4. 데이터베이스 설계

### 4.1 현재 스키마 (SQLite + Prisma)

```sql
-- 사용자
User {
  id        Int      @id @default(autoincrement())
  email     String   @unique
  name      String?
  password  String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

-- 종목 마스터
Stock {
  id      Int     @id @default(autoincrement())
  symbol  String  @unique    -- "005930" (삼성전자)
  name    String             -- "삼성전자"
  market  String             -- "KOSPI" | "KOSDAQ" | "NASDAQ"
  backtestResults BacktestResult[]
}

-- 전략 정의
Strategy {
  id          String  @id @default(uuid())
  name        String
  description String?
  settings    String  -- JSON (StrategyDSL 직렬화)
  backtestResults BacktestResult[]
}

-- 백테스트 결과
BacktestResult {
  id         String   @id @default(uuid())
  strategy   Strategy @relation(fields: [strategyId])
  stock      Stock    @relation(fields: [stockId])
  summary    String   -- JSON (메트릭)
  trades     String   -- JSON (거래 내역)
}

-- 백테스트 이력
BacktestHistory {
  id           String   @id @default(uuid())
  strategyName String
  universe     String
  conditions   String   -- JSON
  metrics      String   -- JSON
  createdAt    DateTime @default(now())
}
```

### 4.2 확장 예정 스키마

```sql
-- 가상 계좌
VirtualAccount {
  id           String   @id @default(uuid())
  userId       Int      @relation(User)
  name         String
  initialCash  Float
  currentCash  Float
  createdAt    DateTime @default(now())
  positions    VirtualPosition[]
  orders       VirtualOrder[]
}

-- 가상 포지션
VirtualPosition {
  id          String @id @default(uuid())
  accountId   String @relation(VirtualAccount)
  symbol      String
  quantity    Int
  avgPrice    Float
  currentPrice Float
  unrealizedPnl Float
  openedAt    DateTime
}

-- 가상 주문
VirtualOrder {
  id          String   @id @default(uuid())
  accountId   String   @relation(VirtualAccount)
  symbol      String
  side        String   -- "BUY" | "SELL"
  type        String   -- "MARKET" | "LIMIT"
  quantity    Int
  price       Float?
  status      String   -- "PENDING" | "FILLED" | "CANCELLED"
  filledAt    DateTime?
  createdAt   DateTime @default(now())
}

-- 전략 실행 이력 (가상매매)
StrategyExecution {
  id          String   @id @default(uuid())
  accountId   String   @relation(VirtualAccount)
  strategyId  String   @relation(Strategy)
  status      String   -- "RUNNING" | "PAUSED" | "STOPPED"
  startedAt   DateTime
  stoppedAt   DateTime?
}

-- 알림
Alert {
  id          String   @id @default(uuid())
  userId      Int      @relation(User)
  type        String   -- "PRICE" | "SIGNAL" | "RISK" | "REBALANCE"
  condition   String   -- JSON
  triggered   Boolean  @default(false)
  createdAt   DateTime @default(now())
}
```

---

## 5. API 설계

### 5.1 현재 구현된 API (22개)

#### Frontend API Routes (Next.js)
| Method | Endpoint | 기능 |
|--------|----------|------|
| POST | `/api/login` | 로그인 |
| POST | `/api/logout` | 로그아웃 |
| POST | `/api/register` | 회원가입 |
| GET | `/api/user` | 사용자 정보 |
| GET | `/api/user/info` | 상세 사용자 정보 |
| GET | `/api/stock/quote` | 실시간 시세 |
| GET | `/api/stock/search` | 종목 검색 |
| GET | `/api/stock/historical` | 과거 가격 데이터 |
| GET | `/api/stock/[symbol]/detail` | 종목 상세 |
| GET | `/api/stock/[symbol]/orderbook` | 호가 데이터 |
| GET | `/api/stock/overview` | 시장 개요 |
| GET | `/api/stocks/names` | 종목 목록 |
| POST | `/api/stocks/sync` | 종목 데이터 동기화 |
| GET | `/api/watchlist` | 관심종목 가격 데이터 |
| GET/POST | `/api/watchlist/symbols` | 관심종목 목록 CRUD |
| DELETE/PATCH | `/api/watchlist/symbols/[symbol]` | 종목 삭제/그룹 변경 |
| GET/POST | `/api/watchlist/groups` | 그룹 목록 CRUD |
| PUT/DELETE | `/api/watchlist/groups/[id]` | 그룹 수정/삭제 |
| GET | `/api/market/indices` | 지수 데이터 |
| GET | `/api/news/top` | 뉴스 피드 |
| GET | `/api/universe/data` | 유니버스 필터 데이터 |
| GET/POST | `/api/strategy` | 전략 CRUD |
| GET | `/api/backtest/history` | 백테스트 이력 |
| GET | `/api/backtest/explain` | XAI 설명 |

#### Backend API (FastAPI)
| Method | Endpoint | 기능 |
|--------|----------|------|
| POST | `/backtest` | 백테스트 실행 |
| POST | `/optimize` | 전략 최적화 |
| POST | `/strategy/parse` | 자연어 → 구조화 전략 변환 (NL Parser) |
| POST | `/strategy/backtest-stream` | SSE 스트림 기반 백테스트 실행 (진행률 + 결과) |
| GET | `/model/status` | NL 파서 모델 로딩 상태 확인 |

### 5.2 추가 예정 API

| Method | Endpoint | 기능 | 우선순위 |
|--------|----------|------|----------|
| POST | `/api/virtual-account` | 가상 계좌 생성 | P1 |
| GET | `/api/virtual-account/[id]` | 계좌 상세 조회 | P1 |
| POST | `/api/virtual-account/[id]/order` | 주문 실행 | P1 |
| GET | `/api/virtual-account/[id]/positions` | 포지션 조회 | P1 |
| GET | `/api/virtual-account/[id]/orders` | 주문 이력 | P1 |
| POST | `/api/virtual-account/[id]/strategy/start` | 전략 자동 실행 시작 | ✅ 완료 |
| POST | `/api/virtual-account/[id]/strategy/stop` | 전략 자동 실행 중지 | ✅ 완료 |
| GET | `/api/portfolio/analysis` | 포트폴리오 분석 | P2 |
| GET | `/api/portfolio/rebalance` | 리밸런싱 추천 | P3 |
| GET | `/api/market/sectors` | 섹터별 분석 | P3 |
| GET | `/api/market/correlation` | 상관관계 분석 | P3 |
| POST | `/api/alert` | 알림 설정 | P3 |
| POST | `/api/strategy/share` | 전략 공유 | P4 |
| GET | `/api/strategy/marketplace` | 전략 마켓플레이스 | P4 |

---

## 6. 개발 로드맵

### Phase 1: 핵심 플랫폼 안정화 (현재 ~ v1.0)
> **목표:** 백테스트 엔진 안정성 확보, 핵심 UX 완성

| 작업 | 상세 | 상태 |
|------|------|------|
| 백테스트 엔진 버그 수정 | 시뮬레이터 바이어스 제거, 결과 정확성 검증 | ✅ 완료 |
| 시그널 엔진 벡터화 | 전체 시계열 벡터화 평가로 성능 최적화 | ✅ 완료 |
| 전략 빌더 V2 | 5단계 위자드 UI/UX 개선 | ✅ 완료 |
| **전략연구소 (프롬프트 기반)** | **자연어 전략 생성 — 로컬 LLM 파싱 + 대화형 수정 + SSE 백테스트** | **✅ 완료** |
| Optuna 최적화 통합 | 하이퍼파라미터 자동 최적화 | ✅ 완료 |
| AI 모델 통합 | Transformer+XGBoost 시그널 블록 | ✅ 완료 |
| 테스트 커버리지 확대 | 32개 테스트 파일, 핵심 경로 커버 | ✅ 완료 |
| 결과 대시보드 | 에퀴티 커브, 월별 수익, 종목별 통계 | ✅ 완료 |
| SHAP 설명 AI | 매매 판단 근거 시각화 | ✅ 완료 |

### Phase 2: 가상 매매 시스템 (v1.1)
> **목표:** 실시간 데이터 기반 페이퍼 트레이딩

| 작업 | 상세 | 우선순위 |
|------|------|----------|
| 가상 계좌 DB 스키마 | VirtualAccount, Position, Order 테이블 | ✅ 완료 |
| 주문 시스템 | 시장가/지정가 주문 처리, 체결 로직 | ✅ 완료 |
| 포지션 관리 | 실시간 보유 종목 평가, 평균 단가 계산 | ✅ 완료 |
| 실시간 시세 연동 | WebSocket 또는 폴링 기반 가격 업데이트 | ✅ 완료 |
| 전략 자동 실행 | 백테스트 전략을 가상 시장에서 자동 실행 | ✅ 완료 |
| 거래 내역 & 정산 | 수수료, 세금 포함 실현 손익 계산 | ✅ 완료 |
| 가상 매매 대시보드 | 종합 성과, 일/월별 PnL, 승률 통계 | ✅ 완료 |

### Phase 3: 고급 분석 & 최적화 (v1.2)
> **목표:** 전문적 퀀트 분석 도구 제공

| 작업 | 상세 | 우선순위 |
|------|------|----------|
| 워크포워드 분석 | 훈련/검증 기간 분할 최적화 | ✅ 완료 |
| 몬테카를로 시뮬레이션 | 수익률 분포 확률적 분석 | ✅ 완료 |
| 팩터 분석 | Fama-French, 모멘텀, 밸류 팩터 분해 | P2 |
| 종목 간 상관관계 | 히트맵, 최적 분산 포트폴리오 | P2 |
| 섹터 로테이션 분석 | 업종별 동향, 순환 패턴 | P3 |
| 리밸런싱 시뮬레이션 | 주기적 리밸런싱 전략 백테스트 | P3 |
| 벤치마크 비교 | KOSPI/S&P500 대비 알파/베타 분석 | P3 |
| NL 파서 고도화 | 복합 전략 해석, 다중 진입/청산 조건 조합 자연어 지원 | P2 |
| 전략 저장 & 불러오기 | 프롬프트 기반 생성 전략의 DB 저장, 이력 관리 | P2 |
| 전략 템플릿 | 인기 전략 프롬프트 템플릿 제공 (가치투자, 모멘텀 등) | P2 |

### Phase 4: 소셜 & 마켓플레이스 (v2.0)
> **목표:** 커뮤니티 기반 전략 공유 생태계

| 작업 | 상세 | 우선순위 |
|------|------|----------|
| 전략 공유 | 전략 퍼블리싱, 설명 문서화 | P3 |
| 전략 마켓플레이스 | 공개 전략 검색, 복제, 평가 | P4 |
| 리더보드 | 수익률 기준 전략 랭킹 | P4 |
| 전략 포크 | 공개 전략 복제 후 커스터마이징 | P4 |
| 커뮤니티 피드 | 전략 리뷰, 댓글, 토론 | P4 |

### Phase 5: 글로벌 확장 & 인프라 (v2.1+)
> **목표:** 해외 시장 지원, 프로덕션 인프라

| 작업 | 상세 | 우선순위 |
|------|------|----------|
| 미국 시장 데이터 | NASDAQ/NYSE OHLCV 데이터 수집 | P3 |
| 다중 통화 | USD/KRW 환산, 글로벌 포트폴리오 | P3 |
| PostgreSQL 마이그레이션 | SQLite → PostgreSQL (확장성) | P3 |
| Redis 캐싱 | 시세 데이터, 백테스트 결과 캐시 | P3 |
| Docker 컨테이너화 | 프론트엔드/백엔드/DB 컨테이너 분리 | P3 |
| CI/CD 파이프라인 | GitHub Actions 기반 빌드/테스트/배포 | P3 |
| 모니터링 | Sentry (에러), Grafana (메트릭) | P4 |
| 분당 요청 제한 | Rate Limiting (API 보호) | P3 |

---

## 7. 테스트 전략

### 7.1 현재 테스트 현황

| 영역 | 파일 수 | 프레임워크 | 커버리지 |
|------|---------|-----------|----------|
| 백엔드 시그널 | 5개 | pytest | 높음 |
| 백엔드 시뮬레이터 | 4개 | pytest | 높음 |
| 백엔드 AI | 3개 | pytest | 중간 |
| 백엔드 최적화 | 2개 | pytest | 중간 |
| 백엔드 회귀 | 3개 | pytest | 높음 |
| 백엔드 통합 | 2개 | pytest | 낮음 |
| 프론트엔드 | 1개 | Vitest | 낮음 |

### 7.2 Mock 데이터 생성기

| 항목 | 내용 | 상태 |
|------|------|------|
| 백엔드 OHLCV 생성기 | `backend/engine/mock_data_generator.py` — GBM 기반, 6가지 시나리오, 한국 상하한가·호가 단위 반영 | ✅ 완료 |
| pytest conftest | `backend/tests/conftest.py` — 공용 fixture (mock_ohlcv, mock_data_dir, sim_matrices 등) | ✅ 완료 |
| 프론트엔드 생성기 | `lib/mock-stock-data.ts` — GBM + seeded PRNG(mulberry32) 업그레이드, Math.random() 제거 | ✅ 완료 |
| CLI 도구 | `python -m engine.mock_data_generator --scenario bull --symbols A B --days 252` | ✅ 완료 |

**지원 시나리오:** `bull` / `bear` / `sideways` / `volatile` / `crash_recovery` / `realistic`

### 7.3 테스트 개선 계획

| 영역 | 목표 | 우선순위 |
|------|------|----------|
| 프론트엔드 단위 테스트 | 각 Step 컴포넌트, 블록 에디터 테스트 | P2 |
| E2E 테스트 | Playwright 기반 전략 생성→백테스트 플로우 | P3 |
| 성능 테스트 | 대규모 유니버스 (100+ 종목) 백테스트 벤치마크 | P3 |
| AI 모델 테스트 | 예측 정확도 모니터링, 드리프트 감지 | P3 |

### 7.3 테스트 실행 커맨드

```bash
# 백엔드 (안전한 테스트만)
cd backend && pytest tests/ \
  --ignore=tests/test_backtest_engine.py \
  --ignore=tests/test_engine_ai.py \
  --ignore=tests/test_ai_sell.py \
  --ignore=tests/test_api_isolation.py

# 프론트엔드
npm run test:frontend

# 전체 백엔드
cd backend && pytest tests/
```

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

## 9. 성능 최적화 전략

| 영역 | 현재 방식 | 최적화 계획 |
|------|-----------|-------------|
| 데이터 로딩 | Parquet + Polars | 자주 사용 종목 인메모리 캐시 |
| 시그널 계산 | NumPy 벡터화 | 변경 없음 (이미 최적) |
| 백테스트 실행 | vectorbt 단일 스레드 | 다중 종목 병렬 처리 |
| AI 추론 | PyTorch CPU | 배치 추론, 모델 양자화 |
| 프론트엔드 | CSR (Client-Side) | 결과 페이지 SSR 전환 |
| API 응답 | 매 요청 신규 계산 | Redis 캐싱 (동일 파라미터) |

---

## 10. 운영 & 모니터링 계획

### 10.1 배포 아키텍처 (목표)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Vercel     │────▶│  Cloud Run  │────▶│  Cloud SQL  │
│  (Frontend)  │     │  (Backend)  │     │ (PostgreSQL) │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │    Redis    │
                    │   (Cache)   │
                    └─────────────┘
```

### 10.2 데이터 파이프라인

```
[KRX/해외거래소]
    │ 매일 장 마감 후
    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Data Fetcher │────▶│  Parquet     │────▶│  AI Model    │
│ (스케줄러)    │     │  저장소      │     │  재학습       │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## 11. 핵심 지표 (KPI)

### 11.1 제품 지표

| 지표 | 정의 | 목표 |
|------|------|------|
| 전략 생성 수 | 사용자별 평균 생성 전략 수 | 5개+ / 월 |
| 백테스트 실행 수 | 일일 백테스트 실행 횟수 | 100회+ / 일 |
| 전략 최적화율 | 최적화 기능 사용 비율 | 30%+ |
| 가상 매매 전환율 | 백테스트 → 가상 매매 전환 | 20%+ |
| 사용자 잔존율 | 30일 재방문율 | 40%+ |

### 11.2 기술 지표

| 지표 | 정의 | 목표 |
|------|------|------|
| 백테스트 응답 시간 | 단일 종목 1년 | < 3초 |
| 다중 종목 응답 시간 | 50종목 3년 | < 30초 |
| AI 추론 시간 | 단일 예측 | < 500ms |
| API 가용성 | 월간 업타임 | 99.5%+ |
| 테스트 커버리지 | 백엔드 라인 커버리지 | 80%+ |

---

## 12. 리스크 & 완화 전략

| 리스크 | 영향 | 확률 | 완화 전략 |
|--------|------|------|-----------|
| 데이터 정확성 | 잘못된 백테스트 결과 | 중 | 다중 소스 교차 검증, 데이터 무결성 테스트 |
| 룩어헤드 바이어스 | 과대 추정된 수익률 | 중 | 엄격한 시점 분리, 회귀 테스트 유지 |
| AI 모델 과적합 | 실전 성능 저하 | 높 | 워크포워드 분석, 정기 재학습, 앙상블 |
| 서버 비용 증가 | 운영 지속성 | 중 | 캐싱 최적화, 요청 제한, 무료 티어 제한 |
| 규제 리스크 | 투자 자문 규제 | 낮 | "교육 및 시뮬레이션 목적" 명시, 면책 고지 |
| 실시간 데이터 의존 | 데이터 소스 중단 | 중 | 다중 데이터 프로바이더, 폴백 로직 |

---

## 13. 경쟁 분석 & 차별화

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
1. **자연어 → 퀀트 전략:** 한국어 프롬프트만으로 AI가 투자 전략을 자동 생성 — 코딩도 블록 조합도 불필요
2. **대화형 전략 수정:** 채팅으로 점진적으로 전략 파라미터를 조정하며 최적화
3. **설명 가능 AI:** 단순 수익률이 아닌, "왜" 매수/매도했는지 SHAP으로 해석
4. **한국 시장 딥 커버리지:** 4,052개 한국 종목, 기관/외인 수급, PER/PBR 등 국내 특화 데이터
5. **로컬 AI 프라이버시:** MLX/Ollama 기반 로컬 LLM 사용 — 투자 전략이 외부 서버로 전송되지 않음

---

## 14. 비즈니스 모델 (안)

### 14.1 프리미엄 모델

| 티어 | 가격 | 기능 |
|------|------|------|
| **Free** | ₩0 | 기본 블록 10개, 백테스트 5회/일, 1년 데이터 |
| **Pro** | ₩19,900/월 | 전체 블록, 무제한 백테스트, 5년 데이터, AI 시그널 |
| **Premium** | ₩49,900/월 | Pro + 자동 최적화, 가상 매매, 실시간 알림, 전략 공유 |

### 14.2 수익 다각화
- **전략 마켓플레이스:** 유료 전략 판매 시 수수료 (20%)
- **API 액세스:** 기업/기관용 백테스트 API (₩99,000/월~)
- **교육 콘텐츠:** 퀀트 투자 강의, 전략 설계 가이드

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

**Infrastructure**
- SQLite + Prisma ORM (현재), PostgreSQL (목표)
- ESLint, Vitest, pytest

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
```

### C. 파일 구조 참조

- 전략연구소 UI: `app/analytics/page.tsx` (프롬프트 기반 채팅 인터페이스)
- NL 전략 파서: `backend/engine/nl_parser.py` (자연어 → ParsedStrategy)
- 전략 변환기: `backend/engine/strategy_converter.py` (ParsedStrategy → BacktestRequest)
- 전략 DSL 타입: `types/strategy.ts`
- 시그널 블록 정의: `lib/strategy-blocks.ts` (879줄)
- 백테스트 엔진: `backend/backtest_engine.py` (14.5KB)
- 시그널 엔진: `backend/engine/signals.py` (30KB)
- 시뮬레이터: `backend/engine/simulator.py` (7.7KB)
- AI 엔진: `backend/ai/ai_engine.py` (11.9KB)
- 최적화: `backend/ai/local_optimization_agent.py` (8.2KB)
- 전략 빌더 V2 (레거시): `components/strategy/StrategyComposerV2.tsx`

---

*이 문서는 프로젝트의 현재 상태와 향후 계획을 반영합니다. 개발 진행에 따라 업데이트됩니다.*
