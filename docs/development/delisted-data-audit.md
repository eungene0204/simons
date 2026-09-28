# 상장폐지 종목 가격 데이터 점검 (2026-09-28)

Task:
로컬 상장폐지 목록과 가격 파일을 대조하고 집계 기준·결과를 기록한다.

Boundary:
Governance / Policy Docs (Boundary G)

Files allowed:
- `docs/development/delisted-data-audit.md`
- `docs/software_architecture.md`

Do not:
- 애플리케이션 코드, 데이터, 수집 스크립트를 수정하지 않는다.
- 티커가 같다는 이유만으로 서로 다른 상장 이력의 가격을 보유했다고 판단하지 않는다.

Requirements:
- 국내 주식, 국내 ETF, 미국 Stock/ETF를 각각 집계한다.
- 파일 부재, 상장 기간 내 가격 부재, 식별 미확정을 구분한다.
- 실제 파일을 읽어 날짜와 유효 종가를 검증한다.

Run:
- 아래 읽기 전용 점검을 `.venv/bin/python`으로 실행한다.
- 코드 변경이 없으므로 프론트엔드·백엔드 단위 테스트는 해당하지 않는다.

Deliver:
- 점검 결과 및 재현 방법 문서, 아키텍처 문서 연결.

## 범위와 판정 기준

- 현재 작업 디렉터리의 로컬 데이터 기준이다. 운영 서버 데이터나 외부 거래소의 최신 전체 명단은 조회하지 않았다.
- 데이터는 일별 가격 이력(OHLCV)이며, 재무 지표의 결측·전 기간 연속성·상장폐지 직전 최종 거래일 수록 여부는 이번 집계의 대상이 아니다.
- 국내 주식: `data/stock-master.json`의 `delistingDate`가 있는 498개. 마스터 생성 시각은 2026-09-16이며 상장폐지 이력 하한은 2015-01-01이다.
- 국내 ETF: `data/etf-delisted.json`의 244개. 목록 생성 시각은 2026-07-19이다.
- 미국: `data/us-delisted.json`의 9,451개(Stock 7,469개·ETF 1,982개). 목록 생성 시각은 2026-08-31이다. Stock 분류에는 워런트·유닛 등의 증권도 포함되어 있어 전부 보통주를 뜻하지 않는다.
- 국내 파일은 `data/ohlcv/{symbol}.parquet`, 미국 파일은 `data/ohlcv-us/{symbol}.parquet`와 대조했다.
- 유효 가격: 날짜가 있고 종가가 유한한 양수인 행. 상장 기간은 상장일(있는 경우)부터 상장폐지일까지 양 끝을 포함한다. 국내 ETF 목록에는 상장일이 없어 상장폐지일 이전 유효 행의 존재를 검사했다.

## 결과

| 구분 | 목록 수 | 파일 없음 | 파일은 있으나 상장 기간 내 가격 없음 | 기간 내 가격 존재 | 가격 보유 여부 미확정 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 국내 주식 | 498 | 0 | 0 | 498 | 0 |
| 국내 ETF | 244 | 0 | 0 | 244 | 0 |
| 미국 Stock | 7,469 | 7,171 | 139 | 159 | 159 |
| 미국 ETF | 1,982 | 1,948 | 21 | 13 | 13 |
| 미국 합계 | 9,451 | 9,119 | 160 | 172 | 172 |

미국의 **상장 기간 내 가격이 없는 항목은 최소 9,279개**(Stock 7,310개·ETF 1,969개)다. 이는 파일이 없는 9,119개와 파일의 가격 기간이 겹치지 않는 160개를 합한 것이다. 표의 미확정 열은 기간 내 가격 존재 열의 부분집합이며 별도로 더하지 않는다.

미국에서 같은 티커의 파일이 있는 332개는 모두 목록의 `reusedByActive`에 들어 있다. 기간이 겹치는 172개도 동일 회사·동일 증권의 가격인지 추가 식별이 필요하다. `reusedByActive`에는 명칭이 거의 같은 항목도 있으므로 332개 전부를 다른 회사라고 단정하지 않는다. 별도 상장폐지 가격 백필이 완료되었다고도 판단할 수 없다.

예: ACCL의 상장폐지 명칭은 Accelrys Inc(2014-05-06 폐지)지만 현행 명칭은 Acco Group Holdings Limited이며 가격 파일은 2025-10-17부터 시작한다. ACB는 상장폐지 명칭 ACap Energy Ltd와 현행 명칭 Aurora Cannabis Inc.가 달라, 기간이 겹쳐도 티커만으로 연결하면 안 된다.

별도 국내 제외 원장 `data/delisted-stocks.json`의 78개도 전부 유효 가격이 있었다. 이 중 상장폐지 마스터와 겹치는 것은 12개이며, 나머지 66개 중 62개는 현행 `korea-stocks.json`에도 있다. 이 원장을 확정 상장폐지 명단으로 합산하지 않았다.

검증 결과: 검사한 기존 파일 1,074개(국내 742개·미국 332개)는 모두 날짜·종가를 읽을 수 있었고 유효 가격이 있었다. 집계 합계와 미국 티커 재사용 분류를 교차검증했으며 모두 통과했다.

## 재현 방법

저장소 루트에서 `.venv/bin/python`으로 다음을 실행한다. 파일을 읽기만 하며 데이터 수집이나 저장은 수행하지 않는다.

```python
import json
from collections import Counter
from pathlib import Path
import polars as pl

root = Path("data")
us = json.loads((root / "us-delisted.json").read_text())
groups = {
    "KR_STOCK": [s for s in json.loads((root / "stock-master.json").read_text())["stocks"] if s.get("delistingDate")],
    "KR_ETF": json.loads((root / "etf-delisted.json").read_text())["etfs"],
    "US": us["entries"],
}
for group, entries in groups.items():
    counts = Counter()
    for entry in entries:
        counts["total"] += 1
        folder = "ohlcv-us" if group == "US" else "ohlcv"
        path = root / folder / (entry["symbol"] + ".parquet")
        if not path.exists():
            counts["missing_file"] += 1
            continue
        frame = pl.read_parquet(path, columns=["date", "close"])
        valid = frame.filter(pl.col("date").is_not_null() & pl.col("close").is_finite() & (pl.col("close") > 0))
        counts["valid_file"] += int(valid.height > 0)
        overlap = valid.filter(pl.col("date").cast(pl.Date) <= pl.lit(entry["delistingDate"]).str.to_date())
        start = entry.get("ipoDate") or entry.get("listingDate")
        if start:
            overlap = overlap.filter(pl.col("date").cast(pl.Date) >= pl.lit(start).str.to_date())
        counts["with_listing_overlap" if overlap.height else "no_listing_overlap"] += 1
        if group == "US":
            counts["reused_present"] += int(entry["symbol"] in us["reusedByActive"])
    print(group, dict(counts))
```
