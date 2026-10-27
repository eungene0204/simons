# 전략 시뮬레이션 실행 명세

- 상태: **구현 완료(2026-10-27) — Z-1~Z-10, Q-1, G-2.** 구현 결과·검증·요구사항 대조는 §9, 명세와 달라진 점은 §9.2,
  남은 제약은 §8. (명세는 같은 날 먼저 작성했고 이 문서가 구현에 맞게 갱신된 정본이다.)
- 전용 boundary: `docs/architecture/boundaries.md` **Boundary Z: Public Strategy Simulation**.
  내비게이션 연결은 Boundary Q, 구현 후 문서 갱신은 Boundary G의 별도 작업이다.
- 성격: 투자 연구 도구. 전략 추천·자동 최적화·최적 파라미터 탐색·시장 전망·매매 시점 제안·
  전략 우열 판단은 제공하지 않는다.

## 0. 목적과 비목표

목적: 저장되어 있고 공개(`Strategy.isPublic`)로 설정된 전략을 대상으로 최근 3년~오늘(Asia/Seoul)의
과거 데이터 시뮬레이션 결과를 공개하고, 방문자가 지표 파라미터를 바꿔 결과 변화를 같은 조건으로
비교해 볼 수 있게 한다.

비목표(초기 버전에서 하지 않는 것):
- 조건 추가·삭제, 지표 교체, 연산자 변경, 자연어 재해석(LLM 호출 없음)
- 위험 관리(손절·익절·트레일링·보유 기간)·랭킹·자금 배분·유니버스 수정
- 자동 최적화·파라미터 탐색·여러 수정안 동시 비교·결과 순위/정렬
- 거래 내역 표, 자산 곡선·낙폭·종목별 차트, 고급 분석 패널
- 수정 결과 저장·공유 링크, 소유자 전략 반영

## 1. 조사 결과 (2026-10-27, 근거 경로)

| 항목 | 현행 | 근거 |
|---|---|---|
| 공개 플래그 | `Strategy.isPublic`(기본 false, 2026-10-20), 소유자가 '내 전략' 카드 토글로 전환 | `prisma/schema.prisma` Strategy, `app/api/strategy/[id]/route.ts` PATCH, `components/strategy/MyStrategiesView.tsx` |
| 기존 공개 목록 | `GET /api/shared/strategies` — **로그인 필수**(`getOwnershipContext`), `isPublic && isSaved && deletedAt null`, 성과는 공개 가상계좌 수익률. 상단 메뉴에서는 숨김(2026-10-21) | `app/api/shared/strategies/route.ts`, `lib/server/sharedStrategies.ts`, `components/layout/TopNavigation.tsx` |
| 전략 ID | `Strategy.id = "<userId>:<DSL sha256>"`(동명 충돌 시 `:<uuid8>` 접미) — **소유자 ID가 들어 있어 공개 식별자로 쓸 수 없다** | `app/api/strategy/route.ts` `buildOwnedStrategyId`, `app/api/strategy/save-with-backtest/route.ts` |
| 삭제 | `DELETE /api/strategy?id=` 는 행을 물리 삭제, `deletedAt` 필드도 존재 | `app/api/strategy/route.ts` |
| 저장 스냅샷(`Strategy.settings`) | 두 형태가 공존. ① 엔진 요청형: `entry`·`exit`·`risk`(`init_cash` 포함)·`options`(`fee_rate`·`slippage_rate`)·`period`·`symbols`·`universe_id`… ② 메타만: `id`·`name`·`description`·`updated_at`(실행 불가). 운영 DB 공개 전략 4건 중 ①=2건, ②=2건(읽기 전용 조회, 2026-10-27) | DB 조회, `pickExecutedRequest`의 `ENGINE_REQUEST_KEYS`(`lib/server/backtestCache.ts`) |
| 백테스트 실행 | Next `POST /api/backtest/run`·`/api/strategy/backtest-stream` 은 **로그인·월 한도 소비·사용자 기록 저장**(`saveCachedResult` → `BacktestHistory`/`BacktestResult`). 엔진 진입점은 FastAPI `POST /backtest` → `backtest_executor.run`(박스 칸 `BACKTEST_LOCAL_SLOTS`, 넘치면 Modal) + 워치독(`BACKTEST_TIMEOUT_S`, 기본 600초) | `app/api/backtest/run/route.ts`, `backend/main.py` `run_backtest`, `backend/backtest_executor.py`, `backend/engine/watchdog.py` |
| 실행 창·준비 기간 | `startDate`/`endDate`(YYYY-MM-DD)가 `period`보다 우선. 엔진이 지표 준비 기간(`_WARMUP_CALENDAR_DAYS = max(400, 최대기간×1.6+40)`)을 자체 확보하고 성과는 창 안에서만 집계 | `backend/backtest_engine.py` 1360·1479행 부근, `backend/schemas.py` `BacktestRequest` |
| 거래 비용 | `options.fee_rate`(매수·매도 대칭, 미지정 시 엔진 기본 0.15%), `options.slippage_rate`(미지정 시 0.20%), `options.sell_tax_rate`(미지정 시 매도일 시행 법정 세율 스케줄). 실제 적용값은 결과 `tradingCosts`로 동봉 | `backend/engine/simulator.py` `resolve_cost_rates`·`applied_trading_costs` |
| 결과 필드 | `initialCapital`, `equity[]`, `dates[]`, `totalReturn`, `cagr`, `maxDrawdown`, `sharpe`, `winRate`, `trades`, `perAssetStats{symbol: {profit,…}}`, `tradingCosts`, `warnings`, `version` | `backend/schemas.py` `BacktestResponse` |
| 거래 수·승률 정의 | `trades = len(pf.trades)` — vectorbt 거래 기록이라 **미청산 포지션을 포함**. 승률도 같은 모집단 | `backend/engine/result_handler.py` 526행 부근 |
| 종목별 손익 | `perAssetStats[sym].profit = pf.total_profit(group_by=False)` — 종목 열별 최종 평가 기준(미청산 평가손익 포함, 비용 차감). 정액 적립식 경로는 별도 계산 | `backend/engine/result_handler.py` 620·860행 부근 |
| 적립식·인출 | `contributions`가 있으면 `totalReturn`·`cagr`·`maxDrawdown`·`sharpe`가 시간가중 기준이 되어 "최종−초기 = 총 손익" 정의와 어긋난다 | `backend/schemas.py` `contributions` 주석 |
| 데이터 기준일 | 한국 지수 parquet(`data/index/KOSPI.parquet`) 최신 일자. 로더 `engine.market_index.load_index_frame("KOSPI", data_dir)` 존재. **한국 휴장일 달력은 저장소에 없다**(`krx_client._latest_trading_date`는 주말만 건너뜀, 미국만 `us_market_calendar`) | `backend/engine/market_index.py`, `backend/engine/krx_client.py` |
| 지표 메타데이터 | REGISTRY의 `IndicatorSpec.parameters{name: ParamSpec(min,max,required)}`, `value_range`, `engine_binding(종류, 엔진 필드)`. 공개 추출기 `build_public_metadata()`가 default·recommended_value를 제외하고 내보냄 | `backend/strategy_conversation/registry/indicator_registry.py`, `public_metadata.py` |
| 내부 호출 | Next 서버 → FastAPI는 `fetchBackend`(내부 토큰 헤더 자동 첨부) | `lib/server/backend.ts` |
| 모달·포커스 | `useDialogBehavior`(Esc·포커스 트랩·포커스 복귀) 공용 훅, 차트는 `recharts` 의존성 보유 | `lib/hooks/useDialogBehavior.ts`, `components/ui/ConfirmDialog.tsx`, `package.json` |
| 익명 요청 식별 | 게시판의 `identity(request)` — 신뢰 IP 헤더(`BOARD_TRUSTED_IP_HEADER`)가 없으면 모든 요청을 공용 식별자로 묶는 보수 정책 | `lib/board/server.ts` |
| 메뉴 | `TopNavigation.tsx`의 항목 배열(전략공유는 주석 처리로 숨김) | `components/layout/TopNavigation.tsx` |

결론:
1. 기존 Next 백테스트 라우트는 로그인·한도·사용자 기록 저장이 묶여 있어 **익명 공개 실행에 재사용할 수 없다**
   (인증 완화 금지). 엔진 실행은 FastAPI `backtest_executor.run`을 그대로 쓰는 **전용 공개 엔드포인트**를 둔다.
2. 지표 계산·준비 기간·비용·체결은 엔진이 이미 처리한다. 공개 기능은 요청을 조립하고(창·파라미터)
   결과를 **잘라 내기만** 한다(재계산 금지).
3. 공개 식별자는 `Strategy.id`가 아닌 별도 불투명 ID(`publicId`)를 쓴다.

## 2. 결정

### 2.1 확정 설계(이 명세의 기본값)

- 경로: 페이지 `/strategy-simulation`(카드 목록), 상세는 같은 페이지의 모달이며 딥링크 `?id=<publicId>`로 연다(형식이 틀린 값은 무시). 모달을 열고 닫으면 주소의 `?id=`가 함께 바뀐다.
- 원본 결과: 서버에 영속 저장(§5)하고 **조회 시 재검증·지연 갱신**(stale-while-revalidate). 목록·상세 조회는
  저장된 결과만 읽으며, 결과가 없거나 낡았으면 백그라운드 갱신을 예약할 뿐 요청 안에서 기다리지 않는다.
- 수정 결과: 방문자별 임시 사본으로만 실행하고 서버 메모리의 짧은 캐시에만 둔다(DB·사용자 기록 저장 없음).
- 계산은 FastAPI 공개 엔드포인트 하나가 창 계산·스냅샷 검증·파라미터 검증·엔진 실행·결과 축약을 맡는다.
  Next는 공개 여부 검사·식별자 변환·캐시·요청 제한·중복 합치기를 맡는다.

### 2.2 결정 (D1·D5는 사용자가 명시 승인, 나머지는 권장안대로 진행)

- D2: "서버 칸이 넘치면 로컬 9b 모델을 쓰라"는 지시를 백테스트에는 적용할 LLM이 없다는 점을 알리고 "배포 전 Modal 비용을 만들지 않는다"로 해석했다.
  실행 정책(`backtest_executor.py`)은 건드리지 않았고 공개 실행은 동시 1건·즉시 429로 제한했다.
- D3·D4·D6·D7은 사용자 확인 없이 권장안으로 구현했다. 바꾸고 싶으면 이 표의 해당 행을 기준으로 별도 작업을 연다.
- D5: 승인 후 '내 전략' 공개 토글의 안내 문구를 "공개하면 로그인 없이 누구나 볼 수 있는 전략 시뮬레이션 화면에 …"로 바꿨다(`MyStrategiesView.tsx`). 기존 공개 전략 소유자에게 알리는 일은 하지 않았다(§8).

| ID·상태 | 결정 | 권장안 | 막는 작업 |
|---|---|---|---|
| D1 ✅ 승인(2026-10-27, 운영 DB 적용 완료) | 원본 결과 영속 저장을 위한 **신규 Prisma 모델 1개**(`PublicSimulationResult`)와 마이그레이션. Global Forbidden의 `prisma/**` 예외를 Boundary Z에 이 모델 한정으로 추가해야 한다 | 승인. 대안(서버 메모리)은 재시작·배포마다 전 카드가 '계산 중'이 되고 "갱신 중 이전 결과 표시" 요구를 만족하지 못한다 | Z-4 이후 전부 — **착수 전 승인 필요** |
| D2 ✅ 해석 후 진행 | 익명 실행이 박스 칸을 넘치면 `backtest_executor`가 **Modal로 넘긴다(비용 발생)** | 공개 실행 동시 1건 상한 + 요청 제한(§3.8)으로 시작하고 Modal 넘침은 허용. 차단을 원하면 `backtest_executor.py` 변경이 필요해 Boundary Z 밖이다 | Z-3 — **착수 전 승인 필요** |
| D3 ✅ 권장안 적용 | 한국 휴장일 달력이 없다 → 데이터 지연 판정 기준 | "오늘 기준" 문구를 쓰지 않고 항상 데이터 기준일을 표기. 직전 평일보다 오래되면 "데이터가 최신 확정 거래일보다 늦을 수 있음(휴장일 포함 가능)" 표시(§3.2). 정확한 판정이 필요하면 달력 의존성 추가를 별도 결정 | Z-1 |
| D4 ✅ 권장안 적용 | 초기 버전 제외 대상: 정액 적립식·정기 인출 전략, 미국 유니버스 전략, AI 신호(`ai_model`·`ai_drop_model`) 전략 | 제외하고 '시뮬레이션 불가 + 사유' 표시. 적립식은 총 손익 정의 불일치, 미국은 /us 차단 중, AI 신호는 운영 스위치로 꺼질 수 있음 | Z-1·Z-3 |
| D5 ✅ 승인(2026-10-27 "공개 전략을 노출해도 돼") | **공개 범위 확대**: 지금까지 `isPublic`은 "로그인 사용자에게 보이는 전략공유"였다. 이 메뉴는 같은 플래그로 **비로그인 방문자에게 전략 조건과 성과**를 공개한다. 기존 공개 전략 4건의 소유자는 이 노출에 동의한 적이 없다 | 메뉴 공개(Q-1) 전에 '내 전략' 토글 안내 문구를 "로그인 없이 누구나 열람"으로 바꾸는 작업(Boundary A/P, 별도 승인)을 먼저 하거나, 별도 동의 플래그를 둔다. 결정 전에는 Q-1을 하지 않는다 | Q-1 — **착수 전 승인 필요** |
| D6 ✅ 권장안 적용 | 스냅샷에 `risk.init_cash`·`options.fee_rate`·`options.slippage_rate` 중 하나라도 없을 때 | 엔진 기본값으로 채우지 않고 '시뮬레이션 불가(계산 조건 누락)'. 증권거래세는 사용자 설정이 아닌 법정 세율이라 미지정 시 엔진의 시행일 기준 스케줄을 쓰고 적용 범위를 표시 | Z-1 |
| D7 ✅ 권장안 적용 | 엔진 `trades`·`winRate`는 미청산 포지션을 포함한다 → 요구사항의 "완료 거래 수"와 정의가 다르다 | 기존 백테스트와 같은 값을 쓰되 라벨을 "거래 수(미청산 포함)"·"승률(미청산 평가 포함)"로 정확히 표기. '완료 거래 수'라는 이름은 쓰지 않는다 | Z-1 |

## 3. 기능 명세

### 3.1 공개 범위와 접근 제어

- **공개 대상 조건(단일 정의)**: `Strategy.isPublic = true AND isSaved = true AND deletedAt IS NULL`.
  목록·상세·원본 결과 조회·수정 실행·캐시 응답·백그라운드 갱신 저장의 **모든 지점**에서 같은 조건을 DB로 다시 확인한다.
- 로그인 불필요. 기존 인증·소유권 검사(`getOwnershipContext`·`withOwnership`)는 건드리지 않으며, 공개 라우트는
  사용자 세션을 읽지 않는다.
- 공개 식별자 `publicId`: `PublicSimulationResult`(§5) 행의 무작위 ID. `Strategy.id`(소유자 ID 포함)는 응답에 싣지 않는다.
- 공개 응답 필드는 **허용 목록**으로만 만든다:
  - 전략: `publicId`, `name`, `description`, 조건 표시용 스냅샷 부분집합 — `entry`, `exit`, `risk`의 표시 필드,
    `universe_id`, `sector`, `etf_theme`, `exclude_sectors`, `listing_from`, `listing_to`, `backtest_mode`,
    `target_stocks`(종목명·코드만). `symbols`(전체 종목 목록)·`id`·`strategy_id`·`userId`·`canonical_strategy_dsl`은 제외.
  - 결과: §4.3의 공개 요약 DTO만. 엔진 원본 결과(`signals`·`analytics`·`warnings` 원문 등)는 싣지 않는다.
  - 소유자 이름·이메일·계좌·가상계좌 성과·비공개 실행 기록·`BacktestHistory`는 어떤 응답에도 없다.
- 공개 철회·삭제:
  - 목록·상세: 조회 쿼리가 공개 조건으로 조인하므로 즉시 사라진다(상세는 404).
  - 원본 결과 행: `Strategy` 삭제 시 FK `onDelete: Cascade`로 함께 삭제. 비공개 전환 시 행은 남지만 조회 조건에서 걸러진다.
  - 진행 중 실행: 엔진 응답을 받은 뒤 **저장·응답 직전에** 공개 조건과 `snapshotHash`를 다시 확인한다.
    불일치면 결과를 버리고 저장하지 않으며 수정 실행 응답은 404(`STRATEGY_NOT_PUBLIC`).
  - 방문자 수정 캐시 히트도 응답 전에 공개 조건을 다시 확인한다.
- 목록: 전략명 부분 검색(`q`, 대소문자 무시, 1~50자), 페이지 이동(`page`, 20개). 기본 정렬은 전략명 오름차순(동명은 `publicId`).
  전체 건수를 매번 세지 않고 21번째 행으로 다음 페이지 유무를 판단한다. 추천·순위·성과순 정렬은 없다.

### 3.2 계산 기간과 데이터 기준

정의(모두 FastAPI 공개 모듈이 계산, `zoneinfo("Asia/Seoul")`):

| 용어 | 정의 |
|---|---|
| 오늘(`today`) | 계산 시작 시각의 Asia/Seoul 날짜 |
| 요청 시작일(`requestedStart`) | `today`에서 달력 기준 3년 전 같은 월·일. 그 해에 해당 일이 없으면(2월 29일) **2월 28일** |
| 요청 종료일(`requestedEnd`) | `today` |
| 데이터 기준일(`dataAsOf`) | `load_index_frame("KOSPI", data_dir)`의 최신 일자 = 확정 데이터가 있는 마지막 거래일. 장중이거나 당일 동기화 전이면 자연히 전 거래일 |
| 엔진 요청 창 | `startDate = requestedStart`, `endDate = min(today, dataAsOf)`. 휴장일·장중에도 같은 규칙 |
| 실제 계산 기간(`actualStart`~`actualEnd`) | 엔진 결과 `dates[0]`~`dates[-1]` |
| 계산 완료 시각(`computedAt`) | 엔진 응답 수신 시각(UTC 저장, 화면은 KST) |

- 윤년 예: `today=2028-02-29` → `requestedStart=2025-02-28`; `today=2027-03-01` → `2024-03-01`; `today=2026-02-28` → `2023-02-28`.
- 준비 기간: 엔진이 `startDate` 이전 데이터를 자체 확보한다(재구현 금지). 성과 지표·곡선·종목 손익은 엔진이
  창 안에서 집계한 값만 쓴다. 검증: `actualStart >= requestedStart`, `actualEnd <= endDate`.
- 미래 데이터: 창 종료가 `dataAsOf`를 넘지 않으며 엔진의 체결 지연(`next_open` 등) 규칙을 그대로 따른다.
- 3년 미만: `actualStart`가 `requestedStart`보다 **7일 넘게** 늦으면(최장 연휴 여유) `limited = true`,
  사유 `DATA_STARTS_LATER`("데이터 시작일이 요청 시작일보다 늦습니다")와 실제 기간을 표시한다. 엔진 결과가 빈 창이면 실패(§3.8).
- 지연 표시(D3): 화면은 "오늘 기준"이라고 쓰지 않는다. 항상 "데이터 기준일 YYYY-MM-DD"를 표기하고,
  `dataAsOf`가 `today` 직전 평일보다 이르면 `stale = true` → "데이터가 최신 확정 거래일보다 늦을 수 있습니다(휴장일 포함 가능)".
- 화면에는 요청 기간 / 실제 계산 기간 / 데이터 기준일 / 계산 완료 시각을 **각각 별도 줄**로 표시한다.

### 3.3 실행 스냅샷과 계산 조건

- 원본 스냅샷 = `Strategy.settings` JSON에서 `ENGINE_REQUEST_KEYS`(`lib/server/backtestCache.ts`) 집합만 고른 엔진 요청.
  `snapshotHash = sha256(stableStringify(스냅샷))`.
- 실행 가능 판정(순서대로, 첫 실패가 사유):
  1. `entry`·`exit`·`risk` 객체가 있고 `symbols`가 비어 있지 않거나 `universe_id`가 있다 — 아니면 `NO_EXECUTABLE_SNAPSHOT`
  2. FastAPI `BacktestRequest` 스키마 검증 통과 — 아니면 `INVALID_SNAPSHOT`
  3. D6: `risk.init_cash`·`options.fee_rate`·`options.slippage_rate` 존재 — 아니면 `MISSING_RUN_CONDITION`(누락 항목명 포함)
  4. D4: 적립식·인출 옵션, 미국 유니버스, AI 신호 조건 없음 — 아니면 각각 `UNSUPPORTED_CONTRIBUTIONS`·`UNSUPPORTED_REGION`·`UNSUPPORTED_AI_SIGNAL`
- 실행 요청 = 스냅샷 깊은 복사 + `startDate`/`endDate`(§3.2) 덮어쓰기. `period`는 창이 우선하므로 그대로 두고,
  화면에 "원본 저장 기간(예: 5y)과 별개로 이 메뉴는 최근 3년 고정"을 표시한다. 그 밖의 값은 바꾸지 않는다.
- 표시하는 계산 조건: 초기자금(`risk.init_cash`), 수수료(`tradingCosts.buyFeeRate`·`sellFeeRate`), 슬리피지(`slippageRate`),
  증권거래세(`sellTaxRate` 또는 `sellTaxRateRange` + "매도일 시행 세율"), 체결 기준(`risk.execution_timing`,
  `execution_delay_days`). 값은 엔진이 **실제 적용해 돌려준** `tradingCosts`에서 읽는다.
- 원본과 수정본은 같은 창·초기자금·비용·`dataAsOf`·엔진 버전을 쓴다(§3.7).

### 3.4 요약 지표

| 지표 | 원천 | 단위/표기 | 계산 불가 |
|---|---|---|---|
| 초기자금 | `initialCapital` | 원 | 없음(필수 조건) |
| 최종 평가자산 | `equity[-1]` | 원 | 곡선 비면 실패 |
| 총 손익 | `equity[-1] − initialCapital` | 원, 부호 표시 | 〃 |
| 누적 수익률 | `totalReturn` | % | 〃 |
| 최대 낙폭(MDD) | `maxDrawdown` | % | 〃 |
| CAGR | `cagr` | % | 실제 기간 < 1년이면 '—' "기간이 1년 미만" |
| 샤프 비율 | `sharpe` | 소수 2자리 | 수익률 변동 0이면 '—' "변동 없음" |
| 승률(미청산 평가 포함) | `winRate` | % | `trades = 0`이면 '—' "거래 없음" |
| 거래 수(미청산 포함) | `trades` | 회 | — |

- 총 손익 기준: **실현손익 + 마지막 데이터 기준일 종가로 평가한 미실현손익**, 수수료·증권거래세·슬리피지 차감 후.
  화면 툴팁에 그대로 명시한다.
- 지표는 기존 백테스트 결과와 **같은 필드·같은 값**이다(재계산 금지). 검증: 같은 요청을 기존 `/backtest`로 실행한 값과 일치.
- 일관성 검사: `|(equity[-1]/initialCapital − 1)×100 − totalReturn| ≤ 0.01`. 어긋나면 해당 결과를 실패로 처리(`INCONSISTENT_RESULT`).
- 상태 구분: `ready`(정상) / `no_trades`(실행 성공·거래 0 — 지표는 표시, 승률 '—') / `unavailable`(실행 불가 사유) /
  `failed`(실행 오류·시간 초과·일관성 실패) / `pending`(아직 결과 없음, 계산 예약됨). 실패를 0%나 거래 없음으로 바꾸지 않는다.

### 3.5 종목별 손익 기여

- 대상: 실행에서 실제 거래·보유한 종목 = `perAssetStats` 중 `trades > 0` 또는 `profit ≠ 0`.
- 손익 기여액 = `perAssetStats[sym].profit`(원). 기준은 총 손익과 같다(실현+미실현, 비용 차감).
- 일관성 검사: `|Σ profit − 총 손익| ≤ max(1원, |총 손익|×0.0001)`. 어긋나면 종목 영역만 "집계 기준이 전체 결과와 맞지 않아 표시하지 않습니다"로 대체(가짜 값 금지).
- 상위 3 = `profit` 내림차순 중 `profit > 0`, 하위 3 = 오름차순 중 `profit < 0`. 한 종목은 한쪽에만 나온다(중복 없음).
  해당 종목이 없으면 그 칸은 빈 상태 문구. 거래가 없으면 두 칸 모두 "이 기간에 거래가 없었습니다".
- 표시: 종목명(서버가 기존 종목 마스터로 매핑, 실패 시 코드), 종목코드, 손익 기여액.
- 제목: '손익 기여 상위 종목', '손익 기여 하위 종목'. 부제 "기간 내 과거 손익 집계". 추천·전망 표현 금지.

### 3.6 그래프

- 종류는 **누적 수익률 선 차트 하나**. X축 날짜, Y축 누적 수익률(%) = `(equity[i] / initialCapital − 1) × 100`.
- 원본만 있으면 한 선(원본). 수정 결과가 있으면 같은 차트에 원본·수정본 두 선(범례: '공개 원본', '사용자 수정 시뮬레이션').
  두 결과의 날짜 축은 같은 창이라 같아야 하며, 다르면 수정본을 실패(`WINDOW_MISMATCH`)로 처리한다.
- 툴팁: 날짜 + 해당 시점 누적 수익률(두 선이면 둘 다).
- 카드 미니 그래프: 같은 저장 결과의 곡선을 서버가 최대 120점으로 줄인 것(첫·마지막 점 포함, 등간격 인덱스).
  상세는 일별 전체 곡선. 결과가 없거나 실패면 그래프 자리를 상태 문구로 대체한다(임의 곡선 금지).
- 자산 곡선·낙폭·종목별 차트는 만들지 않는다.

### 3.7 지표 수정과 결과 비교

- 수정 가능 항목 설명자(`editableParams`)는 **서버(FastAPI)가 스냅샷과 REGISTRY로 결정론적으로 만든다**. 프론트엔드는
  이름·단위·범위·지원 여부 사전을 두지 않고 설명자를 그대로 렌더한다.
  - 대상: `entry.conditions[i]`·`exit.conditions[i]` 각각. 조건의 `(type, id)`를 `IndicatorSpec.engine_binding`으로 되짚어 잎 스펙을 찾는다.
  - 항목: 조건 `params`에 **이미 존재하는** 키 중 ① 스펙 `parameters`에 같은 이름이 있고 min/max가 모두 정의된 키,
    ② 임계값 `value`이며 스펙 `value_range`가 있는 경우. 각 항목 = `{path, label, unit, original, minimum, maximum, integer, editable:true}`.
  - 그 밖의 숫자 키는 `editable:false`와 사유(`NO_RANGE_METADATA`·`UNSUPPORTED_INDICATOR`)로 보여 준다. 연산자 같은 문자열 키는 파라미터가 아니므로 나열하지 않는다(`NOT_A_PARAMETER`는 쓰지 않는다 — §9.2).
  - default·recommended_value는 쓰지 않는다. 원본에 없는 키를 새로 만들지 않는다(누락 값 보완 금지).
  - 이름표는 REGISTRY `display_name` + 파라미터명. 정수 여부는 원본 값이 정수이고 스펙이 기간형(`period`·`*_days`)일 때.
- 수정 요청: `{publicId, overrides: [{path, value}], baseSnapshotHash, dataAsOf}`. 서버 검증(실패 시 400 `INVALID_PARAMETER` + 항목별 사유):
  - `path`가 설명자의 `editable:true` 항목일 것, 값은 유한 수, `[minimum, maximum]` 안, 정수 항목은 정수.
  - `baseSnapshotHash`가 현재 스냅샷과 같고 `dataAsOf`가 원본 결과의 기준일과 같을 것 — 아니면 409 `BASELINE_CHANGED`(화면은 원본을 다시 불러온다).
  - 항목 수 ≤ 설명자 항목 수, 중복 path 금지. 모든 값이 원본과 같으면 실행하지 않고 원본 결과를 돌려준다.
- 실행: 원본 스냅샷의 **깊은 복사본**에만 덮어쓴 뒤 원본과 같은 창으로 실제 백테스트를 실행한다. 원본 `Strategy.settings`·원본 결과 행은 읽기만 한다.
- 화면 동작(모달 안):
  - 입력이 유효해진 뒤 600ms 디바운스로 자동 재계산. 유효하지 않은 입력은 필드 옆에 사유를 표시하고 요청하지 않는다.
  - 모달당 **동시 1건**. 실행 중 새 입력이 오면 대기열의 마지막 입력 하나만 남기고, 진행 중 요청이 끝나면 그 입력으로 다시 보낸다.
    응답은 요청 순번·모달 세션 토큰·전략 `publicId`가 모두 현재와 같을 때만 반영한다(늦은 응답·다른 전략·닫힌 모달 응답 폐기).
    모달을 닫거나 전략을 바꾸면 `AbortController`로 진행 중 요청을 끊는다.
  - 계산 중에는 수정본 지표·종목·선을 흐리게 하고 "현재 입력으로 계산 중" 표시. 이전 수정 결과를 현재 입력 결과처럼 보이지 않게 한다.
  - 완료 시 요약 지표·종목별 손익·차트를 함께 갱신. 원본값·수정값·차이를 숫자로 표시하며 수익률·MDD·CAGR 차이는 **%p**, 금액 차이는 원.
  - '원본으로 초기화'는 입력을 원본값으로 되돌리고 수정 결과·대기 요청을 지운다.
  - 수정 결과에는 항상 '사용자 수정 시뮬레이션' 표시. 카드·원본 결과·소유자 전략에 반영하지 않는다. 모달을 닫고 다시 열면 원본으로 시작한다.

### 3.8 실행 안정성과 캐시

- 캐시 키(공통): `sha256(stableStringify({kind, snapshotHash, overrides(정렬), requestedStart, endDate, initCash, feeRate, slippageRate, sellTaxRate, dataAsOf, engineVersion}))`.
  `kind ∈ {original, modified}`로 원본·수정 캐시를 분리한다.
- 원본 결과(§5 DB):
  - 조회 시 `snapshotHash`·`dataAsOf`(현재 값)·`engineVersion`(현재 값) 중 하나라도 다르면 `refreshing`으로 표시하고 이전 결과와 그 기준일을 그대로 보여 준다.
  - 갱신 예약은 행의 `refreshLeaseUntil`을 조건부 갱신(CAS)으로 잡은 프로세스 하나만 실행한다. 원본 갱신 동시 1건, 순차 처리.
  - 현재 `dataAsOf`·엔진 버전은 FastAPI `GET /public-simulation/baseline`을 Next가 5분간 메모리 캐시해 얻는다(목록 조회가 엔진을 실행하지 않는다).
  - 실패 시 이전 결과를 유지하고 `lastError`·`lastAttemptAt`을 기록한다. 다음 시도는 **고정 15분**(`BUSY`는 60초) 뒤이며 지수 지연은 구현하지 않았다(§9.2).
  - 날짜가 바뀌어 `window.requestedStart`가 달라진 결과도 낡은 것으로 보고 갱신한다. 원본이 낡았거나 `pending`인 동안 수정 실행은 409 `BASELINE_CHANGED`(`reason: REFRESHING`)로 막는다.
- 수정 결과(서버 메모리 LRU, Next 프로세스): 최대 500개, TTL 30분. 같은 키의 진행 중 요청은 하나로 합친다(in-flight map).
- 요청 제한(익명): 식별자 = `lib/board/server.ts`의 `identity(request)`(가져다 쓰기만, 수정 금지).
  수정 실행 20회/10분/식별자, 전체 60회/10분. 초과 시 429 `RATE_LIMITED` + `retryAfterSeconds`.
- 동시 실행(FastAPI): 공개 엔드포인트 전용 세마포어 `PUBLIC_SIMULATION_MAX_CONCURRENCY`(기본 1). 비어 있지 않으면 즉시 429 `BUSY`(대기열 없음).
- 시간 제한: 공개 실행 `PUBLIC_SIMULATION_TIMEOUT_S`(기본 180초)을 워치독 한도로 쓰고, Next `fetchBackend` 타임아웃은 그보다 15초 길게. 초과 시 `failed/TIMEOUT`.
- 사용자 안내(상태 → 문구·행동):
  - `RATE_LIMITED`/`BUSY` → "요청이 많아 지금은 계산할 수 없습니다. N초 뒤 다시 시도해 주세요." + 다시 시도 버튼
  - `TIMEOUT`/`ENGINE_ERROR` → "계산에 실패했습니다." + 다시 시도 버튼(원본 결과는 그대로)
  - `STRATEGY_NOT_PUBLIC` → "이 전략은 더 이상 공개되어 있지 않습니다." 모달 내용 비움
  - `unavailable` → '시뮬레이션 불가' + 사유
- 원본 결과 저장·조회·수정 결과 모두 사용자 기록 테이블(`BacktestHistory`·`BacktestResult`·`UserBacktestHistory`)에 쓰지 않으며 월 백테스트 한도를 소비하지 않는다.

### 3.9 UI와 문구

- `docs/UI_GUIDELINES.md` 토큰(`--background`, `--text-label`, flat-card, `rounded-2xl`, 모달 그림자)과 다크 전용 규칙을 따른다.
- 목록: 검색창 + 반응형 카드 그리드(모바일 1열, `md` 2열, `xl` 3열) + 이전/다음 페이지.
- 카드(`<button>` 또는 `role="button"`+`tabIndex=0`, Enter/Space로 열기): 전략명, 설명 2줄 말줄임, 누적 수익률, 총 손익, MDD,
  미니 그래프, 데이터 기준일, 상태 배지(계산 중·갱신 중·데이터 부족·시뮬레이션 불가·실패). 순위·추천 배지 없음.
- 모달(`role="dialog"`, `aria-modal`, `aria-labelledby`, `useDialogBehavior`로 Esc·포커스 트랩·닫으면 카드로 포커스 복귀):
  순서 = 전략 정보(이름·설명·조건 요약) → 기간·계산 조건 → 요약 지표(원본/수정/차이) → 누적 수익률 차트 → 종목별 손익 → 지표 수정 폼(+원본으로 초기화).
  모바일은 전체 화면, 내용은 모달 내부 스크롤. 닫기 버튼 명시.
- 폼: 각 입력에 `<label>`·단위·허용 범위 표시, `aria-invalid`·`aria-describedby`로 오류 연결. 계산 상태는 `aria-live="polite"`.
- 공통 안내는 페이지 하단에 한 번: '과거 데이터 기반 시뮬레이션 결과이며 미래 수익을 보장하지 않습니다.'
- 지표 툴팁은 뜻과 읽는 법만(예: "MDD — 기간 중 고점 대비 가장 크게 떨어진 비율"). 평가·권유 문구 금지.
- 금지 문구: 추천 전략·최고의 전략·지금 매수/매도·AI 투자 코치·유망·우수·더 좋은·수익 보장. 원본/수정 비교에도 "개선"·"악화" 대신 "차이"만 쓴다.
- 모든 신규 문구는 `t()`로 감싸고 `lib/i18n/en.ts`에 영어를 추가한다(i18n 커버리지 게이트).

## 4. API 계약

### 4.1 FastAPI (내부 토큰 필수, `fetchBackend` 경유만)

- (실제 경로는 모두 `/internal/public-simulation/…` — `/internal/` 접두 경로가 내부 토큰 잠금 대상이기 때문이다)
- `GET /public-simulation/baseline` → `{ today, requestedStart, requestedEnd, endDate, dataAsOf, stale, engineVersion }`
- `POST /public-simulation/run`
  - 요청: `{ snapshot: <엔진 요청>, overrides?: [{path, value}] }` (snapshot은 Next가 DB에서 읽어 넣는다. 브라우저 입력이 아니다)
  - 응답 200: `{ status: "ready"|"no_trades", window, conditions, summary, curve, contributors, editableParams, engineVersion, dataAsOf, computedAt }`
  - 응답 200 `{ status: "unavailable", reason }` — 실행 불가 판정(§3.3)
  - 400 `INVALID_PARAMETER`(항목별 사유), 429 `BUSY`, 504 `TIMEOUT`, 500 `ENGINE_ERROR`(메시지 일반화, 내부 경로·스택 미포함)
- `POST /public-simulation/describe` → `{ status, reason?, editableParams }` — 실행 없이 실행 가능 판정·설명자만(모달 첫 렌더용)

### 4.2 Next.js (공개, 세션 불필요)

- `GET /api/strategy-simulation?q=&page=` → `{ items: CardDTO[], page, hasNext, baseline: {dataAsOf, stale, requestedStart, requestedEnd} }`
- `GET /api/strategy-simulation/[publicId]` → `DetailDTO`(전략 공개 필드 + 원본 결과 + `editableParams` + 상태). 비공개·없음 → 404
- `POST /api/strategy-simulation/[publicId]/run` → 요청 `{ overrides, baseSnapshotHash, dataAsOf }`, 응답 수정 결과 DTO. 오류 코드는 §3.8
- 모든 응답 `Cache-Control: no-store`(공개 철회가 CDN·브라우저 캐시로 남지 않게).

### 4.3 공개 결과 DTO

```ts
type PublicSimulationResult = {
  status: "pending" | "refreshing" | "ready" | "no_trades" | "unavailable" | "failed";
  reason?: string;                       // unavailable/failed 코드
  window?: { requestedStart: string; requestedEnd: string; actualStart: string; actualEnd: string;
             dataAsOf: string; stale: boolean; limited: boolean; limitReason?: string };
  computedAt?: string;                   // ISO UTC
  conditions?: { initialCapital: number; buyFeeRate: number; sellFeeRate: number; slippageRate: number;
                 sellTaxRate: number | null; sellTaxRateRange: [number, number] | null;
                 executionTiming: string; executionDelayDays: number | null; savedPeriod: string | null };
  summary?: { initialCapital: number; finalEquity: number; totalProfit: number; totalReturnPct: number;
              maxDrawdownPct: number; cagrPct: number | null; sharpe: number | null; winRatePct: number | null;
              trades: number; unavailableReasons: Record<string, string> };
  curve?: { dates: string[]; returnPct: number[] };      // 상세=일별, 카드=최대 120점
  contributors?: { top: Contributor[]; bottom: Contributor[]; hidden?: "INCONSISTENT" };
  engineVersion?: string;
};
type Contributor = { symbol: string; name: string; profit: number };
```

## 5. 데이터 모델 (D1 승인 시)

```prisma
model PublicSimulationResult {
  id                String    @id @default(cuid())   // = publicId
  strategyId        String    @unique
  snapshotHash      String
  dataAsOf          String?
  engineVersion     String?
  status            String    @default("pending")
  reason            String?
  result            String?   // §4.3 공개 DTO(상세 곡선 포함) JSON — 엔진 원본 결과 아님
  computedAt        DateTime?
  refreshLeaseUntil DateTime?
  lastAttemptAt     DateTime?
  lastError         String?
  createdAt         DateTime  @default(now())
  updatedAt         DateTime  @updatedAt
  Strategy          Strategy  @relation(fields: [strategyId], references: [id], onDelete: Cascade)
}
```

- `Strategy`에 역관계 필드 한 줄 추가 외 기존 모델·컬럼 변경 없음. 마이그레이션 `prisma/migrations/<timestamp>_public_strategy_simulation/` 하나.
- 행 생성: 목록/상세 조회에서 공개 전략에 행이 없으면 `pending` 행을 만든다(upsert, `publicId` 발급).

## 6. 작업 목록

공통 규칙: 작업마다 정확히 하나의 boundary. 3~5개 파일, 가능하면 200줄 미만. 앞 작업 검증 통과 후 다음 작업.
공통 Do not(모든 작업에 적용): 비공개 정보 노출, 원본 전략·결과 변경, 가상계좌 성과 사용, 엔진·지표·provider 재구현,
인증·소유권 완화, 누락 설정 임의 보완, 추천·자동 개선·최적 탐색, 사용자 원문 정규식 해석, boundary 밖 파일 수정.
Run 공통: Python 변경 → `uv run pytest backend/tests`(CLAUDE.md의 서버 필요 제외 목록 적용), 프론트/Next API 변경 →
`npm run test:frontend`, 해당 시 `npm run lint`·`npm run build`(dev 서버와 충돌하지 않게 격리 폴더). 미국 전용 검사·예시 게이트·실모델 호출 제외.

### Z-1 기간·결과 축약 순수 모듈 (Boundary Z) ✅ 완료
- Files: `backend/public_simulation/__init__.py`, `backend/public_simulation/window.py`, `backend/public_simulation/summary.py`,
  `backend/tests/test_public_simulation_window.py`, `backend/tests/test_public_simulation_summary.py`
- Requirements: §3.2 창 계산(주입 가능한 `now`/`dataAsOf`), §3.3 실행 가능 판정(D4·D6), §3.4 지표·상태·일관성 검사,
  §3.5 종목 기여(중복 없음·일관성), §3.6 곡선·120점 축약. 엔진 결과 dict를 입력으로 받는 순수 함수.
- Tests: 오늘·휴장일(주말)·장중(dataAsOf=전일)·윤년 3건·데이터 지연(stale)·3년 미만(limited)·거래 없음·일관성 실패·종목 1~2개·상하위 중복 없음.
- Deliver: 순수 모듈과 테스트, `trades`·`perAssetStats.profit` 정의 확인 결과(D7) 기록.

### Z-2 수정 가능 파라미터 설명자·검증 (Boundary Z) ✅ 완료
- Files: `backend/public_simulation/params.py`, `backend/tests/test_public_simulation_params.py`
- Requirements: §3.7 설명자(REGISTRY `engine_binding` 역조회, 존재 키만, default 미사용), 덮어쓰기 검증, 깊은 복사본 적용(원본 불변 테스트).
- Tests: RSI 기간·기준값, 이동평균 기간, 범위 메타 없는 키 잠금, 범위 밖·비정수·NaN·없는 path·중복 path 거절, 원본 dict 불변.

### Z-3 FastAPI 공개 엔드포인트 (Boundary Z, D2 승인 후) ✅ 완료
- Files: `backend/api/public_simulation_routes.py`, `backend/main.py`(`include_router` 두 줄만), `backend/tests/test_public_simulation_routes.py`
- Requirements: §4.1. `BacktestRequest` 검증 → 창 덮어쓰기 → 세마포어 → `watchdog_run_with_timeout(lambda: backtest_executor.run(engine, req))` →
  Z-1 축약. 종목명은 기존 종목 마스터 조회 함수 재사용. 오류 메시지 일반화.
- Tests: 엔진 mock으로 상태별 응답, BUSY 429, TIMEOUT 504, 잘못된 파라미터 400, 원본/수정본 창·비용·dataAsOf 동일,
  **기존 `/backtest` 결과와 요약 지표 일치**(같은 mock 결과 기준).

### Z-4 원본 결과 저장 모델 (Boundary Z, **D1 승인 후**) ✅ 완료
- Files: `prisma/schema.prisma`(모델 1개 + `Strategy` 역관계 한 줄), `prisma/migrations/<ts>_public_strategy_simulation/migration.sql`
- Run: `npm run db:generate`, `npm run test:frontend`. 운영 DB 적용은 사용자 지시가 있을 때만.

### Z-5 Next 서버 서비스 (Boundary Z) ✅ 완료
- Files: `lib/server/publicSimulation/access.ts`(공개 조건·허용 목록·publicId 조회·스냅샷 추출/해시), `lib/server/publicSimulation/originals.ts`(baseline 캐시·지연 갱신·리스 CAS·저장 직전 재확인), `lib/server/publicSimulation/modified.ts`(LRU·in-flight 합치기·요청 제한), `lib/server/publicSimulation/publicSimulation.test.ts`
- Tests: 비공개·삭제·`isSaved=false` 차단, 실행 도중 비공개 전환 시 저장·응답 폐기, 스냅샷 변경 시 refreshing, 캐시 키 구분, 요청 제한 429, 중복 요청 합치기.

### Z-6 Next 공개 API 라우트 (Boundary Z) ✅ 완료
- Files: `app/api/strategy-simulation/route.ts`, `app/api/strategy-simulation/[publicId]/route.ts`, `app/api/strategy-simulation/[publicId]/run/route.ts`, `app/api/strategy-simulation/route.test.ts`
- Tests: 검색·페이지·이름순, 공개 필드 허용 목록(소유자·symbols·Strategy.id 부재), 404, `no-store`, 오류 코드 매핑, 목록 조회가 엔진 실행을 부르지 않음.

### Z-7 목록 화면 (Boundary Z) ✅ 완료
- Files: `app/strategy-simulation/page.tsx`, `components/strategy-simulation/SimulationCardGrid.tsx`, `components/strategy-simulation/SimulationMiniChart.tsx`, `components/strategy-simulation/SimulationCardGrid.test.tsx`, `lib/i18n/en.ts`(신규 문구만)
- Tests: 반응형 클래스, 상태별 카드(결과 없음 시 그래프 없음), Enter/Space 열기, 검색·페이지.

### Z-8 상세 모달·차트·요약 (Boundary Z) ✅ 완료
- Files: `components/strategy-simulation/SimulationDetailModal.tsx`, `components/strategy-simulation/SimulationReturnChart.tsx`, `components/strategy-simulation/SimulationSummary.tsx`, `components/strategy-simulation/SimulationDetailModal.test.tsx`, `lib/i18n/en.ts`
- Tests: 카드↔모달 원본 수익률·기간·기준일 일치, 차트 1개(원본만 1선/수정 시 2선), 종목 상하위 빈 상태, Esc·닫기·포커스 이동·복귀, 딥링크 `?id=`.

### Z-9 지표 수정 폼·재계산 훅 (Boundary Z) ✅ 완료
- Files: `components/strategy-simulation/SimulationParamForm.tsx`, `components/strategy-simulation/useModifiedSimulation.ts`, `components/strategy-simulation/useModifiedSimulation.test.tsx`, `lib/i18n/en.ts`
- Tests(가짜 타이머): 600ms 디바운스, 빠른 연속 수정 시 마지막 입력 결과만 반영, 늦은 응답 폐기, 모달 닫기·재열기·전략 전환 시 원본 시작·응답 미반영, 원본으로 초기화, %p 차이 표기, 잘못된 입력 미요청, 카드 성과 불변.

### Q-1 상단 메뉴 연결 (Boundary Q, **D5 결정 후**) ✅ 완료
- Files: `components/layout/TopNavigation.tsx`(항목 1개), `components/__tests__/TopNavigationQuickSearch.test.tsx`(메뉴 사례 추가만).
  `lib/i18n/en.ts`는 Boundary Q 밖이므로 메뉴 라벨 번역은 Z-7에서 미리 넣는다.
- Tests: 메뉴 노출·순서·활성 표시.

### Z-10 화면 보완 (Boundary Z) ✅ 완료
- 요구사항 대조에서 드러난 화면 격차를 메운 프론트 전용 작업: 계산 불가 지표 '—'+사유, 지표 툴팁, 총 손익 기준 문구, 요청·실제 기간과 계산 완료 시각 구분 표시,
  종목코드 병기·'손익 기여 상위/하위 종목' 제목, 수정 결과의 전체 지표 비교·종목별 손익 반영과 '사용자 수정 시뮬레이션' 표기, 구성 순서 정렬,
  `useDialogBehavior` 공용 훅으로 포커스 트랩·복귀, 모바일 전체 화면, 카드 포커스 복귀(`data-card-id`).

### G-2 구현 반영 문서 갱신 (Boundary G) ✅ 완료
- Files: 이 문서, `docs/PROJECT_PLAN.md`, `docs/software_architecture.md`, `docs/SRS.md`, 필요 시 `docs/architecture/boundaries.md`
- Requirements: 실제 구현·검증 결과·남은 제약으로 갱신(상태 표기 변경).

## 7. 필수 검증 시나리오 → 작업

| 시나리오 | 작업 |
|---|---|
| 비공개·삭제 전략의 목록·상세·실행·캐시 접근 차단 | Z-5, Z-6 |
| 실행 도중 공개 철회 시 결과 노출 차단 | Z-5 |
| 오늘·휴장일·장중·윤년·데이터 지연·3년 미만 | Z-1 |
| 기존 백테스트와 요약 지표 일치 | Z-3 |
| 방문자 수정 후 원본 설정·저장 데이터 보존 | Z-2, Z-5 |
| 잘못된 파라미터 서버 측 검증 | Z-2, Z-3 |
| 빠른 연속 수정 시 마지막 입력 결과만 반영 | Z-9 |
| 원본·수정본 계산 조건·데이터 버전 일치 | Z-3, Z-5 |
| 거래 없음·계산 불가·실행 실패 구분 | Z-1, Z-8 |
| 손익 기여 집계·중복 없는 표시 | Z-1, Z-8 |
| 모바일·키보드 접근, 차트 하나 | Z-7, Z-8 |
| 카드↔모달 수치 일치, 올바른 전략 모달, 카드 불변, 비동기 응답 미혼입 | Z-8, Z-9 |

## 8. 남은 제약

- 한국 휴장일 달력이 없어 데이터 지연 판정은 평일 기준 근사다(D3). "오늘 기준" 문구를 쓰지 않는 것으로 오표시를 막는다.
- 스냅샷의 `symbols`는 저장 시점에 풀린 목록이다. 기존 재실행(`executedRequest`)과 같은 의미이며 이 기능이 바꾸지 않는다.
- 엔진 `trades`·`winRate`는 미청산 포지션을 포함한다(D7). 요구사항의 "완료 거래 수"는 제공하지 않는다.
- 공개 실행이 박스 칸을 넘치면 Modal 비용이 생길 수 있다(D2). 동시 1건·요청 제한으로 완화했을 뿐 차단하지 않는다.
- 운영 DB 공개 전략 4건 중 2건은 메타만 저장되어 있어 '시뮬레이션 불가'로 표시된다.
- 로컬 개발 환경의 `DATABASE_URL`이 운영 Supabase를 가리킨다(2026-10-27 확인). 테스트는 mock Prisma로 하고 운영 DB에는 쓰지 않았다. 마이그레이션만 사용자 승인으로 운영에 적용했다.
- **D5 후속 일부 미실행**: 토글 안내 문구는 바꿨지만(툴팁이라 모바일 터치에서는 잘 보이지 않는다), 이미 공개 중인 전략의 소유자에게 알리는 일은 하지 않았다(외부 발송이라 별도 승인 필요).
- **미국 지역**: `/us`에서는 상단·모바일 메뉴의 '전략 시뮬레이션'을 숨기고(`TopNavigation.tsx`의 `krOnly`), `/us/strategy-simulation` 직접 주소는 404로 처리한다(`page.tsx`의 `getRequestRegion()`). 공개 API(`/api/strategy-simulation/**`)는 지역과 무관하게 열려 있다.
- `POST /internal/public-simulation/describe`는 만들었지만 Next가 쓰지 않는다(상세는 저장된 원본 결과의 `editableParams`를 쓴다).
- 엔진이 적용 비용으로 배당세율을 돌려주지 않아 화면에 배당세는 없다(수수료·슬리피지·증권거래세·체결 시점만 표시).
- **미검증**: 실제 브라우저·모바일 기기에서의 화면·키보드·포커스 확인(컴포넌트 테스트만 — 로컬 `DATABASE_URL`이 운영 DB라 목록 조회가 운영 `PublicSimulationResult`에 행을 쓰게 되어 실행하지 않았다), `npm run build`(dev 서버가 `.next`를 쓰고 있어 실행하지 않음), 운영 데이터에서의 원본 결과 최초 채우기 소요 시간.
- 운영 반영 시 FastAPI(`/internal/public-simulation/*`)와 Next를 함께 배포해야 한다. 미국 parquet 컬럼 통일(`scripts/backfill_us_stocks.py` 변경 반영)은 프로덕션에서 실행해야 한다(로컬 parquet은 올리지 않는다).

## 9. 구현 결과 (2026-10-27)

### 9.1 변경 파일과 검증

| 작업 | 파일 | 검증 |
|---|---|---|
| Z-1 | `backend/public_simulation/{__init__,window,summary}.py` | 단위 테스트 11+23. 실제 엔진 1회 실행으로 총 손익=종목 손익 합(959,242원)·수익률/평가자산 일치 확인 |
| Z-2 | `backend/public_simulation/params.py` | 단위 테스트 21. 실제 엔진: 원본 10.776%·거래 31, RSI 기준값 25로 수정 시 -5.887%·거래 6, 창·자본·비용·버전 동일 |
| Z-3 | `backend/api/public_simulation_routes.py`, `backend/main.py`(include_router) | 라우트 테스트 21. 실제 `main.app`에서 내부 토큰 통과 200, 토큰 없음 404 확인 |
| Z-4 | `prisma/schema.prisma`, `prisma/migrations/20261027000000_public_strategy_simulation/` | 사용자 승인으로 `prisma migrate deploy` 운영 적용("Database schema is up to date") |
| Z-5 | `lib/server/publicSimulation/{access,originals,modified}.ts` | 테스트 35 (공개 조건 재확인, 실행 중 철회, 해시·기준일 불일치, 리스 CAS, 캐시·in-flight, 요청 제한, 오류 매핑) |
| Z-6 | `app/api/strategy-simulation/{route,[publicId]/route,[publicId]/run/route,response}.ts` | 테스트 27 (허용 필드, no-store, 404, 입력 검증, 오류 코드 매핑, 목록이 엔진 미실행) |
| Z-7 | `app/strategy-simulation/page.tsx`, `components/strategy-simulation/{SimulationCardGrid,SimulationMiniChart}.tsx` | 테스트 5 |
| Z-8 | `SimulationDetailModal`, `SimulationReturnChart`, `SimulationMetrics`, `SimulationBrowser`, `format.ts` | 테스트 8 |
| Z-9 | `useModifiedSimulation.ts`, `SimulationParamForm`, `SimulationComparison` | 테스트 8(가짜 타이머: 600ms 디바운스, 마지막 입력만 반영·늦은 응답 폐기[보호 코드 제거 시 실패 확인], 초기화, 재열기, 오류 구분) |
| Z-10 | 위 화면 파일 보완 | 위 화면 테스트에 포함 |
| (D5 후속) | `components/strategy/MyStrategiesView.tsx`(토글 안내 문구), `app/strategy-simulation/page.tsx`(`/us` 404), `SimulationBrowser.tsx`(딥링크) | 페이지 테스트 2, 딥링크 테스트 3 |
| Q-1 | `components/layout/TopNavigation.tsx`, `components/__tests__/TopNavigationQuickSearch.test.tsx` | 메뉴 위치·링크 테스트 1, `/us`에서 숨김 테스트 1(숨김 설정을 빼면 실패 확인) |
| (예외) | `scripts/backfill_us_stocks.py`, `backend/tests/test_backfill_us_stocks.py` | 사용자 요청으로 `test_columns_match_korean_schema` 실패(미국 COLUMNS가 한국 스키마보다 5개 부족)를 맞춤. Boundary Z 밖 파일이며 미국 parquet 자체는 수정하지 않았다 |

최종 전체 실행: 백엔드 `pytest tests/`(서버·AI 모델 필요 4개 파일 제외) **5,680 passed, 5 skipped**, 프론트 `npm run test:frontend` **366 파일 passed(1 skipped), 2,731 tests passed(2 skipped)**.
`tsc --noEmit`은 이 기능 파일에서 오류 0(저장소 기존 3건은 무관), `eslint app/strategy-simulation components/strategy-simulation lib/server/publicSimulation` 오류 0.

### 9.2 명세와 달라진 점

1. 설명자는 숫자 파라미터만 나열한다(문자열 키는 파라미터가 아님). `NOT_A_PARAMETER` 사유는 쓰지 않는다.
2. 원본 갱신 실패 재시도는 고정 15분(`BUSY` 60초), 지수 지연 없음. 날짜 변경(Seoul)과 `requestedStart` 변화도 갱신 사유이며, 원본이 낡은 동안 수정 실행은 409 `REFRESHING`.
3. 수정 재계산은 대기열을 두지 않는다. 새 입력이 오면 이전 요청을 취소하고 마지막 입력만 보낸다(요청 순번이 현재와 같은 응답만 반영).
4. 계산 중에는 수정 결과를 흐리게 하는 대신 숨기고 "계산하고 있습니다"만 보인다(이전 결과가 현재 입력 결과처럼 보이지 않게).
5. 차트 범례 없음(툴팁이 원본/수정을 구분). 카드 그리드는 `sm` 2열·`lg` 3열. 모달은 `aria-label`을 쓰고 `aria-live` 대신 오류에 `role=alert`.
6. 카드 부제 "기간 내 과거 손익 집계" 없음. 종목 영역이 비면 "해당 종목이 없습니다", 거래가 없으면 요약 영역에 "이 기간에는 거래가 없었습니다".
7. 파일 구성: `SimulationSummary.tsx` 대신 `SimulationMetrics.tsx`(요약·툴팁·지표 정의 한 곳), 비교표 `SimulationComparison.tsx`, 목록+모달 `SimulationBrowser.tsx`, 공용 표기 `format.ts`. 훅 테스트는 `SimulationParamEdit.test.tsx`.
8. 모달의 Esc·포커스 트랩·포커스 복귀·스크롤 잠금은 공용 `useDialogBehavior`를 쓴다. Safari가 클릭으로 버튼에 포커스를 주지 않아 닫을 때 카드 `data-card-id`로 한 번 더 포커스를 돌려준다.

### 9.3 프롬프트 요구사항 대조

| 요구 | 상태 |
|---|---|
| 1 메뉴·공개 범위·서버 재확인·허용 목록 응답·검색·페이지·이름순 | ✅ (메뉴는 한국 지역에만 노출 — §8) |
| 2 Seoul 오늘·3년 창·윤년·최신 확정 거래일·요청/실제/기준일/계산 시각 구분·3년 미만 표시 | ✅ 휴장일은 평일 근사(D3) |
| 3 기존 실행 경로 재사용·비용 표시·적용 초기자금·불가 사유·지연 갱신·갱신 중 이전 결과 표시 | ✅ 배당세 없음(엔진 미제공) |
| 4 필수 지표·CAGR/샤프/승률/거래 수·총 손익 기준 명시·'—'와 사유 | ✅ "완료 거래 수" 대신 "거래 수(미청산 포함)"(D7) |
| 5 종목 손익 기여 상·하위 3·종목명·코드·중복 없음·빈 상태 | ✅ |
| 6 누적 수익률 차트 하나·수정 시 두 선·툴팁 | ✅ 범례 없음 |
| 7 파라미터 폼(메타 기반)·600ms·마지막 입력만·%p·초기화·원본 불변·실제 재계산 | ✅ 숫자 파라미터만 |
| 8 캐시 분리·키·동시 실행·중복 합치기·시간 제한·요청 제한·실패 구분 | ✅ |
| 9 UI 순서·모바일·키보드·툴팁·공통 안내 한 번·금지 문구 없음 | ✅ 실기기 미확인 |
| 카드·모달 요구(카드 필드·미니 그래프·모달 구성·포커스·Esc·카드 복귀) | ✅ 실브라우저 미확인 |
| 메뉴 연결(Q) | ✅ (`/us`에서는 숨김) |
| 문서 갱신(G) | ✅ 이 문서 외 PROJECT_PLAN·software_architecture·SRS·boundaries.md |

## 목록 노출 규칙 (2026-10-27)

시뮬레이션할 수 없는 전략은 목록(카드 그리드)에서 뺀다 — 실행 가능한 스냅샷이 없는 전략, 현재 스냅샷으로 이미 `unavailable`(미국 시장·적립식·비용 정보 없음 등)로 판정된 전략. 실행 가능 여부는 저장 설정을 읽어야 알 수 있어 `listPublicStrategies`가 200건 배치로 훑어 거른 뒤 쪽을 자른다. 아직 계산 전(pending)인 전략은 보이며, 계산 후 `unavailable`이면 다음 조회부터 사라진다. 직접 링크(상세)는 사유와 함께 열린다.
