"""해석 글 생성기(make_post.py)·편집 계획(make_plan.py)이 그래프 칸의 하위 항목을 빠뜨리지 않는지 확인한다.

2026-10-20 사고: `summary_parts`가 칸 제목 바로 다음 한 줄만 읽어, 업종 조선 전략 글에서 `업종: 조선`과
`최대 10종목 보유`가 빠진 채 "투자 대상: KOSDAQ + KOSPI"만 나갔다(조선 종목만 대상이었다는 사실이 글에서 사라짐).
녹화(joseon-1020)의 확정 직전 요약 텍스트를 그대로 쓴다. 네트워크·앱은 쓰지 않는다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "x-backtest-post" / "scripts"

SUMMARY = """전략 진행률
8/8
유니버스
매수 조건
매도 조건
최대 보유
리밸런싱
리밸런싱 방식
해당 없음
리스크 관리
백테스트 기간
초기 자본
30

조선 관련주 전략을 만들어줘

현재까지 이해한 전략입니다
그래프
텍스트로 보기
현재까지 이해한 전략
투자 대상
KOSDAQ + KOSPI
업종: 조선
매수 규칙
RSI(14) <= 30
자금 배분
최대 10종목 보유
종목당 비중 10%
비중 방식: 동일 비중
초기 자본 10,000,000원
백테스트 기간 5년
리밸런싱
리밸런싱 없음
매도 규칙
RSI(14) >= 70

모든 조건을 정했습니다. 현재까지의 전략을 확인하고 확정해 주세요.

전 단계
전략 확인
이 전략으로 확정
대화 종료"""


@pytest.fixture(scope="module")
def mods():
    sys.path.insert(0, str(_SCRIPTS))
    loaded = {}
    for name in ("make_plan", "make_post"):
        spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        loaded[name] = module
    yield loaded
    for name in loaded:
        sys.modules.pop(name, None)
    sys.path.remove(str(_SCRIPTS))


def test_summary_parts_reads_every_item_under_a_group(mods):
    parts = mods["make_plan"].summary_parts(SUMMARY)
    assert parts["universe_items"] == ["KOSDAQ + KOSPI", "업종: 조선"]
    assert parts["allocation_items"] == [
        "최대 10종목 보유", "종목당 비중 10%", "비중 방식: 동일 비중", "초기 자본 10,000,000원", "백테스트 기간 5년",
    ]
    # 기존 칸 값은 그대로
    assert (parts["buy"], parts["sell"], parts["period"], parts["rebalance"]) == ("RSI(14) <= 30", "RSI(14) >= 70", "5년", "리밸런싱 없음")


def test_post_settings_include_sector_and_max_holdings(mods):
    post = mods["make_post"]
    parts = mods["make_plan"].summary_parts(SUMMARY)
    lines = post.settings_lines(parts, ["손절 안 함", "익절 안 함"], [])
    assert "최대 보유 종목: 10종목(종목당 비중 10%, 동일 비중)" in lines
    assert post.allocation_lines([]) == []


def test_video_title_card_text_includes_sector_and_max_holdings(mods):
    meta = mods["make_plan"].with_defaults(
        {}, {"summary": SUMMARY, "prompt": "조선 관련주 전략을 만들어줘", "log": [], "metrics": {"benchmark_name": "KODEX 코스피", "benchmark": "+124.74%"}}
    )
    assert "업종: 조선" in meta["subtitle"] and "최대 10종목 보유" in meta["subtitle"]
    assert "업종: 조선" in meta["end_title"]
