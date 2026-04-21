"""
Promoter — converts an approved candidate into a live paper-trading account.

생성 단계:
1. Strategy 레코드 (settings = BacktestRequest JSON)
2. VirtualAccount (tradingMode='auto', strategyId 연결)
3. VirtualMarketState (status='stopped' — 사용자가 start 버튼 클릭 시 running)

에이전트는 자동 start 하지 **않는다** — 사용자 명시적 승인이 필요하다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from research.generator import Candidate

logger = logging.getLogger(__name__)


class Promoter:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def promote(
        self,
        candidate: Candidate,
        user_id: int,
        strategy_name: str,
        initial_cash: float = 10_000_000.0,
        optimized_request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request_payload = optimized_request or candidate.backtest_request
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        strategy_id = f"strat_{uuid.uuid4().hex[:16]}"
        account_id = f"va_{uuid.uuid4().hex[:16]}"
        state_id = f"vms_{uuid.uuid4().hex[:16]}"

        symbols = request_payload.get("symbols") or []
        universe_id = request_payload.get("universe_id") or "kospi200"
        settings_json = json.dumps(request_payload, ensure_ascii=False)

        try:
            self.db.execute("BEGIN")
            self.db.execute(
                """
                INSERT INTO Strategy (id, name, description, settings, strategyType, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy_id,
                    strategy_name,
                    candidate.parsed_dsl.get("description", "[research-agent]"),
                    settings_json,
                    "research",
                    now_iso,
                    now_iso,
                ),
            )

            self.db.execute(
                """
                INSERT INTO VirtualAccount (
                    id, name, initialCash, currentCash,
                    strategyId, strategyName, tradingMode, createdAt, updatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    f"[agent] {strategy_name}",
                    float(initial_cash),
                    float(initial_cash),
                    strategy_id,
                    strategy_name,
                    "auto",
                    now_iso,
                    now_iso,
                ),
            )

            self.db.execute(
                """
                INSERT INTO VirtualMarketState (
                    id, accountId, startDate, status, symbols, createdAt, updatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state_id,
                    account_id,
                    now.strftime("%Y-%m-%d"),
                    "stopped",
                    json.dumps(symbols),
                    now_iso,
                    now_iso,
                ),
            )
            self.db.commit()
        except sqlite3.Error as e:
            self.db.rollback()
            logger.exception("[Promoter] promotion failed")
            raise RuntimeError(f"promotion failed: {e}") from e

        return {
            "strategyId": strategy_id,
            "accountId": account_id,
            "stateId": state_id,
        }

    def active_promotion_count(self, user_id: int) -> int:
        """Best-effort user-level count — VirtualAccount schema has no userId
        so we use a convention: strategyName prefix embeds user id.

        Returns count of agent-created auto accounts (by tradingMode='auto').
        """
        cur = self.db.execute(
            "SELECT COUNT(*) FROM VirtualAccount WHERE tradingMode = 'auto'"
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0
