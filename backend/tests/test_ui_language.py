"""UI 표시 언어(ko/en) 컨텍스트 — LLM 자유 서술의 언어 지시와 결정론 안내문 선택."""
import threading

import ui_language


def test_default_is_korean_and_directive_is_empty():
    assert ui_language.get_ui_language() == "ko"
    assert ui_language.language_directive() == ""
    assert ui_language.append_directive("질문") == "질문"


def test_bind_english_appends_directive_to_prompt_tail_only():
    with ui_language.bind("en"):
        assert ui_language.get_ui_language() == "en"
        out = ui_language.append_directive("USER PROMPT")
        assert out.startswith("USER PROMPT\n\n")
        assert "English" in out
        # JSON 키·enum·칩은 바꾸지 말라는 계약이 지시문에 들어 있다
        assert "JSON keys" in out and "chip" in out
    # 컨텍스트를 벗어나면 원복
    assert ui_language.get_ui_language() == "ko"


def test_normalize_accepts_bcp47_and_rejects_unknown():
    assert ui_language.normalize("en-US") == "en"
    assert ui_language.normalize("EN") == "en"
    assert ui_language.normalize("en-GB,en;q=0.9,ko;q=0.8") == "en"
    assert ui_language.normalize("ja") == "ko"
    assert ui_language.normalize(None) == "ko"


def test_msg_picks_language_and_formats_placeholders():
    assert ui_language.msg("'{names}' 조건", "'{names}' condition", names="a, b") == "'a, b' 조건"
    with ui_language.bind("en"):
        assert ui_language.msg("'{names}' 조건", "'{names}' condition", names="a, b") == "'a, b' condition"


def test_contextvar_does_not_leak_into_new_thread_unless_rebound():
    """parse-stream이 스레드 안에서 다시 bind 해야 하는 이유의 회귀 — 자동 전파되지 않는다."""
    seen = {}

    def worker():
        seen["lang"] = ui_language.get_ui_language()

    with ui_language.bind("en"):
        th = threading.Thread(target=worker)
        th.start()
        th.join()
    assert seen["lang"] == "ko"
