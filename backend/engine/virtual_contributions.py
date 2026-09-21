"""가상계좌 정액 적립식 — 납입 회차의 판정과 입금 기록.

백테스트의 적립 장부(engine/contributions.py)는 전 기간 달력을 한 번에 훑지만, 자동매매 루프는
30초마다 '오늘'만 본다. 이 모듈이 그 사이를 잇는다: 오늘이 새 납입 주기인지 판정하고, 입금을
**하루 한 번만** 기록한다.

계약
- 1회차는 계좌의 초기 자본이다(백테스트의 첫 봉과 같은 규약) — 입금 없이 매수만 시작한다.
- 이후에는 마지막 기록일과 오늘의 주기 키가 다르면 새 회차다. 서버가 꺼져 납입일을 놓쳐도 같은
  주기 안에 돌아오면 그날 납입하고, 한 주기를 통째로 놓치면 그 회차는 건너뛴다(소급 입금 없음,
  2026-09-21 사용자 결정).
- 총 납입액(초기 자본 + 누적 납입)은 계좌의 `contributionCap`(생성 시점 플랜 모의 투자금)을 넘지
  않는다 — 남은 한도만큼만 넣고, 한도에 닿으면 그 주기는 'CAPPED'로 닫는다(2026-09-21 사용자 결정).
- (accountId, date) 유니크가 중복 입금의 정본 가드다. 입금 기록과 잔액 증가는 한 트랜잭션이다 —
  체결 창(5분) 동안 루프가 10번쯤 다시 들어오고, 프로세스가 재시작돼도 두 번 넣지 않는다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from engine.live_signal_utils import _period_key

START = "CONTRIBUTION_START"
DEPOSIT = "CONTRIBUTION"
CAPPED = "CONTRIBUTION_CAPPED"


@dataclass(frozen=True)
class ContributionRound:
    kind: str          # START | CONTRIBUTION | CONTRIBUTION_CAPPED
    credited: float    # 이번 회차에 실제로 들어온 금액
    cash: float        # 입금 뒤 계좌 현금 — 이번 회차 매수 예산


def is_new_period(last_date: Optional[str], today: str, period: str) -> bool:
    """마지막 기록일 이후 새 납입 주기가 시작됐는가. 기록이 없으면 1회차다."""
    if not last_date:
        return True
    if period == "daily":
        return last_date != today
    return _period_key(last_date, period) != _period_key(today, period)


def claim_round(con: Any, account_id: str, today: str, amount: float, period: str,
                now: Any) -> Optional[ContributionRound]:
    """오늘이 새 회차면 입금을 기록하고 회차를 돌려준다. 아니면(또는 이미 처리됐으면) None."""
    last = con.execute(
        'SELECT MAX(date) FROM "VirtualCashEvent" WHERE "accountId" = ?', (account_id,)
    ).fetchone()
    last_date = last[0] if last else None
    if not is_new_period(last_date, today, period):
        return None

    account = con.execute(
        'SELECT "initialCash", "contributedCash", "contributionCap", "currentCash" '
        'FROM "VirtualAccount" WHERE id = ? FOR UPDATE', (account_id,)
    ).fetchone()
    if account is None:
        con.rollback()
        return None
    initial, contributed, cap, cash = (float(v) if v is not None else None for v in account)

    if last_date is None:
        kind, credit = START, 0.0
    else:
        room = float("inf") if cap is None else cap - (initial + contributed)
        credit = max(0.0, min(float(amount), room))
        kind = DEPOSIT if credit > 0 else CAPPED

    claimed = con.execute(
        'INSERT INTO "VirtualCashEvent" (id, "accountId", type, amount, "balanceAfter", date, "createdAt") '
        'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT ("accountId", date) DO NOTHING',
        (str(uuid.uuid4()), account_id, kind, credit, cash + credit, today, now),
    )
    if claimed.rowcount != 1:
        con.rollback()
        return None
    if credit > 0:
        con.execute(
            'UPDATE "VirtualAccount" SET "currentCash" = "currentCash" + ?, '
            '"contributedCash" = "contributedCash" + ?, "updatedAt" = ? WHERE id = ?',
            (credit, credit, now, account_id),
        )
    con.commit()
    return ContributionRound(kind=kind, credited=credit, cash=cash + credit)
