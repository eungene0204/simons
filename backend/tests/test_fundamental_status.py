"""fundamental_status 모듈 유닛 테스트."""

from engine.fundamental_status import (
    DIVIDE_BY_ZERO,
    LOSS_NARROWED,
    LOSS_TRANSITION,
    LOSS_WIDENED,
    MISSING_DATA,
    NEGATIVE_CASHFLOW,
    NEGATIVE_EARNINGS,
    NEGATIVE_EBIT,
    NEGATIVE_EBITDA,
    NEGATIVE_EQUITY,
    TURNAROUND,
    ev_ebit_status,
    ev_ebitda_status,
    growth_and_status,
    pbr_status,
    pcr_status,
    per_status,
    roe_status,
    status_message,
)


# ── per_status ──

def test_per_status_positive_eps_is_valid():
    assert per_status(1000.0) is None

def test_per_status_negative_eps():
    assert per_status(-1000.0) == NEGATIVE_EARNINGS

def test_per_status_zero_eps():
    assert per_status(0.0) == DIVIDE_BY_ZERO

def test_per_status_missing_eps():
    assert per_status(None) == MISSING_DATA


# ── pbr_status / roe_status (자본잠식) ──

def test_pbr_status_positive_equity_is_valid():
    assert pbr_status(50000.0) is None

def test_pbr_status_negative_equity():
    assert pbr_status(-50000.0) == NEGATIVE_EQUITY

def test_pbr_status_zero_equity():
    assert pbr_status(0.0) == DIVIDE_BY_ZERO

def test_roe_status_negative_equity():
    assert roe_status(-1.0) == NEGATIVE_EQUITY

def test_roe_status_positive_equity_is_valid():
    assert roe_status(1.0) is None


# ── pcr_status ──

def test_pcr_status_positive_ocf_is_valid():
    assert pcr_status(1_000_000.0) is None

def test_pcr_status_negative_ocf():
    assert pcr_status(-1_000_000.0) == NEGATIVE_CASHFLOW

def test_pcr_status_missing_ocf():
    assert pcr_status(None) == MISSING_DATA


# ── ev_ebitda_status / ev_ebit_status ──

def test_ev_ebitda_status_positive_is_valid():
    assert ev_ebitda_status(100.0) is None

def test_ev_ebitda_status_negative():
    assert ev_ebitda_status(-100.0) == NEGATIVE_EBITDA

def test_ev_ebit_status_valid_when_both_positive():
    assert ev_ebit_status(ebitda=100.0, ebit=80.0) is None

def test_ev_ebit_status_negative_ebit():
    assert ev_ebit_status(ebitda=100.0, ebit=-10.0) == NEGATIVE_EBIT

def test_ev_ebit_status_missing_when_ebitda_nonpositive():
    """EBITDA<=0이면 EV 자체를 역산할 수 없어 ebit 부호와 무관하게 MISSING_DATA."""
    assert ev_ebit_status(ebitda=-100.0, ebit=80.0) == MISSING_DATA
    assert ev_ebit_status(ebitda=0.0, ebit=80.0) == MISSING_DATA


# ── growth_and_status ──

def test_growth_profit_to_profit_uses_normal_formula():
    growth, status = growth_and_status(prior=100.0, current=120.0)
    assert growth == 20.0
    assert status is None

def test_growth_turnaround_loss_to_profit():
    growth, status = growth_and_status(prior=-50.0, current=30.0)
    assert growth is None
    assert status == TURNAROUND

def test_growth_loss_transition_profit_to_loss():
    growth, status = growth_and_status(prior=50.0, current=-30.0)
    assert growth is None
    assert status == LOSS_TRANSITION

def test_growth_loss_transition_profit_to_breakeven():
    """흑자(prior>0)에서 손익분기(current==0)도 적자전환으로 취급한다."""
    growth, status = growth_and_status(prior=50.0, current=0.0)
    assert growth is None
    assert status == LOSS_TRANSITION

def test_growth_loss_narrowed():
    growth, status = growth_and_status(prior=-100.0, current=-40.0)
    assert growth is None
    assert status == LOSS_NARROWED

def test_growth_loss_widened():
    growth, status = growth_and_status(prior=-40.0, current=-100.0)
    assert growth is None
    assert status == LOSS_WIDENED

def test_growth_loss_unchanged_treated_as_narrowed():
    growth, status = growth_and_status(prior=-50.0, current=-50.0)
    assert growth is None
    assert status == LOSS_NARROWED

def test_growth_divide_by_zero_prior():
    growth, status = growth_and_status(prior=0.0, current=10.0)
    assert growth is None
    assert status == DIVIDE_BY_ZERO

def test_growth_missing_data():
    assert growth_and_status(prior=None, current=10.0) == (None, MISSING_DATA)
    assert growth_and_status(prior=10.0, current=None) == (None, MISSING_DATA)


# ── status_message ──

def test_status_message_returns_korean_text_for_known_code():
    msg = status_message(NEGATIVE_EARNINGS)
    assert msg and "순이익" in msg

def test_status_message_none_for_valid_value():
    assert status_message(None) is None
