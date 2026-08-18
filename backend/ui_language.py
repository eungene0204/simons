"""요청의 UI 표시 언어(ko/en) — 사용자에게 보이는 LLM 자유 서술의 언어를 정한다.

프론트가 요청 본문의 `language`(또는 `Accept-Language`)로 보내고, 엔드포인트가 이 컨텍스트에
묶는다. LLM 호출부(인터프리터·코치·리포트)는 `language_directive()`를 **사용자 프롬프트 끝에**
덧붙인다 — 시스템 프롬프트에 넣지 않는 이유는 프리픽스 캐시(Ollama/Modal)를 언어별로 쪼개지
않기 위해서다(병목은 프리필).

번역 대상은 자유 서술뿐이다. JSON 키·enum·지표 정본값·칩 문자열(결속 프로토콜)은 언어와
무관하게 그대로다 — 결정론 문구(슬롯 질문·칩·알림)는 프론트 사전(lib/i18n/en.ts)이 표시
지점에서 옮긴다.

스레드 경계: contextvars는 새 스레드로 전파되지 않으므로 파싱 스레드 안에서 다시 bind 한다
(cancellation.bind와 같은 패턴).
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator, Optional

SUPPORTED = ("ko", "en")
DEFAULT_LANGUAGE = "ko"

_ui_language: contextvars.ContextVar[str] = contextvars.ContextVar("ui_language", default=DEFAULT_LANGUAGE)


def normalize(value: Optional[str]) -> str:
    """'en', 'en-US', 'EN' → 'en'; 모르는 값·None → 'ko'."""
    if not value:
        return DEFAULT_LANGUAGE
    code = str(value).strip().lower().split(",")[0].split(";")[0].split("-")[0]
    return code if code in SUPPORTED else DEFAULT_LANGUAGE


def get_ui_language() -> str:
    return _ui_language.get()


@contextlib.contextmanager
def bind(language: Optional[str]) -> Iterator[str]:
    """현재 컨텍스트(스레드)에 UI 언어를 묶는다."""
    token = _ui_language.set(normalize(language))
    try:
        yield _ui_language.get()
    finally:
        _ui_language.reset(token)


_ENGLISH_DIRECTIVE = (
    "[UI language: English] The user is reading the interface in English. "
    "Write every user-facing sentence in your output — clarification questions, "
    "messages, summaries, explanations, advice — in natural English. "
    "Do NOT translate or change JSON keys, enum values, field names, indicator names, "
    "canonical universe/sector labels, or option/chip strings; those must stay exactly as specified."
)


def language_directive(language: Optional[str] = None) -> str:
    """LLM 사용자 프롬프트 끝에 덧붙일 언어 지시. 한국어(기본)면 빈 문자열."""
    code = normalize(language) if language is not None else get_ui_language()
    return _ENGLISH_DIRECTIVE if code == "en" else ""


def append_directive(prompt: str, language: Optional[str] = None) -> str:
    directive = language_directive(language)
    return f"{prompt}\n\n{directive}" if directive else prompt


def msg(ko: str, en: str, **values: object) -> str:
    """UI 언어에 맞는 문구를 고른 뒤 {name} 자리표시자를 채운다 — 백엔드 결정론 안내문 전용.

    (프론트 사전으로 옮길 수 없는, 값이 섞인 템플릿 문구에만 쓴다. 고정 문구는 프론트
    lib/i18n/en.ts가 표시 지점에서 옮기므로 여기 두 번 적지 않는다.)
    """
    template = en if get_ui_language() == "en" else ko
    return template.format(**values) if values else template
