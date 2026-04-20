# Retro

---

## 2026-04-20 (세션 2)

## 무엇을 했나

1. 백테스트 기본 기간 5년 → **3년으로 변경** (`BacktestConfig.tsx`)
2. 삼성에피스홀딩스(`0126Z0`) 데이터 없음 원인 파악 — 2025-11-24 KOSPI 재상장 종목으로 pykrx/FDR 미수록
3. Yahoo Finance(`0126Z0.KS`) 경로로 98거래일 OHLCV 수집 → `data/ohlcv/0126Z0.parquet` 생성
4. 백테스트 로그의 TOP/BOT 종목이 0거래 종목을 잘못 포함하던 버그 수정 (`BacktestDashboard.tsx`)

---

## 배운 점

### 1. pykrx도 2025년 신상장 종목을 못 찾는 경우가 있다
- 삼성에피스홀딩스는 pykrx `get_market_ticker_list`에 나오지 않고 OHLCV도 0행 반환
- Yahoo Finance에서 `.KS` 접미사(`0126Z0.KS`)를 붙여야 데이터 조회 가능
- 인적분할/재상장 종목은 pykrx가 못 잡는 케이스가 앞으로도 발생할 수 있음

### 2. 0거래 종목이 TOP1으로 출력되는 구조적 허점
- `perAssetStats`는 유니버스 전체 종목을 포함 — 거래 0건 종목도 포함
- profit=0인 종목들을 내림차순 정렬하면 배열 삽입 순서 그대로 유지 → 첫 번째 종목이 TOP1
- WARN(조건 미충족)과 INFO(TOP1 로그)가 동시에 나와 사용자 혼란 유발

---

## 실수 / 아쉬웠던 점

1. **삼성에피스홀딩스를 처음에 비상장으로 잘못 판단** — pykrx 조회 결과만 보고 "비상장 법인"이라고 했지만 실제로는 2025년 재상장 종목. 사용자가 정정해서 발견할 수 있었음. 종목 코드 형식(`0126Z0`) 자체는 비상장 코드와 같은 패턴이라 더 다양한 소스를 먼저 교차 확인했어야 했음.

2. **TOP/BOT 로그의 0거래 종목 필터 누락** — 이 버그는 `trades > 0` 한 줄이면 막을 수 있었지만, 로그 생성 시점에 해당 검증 로직이 없었음. 로그 생성 코드 작성 시 "표시 대상 조건"을 명시적으로 고려해야 함.

---

## 결정 사항

| 결정 | 이유 |
|------|------|
| 백테스트 기본 기간 3년으로 단축 | 5년은 기본값으로 너무 길어 초기 사용 경험 저하 |
| 재상장/인적분할 종목은 Yahoo Finance(`심볼.KS`)로 수동 수집 | pykrx가 신규 재상장 종목을 커버 못 하는 경우 대비 |
| TOP/BOT 로그에서 `trades === 0` 종목 제외 | 거래 없는 종목이 TOP에 오르면 사용자 혼란, 의미 없는 정보 |

---

## 다음에 할 일

- [ ] 삼성에피스홀딩스가 실제 KOSPI200 구성종목인지 KRX 공식 확인 — 맞다면 `kospi200-cache.json`에 포함되도록 보완
- [ ] pykrx가 수록 못 하는 재상장/인적분할 종목 패턴 파악 후, 데이터 수집 파이프라인에 Yahoo Finance fallback 추가 검토
- [ ] `perAssetStats`에서 0거래 종목을 백엔드에서도 제외할지 검토 (현재는 프론트엔드 필터만)

---

## 2026-04-20

## 무엇을 했나

1. 백테스트 로그에서 `[WARN] 아크릴(0007C0): 데이터 없음` 경고 원인 파악
2. `korea-stocks.json`에는 등록됐지만 parquet 파일이 없는 42개 종목 수집
3. `collect_data.py` / `sync_data.py` / `data_fetcher.py` FDR → pykrx 마이그레이션
4. KOSPI200 백테스트가 200개가 아닌 ~85개만 돌고 있던 버그 수정
5. 4072개 parquet 파일 중 1488개의 `datetime[ns]` → `datetime[us]` 일괄 정규화

---

## 배운 점

### 1. 알파벳 포함 KRX 종목 코드 (`0007C0` 형식)
- KRX는 최근 6자리 숫자+알파벳 혼합 코드로 신규 상장 종목을 발행하고 있음
- **FDR(FinanceDataReader)은 이 형식을 Yahoo Finance로 그대로 조회** → 404 에러
- **pykrx는 KRX 직접 조회**라서 혼합 코드도 정상 처리
- `collect_data.py`가 처음부터 FDR 기반이었기 때문에 이 형식 종목들이 전부 누락돼 왔음

### 2. 종목 등록 ≠ 데이터 수집
- `/sync-stocks` 엔드포인트는 `korea-stocks.json` 메타데이터만 추가
- OHLCV parquet 수집은 별도 `collect_data.py` / `sync_data.py` 실행이 필요
- 신규 상장 종목은 두 번째 단계가 실패하면 조용히 누락됨 — 경고 로그만 남음

### 3. `route.ts` 하드코딩의 위험
- `app/api/universe/data/route.ts`의 `kospi200` 배열이 언제부터인가 85개짜리 스냅샷으로 굳어 있었음
- 프론트엔드 `UniverseResolver`는 이 API만 바라보기 때문에 KOSPI200 백테스트가 실질적으로 85개 종목에만 돌고 있었음
- 캐시 파일(`kospi200-cache.json`)은 항상 200개를 갖고 있었는데 API가 읽지 않았음

### 4. `datetime[ns]` vs `datetime[us]`
- pykrx로 생성한 parquet 파일은 `datetime[ns]`, 기존 파일은 `datetime[us]`
- polars에서 `.cast(pl.Utf8)` 비교 시 ns는 `"2025-11-24 00:00:00.000000000"`, us는 `"2025-11-24 00:00:00.000000"` — 문자열 prefix 비교라 실제 필터 결과는 같지만
- 엔진 내부에서 두 dtype이 섞이면 concat/join 시 스키마 불일치 오류 가능성 있음
- 기존 2626개도 확인해보니 절반 가까운 1488개가 `ns`였음 — 일괄 정규화 필요했던 상황

---

## 실수 / 아쉬웠던 점

1. **FDR 실패 원인을 처음에 잘못 추정** — "종목 등록이 안 됐나?" 먼저 봤지만, 실제로는 심볼 형식 자체를 FDR이 지원 안 하는 게 원인. 더 빨리 FDR URL 에러 메시지를 읽었으면 바로 알 수 있었음.

2. **route.ts 85개 하드코딩을 뒤늦게 발견** — 사용자가 "199개" 라고 했을 때 처음엔 백엔드 _load_kospi200() 경로만 추적했음. 프론트엔드가 symbols를 직접 결정한다는 구조를 먼저 파악했어야 했음.

3. **datetime dtype 불일치가 이미 4072개 파일에 퍼져 있었음** — 이번에 발견해서 일괄 수정했지만, pykrx 도입 시점에 dtype을 명시해야 했음. 앞으로 parquet 저장할 때 항상 `cast(pl.Datetime('us'))` 명시할 것.

---

## 결정 사항

| 결정 | 이유 |
|------|------|
| OHLCV 수집 전면 pykrx 전환 | FDR은 알파벳 포함 KRX 코드 미지원, pykrx는 KRX 공식 직접 조회 |
| `route.ts` kospi200를 캐시 파일 동적 로드로 변경 | 하드코딩은 구성종목 변경 시 조용히 틀려지는 구조적 결함 |
| parquet 저장 시 datetime dtype `us` 강제 | 엔진 내부 concat/join 안전성, 기존 파일과 스키마 일관성 |
| `sync_data.py` fallback도 FDR StockListing → pykrx | KRX KIND 실패 시 fallback이 다시 FDR이면 혼합 코드 종목 누락 반복 |

---

## 다음에 할 일

- [ ] `sync_data.py`의 증분 업데이트가 실제로 pykrx로 잘 돌아가는지 내일 자정 스케줄러 로그 확인
- [ ] `kospi200-cache.json`이 만료(7일 TTL)되면 Naver 스크래핑이 재실행됨 — 재조회 후 200개가 유지되는지 검증 필요
- [ ] `_KOSPI200_SUPPLEMENTAL_SYMBOLS = {"0126Z0"}` — 삼성에피스홀딩스가 실제 KOSPI200 구성종목인지 KRX 공식 확인 (Naver에서 누락될 경우를 대비해 추가된 것인데, 검증 필요)
- [ ] `data_fetcher.py`의 `fetch_and_enrich`에서 pykrx 호출 후 parquet 저장 시 `datetime[us]` 명시적 cast 추가
- [ ] `collect_data.py`의 새 pykrx 기반 로직 백엔드 테스트 추가 (기존 FDR 테스트는 없었음)
