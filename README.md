# Simons — 종합 투자 시뮬레이션 플랫폼

한국/글로벌 주식 퀀트 투자 플랫폼. 자연어 프롬프트로 투자 전략을 설계하고, 백테스트와 가상매매로 전략을 검증하는 풀스택 웹 서비스.

## 핵심 기능

- **자연어 전략 생성** — 한국어로 전략을 설명하면 로컬 LLM(MLX/Ollama)이 퀀트 전략으로 자동 변환
- **벡터화 백테스트 엔진** — 4,052개 한국 종목 대상 vectorbt 기반 고속 시뮬레이션
- **AI 시그널 블록** — Transformer + XGBoost 하이브리드 모델, SHAP 기반 설명 가능 AI
- **전략 최적화** — Optuna 베이지안 최적화, 워크포워드 분석, 몬테카를로 시뮬레이션
- **가상매매 시스템** — 실시간 시세 기반 페이퍼 트레이딩, 리스크 관리 자동 적용
- **멀티 Provider 시세** — KIS(한국투자증권) → Naver → yfinance → pykrx → KRX 폴백 체인

## 기술 스택

| 영역 | 기술 |
|------|------|
| **Frontend** | Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts, TradingView Charts |
| **Backend** | Python FastAPI, Polars, Pandas, vectorbt, stockstats |
| **AI/ML** | PyTorch (Transformer), XGBoost, SHAP, Optuna, MLX (Apple Silicon) |
| **Database** | SQLite + Prisma ORM (12개 모델) |
| **Data** | 4,052개 종목 OHLCV Parquet, KIS WebSocket, KRX API |

## 시작하기

### 1. 환경 변수 설정

`.env` 파일 생성:

```env
DATABASE_URL="file:./prisma/prisma/dev.db"
JWT_SECRET=your_secret_key_here

# 한국투자증권 API (실시간 시세, 호가)
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
KIS_ACCOUNT_NO=your_account_number

# KRX Open API (유니버스 동기화)
KRX_API_KEY=your_krx_api_key
```

### 2. 프론트엔드 설치

```bash
npm install
npm run db:migrate
npm run db:generate
```

### 3. 백엔드 설치

```bash
cd backend
pip install -r requirements.txt
```

### 4. 서버 실행

```bash
npm run dev          # Next.js 프론트엔드 (port 3000)
npm run dev:backend  # FastAPI 백엔드 (port 8000)
npm run dev:all      # 프론트엔드 + 백엔드 + 스케줄러 동시 실행
```

## 프로젝트 구조

```
simons/
├── app/                    # Next.js App Router
│   ├── analytics/          # 전략연구소 (프롬프트 기반 전략 생성)
│   ├── backtest/           # 백테스트 이력 & 상세
│   ├── virtual-account/    # 가상계좌 & 가상매매
│   ├── stock/[symbol]/     # 종목 상세 (차트, 호가, 시그널)
│   ├── kospi/              # 시장 대시보드
│   ├── watchlist/          # 관심종목
│   └── api/                # 60+ REST API 엔드포인트
├── backend/                # Python FastAPI 서버
│   ├── main.py             # FastAPI 앱, 15+ 엔드포인트
│   ├── backtest_engine.py  # 백테스트 오케스트레이터
│   ├── engine/             # 핵심 엔진 모듈 (19개 파일)
│   │   ├── signals.py      #   시그널 엔진 (벡터화)
│   │   ├── simulator.py    #   매매 시뮬레이터 (vectorbt)
│   │   ├── indicators.py   #   기술적 지표 20+종
│   │   ├── nl_parser.py    #   자연어 파서 (MLX/Ollama)
│   │   ├── virtual_trader.py # 가상매매 자동 실행기
│   │   ├── market_data.py  #   멀티 Provider 시세 (CircuitBreaker)
│   │   └── providers/      #   시세 Provider 6개 (KIS, Naver, yfinance...)
│   ├── ai/                 # AI/ML 모듈
│   │   ├── ai_engine.py    #   Transformer + XGBoost v2 (45 피처)
│   │   ├── xai_engine.py   #   SHAP 설명 가능 AI
│   │   └── summarize.py    #   AI 백테스트 요약 (Qwen 7B)
│   └── tests/              # 38개 pytest 테스트
├── components/             # React 컴포넌트
│   ├── strategy/           # 전략 빌더 (Composer, Steps, Backtest, XAI)
│   ├── dashboard/          # 홈 대시보드
│   ├── order/              # 호가창, 주문
│   ├── portfolio/          # 포트폴리오 분석
│   └── __tests__/          # 24개 Vitest 테스트
├── lib/
│   ├── strategy-blocks.ts  # 29개 시그널 블록 정의
│   ├── strategy/           # BacktestService, UniverseResolver
│   └── scheduler.ts        # 장 스케줄러
├── data/
│   ├── ohlcv/              # 4,052개 종목 OHLCV Parquet
│   └── korea-stocks.json   # 한국 종목 마스터 (1,500+개)
├── model/                  # AI 모델 아티팩트 (Transformer v2 + XGBoost)
├── prisma/schema.prisma    # DB 스키마 (12개 모델)
└── types/strategy.ts       # 전략 DSL 핵심 타입
```

## 주요 기능 상세

### 전략연구소 (`/analytics`)

자연어 채팅 인터페이스에서 투자 전략을 설명하면:

1. 로컬 LLM(MLX Qwen2.5-32B 또는 Ollama)이 자동으로 전략 파싱
2. 유니버스, 필터, 시그널, 리스크 설정을 요약 표시
3. 대화형으로 파라미터 점진적 수정 가능
4. SSE 스트림으로 백테스트 진행률 실시간 전달

### 시그널 블록 (29개)

| 분류 | 블록 |
|------|------|
| 기술적 지표 | MA 크로스오버, RSI, MACD, 볼린저밴드, 거래량 급증, 돌파, EMA, 스토캐스틱, CCI, ADX |
| 펀더멘탈 필터 | PER, PBR, ROE, 부채비율, 시가총액, 거래대금, 거래정지 제외 |
| 수급 | 기관/외인 순매수 |
| AI/ML | `ai_model` (상승 예측), `ai_drop_model` (하락 예측) |
| 리스크 | 손절/익절, 최대 보유기간, 트레일링 스탑 |

### 백테스트 엔진

```
DataLoader (Parquet)
  → IndicatorEngine (기술적 지표)
  → SignalEngine (벡터화 boolean 평가)
  → AIEngine (선택, Transformer+XGBoost)
  → Simulator (vectorbt, SL/TP/TS/MaxHold)
  → ResultHandler (CAGR, Sharpe, MDD, 종목별 통계)
```

**성능 메트릭:** Total Return, CAGR, MDD, Sharpe, Sortino, Win Rate, Profit Factor, Kelly, 월별/종목별 수익률

### 가상매매 시스템 (`/virtual-account`)

- 복수 계좌 관리, 시장가/지정가 주문
- 전략 연동 자동매매 (VirtualTrader 백그라운드 루프)
- 리스크 관리 자동 적용 (SL/TP/TS/MaxHold)
- 수수료·세금 포함 실현 손익 정산
- 매매 로그 (진입/청산/오류 사유 기록)

### 장 스케줄러

| 시간 (KST) | 작업 |
|------------|------|
| 08:50 | 장전 캐시 워밍 |
| 09:00 | 장 개시, 자동매매 시작 |
| 09:05~15:25 | 1분 간격 시그널 평가 + 자동매매 |
| 15:30 | 장 마감, 자동매매 일시정지 |

## 데이터베이스

SQLite + Prisma ORM, 12개 모델:

`User` · `Stock` · `Strategy` · `BacktestResult` · `BacktestHistory`  
`VirtualAccount` · `VirtualMarketState` · `VirtualOrder` · `VirtualPosition` · `VirtualMarketLog`  
`WatchlistGroup` · `WatchlistSymbol`

## 테스트

```bash
# 백엔드 (서버/AI 모델 불필요한 테스트)
cd backend && pytest tests/ \
  --ignore=tests/test_backtest_engine.py \
  --ignore=tests/test_engine_ai.py \
  --ignore=tests/test_ai_sell.py \
  --ignore=tests/test_api_isolation.py

# 프론트엔드
npm run test:frontend
```

- 백엔드: 38개 pytest 파일 (시그널, 시뮬레이터, AI, 최적화, 시세, 회귀 테스트)
- 프론트엔드: 24개 Vitest 파일 (컴포넌트, API 라우트, 유틸리티)

## Harness Engineering

프로젝트에는 이제 `backend/harness/runner.py` 기반의 최소 백테스트 하네스 레이어가 들어 있습니다.

- 목적: 고정된 parquet 픽스처와 전략 입력으로 백테스트를 반복 실행하고, 핵심 기대값이 깨졌는지 빠르게 확인
- 위치: `backend/harness/suites/backtest_smoke.json`
- 출력: pass/fail, 케이스별 실패 사유, 요약 메트릭, 실행 시간 JSON 리포트

실행 예시:

```bash
python3 backend/harness/runner.py \
  backend/harness/suites/backtest_smoke.json \
  --output backend/harness/reports/backtest_smoke.latest.json
```

기본 스위트는 세 가지를 검증합니다.

- `CONFIG_TEST`: `same_close` 진입이 같은 봉 종가에 체결되는지
- `ZERO_TRADE_TEST`: 무매매 전략에서 사용자 경고가 유지되는지
- `TIME_EXIT_TEST_V2`: `max_holding_days`가 시간 기반 청산 사유를 생성하는지

새 케이스를 추가할 때는 `request`와 `expect`만 넣으면 됩니다. `expect`는 아래 형태를 지원합니다.

- `metric_ranges`: `totalReturn`, `trades` 같은 결과 필드의 `min` / `max` / `equals` / `approx`
- `signal_count`, `warning_count`, `date_count`
- `warnings_include`: 경고 문구 substring 검증
- `signals_include`: `type`, `date`, `price`, `condition_contains` 기반 시그널 검증

## DB 관리

```bash
npm run db:migrate    # Prisma 마이그레이션
npm run db:generate   # Prisma Client 재생성
npm run db:studio     # Prisma Studio GUI
```

## 빌드 & 린트

```bash
npm run build   # prisma generate + next build
npm run lint    # ESLint
```
