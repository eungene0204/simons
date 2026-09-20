"""잔차 반전 시그널(ranking.residual_reversal) 사전계산 캐시 구축 → data/factor_cache/.

만드는 것
---------
- ``returns.parquet``·``sector_returns.parquet`` — 전 종목 지표 전용 수익률과 섹터 합·개수
  (모든 회귀 룩백·누적 기간 조합의 공통 재료).
- ``score_60_5.parquet`` — 기본 조합(회귀 60일·누적 5일) 종목별 원점수.
- ``meta.json`` — 데이터 지문. 백테스트는 지문이 현재 데이터와 일치할 때만 캐시를 쓴다
  (다르면 같은 계산을 그 자리에서 한다 — 캐시는 답을 바꾸지 않는다, engine/residual_factor.py).

실행
----
    python backend/scripts/build_residual_factor_cache.py

가격(data/ohlcv)·지수(data/index)가 바뀐 **뒤에** 돌려야 한다 — 야간 갱신은
scripts/sync_data.py가 지수 갱신 다음 단계로 부른다. 전 종목 기준 약 30초.

이 스크립트는 사용자 원문을 읽지 않는다(데이터 파이프라인).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))


def main() -> int:
    from engine import residual_factor

    data_dir = str(_PROJECT_ROOT / "data" / "ohlcv")
    started = time.perf_counter()
    count = residual_factor.build_default_score_cache(data_dir)
    print(f"잔차 반전 시그널 캐시 구축 완료: {count}종목, "
          f"{time.perf_counter() - started:.1f}초 → {residual_factor.cache_dir_for(data_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
