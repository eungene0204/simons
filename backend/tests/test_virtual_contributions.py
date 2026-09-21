"""가상계좌 정액 적립식 — engine/virtual_contributions.py + 자동매매 루프 연결.

핵심 계약:
- 1회차는 초기 자본이다(입금 없음). 이후 마지막 기록일과 주기 키가 달라지면 새 회차.
- (accountId, date) 유니크로 하루 한 번 — 체결 창에 루프가 다시 들어와도 두 번 넣지 않는다.
- 놓친 납입일은 같은 주기 안에서 늦게 1회, 주기를 통째로 놓치면 건너뛴다(소급 없음).
- 총 납입액(초기 자본 + 누적 납입)은 contributionCap을 넘지 않는다.
- 조건·랭킹·손절과 섞인 전략, 지정 종목이 아닌 전략에는 납입하지 않는다(백테스트 엔진과 같은 계약).
"""

from datetime import datetime

import pytest

pytest.importorskip("vectorbt")

from engine import virtual_contributions as vc  # noqa: E402
from engine.virtual_trader import VirtualTrader, _contribution_plan  # noqa: E402

NOW = datetime(2026, 1, 1)


@pytest.fixture
def account(app_db):
    app_db.execute(
        'INSERT INTO "VirtualAccount" (id, name, "initialCash", "currentCash", "contributionCap", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("acc1", "적립", 1_000_000, 1_000_000, 2_200_000, NOW),
    )
    app_db.commit()
    return app_db


def _account_row(con):
    return con.execute(
        'SELECT "currentCash", "contributedCash" FROM "VirtualAccount" WHERE id = ?', ("acc1",)
    ).fetchone()


# ─── 주기 판정 ────────────────────────────────────────────────────────────────

def test_new_period_detection():
    assert vc.is_new_period(None, "2026-03-02", "monthly")
    assert not vc.is_new_period("2026-03-02", "2026-03-31", "monthly")
    assert vc.is_new_period("2026-03-31", "2026-04-01", "monthly")
    assert vc.is_new_period("2026-03-27", "2026-03-30", "weekly")          # 금 → 다음 주 월
    assert not vc.is_new_period("2026-03-30", "2026-04-02", "weekly")      # 같은 주(월이 바뀌어도)
    assert vc.is_new_period("2026-03-02", "2026-03-03", "daily")
    assert not vc.is_new_period("2026-03-02", "2026-03-02", "daily")


# ─── 회차 기록 ────────────────────────────────────────────────────────────────

def test_first_round_is_initial_capital_without_deposit(account):
    round_ = vc.claim_round(account, "acc1", "2026-03-02", 500_000, "monthly", NOW)
    assert (round_.kind, round_.credited, round_.cash) == (vc.START, 0.0, 1_000_000.0)
    assert tuple(_account_row(account)) == (1_000_000.0, 0.0)


def test_same_day_and_same_period_are_claimed_once(account):
    assert vc.claim_round(account, "acc1", "2026-03-02", 500_000, "monthly", NOW) is not None
    assert vc.claim_round(account, "acc1", "2026-03-02", 500_000, "monthly", NOW) is None   # 같은 날 재진입
    assert vc.claim_round(account, "acc1", "2026-03-20", 500_000, "monthly", NOW) is None   # 같은 달


def test_new_period_credits_cash_and_contributed_total(account):
    vc.claim_round(account, "acc1", "2026-03-02", 500_000, "monthly", NOW)
    round_ = vc.claim_round(account, "acc1", "2026-04-01", 500_000, "monthly", NOW)
    assert (round_.kind, round_.credited, round_.cash) == (vc.DEPOSIT, 500_000.0, 1_500_000.0)
    assert tuple(_account_row(account)) == (1_500_000.0, 500_000.0)
    events = account.execute(
        'SELECT type, amount, "balanceAfter", date FROM "VirtualCashEvent" ORDER BY date').fetchall()
    assert [tuple(e) for e in events] == [
        (vc.START, 0.0, 1_000_000.0, "2026-03-02"), (vc.DEPOSIT, 500_000.0, 1_500_000.0, "2026-04-01")]


def test_missed_day_deposits_late_within_the_period_and_skips_a_whole_missed_period(account):
    vc.claim_round(account, "acc1", "2026-03-02", 500_000, "monthly", NOW)
    # 4월 1일에 서버가 꺼져 있었다 → 4월 중순에 돌아오면 그날 납입한다.
    assert vc.claim_round(account, "acc1", "2026-04-15", 500_000, "monthly", NOW).credited == 500_000
    # 5월을 통째로 놓쳤다 → 6월에 한 번만 넣는다(5월분 소급 없음).
    assert vc.claim_round(account, "acc1", "2026-06-10", 500_000, "monthly", NOW).credited == 500_000
    assert _account_row(account)[1] == 1_000_000.0


def test_total_contributed_never_exceeds_the_plan_cap(account):
    vc.claim_round(account, "acc1", "2026-03-02", 500_000, "monthly", NOW)
    assert vc.claim_round(account, "acc1", "2026-04-01", 500_000, "monthly", NOW).credited == 500_000
    assert vc.claim_round(account, "acc1", "2026-05-04", 500_000, "monthly", NOW).credited == 500_000
    partial = vc.claim_round(account, "acc1", "2026-06-01", 500_000, "monthly", NOW)
    assert (partial.kind, partial.credited) == (vc.DEPOSIT, 200_000.0)      # 한도까지 남은 만큼만
    capped = vc.claim_round(account, "acc1", "2026-07-01", 500_000, "monthly", NOW)
    assert (capped.kind, capped.credited) == (vc.CAPPED, 0.0)
    assert vc.claim_round(account, "acc1", "2026-07-02", 500_000, "monthly", NOW) is None    # 같은 주기는 닫혔다
    cash, contributed = _account_row(account)
    assert 1_000_000 + contributed == 2_200_000 and cash == 2_200_000


# ─── 자동매매 루프 연결 ───────────────────────────────────────────────────────

_DCA_RISK = {"contribution_amount": 500_000, "contribution_period": "monthly"}


def test_plan_only_for_unconditional_designated_symbol_strategies():
    dsl = {"backtest_mode": "single_asset"}
    assert _contribution_plan(dsl, {}, {}, _DCA_RISK, "acc1") == (500_000.0, "monthly")
    assert _contribution_plan({"backtest_mode": "universe"}, {}, {}, _DCA_RISK, "acc1") is None
    assert _contribution_plan(dsl, {"conditions": [{"id": "rsi"}]}, {}, _DCA_RISK, "acc1") is None
    assert _contribution_plan(dsl, {}, {}, {**_DCA_RISK, "stop_loss_pct": 10}, "acc1") is None
    assert _contribution_plan(dsl, {}, {}, {"contribution_amount": 500_000}, "acc1") is None   # 반쪽 설정
    assert _contribution_plan(dsl, {}, {}, {}, "acc1") is None


def test_run_contribution_buys_designated_symbols_equally_once_per_period(account):
    trader = VirtualTrader(market_data_provider=None, data_loader=None)
    prices = {"069500": 50_000.0, "360750": 20_000.0}
    names = {"069500": "KODEX 200", "360750": "TIGER 미국S&P500"}

    trader._run_contribution("acc1", (500_000.0, "monthly"), list(prices), "2026-03-02", prices, names)
    orders = account.execute('SELECT symbol, side, quantity FROM "VirtualOrder" ORDER BY symbol').fetchall()
    # 1회차 = 초기 자본 100만을 두 종목에 50만씩. 체결가는 슬리피지·호가 반올림이 붙어 시세보다 높다.
    assert [(o[0], o[1]) for o in orders] == [("069500", "BUY"), ("360750", "BUY")]
    assert orders[0][2] == 9 and orders[1][2] == 24
    # 납입 매수는 매수(entry)로 기록한다 — 신호 로그 화면은 entry가 아니면 '매도' 배지를 그린다.
    logs = account.execute('SELECT "signalType", action, reason FROM "VirtualMarketLog"').fetchall()
    assert {(l[0], l[1]) for l in logs} == {("entry", "auto_executed")}
    assert all("정기 적립 시작" in l[2] for l in logs)

    # 체결 창 안에서 루프가 다시 들어와도 같은 날·같은 달에는 아무 일도 없다.
    trader._run_contribution("acc1", (500_000.0, "monthly"), list(prices), "2026-03-02", prices, names)
    trader._run_contribution("acc1", (500_000.0, "monthly"), list(prices), "2026-03-03", prices, names)
    assert account.execute('SELECT COUNT(*) FROM "VirtualOrder"').fetchone()[0] == 2

    # 다음 달 첫 체결 창: 50만 입금 뒤 남은 현금 전부를 다시 균등하게 나눠 산다.
    cash_before = _account_row(account)[0]
    trader._run_contribution("acc1", (500_000.0, "monthly"), list(prices), "2026-04-01", prices, names)
    assert account.execute('SELECT COUNT(*) FROM "VirtualOrder"').fetchone()[0] == 4
    cash_after, contributed = _account_row(account)
    assert contributed == 500_000.0 and cash_after < cash_before + 500_000


def test_no_priced_symbol_means_no_round_is_consumed(account):
    """시세가 없는 날(휴장·스테일)은 회차를 쓰지 않는다 — 다음 거래일에 그 주기의 납입이 살아 있어야 한다."""
    trader = VirtualTrader(market_data_provider=None, data_loader=None)
    trader._run_contribution("acc1", (500_000.0, "monthly"), ["069500"], "2026-03-02", {}, {})
    assert account.execute('SELECT COUNT(*) FROM "VirtualCashEvent"').fetchone()[0] == 0
