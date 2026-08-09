"""엔진 v12.0부터 손익비는 손실 거래 0건일 때 None(=∞)으로 내려온다.

/backtest 라우트의 디버그 로그가 이 값을 `:.2f`로 서식하면 TypeError가 나고,
라우트의 광역 except가 이를 'Engine error' 500으로 둔갑시켜 — 계산이 전부 끝난
무손실 백테스트가 로그 한 줄 때문에 실패한다. 회귀 방지 테스트.
"""

from main import format_pf_for_log


def test_none_pf_formats_as_inf_instead_of_raising():
    # 버그 재현: f"{None:.2f}"는 TypeError → 응답 500. 헬퍼는 문자열로 우회한다.
    assert format_pf_for_log(None) == "inf"


def test_numeric_pf_keeps_two_decimals():
    assert format_pf_for_log(1.234) == "1.23"
    assert format_pf_for_log(0) == "0.00"
