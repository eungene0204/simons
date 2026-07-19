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
    detect_symbol_ambiguity,
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


# ─── 되묻기(복수 종목) ────────────────────────────────────────────────────────

def test_symbol_ambiguity_clarification():
    parsed = ParsedStrategy(description="복수", target_symbols=["005930", "000660"])
    question, suggestions = detect_symbol_ambiguity(parsed)
    assert question is not None and "여러 종목" in question
    assert any("삼성전자" in s for s in suggestions)
    assert any("SK하이닉스" in s for s in suggestions)


def test_no_ambiguity_for_single_target():
    parsed = ParsedStrategy(description="단일", target_symbols=["005930"])
    assert detect_symbol_ambiguity(parsed) == (None, None)


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
