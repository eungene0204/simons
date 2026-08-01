from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path


_BASE_DIR = Path(__file__).resolve().parent.parent

# 파싱 로직이 바뀌어 기존 캐시 항목이 낡은 결과(예: 음수 손절 오드롭 notice)를 계속
# 반환할 수 있을 때 범프한다. date_stamp는 일 단위라 당일 오염 항목을 못 걸러낸다.
# v6: 섹터/업종 조건 지원 — 이전 버전에서 미지원 안내로 파싱된 결과 무효화
# v7: 섹터 큐에 '중심/위주' 추가 — "반도체 중심으로"가 섹터 없이 파싱된 결과 무효화
# v8: '로봇' 독립 정본 섹터 신설(기계/장비에서 분리) + 다중 섹터 — 로봇이 미지원 안내
#     또는 기계/장비로 파싱된 결과 무효화
NL_PARSER_CACHE_VERSION = "8"
_UNIVERSE_FILES = (
    _BASE_DIR / "data" / "korea-stocks.json",
    _BASE_DIR / "data" / "kospi200-cache.json",
)


def universe_cache_stamp() -> str:
    parts: list[str] = []
    for path in _UNIVERSE_FILES:
        if path.exists():
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
        else:
            parts.append(f"{path.name}:missing")
    return "|".join(parts)


def nl_cache_key(
    prompt: str, backend: str, model: str | None, previous_parsed: dict | None,
    pending_ask: dict | None = None, pending_question: str | None = None,
) -> str:
    payload = {
        "prompt": prompt.strip(),
        "backend": backend,
        "model": model or "",
        "previous_parsed": previous_parsed or {},
        # 같은 프롬프트라도 직전 planner 질문 컨텍스트가 다르면 칩 결정론 귀속 결과가
        # 달라진다(run_chip_answer) — 키에 포함해 컨텍스트 간 캐시 충돌을 막는다.
        "pending_ask": pending_ask or {},
        # 같은 답("3억원")이라도 어떤 질문에 대한 답이냐에 따라 귀속 필드가 달라진다 —
        # pending_ask와 같은 이유로 키에 포함한다.
        "pending_question": pending_question or "",
        "universe_stamp": universe_cache_stamp(),
        # 상대 기간 표현("백테스트 2년")은 파싱 시점의 오늘 기준 명시 날짜로 변환돼 결과에
        # 저장되므로, 장수 프로세스에서 자정을 넘겨도 스테일 날짜가 반환되지 않게 키를 일 단위로 돌린다.
        "date_stamp": date.today().isoformat(),
        "parser_version": NL_PARSER_CACHE_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
