"""뉴스 전략 테스트 스크립트 회귀 — make_note(해석 카드 짝·해석 절 숫자·열기 링크)와 fetch_yonhap(피드 파싱).

실행: cd backend && uv run --frozen pytest ../.claude/skills/news-strategy-test/scripts/test_make_note.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from make_note import campaign_of, card_pairs, interpretation, open_link  # noqa: E402

# 2026-11-03 01-ess-ma/result.json의 summary 그대로
ESS_SUMMARY = (
    "현재까지 이해한 전략입니다\n\n유니버스\n전력저장장치(ESS)\n종목 41개 펼쳐보기\n업종\n이차전지\n"
    "매수 조건\n20일선-60일선 골든크로스\n매도 조건\n20일선-60일선 데드크로스\n포트폴리오\n지정 종목 41개 균등 투자\n"
    "리밸런싱\n설정 안 함\n백테스트 기간\n5년\n초기 자본\n10,000,000원\n리스크 관리\n손절 안 함 · 익절 안 함"
)


def test_expand_button_does_not_shift_pairs():
    assert card_pairs(ESS_SUMMARY) == [
        ("유니버스", "전력저장장치(ESS)"),
        ("업종", "이차전지"),
        ("매수 조건", "20일선-60일선 골든크로스"),
        ("매도 조건", "20일선-60일선 데드크로스"),
        ("포트폴리오", "지정 종목 41개 균등 투자"),
        ("리밸런싱", "설정 안 함"),
        ("백테스트 기간", "5년"),
        ("초기 자본", "10,000,000원"),
        ("리스크 관리", "손절 안 함 · 익절 안 함"),  # 줄 수가 홀수가 되며 마지막 칸이 통째로 빠지던 것
    ]


def test_card_without_button_and_repeated_condition_label():
    summary = ("현재까지 이해한 전략입니다\n\n유니버스\nKOSPI · KOSDAQ\n매수 조건\nMACD 골든크로스\n매수 조건\n종가가 20일선 위 유지\n"
               "리스크 관리\n손절 안 함 · 익절 안 함")
    assert card_pairs(summary) == [("유니버스", "KOSPI · KOSDAQ"), ("매수 조건", "MACD 골든크로스"),
                                   ("매수 조건", "종가가 20일선 위 유지"), ("리스크 관리", "손절 안 함 · 익절 안 함")]


def test_unknown_label_stops_instead_of_shifting():
    # 앱이 새 칩 라벨을 더하면 그 줄이 앞 칩의 두 번째 값 줄이 된다 — 밀린 글을 쓰지 않고 멈춘다
    summary = "현재까지 이해한 전략입니다\n유니버스\nKOSPI\n새 칸\n어떤 값\n리스크 관리\n손절 안 함"
    with pytest.raises(SystemExit):
        card_pairs(summary)


def test_open_link_carries_full_utm(tmp_path):
    folder = tmp_path / "2026-11-06" / "01-ess-ma"
    assert campaign_of(folder) == "2026-11-06-01-ess-ma"
    assert open_link("ESS 골든크로스", campaign_of(folder), "tweet") == (
        "https://www.nullstock.im/?prompt=ESS+골든크로스"
        "&utm_source=tweet&utm_medium=referral&utm_campaign=2026-11-06-01-ess-ma"
    )


def test_trades_per_year_uses_calendar_years_not_trading_days():
    # 2026-11-07 01-infosec-rsi: 괄호 속 1180은 거래일 수 — 365로 나누면 연 횟수가 약 1.5배로 나왔다
    metrics = {"trades": "120", "win_rate": "50%", "profit_factor": "1.2", "roi": "+10%", "benchmark": "+5%",
               "benchmark_name": "KODEX 200", "mdd": "-10%", "total_profit": "1,000,000원"}
    log = ["기간: 2022-01-03 ~ 2026-11-02 (1180일)", "평균보유일: 12일"]
    line = next(l for l in interpretation(metrics, log) if l.startswith("- 회전"))
    assert "연 평균 약 24.8회" in line  # 120회 / (1764일 / 365.25)


def test_feed_with_bare_ampersand_still_parses():
    from fetch_yonhap import parse_xml
    raw = "<rss><channel><item><title>S&P 500 &amp; 나스닥 &#38; R&D</title></item></channel></rss>".encode()
    assert parse_xml(raw).findtext("channel/item/title") == "S&P 500 & 나스닥 & R&D"
