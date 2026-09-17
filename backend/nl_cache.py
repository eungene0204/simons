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
# v9: 입력 전체를 인용한 조건 = 형식 위반(1회 재생성 → 잔존 시 안내 없이 제거) — 문장 전체를
#     "'…'는 이동평균 조건이 아니어서"로 되돌려주던 안내가 담긴 결과 무효화(2026-09-17)
#     + 조건 인용 판정(다른 설정 문구·신고가 오분류)을 어휘 정규식에서 LLM 조건 인용 대조로 이관
NL_PARSER_CACHE_VERSION = "9"
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


def _ui_language() -> str:
    """요청 컨텍스트의 표시 언어(=지역). 컨텍스트 밖이면 기본값."""
    try:
        import ui_language

        return ui_language.get_ui_language()
    except Exception:  # noqa: BLE001 — 캐시 키 계산이 요청을 깨면 안 된다
        return ""


def _interpreter_prompt_version() -> str:
    """해석 프롬프트 버전. 임포트 실패는 빈 문자열(키가 덜 좁아질 뿐 오염은 없다)."""
    try:
        from strategy_conversation.interpreter.prompts import PROMPT_VERSION

        return str(PROMPT_VERSION)
    except Exception:  # noqa: BLE001
        return ""


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
        # 표시 언어 = **지역**이다(/us는 en, KR은 ko — lib/geo/region). 지역이 유니버스
        # 기본값(SP500 vs KOSPI200)·지역 격리 가드·되묻기 언어를 모두 좌우하므로 키에서
        # 빠지면 같은 문장에 대해 **먼저 온 지역의 결과를 다른 지역이 받는다**
        # (2026-08-27 실측: /us 게이트가 KR 문맥으로 채워진 캐시를 그대로 받아 왔다).
        "ui_language": _ui_language(),
        # 해석 프롬프트가 바뀌면 같은 문장의 결과도 바뀐다 — 버전이 키에 없으면 프롬프트를
        # 고쳐도 캐시가 옛 결과를 계속 돌려주고, QA 게이트가 수정 전을 재측정한다(실측:
        # 4.9로 고친 뒤 게이트 100건 중 1건만 새 프롬프트로 파싱됐다).
        "prompt_version": _interpreter_prompt_version(),
        "universe_stamp": universe_cache_stamp(),
        # 상대 기간 표현("백테스트 2년")은 파싱 시점의 오늘 기준 명시 날짜로 변환돼 결과에
        # 저장되므로, 장수 프로세스에서 자정을 넘겨도 스테일 날짜가 반환되지 않게 키를 일 단위로 돌린다.
        "date_stamp": date.today().isoformat(),
        "parser_version": NL_PARSER_CACHE_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
