"""종목별 Phase1 산출물 캐시 — 최적화·워크포워드의 재계산 제거.

백테스트 1회의 시간 97%는 Phase1(종목별 지표 계산 + 전처리)이 쓴다(2026-08-19 실측:
KOSPI200 5Y 4.8s 중 4.7s). 최적화(옵튜나·그리드)와 워크포워드는 **같은 날짜 범위**에서
파라미터만 바꿔 백테스트를 수십 회 반복하는데, 그중 손절·익절·보유종목수·리밸런싱
같은 리스크 파라미터는 Phase1에 영향이 없고, RSI 임계값 같은 값도 지표 컬럼은 바꾸지
않는다. 이 모듈은 Phase1 산출물을 종목 단위로 캐시해 그 반복을 없앤다.

계약
- 결과는 캐시 유무와 무관하게 **바이트 단위로 동일**해야 한다. 그래서 키는 Phase1의
  캐시 구간이 실제로 읽는 입력만으로, 보수적으로 만든다: 종목·워밍업 시작일·기간
  경계·배당 옵션·**구조 파라미터만 남긴 조건 목록**.
- '구조 파라미터'는 지표 컬럼(이름·값)을 결정하는 파라미터다(기간류). 목록은
  ``STRUCTURAL_PARAM_KEYS`` 화이트리스트이며, ``IndicatorEngine.calculate``·
  ``DataResolver._get_required_columns``가 읽는 파라미터 이름과 일치해야 한다 —
  회귀 테스트(``tests/test_prep_cache.py``)가 소스를 스캔해 대조한다.
  화이트리스트에 없는 파라미터(임계값·방향 등)는 키에서 제외되어 캐시 적중을 만든다.
- 수명은 세션(한 번의 최적화 = 워크포워드 한 창)이다. 요청 간에 살아남지 않으므로
  야간 데이터 갱신 후 낡은 값이 남을 일이 없다.
- 메모리는 바이트 예산(``BACKTEST_PREP_CACHE_MB``, 기본 2048)으로 묶고 LRU로 비운다.
"""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

# IndicatorEngine.calculate / DataResolver._get_required_columns 가 params에서 읽는 키 전부.
# 새 지표가 새 파라미터 이름을 읽기 시작하면 여기에 추가해야 한다(테스트가 강제한다).
STRUCTURAL_PARAM_KEYS = frozenset({
    "period", "rsi_period",
    "shortMA", "short_period", "short", "longMA", "long_period", "long",
    "shortPeriod", "longPeriod",
    "fastPeriod", "slowPeriod", "signalPeriod",
    "stdDev",
    "lookbackPeriod",
})

_DEFAULT_BUDGET_MB = 2048


def _leaf_conditions(group: Optional[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    if not group:
        return
    for c in group.get("conditions", []) or []:
        if isinstance(c, dict) and "conditions" in c:
            yield from _leaf_conditions(c)
        elif isinstance(c, dict):
            yield c


def structural_signature(entry: Optional[Dict[str, Any]], exit_: Optional[Dict[str, Any]]) -> str:
    """조건 목록에서 지표 컬럼을 결정하는 부분만 남긴 정본 문자열(키 재료).

    순서를 보존한다 — IndicatorEngine이 조건 순서대로 처리하므로 보수적으로 둔다.
    """
    items: List[Tuple[str, Dict[str, Any]]] = []
    for cond in list(_leaf_conditions(entry)) + list(_leaf_conditions(exit_)):
        params = cond.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        structural = {k: params[k] for k in sorted(params) if k in STRUCTURAL_PARAM_KEYS}
        items.append((str(cond.get("id", "")), structural))
    return json.dumps(items, ensure_ascii=False, sort_keys=True, default=str)


class SymbolPrepCache:
    """(키 → Phase1 산출물) LRU. 값은 호출자가 소유하는 dict — 넣을 때 그대로 보관하고,
    꺼낼 때 가변 객체(pandas)는 복사해 돌려준다(하류 in-place 수정으로부터 격리)."""

    def __init__(self, budget_bytes: Optional[int] = None):
        if budget_bytes is None:
            budget_bytes = int(float(os.environ.get("BACKTEST_PREP_CACHE_MB", _DEFAULT_BUDGET_MB)) * 1024 * 1024)
        self.budget_bytes = max(0, int(budget_bytes))
        self._items: "OrderedDict[Tuple, Tuple[Dict[str, Any], int]]" = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    # ── 크기 추정 ─────────────────────────────────────────────────
    @staticmethod
    def _estimate_bytes(entry: Dict[str, Any]) -> int:
        total = 256
        pdf = entry.get("pdf")
        if pdf is not None:
            try:
                total += int(pdf.memory_usage(deep=False).sum())
            except Exception:
                pass
        df_pl = entry.get("df_pl")
        if df_pl is not None:
            try:
                total += int(df_pl.estimated_size())
            except Exception:
                pass
        return total

    # ── 공개 API ─────────────────────────────────────────────────
    def get(self, key: Tuple) -> Optional[Dict[str, Any]]:
        with self._lock:
            found = self._items.get(key)
            if found is None:
                self.misses += 1
                return None
            self._items.move_to_end(key)
            self.hits += 1
            entry = found[0]
        out = dict(entry)
        if out.get("pdf") is not None:
            out["pdf"] = out["pdf"].copy()
        if out.get("res_logs") is not None:
            out["res_logs"] = [dict(l) for l in out["res_logs"]]
        return out

    def put(self, key: Tuple, entry: Dict[str, Any]) -> None:
        size = self._estimate_bytes(entry)
        if size > self.budget_bytes:
            return  # 예산보다 큰 항목은 담지 않는다(전체를 비우며 넣는 것보다 낫다)
        stored = dict(entry)
        if stored.get("pdf") is not None:
            stored["pdf"] = stored["pdf"].copy()
        with self._lock:
            old = self._items.pop(key, None)
            if old is not None:
                self._bytes -= old[1]
            self._items[key] = (stored, size)
            self._bytes += size
            while self._bytes > self.budget_bytes and self._items:
                _, (_, evicted) = self._items.popitem(last=False)
                self._bytes -= evicted

    def __len__(self) -> int:
        return len(self._items)

    @property
    def bytes_used(self) -> int:
        return self._bytes

    def stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "entries": len(self._items), "bytes": self._bytes}
