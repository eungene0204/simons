"""US 서비스(/us) 전용 정형 응답 카탈로그 — KR agent(intent/scope.py)와 같은 설계.

분류기 agent의 구조는 KR과 동일하다: 원문 → LLM 의미 해석(intent/interpreter.py) →
구조화 출력 → 도메인 정책(라벨→정형 응답). 이 모듈은 그 마지막 레이어가 요청 언어
(ui_language, /us는 en)에 따라 고르는 **US 전용 응답 문구**만 담는다 — 원문을 읽는
예측자(is_*)는 두지 않는다(해석은 LLM 소관, [feedback_nl_parser_hybrid]).

문구는 KR 문구집의 **번역이 아니라 같은 의미의 네이티브 표현**이다(사용자 결정
2026-08-26 — 직역은 어색할 수 있어 의미만 보존하고 영어 화자에게 자연스럽게 쓴다).
문구 원칙은 KR과 동일하다(CLAUDE.md 규제 안전 — 추천·전망·맞춤 조언 금지, 연구·검증
안내만). 예시는 US 레인이 실제 실행할 수 있는 개념만 쓴다(S&P 500·Nasdaq-100
유니버스, 모멘텀 상위 K, 가치 스크리닝, RSI·이동평균, 지정 종목 백테스트) —
KR 카탈로그의 업종 유니버스 예시는 US 업종 필터(GICS) 미지원이라 의도적으로 없다
(미지원 개념을 제안해 막다른 길을 만들지 않는다는 KR 원칙 그대로).
"""

from __future__ import annotations

from hashlib import sha256
from typing import Optional

GREETING_REPLIES = (
    "Hello! What investment idea would you like to explore?",
    "Hi there! What kind of strategy should we dig into today?",
    "Welcome! Is there a trading strategy you'd like to backtest?",
)

OFFTOPIC_REFUSAL = (
    "That's outside what I can help with — I'm dedicated to investment strategy "
    "research and analysis. I'd be happy to help with anything related to "
    "investment strategies or backtesting, though."
)

# [규제 안전] 특정 종목 매수·매도·보유 추천 금지 — KR STOCK_PICK_REDIRECT와 같은 구조:
# 거절만 하지 않고 '어떤 조건에서 사고팔 것인가'를 정의·검증하는 전략 설계로 이끈다.
STOCK_PICK_REDIRECT = (
    "I can't recommend specific stocks or tell you what to buy right now — but what "
    "we can do is define when to buy and sell as a strategy, and put it to the test.\n\n"
    "For example, you could start with:\n"
    "• An 'oversold rebound' strategy that buys when RSI dips below 30 and sells above 70\n"
    "• A trend-following strategy that buys on a golden cross — the 20-day moving average "
    "crossing above the 60-day\n"
    "• A value strategy that screens for undervalued quality stocks with low P/B and high ROE\n\n"
    "Does any of these appeal to you? If there's a trading style you've had your eye on, "
    "tell me about it — we can layer in stop-losses, take-profits, or holding periods and "
    "see how it would have performed.",

    "I can't tell you what to buy, but we can take your investment idea, turn it into "
    "a strategy, and backtest it together.\n\n"
    "For example, you could build:\n"
    "• A momentum strategy that buys the strongest performers of the last 3 months\n"
    "• A breakout strategy that buys when price clears its recent highs\n"
    "• A strategy that flags stocks trading on unusually heavy volume\n\n"
    "If any of these sound interesting, let me know. We can also pick a universe to "
    "target — S&P 500, Nasdaq-100, and more — and run a backtest right away.",

    "I can't tell you what to buy, but we can turn your investment idea into a strategy "
    "and see how it holds up against historical data.\n\n"
    "A few ways to get started:\n"
    "• An indicator-based strategy like 'buy below RSI 30, sell above 70'\n"
    "• A trend strategy that buys when a short moving average crosses above a longer one\n"
    "• A screening strategy that picks undervalued stocks by low P/E or P/B\n\n"
    "What market or investing style interests you? Share your idea and I'll turn it "
    "into a strategy you can verify.",
)

ONBOARDING_REPLY = (
    "New here, or not sure where to start? I can walk you through building a strategy "
    "step by step — just pick a few options and we'll go straight to a backtest."
)

STRATEGY_PICK_REPLY = (
    "I don't rank strategies or recommend one over another — but we can take an idea "
    "you're drawn to, turn it into a strategy, and backtest it on historical data. "
    "I'll walk you through it step by step; make your picks and the backtest follows."
)

PERSONAL_ADVICE_REPLY = (
    "I don't offer strategy or stock recommendations tailored to personal circumstances "
    "like age, assets, or occupation — every investment decision is yours to make. "
    "What you can do here is choose the conditions you want, build a strategy, and "
    "verify it on historical data. I'll walk you through it step by step; make your "
    "picks and the backtest follows."
)

UNSUPPORTED_FEATURE_REPLY = (
    "Sorry — analysis of news, filings, and similar catalysts isn't available right now. "
    "Share another investment idea and I can turn it into a strategy and backtest it. "
    "Ideas built on technical indicators (RSI, moving averages, volume) or fundamentals "
    "(P/E, P/B, ROE) translate into strategies right away."
)

LIVE_TRADING_REPLY = (
    "I can't place trades in a real account or manage money on your behalf — this is a "
    "research tool for designing strategies and validating them on historical data. "
    "What you can do is build a strategy, backtest it, and then run it like the real "
    "thing in a virtual paper-trading account."
)

# 워크플로 제어 효과 → 정형 안내(결정론 매핑 — KR classifier._EFFECT_REPLIES와 동일 구조).
# RESUME은 안내 없이 이어서 진행하므로 문구가 없다(KR과 동일).
EFFECT_PAUSE_REPLY = (
    "I've paused the strategy for now. Everything you've set so far is saved — "
    "just say the word when you'd like to pick it back up."
)
EFFECT_CANCEL_REPLY = (
    "I've cancelled this strategy. Whenever you'd like to start a new one, just let me know."
)
EFFECT_RESTART_REPLY = (
    "Let's scrap the current strategy and start fresh. "
    "What conditions would you like to begin with?"
)

# 종목 전환 예시 — 엔진의 US 레인이 실제 실행할 수 있는 개념만 쓴다(KR과 같은 원칙).
_STOCK_REDIRECT_EXAMPLE_LARGE_CAP = (
    "• A momentum strategy that buys the top 5 performers of the last 3 months "
    "among S&P 500 large caps"
)
_STOCK_REDIRECT_EXAMPLES_COMMON = (
    "• A value strategy that screens for undervalued quality stocks with low P/B and high ROE\n"
    "• An oversold rebound strategy that buys when RSI dips below 30 and sells above 70"
)


def stock_question_redirect(
    name: Optional[str] = None,
    market: Optional[str] = None,
    sector: Optional[str] = None,
    overseas: bool = False,
) -> str:
    """특정 종목 매수·매도 질문에 대한 '추천 불가 안내 + 전략 전환' 문구(US 버전).

    KR 버전과 시그니처를 맞춘다(도메인 정책 레이어가 언어와 무관하게 같은 호출을 하도록).
    market·sector·overseas는 KR 시장 분기(코스닥 예시·업종 유니버스·해외 미지원 안내)용이라
    US 카탈로그에서는 쓰지 않는다 — US 레인은 업종 필터(GICS)가 없고, 지수 유니버스
    예시로 통일한다. 지정 종목 백테스트(single-asset)는 US 티커 registry가 지원하므로
    KR과 같이 그 종목 자체를 검증하는 예시를 첫 줄에 둔다(검증은 추천이 아니다).
    """
    if name:
        lead = (
            f"I can't offer buy/sell judgments or recommendations on {name}.\n\n"
            f"But if {name} has caught your interest, we can turn that into a strategy — "
            "'under what conditions would I buy and sell?' — and put it to the test.\n\n"
            "For example, you could start with:\n"
        )
        single_asset_example = (
            f"• A backtest on {name} itself — buy on a golden cross (5-day/20-day), "
            "sell on a dead cross"
        )
    else:
        lead = (
            "I can't offer buy/sell judgments or recommendations for specific stocks.\n\n"
            "But we can take the idea behind a stock you're interested in and turn it into "
            "a strategy — 'under what conditions would I buy and sell?' — and put it to "
            "the test.\n\n"
            "For example, you could start with:\n"
        )
        single_asset_example = ""
    examples = "\n".join(
        part
        for part in (
            single_asset_example,
            _STOCK_REDIRECT_EXAMPLE_LARGE_CAP,
            _STOCK_REDIRECT_EXAMPLES_COMMON,
        )
        if part
    )
    return (
        f"{lead}{examples}\n\n"
        "If any of these interest you, let me know — I'll turn it into a strategy "
        "and run the backtest right away."
    )


def greeting_reply(text: str) -> str:
    """인사 응답을 입력 기반으로 결정적으로 하나 고른다(캐시 친화 — KR과 동일 설계)."""
    idx = int(sha256(text.encode("utf-8")).hexdigest(), 16) % len(GREETING_REPLIES)
    return GREETING_REPLIES[idx]


def stock_pick_reply(text: str) -> str:
    """열린 추천 요청에 대한 전략 전환 안내를 입력 기반으로 결정적으로 하나 고른다."""
    idx = int(sha256(text.encode("utf-8")).hexdigest(), 16) % len(STOCK_PICK_REDIRECT)
    return STOCK_PICK_REDIRECT[idx]
