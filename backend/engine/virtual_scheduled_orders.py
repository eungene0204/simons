"""가상계좌 예약 주문 큐 — 신호 후 N거래일 지연 체결(risk.execution_delay_days>1)의 자동매매 대응.

백테스트(engine v16.9.0)는 신호표를 N칸 밀어 신호 봉의 N번째 거래일 시가에 체결한다. 자동매매
루프(engine/virtual_trader.py)는 매일 방금 마감된 봉으로 신호를 새로 계산해 그날 집행 창에서
바로 주문하므로 "며칠 뒤 집행"을 들고 있을 자리가 없다 — 이 큐가 그 자리다.

계약
- 신호가 난 날(지연 1이었다면 체결됐을 날 = signalDate)에 행을 만든다. 같은 계좌·종목·방향의
  미집행 행이 있으면 다시 만들지 않는다(신호가 며칠 이어져도 한 건 — 백테스트에서 보유 중 재신호가
  무시되는 것과 같다).
- signalDate 이후 delayDays-1 거래 세션이 지난 첫 집행 창에서 집행한다. 세션은 그 종목의 봉
  (+오늘 실시간 봉)으로 센다(count_holding_sessions와 같은 자). 서버 정지 등으로 창을 놓치면
  다음 창으로 이월된다(백테스트의 거래 불가일 이월과 같은 계약).
- 리스크 청산(손절·익절·트레일링·보유일)·강제청산은 큐를 거치지 않고 종전대로 즉시 집행한다.
- 예약 당시 전략(strategyId)이 바뀌면 집행하지 않고 CANCELLED로 닫는다.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import db as appdb
from engine.live_signal_utils import count_holding_sessions

logger = logging.getLogger(__name__)

STATUS_SCHEDULED = "SCHEDULED"
STATUS_EXECUTED = "EXECUTED"
STATUS_NOTIFIED = "NOTIFIED"
STATUS_SKIPPED = "SKIPPED"
STATUS_CANCELLED = "CANCELLED"

# SKIPPED/CANCELLED 사유 코드(표시 문장이 아니라 코드 — 화면 문구는 프론트 사전 소관).
RES_NO_POSITION = "NO_POSITION"
RES_ALREADY_HELD = "ALREADY_HELD"
RES_MAX_POSITIONS = "MAX_POSITIONS"
RES_INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
RES_ALREADY_EXITED_TODAY = "ALREADY_EXITED_TODAY"
RES_STRATEGY_CHANGED = "STRATEGY_CHANGED"


def fetch_open(account_id: str) -> list[dict]:
    con = appdb.connect()
    try:
        rows = con.execute(
            'SELECT * FROM "VirtualScheduledOrder" WHERE "accountId" = ? AND status = ? '
            'ORDER BY "createdAt"',
            (account_id, STATUS_SCHEDULED),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def enqueue(
    account_id: str,
    strategy_id: Optional[str],
    symbol: str,
    name: Optional[str],
    side: str,
    signal_type: str,
    signal_date: str,
    delay_days: int,
    reason: Optional[str],
) -> Optional[str]:
    """예약 행을 만든다. 같은 계좌·종목·방향의 미집행 행이 있으면 None(멱등)."""
    order_id = str(uuid.uuid4())
    now = appdb.now()
    con = appdb.connect()
    try:
        existing = con.execute(
            'SELECT id FROM "VirtualScheduledOrder" WHERE "accountId" = ? AND symbol = ? '
            'AND side = ? AND status = ?',
            (account_id, symbol, side, STATUS_SCHEDULED),
        ).fetchone()
        if existing:
            return None
        con.execute(
            'INSERT INTO "VirtualScheduledOrder" (id, "accountId", "strategyId", symbol, name, side, '
            '"signalType", "signalDate", "delayDays", reason, status, "createdAt", "updatedAt") '
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, account_id, strategy_id, symbol, name, side, signal_type, signal_date,
             int(delay_days), reason, STATUS_SCHEDULED, now, now),
        )
        con.commit()
        return order_id
    except Exception as e:
        con.rollback()
        logger.error("[ScheduledOrder] 예약 DB 오류 %s %s: %s", account_id, symbol, e)
        return None
    finally:
        con.close()


def resolve(
    scheduled_id: str,
    status: str,
    resolution: Optional[str] = None,
    order_id: Optional[str] = None,
) -> bool:
    """미집행(SCHEDULED) 행만 닫는다 — 조건부 UPDATE라 다른 틱·경로와의 이중 집행을 막는다."""
    now = appdb.now()
    con = appdb.connect()
    try:
        claimed = con.execute(
            'UPDATE "VirtualScheduledOrder" SET status = ?, resolution = ?, "orderId" = ?, '
            '"resolvedAt" = ?, "updatedAt" = ? WHERE id = ? AND status = ?',
            (status, resolution, order_id, now, now, scheduled_id, STATUS_SCHEDULED),
        ).rowcount
        con.commit()
        return bool(claimed)
    except Exception as e:
        con.rollback()
        logger.error("[ScheduledOrder] 상태 갱신 오류 %s: %s", scheduled_id, e)
        return False
    finally:
        con.close()


def sessions_since(data_loader: Any, symbol: str, signal_date: str, today: str, quote: Any = None) -> int:
    """signalDate 뒤로 오늘까지 지난 거래 세션 수(오늘 실시간 봉 포함)."""
    if data_loader is None:
        return 0
    return count_holding_sessions(data_loader, symbol, signal_date, today, quote)


def is_due(order: dict, sessions: int) -> bool:
    """지연 N = 신호 봉의 N번째 거래일 체결. signalDate가 그 첫 번째이므로 N-1 세션이 지나면 집행."""
    return sessions >= max(0, int(order.get("delayDays") or 1) - 1)
