"""
VirtualTrader — FastAPI 백그라운드 자동매매 엔진

장중(KST 09:00~15:30, 평일) 30초 간격으로:
  1. running 상태의 가상계좌 조회 (SQLite)
  2. 전략 조건 파싱 (Strategy.settings JSON)
  3. 실시간 시세 조회 (MarketDataProvider)
  4. 시그널 평가 (SignalEngine)
  5. 리스크 관리 (SL / TP / 트레일링스톱 / 최대보유일)
  6. 자동매매 실행 + 로그 기록 (SQLite 직접 기록)
  7. 포지션 현재가 / peakPrice 갱신
"""

import asyncio
import json
import logging
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from engine.live_signal_utils import prepare_signal_dataframe
from engine.listing_status import (
    ListingStatus, is_buy_allowed, is_sell_allowed, write_audit_log,
    get_stock_listing_status,
)

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────
_KST = timezone(timedelta(hours=9))
REFRESH_INTERVAL = 30          # 장중 시그널 평가 간격 (초)
HISTORY_DAYS = 75              # 시그널 평가에 사용할 OHLCV 기간

FEE_RATE = 0.00015             # 수수료 0.015%
TAX_RATE = 0.0015              # 증권거래세 0.15% (2025년~, 백테스트 엔진 기본값과 동일)
MARKET_SLIPPAGE = 0.0005       # 시장가 슬리피지 0.05%


# ── 주문 계산 유틸 ──────────────────────────────────────────────────────────

def _round_tick(price: float) -> int:
    # KRX 호가단위 (2023-01 개편, 코스피/코스닥 공통)
    if price < 2_000:   return round(price)
    if price < 5_000:   return round(price / 5) * 5
    if price < 20_000:  return round(price / 10) * 10
    if price < 50_000:  return round(price / 50) * 50
    if price < 200_000: return round(price / 100) * 100
    if price < 500_000: return round(price / 500) * 500
    return round(price / 1_000) * 1_000


def _filled_price(price: float, side: str) -> int:
    raw = price * (1 + MARKET_SLIPPAGE) if side == "BUY" else price * (1 - MARKET_SLIPPAGE)
    return _round_tick(max(1, raw))


def _fee(filled: int, qty: int) -> int:
    return math.floor(filled * qty * FEE_RATE)


def _tax(filled: int, qty: int) -> int:
    return math.floor(filled * qty * TAX_RATE)


def _buy_cost(filled: int, qty: int) -> int:
    return filled * qty + _fee(filled, qty)


def _sell_proceeds(filled: int, qty: int) -> float:
    return filled * qty - _fee(filled, qty) - _tax(filled, qty)


def _realized_pnl(sell_price: int, avg_buy: float, qty: int, fee: int, tax: int) -> float:
    return (sell_price - avg_buy) * qty - fee - tax


def _coerce_numeric(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_ms() -> int:
    """Prisma가 SQLite DateTime을 epoch ms 정수로 저장하므로 동일 포맷으로 기록한다."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _parse_db_datetime(value) -> Optional[datetime]:
    """DateTime 컬럼 값 파싱 — Prisma(epoch ms 정수)와 구버전 Python(ISO 문자열) 모두 지원."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


# ── 시장 시간 ────────────────────────────────────────────────────────────────

def _is_market_hours() -> bool:
    now = datetime.now(_KST)
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return 900 <= t <= 1530


def _fresh_price_map(quotes: dict, today: str) -> dict[str, int]:
    """오늘 날짜(KST)의 시세만 매매에 사용한다.

    평일 공휴일(KRX 휴장)에는 제공자들이 마지막 거래일 날짜(또는 None)를 반환하므로
    여기서 전부 걸러져 매매·리스크 청산·지정가 체결이 보류된다. 데이터 소스 장애로
    과거 시세가 내려오는 경우도 같은 방식으로 방어된다.
    """
    return {
        sym: q.close
        for sym, q in quotes.items()
        if q.close > 0 and getattr(q, "date", None) == today
    }


# ── DB 경로 ──────────────────────────────────────────────────────────────────

def _db_path() -> str:
    # 프로젝트 루트: backend/engine/virtual_trader.py 기준 3단계 위
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("file:"):
        rel = db_url[len("file:"):]
        # Prisma는 file: 경로를 schema.prisma 위치(prisma/) 기준으로 해석한다
        prisma_dir = os.path.join(project_root, "prisma")
        return os.path.normpath(os.path.join(prisma_dir, rel))
    return os.path.join(project_root, "prisma", "prisma", "dev.db")


# ── VirtualTrader ────────────────────────────────────────────────────────────

class VirtualTrader:
    """
    FastAPI 백그라운드 자동매매 엔진.

        trader = VirtualTrader(market_data_provider, data_loader)
        await trader.start()   # startup 이벤트
        await trader.stop()    # shutdown 이벤트
    """

    def __init__(self, market_data_provider, data_loader, ai_engine=None):
        self._mdp = market_data_provider
        self._loader = data_loader
        self._ai_engine = ai_engine
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._db = _db_path()

    # ── 생명주기 ──────────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[VirtualTrader] 시작 (DB: %s, 간격: %ds)", self._db, REFRESH_INTERVAL)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[VirtualTrader] 중지")

    # ── 메인 루프 ─────────────────────────────────────────────────────────────

    async def _loop(self):
        while self._running:
            try:
                if _is_market_hours():
                    await self._refresh_all()
                else:
                    logger.debug("[VirtualTrader] 장외 시간, 대기")
            except Exception as e:
                logger.error("[VirtualTrader] 루프 예외: %s", e, exc_info=True)
            await asyncio.sleep(REFRESH_INTERVAL)

    async def _refresh_all(self):
        """running 상태 계좌 전체 순회"""
        accounts = await asyncio.to_thread(self._fetch_running_accounts)
        if not accounts:
            return
        logger.info("[VirtualTrader] 새로고침: %d개 계좌", len(accounts))
        for account in accounts:
            try:
                await self._refresh_account(account)
            except Exception as e:
                logger.error("[VirtualTrader] 계좌 %s 오류: %s", account["id"], e, exc_info=True)

    # ── SQLite 읽기 ───────────────────────────────────────────────────────────

    def _fetch_running_accounts(self) -> list[dict]:
        """running 상태 VirtualMarketState + VirtualAccount 조인"""
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute("""
                SELECT
                    a.id, a.currentCash, a.strategyId, a.tradingMode,
                    s.symbols, s.id AS stateId
                FROM VirtualMarketState s
                JOIN VirtualAccount a ON a.id = s.accountId
                WHERE s.status = 'running'
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def _fetch_strategy(self, strategy_id: str) -> Optional[dict]:
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute("SELECT settings FROM Strategy WHERE id = ?", (strategy_id,)).fetchone()
            if row:
                return json.loads(row["settings"])
            return None
        finally:
            con.close()

    def _fetch_positions(self, account_id: str) -> list[dict]:
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM VirtualPosition WHERE accountId = ?", (account_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def _fetch_pending_orders(self, account_id: str) -> list[dict]:
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM VirtualOrder WHERE accountId = ? AND status = 'PENDING'",
                (account_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def _fetch_today_logs(self, account_id: str, today: str) -> set[str]:
        """오늘 기록된 (symbol_signalType_action) 집합 반환 — 하루 1회 중복 방지용"""
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT symbol, signalType, action FROM VirtualMarketLog "
                "WHERE accountId = ? AND date = ? AND action IN ('auto_executed', 'notified')",
                (account_id, today),
            ).fetchall()
            return {f"{r['symbol']}_{r['signalType']}_{r['action']}" for r in rows}
        finally:
            con.close()

    def _fetch_current_cash(self, account_id: str) -> float:
        con = sqlite3.connect(self._db)
        try:
            row = con.execute("SELECT currentCash FROM VirtualAccount WHERE id = ?", (account_id,)).fetchone()
            return row[0] if row else 0.0
        finally:
            con.close()

    def _fetch_stock_names(self, symbols: list[str]) -> dict[str, str]:
        """Stock 테이블에서 종목명 조회. 없으면 symbol을 fallback으로 사용."""
        if not symbols:
            return {}
        con = sqlite3.connect(self._db)
        try:
            placeholders = ",".join("?" * len(symbols))
            rows = con.execute(
                f"SELECT symbol, name FROM Stock WHERE symbol IN ({placeholders})",
                symbols,
            ).fetchall()
            result = {r[0]: r[1] for r in rows if r[1]}
            return result
        except Exception:
            return {}
        finally:
            con.close()

    def _fetch_delisting_policy(self, account_id: str) -> str:
        """계좌의 상장폐지 처리 정책 조회. 기본 AUTO_LIQUIDATE."""
        con = sqlite3.connect(self._db)
        try:
            row = con.execute(
                "SELECT delistingPolicy FROM VirtualAccount WHERE id = ?", (account_id,)
            ).fetchone()
            return row[0] if row and row[0] else "AUTO_LIQUIDATE"
        except Exception:
            return "AUTO_LIQUIDATE"
        finally:
            con.close()

    # ── 계좌 새로고침 ─────────────────────────────────────────────────────────

    async def _refresh_account(self, account: dict):
        account_id = account["id"]
        trading_mode = account["tradingMode"]
        symbols: list[str] = json.loads(account["symbols"])
        strategy_id = account["strategyId"]
        today = datetime.now(_KST).strftime("%Y-%m-%d")

        # 1. 전략 조건 파싱
        entry_conditions = []
        exit_conditions = []
        position_size_pct = 10
        max_positions = 5
        stop_loss_pct = 0.0
        take_profit_pct = 0.0
        trailing_stop_pct = 0.0
        max_holding_days = 0

        if strategy_id:
            dsl = await asyncio.to_thread(self._fetch_strategy, strategy_id)
            if dsl:
                entry_conditions = dsl.get("entry", {}).get("conditions", [])
                exit_conditions = dsl.get("exit", {}).get("conditions", [])
                risk = dsl.get("risk", {})
                position_size_pct = _coerce_numeric(risk.get("position_size_pct"), 10.0)
                max_positions = int(_coerce_numeric(risk.get("max_positions"), 5.0))
                stop_loss_pct = _coerce_numeric(risk.get("stop_loss_pct"))
                take_profit_pct = _coerce_numeric(risk.get("take_profit_pct"))
                trailing_stop_pct = _coerce_numeric(risk.get("trailing_stop_pct"))
                max_holding_days = int(_coerce_numeric(risk.get("max_holding_days")))

        # 2. 실시간 시세 조회 (휴장일/스테일 시세 가드: 오늘 날짜 시세만 매매에 사용)
        quotes = await self._mdp.get_prices(symbols)
        price_map: dict[str, int] = _fresh_price_map(quotes, today)
        if quotes and not price_map:
            logger.debug("[VirtualTrader] 계좌 %s: 오늘(%s) 시세 없음 — 휴장일 또는 스테일 데이터, 매매 보류", account_id, today)
        name_map: dict[str, str] = await asyncio.to_thread(self._fetch_stock_names, symbols)

        # 3. 시그널 평가
        signals = await asyncio.to_thread(
            self._evaluate_signals, symbols, entry_conditions, exit_conditions, quotes
        )

        # 4. 리스크 관리
        positions = await asyncio.to_thread(self._fetch_positions, account_id)
        risk_exits: dict[str, str] = {}
        for pos in positions:
            current_price = price_map.get(pos["symbol"], 0)
            if not current_price:
                continue
            avg = pos["avgPrice"]
            pnl_pct = (current_price - avg) / avg * 100

            if stop_loss_pct > 0 and pnl_pct <= -stop_loss_pct:
                risk_exits[pos["symbol"]] = f"손절 ({pnl_pct:.1f}% ≤ -{stop_loss_pct}%)"
                continue
            if take_profit_pct > 0 and pnl_pct >= take_profit_pct:
                risk_exits[pos["symbol"]] = f"익절 ({pnl_pct:.1f}% ≥ +{take_profit_pct}%)"
                continue
            if trailing_stop_pct > 0:
                peak = pos.get("peakPrice") or avg
                dd_pct = (current_price - peak) / peak * 100
                if dd_pct <= -trailing_stop_pct:
                    risk_exits[pos["symbol"]] = f"트레일링스톱 (최고가 {int(peak):,}원 대비 {dd_pct:.1f}% 하락)"
                    continue
            if max_holding_days > 0:
                opened_dt = _parse_db_datetime(pos.get("openedAt"))
                if opened_dt is not None:
                    holding_days = (datetime.now(timezone.utc) - opened_dt).days
                    if holding_days >= max_holding_days:
                        risk_exits[pos["symbol"]] = f"최대보유일 초과 ({holding_days}일 ≥ {max_holding_days}일)"

        # 리스크 종료를 시그널에 병합
        for sym, reason in risk_exits.items():
            found = next((s for s in signals if s["symbol"] == sym), None)
            if found:
                found["exit_signal"] = True
                found["exit_reason"] = (found.get("exit_reason") or "") + f" + {reason}" if found.get("exit_reason") else reason
            else:
                price = price_map.get(sym, 0)
                signals.append({"symbol": sym, "close": price, "entry_signal": False, "exit_signal": True, "exit_reason": reason})

        # 4.5. 상장 상태 체크: 거래 제한 + 강제청산
        delistingPolicy = await asyncio.to_thread(self._fetch_delisting_policy, account_id)
        for sym in list(symbols):
            status = await asyncio.to_thread(get_stock_listing_status, sym)
            if status == ListingStatus.NORMAL:
                continue

            sig = next((s for s in signals if s["symbol"] == sym), None)

            # 진입 차단: 매수 불허 상태
            if not is_buy_allowed(status):
                if sig:
                    sig["entry_signal"] = False
                    sig["entry_reason"] = None
                logger.debug("[VirtualTrader] 진입 차단 %s (상태: %s)", sym, status)

            # 강제청산: DELISTED / DELISTING_SCHEDULED + AUTO_LIQUIDATE 정책
            if status in (ListingStatus.DELISTED, ListingStatus.DELISTING_SCHEDULED):
                pos = next((p for p in positions if p["symbol"] == sym), None)
                if pos and delistingPolicy == "AUTO_LIQUIDATE":
                    if sig:
                        sig["exit_signal"] = True
                        sig["exit_reason"] = f"강제청산 (상장 상태: {status})"
                    else:
                        price = price_map.get(sym, 0)
                        signals.append({
                            "symbol": sym, "close": price,
                            "entry_signal": False, "exit_signal": True,
                            "exit_reason": f"강제청산 (상장 상태: {status})",
                        })
                    logger.info("[VirtualTrader] 강제청산 예약 %s %s (상태: %s)", account_id, sym, status)

            # TRADING_SUSPENDED: 매도도 차단 (DB에서 강제청산 불가)
            if status == ListingStatus.TRADING_SUSPENDED:
                if sig:
                    sig["exit_signal"] = False
                    sig["entry_signal"] = False

        # 5. 매매 실행
        executed_today = await asyncio.to_thread(self._fetch_today_logs, account_id, today)

        for sig in signals:
            sym = sig["symbol"]
            close = price_map.get(sym, 0)
            if not close:
                continue

            # ── 청산 ─────────────────────────────────────────────────────
            if sig.get("exit_signal"):
                pos = next((p for p in positions if p["symbol"] == sym), None)
                if not pos:
                    continue
                if f"{sym}_exit_auto_executed" in executed_today:
                    continue
                stock_name = name_map.get(sym) or pos.get("name") or sym

                if trading_mode == "auto":
                    order_id = await asyncio.to_thread(
                        self._execute_sell, account_id, sym, stock_name, close, pos["quantity"], pos["avgPrice"]
                    )
                    if order_id:
                        await asyncio.to_thread(
                            self._log_signal, account_id, today, sym, close,
                            "exit", sig.get("exit_reason"), "auto_executed", order_id, stock_name
                        )
                        # 강제청산 감사 로그
                        exit_reason = sig.get("exit_reason") or ""
                        if "강제청산" in exit_reason:
                            await asyncio.to_thread(
                                write_audit_log, account_id, sym,
                                "AUTO_LIQUIDATE", None, None,
                                pos["quantity"], float(close), exit_reason,
                            )
                        executed_today.add(f"{sym}_exit_auto_executed")
                        logger.info("[VirtualTrader] 매도 %s %s %d주 @%d", account_id, sym, pos["quantity"], close)
                elif f"{sym}_exit_notified" not in executed_today:
                    # 알림은 하루 1회만 기록 (30초 틱마다 중복 로그 방지)
                    await asyncio.to_thread(
                        self._log_signal, account_id, today, sym, close,
                        "exit", sig.get("exit_reason"), "notified", None, stock_name
                    )
                    executed_today.add(f"{sym}_exit_notified")

            # ── 진입 ─────────────────────────────────────────────────────
            if sig.get("entry_signal"):
                if f"{sym}_entry_auto_executed" in executed_today:
                    continue
                pos = next((p for p in positions if p["symbol"] == sym), None)
                if pos:
                    continue  # 이미 보유 중
                pos_count = await asyncio.to_thread(self._count_positions, account_id)
                if pos_count >= max_positions:
                    continue
                stock_name = name_map.get(sym, sym)

                if trading_mode == "auto":
                    current_cash = await asyncio.to_thread(self._fetch_current_cash, account_id)
                    order_id = await asyncio.to_thread(
                        self._execute_buy, account_id, sym, stock_name, close, current_cash, position_size_pct
                    )
                    if order_id:
                        await asyncio.to_thread(
                            self._log_signal, account_id, today, sym, close,
                            "entry", sig.get("entry_reason"), "auto_executed", order_id, stock_name
                        )
                        executed_today.add(f"{sym}_entry_auto_executed")
                        logger.info("[VirtualTrader] 매수 %s %s @%d", account_id, sym, close)
                elif f"{sym}_entry_notified" not in executed_today:
                    await asyncio.to_thread(
                        self._log_signal, account_id, today, sym, close,
                        "entry", sig.get("entry_reason"), "notified", None, stock_name
                    )
                    executed_today.add(f"{sym}_entry_notified")

        # 6. PENDING 지정가 주문 체결
        pending_orders = await asyncio.to_thread(self._fetch_pending_orders, account_id)
        for order in pending_orders:
            current_price = price_map.get(order["symbol"], 0)
            if not current_price:
                continue
            side = order["side"]
            limit = order["price"]
            fillable = (side == "BUY" and current_price <= limit) or (side == "SELL" and current_price >= limit)
            if not fillable:
                continue
            await asyncio.to_thread(self._fill_pending_order, account_id, order, current_price)

        # 7. 포지션 현재가 + peakPrice 갱신
        await asyncio.to_thread(self._update_positions, account_id, price_map, quotes)

        # 8. lastRefreshed 갱신
        await asyncio.to_thread(self._update_last_refreshed, account_id, today)

    # ── 시그널 평가 (동기, to_thread에서 실행) ────────────────────────────────

    def _evaluate_signals(
        self,
        symbols: list[str],
        entry_conditions: list,
        exit_conditions: list,
        quotes: dict,
    ) -> list[dict]:
        from engine.signals import SignalEngine
        sig_engine = SignalEngine()
        results = []

        for sym in symbols:
            df = self._loader.load_symbol_data(sym)
            entry_signal = False
            exit_signal = False
            entry_reason = None
            exit_reason = None

            if df is not None and len(df) > 0:
                df_live = prepare_signal_dataframe(
                    df,
                    quotes.get(sym),
                    entry_conditions,
                    exit_conditions,
                    self._ai_engine,
                )
                df_slice = df_live.tail(HISTORY_DAYS + 15)
                if entry_conditions:
                    try:
                        arr, reasons = sig_engine.generate_signals(df_slice, {"conditions": entry_conditions})
                        entry_signal = bool(arr[-1])
                        entry_reason = reasons[-1]
                    except Exception as e:
                        logger.debug("[VirtualTrader] entry signal 오류 %s: %s", sym, e)
                if exit_conditions:
                    try:
                        arr, reasons = sig_engine.generate_signals(df_slice, {"conditions": exit_conditions})
                        exit_signal = bool(arr[-1])
                        exit_reason = reasons[-1]
                    except Exception as e:
                        logger.debug("[VirtualTrader] exit signal 오류 %s: %s", sym, e)

            results.append({
                "symbol": sym,
                "entry_signal": entry_signal,
                "exit_signal": exit_signal,
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
            })

        return results

    # ── 매매 실행 (동기, to_thread에서 실행) ─────────────────────────────────

    def _execute_buy(
        self,
        account_id: str,
        symbol: str,
        name: str,
        price: int,
        current_cash: float,
        position_size_pct: float,
    ) -> Optional[str]:
        invest = current_cash * (position_size_pct / 100)
        filled = _filled_price(price, "BUY")
        # 수수료 포함 총비용이 투자금 안에 들어오도록 수량 산정 (100% 투자 시에도 매수 가능)
        qty = int(invest // (filled * (1 + FEE_RATE)))
        if qty <= 0:
            return None
        cost = _buy_cost(filled, qty)
        if cost > current_cash:
            return None
        fee = _fee(filled, qty)

        order_id = str(uuid.uuid4())
        now_ms = _now_ms()

        con = sqlite3.connect(self._db)
        try:
            con.execute("""
                INSERT INTO VirtualOrder (id, accountId, symbol, name, side, type, quantity, price, filledPrice, fee, status, filledAt, createdAt)
                VALUES (?, ?, ?, ?, 'BUY', 'MARKET', ?, ?, ?, ?, 'FILLED', ?, ?)
            """, (order_id, account_id, symbol, name, qty, price, filled, fee, now_ms, now_ms))

            con.execute("""
                UPDATE VirtualAccount SET currentCash = currentCash - ?, updatedAt = ? WHERE id = ?
            """, (cost, now_ms, account_id))

            existing = con.execute(
                "SELECT quantity, avgPrice, peakPrice FROM VirtualPosition WHERE accountId = ? AND symbol = ?",
                (account_id, symbol)
            ).fetchone()

            if existing:
                new_qty = existing[0] + qty
                new_avg = (existing[1] * existing[0] + filled * qty) / new_qty
                new_peak = max(existing[2] or new_avg, price)
                con.execute("""
                    UPDATE VirtualPosition SET quantity = ?, avgPrice = ?, peakPrice = ?, updatedAt = ?
                    WHERE accountId = ? AND symbol = ?
                """, (new_qty, new_avg, new_peak, now_ms, account_id, symbol))
            else:
                pos_id = str(uuid.uuid4())
                peak = max(filled, price)
                con.execute("""
                    INSERT INTO VirtualPosition (id, accountId, symbol, name, quantity, avgPrice, peakPrice, openedAt, updatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (pos_id, account_id, symbol, name, qty, filled, peak, now_ms, now_ms))

            con.commit()
            return order_id
        except Exception as e:
            con.rollback()
            logger.error("[VirtualTrader] 매수 DB 오류 %s %s: %s", account_id, symbol, e)
            return None
        finally:
            con.close()

    def _execute_sell(
        self,
        account_id: str,
        symbol: str,
        name: str,
        price: int,
        quantity: int,
        avg_buy_price: float,
    ) -> Optional[str]:
        filled = _filled_price(price, "SELL")
        fee = _fee(filled, quantity)
        tax = _tax(filled, quantity)
        proceeds = _sell_proceeds(filled, quantity)
        pnl = _realized_pnl(filled, avg_buy_price, quantity, fee, tax)

        order_id = str(uuid.uuid4())
        now_ms = _now_ms()

        con = sqlite3.connect(self._db)
        try:
            con.execute("""
                INSERT INTO VirtualOrder (id, accountId, symbol, name, side, type, quantity, price, filledPrice, fee, tax, avgBuyPrice, realizedPnl, status, filledAt, createdAt)
                VALUES (?, ?, ?, ?, 'SELL', 'MARKET', ?, ?, ?, ?, ?, ?, ?, 'FILLED', ?, ?)
            """, (order_id, account_id, symbol, name, quantity, price, filled, fee, tax, avg_buy_price, pnl, now_ms, now_ms))

            con.execute("""
                UPDATE VirtualAccount SET currentCash = currentCash + ?, updatedAt = ? WHERE id = ?
            """, (proceeds, now_ms, account_id))

            pos = con.execute(
                "SELECT quantity FROM VirtualPosition WHERE accountId = ? AND symbol = ?",
                (account_id, symbol)
            ).fetchone()

            if pos:
                new_qty = pos[0] - quantity
                if new_qty <= 0:
                    con.execute(
                        "DELETE FROM VirtualPosition WHERE accountId = ? AND symbol = ?",
                        (account_id, symbol)
                    )
                else:
                    con.execute(
                        "UPDATE VirtualPosition SET quantity = ?, updatedAt = ? WHERE accountId = ? AND symbol = ?",
                        (new_qty, now_ms, account_id, symbol)
                    )

            con.commit()
            return order_id
        except Exception as e:
            con.rollback()
            logger.error("[VirtualTrader] 매도 DB 오류 %s %s: %s", account_id, symbol, e)
            return None
        finally:
            con.close()

    def _fill_pending_order(self, account_id: str, order: dict, current_price: int):
        side = order["side"]
        qty = order["quantity"]
        filled = order["price"]  # 지정가로 체결
        fee = _fee(int(filled), qty)
        now_ms = _now_ms()

        con = sqlite3.connect(self._db)
        try:
            # 다른 체결 경로(브라우저 fill 라우트)와의 이중 체결 방지:
            # status='PENDING' 조건부 UPDATE로 원자적으로 선점하고, 실패하면 아무것도 하지 않는다.
            con.execute("BEGIN IMMEDIATE")

            if side == "BUY":
                claimed = con.execute("""
                    UPDATE VirtualOrder SET status = 'FILLED', filledPrice = ?, fee = ?, filledAt = ?
                    WHERE id = ? AND status = 'PENDING'
                """, (filled, fee, now_ms, order["id"])).rowcount
                if not claimed:
                    con.rollback()
                    return

                existing = con.execute(
                    "SELECT quantity, avgPrice, peakPrice FROM VirtualPosition WHERE accountId = ? AND symbol = ?",
                    (account_id, order["symbol"])
                ).fetchone()

                if existing:
                    new_qty = existing[0] + qty
                    new_avg = (existing[1] * existing[0] + filled * qty) / new_qty
                    new_peak = max(existing[2] or new_avg, current_price)
                    con.execute("""
                        UPDATE VirtualPosition SET quantity = ?, avgPrice = ?, currentPrice = ?, peakPrice = ?, updatedAt = ?
                        WHERE accountId = ? AND symbol = ?
                    """, (new_qty, new_avg, current_price, new_peak, now_ms, account_id, order["symbol"]))
                else:
                    pos_id = str(uuid.uuid4())
                    peak = max(int(filled), current_price)
                    con.execute("""
                        INSERT INTO VirtualPosition (id, accountId, symbol, name, quantity, avgPrice, currentPrice, peakPrice, openedAt, updatedAt)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (pos_id, account_id, order["symbol"], order.get("name") or order["symbol"],
                          qty, filled, current_price, peak, now_ms, now_ms))

            else:  # SELL
                pos = con.execute(
                    "SELECT quantity, avgPrice FROM VirtualPosition WHERE accountId = ? AND symbol = ?",
                    (account_id, order["symbol"])
                ).fetchone()
                if not pos or pos[0] < qty:
                    # 보유 수량 부족 → 주문 취소 (fill 라우트와 동일한 처리)
                    con.execute(
                        "UPDATE VirtualOrder SET status = 'CANCELLED' WHERE id = ? AND status = 'PENDING'",
                        (order["id"],)
                    )
                    con.commit()
                    return

                avg_buy = pos[1]
                tax = _tax(int(filled), qty)
                proceeds = _sell_proceeds(int(filled), qty)
                pnl = _realized_pnl(int(filled), avg_buy, qty, fee, tax)

                claimed = con.execute("""
                    UPDATE VirtualOrder SET status = 'FILLED', filledPrice = ?, fee = ?, tax = ?,
                    avgBuyPrice = ?, realizedPnl = ?, filledAt = ? WHERE id = ? AND status = 'PENDING'
                """, (filled, fee, tax, avg_buy, pnl, now_ms, order["id"])).rowcount
                if not claimed:
                    con.rollback()
                    return

                con.execute("""
                    UPDATE VirtualAccount SET currentCash = currentCash + ?, updatedAt = ? WHERE id = ?
                """, (proceeds, now_ms, account_id))

                new_qty = pos[0] - qty
                if new_qty <= 0:
                    con.execute(
                        "DELETE FROM VirtualPosition WHERE accountId = ? AND symbol = ?",
                        (account_id, order["symbol"])
                    )
                else:
                    con.execute(
                        "UPDATE VirtualPosition SET quantity = ?, updatedAt = ? WHERE accountId = ? AND symbol = ?",
                        (new_qty, now_ms, account_id, order["symbol"])
                    )

            con.commit()
        except Exception as e:
            con.rollback()
            logger.error("[VirtualTrader] pending fill 오류 %s: %s", order["id"], e)
        finally:
            con.close()

    def _count_positions(self, account_id: str) -> int:
        con = sqlite3.connect(self._db)
        try:
            row = con.execute(
                "SELECT COUNT(*) FROM VirtualPosition WHERE accountId = ?", (account_id,)
            ).fetchone()
            return row[0] if row else 0
        finally:
            con.close()

    def _update_positions(self, account_id: str, price_map: dict[str, int], quotes: dict):
        con = sqlite3.connect(self._db)
        now_ms = _now_ms()
        try:
            positions = con.execute(
                "SELECT symbol, peakPrice, avgPrice FROM VirtualPosition WHERE accountId = ?", (account_id,)
            ).fetchall()
            for sym, peak, avg in positions:
                price = price_map.get(sym, 0)
                if not price:
                    continue
                # high가 있으면 peakPrice 갱신에 사용
                q = quotes.get(sym)
                high = q.high if q and q.high else price
                new_peak = max(peak or avg, high)
                con.execute("""
                    UPDATE VirtualPosition SET currentPrice = ?, peakPrice = ?, updatedAt = ?
                    WHERE accountId = ? AND symbol = ?
                """, (price, new_peak, now_ms, account_id, sym))
            con.commit()
        except Exception as e:
            con.rollback()
            logger.error("[VirtualTrader] 포지션 갱신 오류 %s: %s", account_id, e)
        finally:
            con.close()

    def _update_last_refreshed(self, account_id: str, today: str):
        con = sqlite3.connect(self._db)
        now_ms = _now_ms()
        try:
            con.execute("""
                UPDATE VirtualMarketState SET lastRefreshed = ?, updatedAt = ? WHERE accountId = ?
            """, (today, now_ms, account_id))
            con.commit()
        finally:
            con.close()

    def _log_signal(
        self,
        account_id: str,
        date: str,
        symbol: str,
        price: float,
        signal_type: str,
        reason: Optional[str],
        action: str,
        order_id: Optional[str],
        stock_name: Optional[str] = None,
    ):
        log_id = str(uuid.uuid4())
        now_ms = _now_ms()
        con = sqlite3.connect(self._db)
        try:
            con.execute("""
                INSERT INTO VirtualMarketLog (id, accountId, date, symbol, stockName, signalType, reason, price, action, orderId, createdAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, account_id, date, symbol, stock_name, signal_type, reason, price, action, order_id, now_ms))
            con.commit()
        except Exception as e:
            logger.error("[VirtualTrader] 로그 기록 오류: %s", e)
        finally:
            con.close()
