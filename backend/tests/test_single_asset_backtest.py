"""단일/지정 종목 백테스트 (FR-STR-068).

특정 종목("삼성전자에 골든크로스 전략")을 지정하면 유니버스(종목 선정) 대신 그 종목만
백테스트한다. 종목명→코드 해석은 LLM이 아니라 결정적 추출이 정본이며, 문맥 가드
(업종·예시·제외 표현)가 유니버스 전략의 단일 종목 오폭을 막는다.
"""
import pytest

from engine.nl_parser import (
    ParsedStrategy,
    TechnicalSignal,
    _apply_prompt_overrides,
    _extract_target_symbols,
    _modify_rule_based,
    _parse_rule_based_strategy,
    _target_change_from_utterance,
    apply_single_asset_adjustments,
)
from engine.strategy_converter import (
    compute_strategy_id,
    to_backtest_request,
    to_canonical_strategy_dsl,
)
from stock_analysis.symbol_resolver import find_in_text


# ─── 결정적 종목 추출 ─────────────────────────────────────────────────────────

def test_extract_target_by_name():
    refs = _extract_target_symbols("삼성전자에 골든크로스 전략을 적용해줘")
    assert refs is not None
    assert [r.symbol for r in refs] == ["005930"]


def test_extract_target_by_alias():
    refs = _extract_target_symbols("하이닉스에 RSI 과매도 전략을 백테스트해줘")
    assert refs is not None
    assert [r.symbol for r in refs] == ["000660"]


def test_extract_target_by_code_with_korean_particle():
    """6자리 코드 + 조사('005930에')도 인식한다 — \\b는 유니코드 경계라 한글 앞에서 실패."""
    refs = _extract_target_symbols("005930에 MACD 전략을 적용해줘")
    assert refs is not None
    assert [r.symbol for r in refs] == ["005930"]


def test_particle_boundary_recognizes_eh_and_ro():
    """'삼성전자에'/'하이닉스로' 같은 조사 결합 표기가 경계로 인정돼야 한다."""
    assert [r.symbol for r in find_in_text("삼성전자에 적용")] == ["005930"]
    assert [r.symbol for r in find_in_text("하이닉스로 바꿔줘")] == ["000660"]
    assert [r.symbol for r in find_in_text("삼성전자만으로 백테스트해줘")] == ["005930"]


def test_context_guard_blocks_exemplar_and_sector_phrases():
    """예시("같은")·업종 서술("속한 ... 업종")·제외("빼고") 문맥은 지정으로 보지 않는다.

    종목질문 리다이렉트·전략 빌더가 합성하는 업종 전략 문구가 단일 종목으로 오폭되면
    유니버스 전략이 조용히 바뀌는 사고가 된다.
    """
    assert _extract_target_symbols("삼성전자 같은 대형주에 투자하는 전략") is None
    assert _extract_target_symbols("삼성전자가 속한 반도체 업종 종목만 대상으로 하는 전략") is None
    assert _extract_target_symbols("삼성전자 빼고 코스피200 전략") is None


def test_overseas_alias_is_not_a_target():
    # 해외 종목은 백테스트 데이터가 없다 — 지정 종목으로 승격하지 않는다.
    assert _extract_target_symbols("엔비디아에 골든크로스 전략을 적용해줘") is None


def test_common_noun_name_needs_stock_intent():
    """일반명사와 겹치는 회사명(대상=Daesang & '진입 대상'의 target)은 종목 지정 의도가
    문맥에 없으면 종목으로 인정하지 않는다 — 유니버스 전략이 조용히 단일 종목으로 바뀌던 사고.
    """
    # '진입 대상으로 설정' — '대상'은 일반명사(target)다. 종목으로 오인식하면 안 된다.
    assert _extract_target_symbols(
        "KOSDAQ에서 52주 신고가를 만들고 거래량이 늘어난 종목을 진입 대상으로 설정해줘"
    ) is None
    assert _extract_target_symbols("투자 대상으로 코스피 대형주를 설정") is None
    # 종목 지정 의도가 드러나면(매매 동사·코드 병기) 정상 인식한다.
    assert [r.symbol for r in _extract_target_symbols("대상 매수해줘")] == ["001680"]
    assert [r.symbol for r in _extract_target_symbols("대상(001680)으로 백테스트")] == ["001680"]


# ─── 룰 fast-path ────────────────────────────────────────────────────────────

def test_rule_parse_single_asset_entry_only_stays_on_fast_path():
    """지정 종목 + 기술 진입만 있는 프롬프트는 LLM에 위임하지 않는다(청산은 추천 보정)."""
    parsed = _parse_rule_based_strategy("삼성전자에 골든크로스 전략을 적용해줘")
    assert parsed is not None
    assert parsed.target_symbols == ["005930"]
    assert parsed.entry_signals and parsed.entry_signals[0].indicator == "ma_crossover"


def test_rule_parse_universe_entry_only_still_falls_back():
    """종목 지정이 없는 기술 진입 단독 프롬프트는 기존대로 LLM에 위임한다(회귀 가드)."""
    assert _parse_rule_based_strategy("골든크로스 전략을 적용해줘") is None


# ─── 단일 종목 보정(청산 추천) ────────────────────────────────────────────────

def test_adjustments_add_opposite_exit_for_crossover():
    parsed = _parse_rule_based_strategy("삼성전자에 골든크로스 전략을 적용해줘")
    adjusted, notices = apply_single_asset_adjustments(parsed)
    assert [(s.indicator, s.signal_type) for s in adjusted.exit_signals] == [("ma_crossover", "sell")]
    # 추천 적용 사실을 안내한다(조용한 임의 실행 금지).
    assert notices and "청산" in notices[0]


def test_adjustments_notice_only_for_non_crossover_entry():
    parsed = ParsedStrategy(
        description="카카오 RSI 30 이하 매수",
        target_symbols=["035720"],
        entry_signals=[TechnicalSignal(indicator="rsi", signal_type="buy", period=14, operator="<=", value=30)],
    )
    adjusted, notices = apply_single_asset_adjustments(parsed)
    assert adjusted.exit_signals == []
    assert notices and "기간 종료까지 보유" in notices[0]


def test_adjustments_noop_when_exit_exists():
    parsed = _parse_rule_based_strategy("삼성전자에 골든크로스 매수, 데드크로스 매도 전략")
    adjusted, notices = apply_single_asset_adjustments(parsed)
    assert notices == []
    assert adjusted is parsed


def test_adjustments_noop_for_universe_strategy():
    parsed = ParsedStrategy(description="유니버스 전략", entry_signals=[
        TechnicalSignal(indicator="ma_crossover", signal_type="buy", short_period=5, long_period=20)
    ])
    adjusted, notices = apply_single_asset_adjustments(parsed)
    assert adjusted is parsed
    assert notices == []


# ─── BacktestRequest 변환 ────────────────────────────────────────────────────

def test_to_backtest_request_single_asset_semantics():
    parsed = _parse_rule_based_strategy("삼성전자에 골든크로스 전략을 적용해줘")
    adjusted, _ = apply_single_asset_adjustments(parsed)
    req = to_backtest_request(adjusted)
    assert req["symbols"] == ["005930"]
    # universe_id=None → 엔진이 PIT 재해석·섹터 필터 없이 지정 목록을 그대로 쓴다.
    assert req["universe_id"] is None
    assert req["sector"] is None
    assert req["backtest_mode"] == "single_asset"
    assert req["target_stocks"] == [{"symbol": "005930", "name": "삼성전자"}]
    # 단일 종목 집중 투자: 100% 배분, 횡단면 랭킹 없음.
    assert req["risk"]["max_positions"] == 1
    assert req["risk"]["position_size_pct"] == 100.0
    assert req["risk"]["ranking_enabled"] is False


def test_to_backtest_request_universe_unchanged():
    parsed = ParsedStrategy(description="PBR 전략", fundamental_filters=[])
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["backtest_mode"] == "universe"
    assert req["target_stocks"] is None
    assert req["universe_id"] == "kospi200"
    assert req["risk"]["ranking_enabled"] is True


# ─── 캐논 DSL / strategy_id ──────────────────────────────────────────────────

def test_canonical_dsl_excludes_empty_target_and_differs_by_symbol():
    base = ParsedStrategy(description="전략")
    assert "target_symbols" not in to_canonical_strategy_dsl(base)

    a = base.model_copy(update={"target_symbols": ["005930"]})
    b = base.model_copy(update={"target_symbols": ["000660"]})
    assert to_canonical_strategy_dsl(a)["target_symbols"] == ["005930"]
    assert compute_strategy_id(a) != compute_strategy_id(b)
    assert compute_strategy_id(a) != compute_strategy_id(base)


# ─── 되묻기(복수 종목) — 폐지(사용자 결정 2026-07-26) ─────────────────────────
# '한 종목만 고르기' 칩 되묻기(detect_symbol_ambiguity)는 제거됐다 — 여러 종목이 지정되면
# 되묻지 않고 전체를 함께 백테스트하며, 축소·교체는 채팅 수정 요청이 처리한다(아래
# test_modify_fast_path_replaces_target 참조).

def test_symbol_ambiguity_reask_removed():
    import engine.nl_parser as nl
    assert not hasattr(nl, "detect_symbol_ambiguity")


# ─── 수정 경로 ───────────────────────────────────────────────────────────────

def _previous_single_asset() -> dict:
    parsed = _parse_rule_based_strategy("삼성전자에 골든크로스 전략을 적용해줘")
    return parsed.model_dump()


def test_modify_fast_path_replaces_target():
    modified = _modify_rule_based("SK하이닉스로 바꿔줘", _previous_single_asset())
    assert modified is not None
    assert modified.target_symbols == ["000660"]


def test_modify_fast_path_alias_replaces_target():
    modified = _modify_rule_based("하이닉스로 바꿔줘", _previous_single_asset())
    assert modified is not None
    assert modified.target_symbols == ["000660"]


def test_modify_explicit_universe_clears_target():
    modified = _modify_rule_based("코스닥 전체로 바꿔줘", _previous_single_asset())
    assert modified is not None
    assert modified.target_symbols == []
    assert modified.universe == ["KOSDAQ"]


def test_modify_unrelated_field_preserves_target():
    modified = _modify_rule_based("손절 5%로 바꿔줘", _previous_single_asset())
    assert modified is not None
    assert modified.target_symbols == ["005930"]
    assert modified.stop_loss_pct == 5.0


def test_target_change_deterministic_judgement():
    # 종목 언급 → 교체
    changed, value = _target_change_from_utterance("SK하이닉스로 바꿔줘", ["005930"])
    assert (changed, value) == (True, ["000660"])
    # 명시적 시장 발화 → 해제
    changed, value = _target_change_from_utterance("코스피200으로 바꿔줘", ["005930"])
    assert (changed, value) == (True, [])
    # 무관 발화 → 유지
    changed, value = _target_change_from_utterance("손절 5%로 바꿔줘", ["005930"])
    assert (changed, value) == (False, ["005930"])


def test_overrides_sector_switch_clears_target():
    """업종 전환 발화는 문맥 가드로 종목 추출이 침묵하므로 섹터 판정이 지정을 해제한다."""
    parsed = ParsedStrategy(description="이전", target_symbols=["005930"])
    updated = _apply_prompt_overrides(parsed, "반도체 업종으로 바꿔줘", skip_signal_validation=True)
    assert updated.target_symbols == []
    assert updated.sector == "반도체"


# ─── 지정 종목 개별 삭제 (2026-07-26 사고 회귀) ─────────────────────────────────
# "현대약품은 빼조"(빼줘 오타)가 삭제가 아니라 '새 지정'으로 오독돼 테마 유니버스
# 10종목이 현대약품 단일 종목으로 교체되던 사고. 삭제 판정이 지정/교체보다 우선한다.

_THEME_TARGETS = ["005930", "000660", "004310", "006400", "008770"]


def test_target_removal_keeps_remaining_symbols():
    for utterance in ("현대약품은 빼조", "현대약품은 빼줘", "현대약품 제외해줘"):
        changed, value = _target_change_from_utterance(utterance, list(_THEME_TARGETS))
        assert changed is True, utterance
        assert value == ["005930", "000660", "006400", "008770"], utterance


def test_target_removal_not_confused_with_risk_removal():
    """'현대약품 손절 빼줘'의 삭제어는 손절에 붙는다 — 인접 요구가 종목 삭제 오폭을 막는다."""
    _, value = _target_change_from_utterance("현대약품 손절 빼줘", list(_THEME_TARGETS))
    assert "004310" in value  # 현대약품이 목록에서 제거되면 안 된다


def test_extract_target_symbols_ignores_removal_mention():
    """삭제어 인접 종목 언급은 '지정'이 아니다 — 초기 파싱에서도 단일 종목 오폭 금지."""
    assert _extract_target_symbols("현대약품은 빼줘") is None
    assert _extract_target_symbols("현대약품은 빼조") is None


def test_modify_fast_path_removes_single_target_from_list():
    previous = _previous_single_asset()
    previous["target_symbols"] = list(_THEME_TARGETS)
    modified = _modify_rule_based("현대약품은 빼줘", previous)
    assert modified is not None
    assert modified.target_symbols == ["005930", "000660", "006400", "008770"]


def test_modify_fast_path_replacement_still_works_after_removal_branch():
    modified = _modify_rule_based("SK하이닉스로 바꿔줘", _previous_single_asset())
    assert modified is not None
    assert modified.target_symbols == ["000660"]


# ─── 종목명 내 업종 조각 오폭 (2026-07-26 사고 회귀 2) ──────────────────────────
# "제주반도체도 추가해줘"의 종목명 내부 조각('반도체'+'도추가')이 _SECTOR_ADDITIVE_RE에
# 걸려 업종 '반도체' 추가로 오판되고 지정 종목 해제까지 연쇄되던 사고. 섹터 판정은 인식된
# 종목명을 가린다(_mask_stock_name_mentions — 기존 regex의 오해석을 줄이는 방향).
# '추가'(합집합) 의미론은 결정론이 판정하지 않는다 — LLM 인터프리터 경로가 소유한다
# (test_strategy_conversation.py::test_symbol_add_patch_compiles_to_target_union).


def test_sector_judgement_ignores_sector_fragment_inside_stock_name():
    from engine.nl_parser import _sector_change_from_utterance

    for utterance in ("제주반도체도 추가해줘", "한미반도체도 넣어줘", "제주반도체 주식 추가해줘"):
        changed, value = _sector_change_from_utterance(utterance, None)
        assert (changed, value) == (False, None), utterance


def test_sector_judgement_still_works_with_stock_name_nearby():
    """종목명을 가려도 진짜 업종 언급('반도체 업종')은 그대로 판정된다."""
    from engine.nl_parser import _sector_change_from_utterance

    changed, value = _sector_change_from_utterance(
        "제주반도체가 속한 반도체 업종으로 바꿔줘", None
    )
    assert (changed, value) == (True, "반도체")
