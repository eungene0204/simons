"""
VirtualTrader — FastAPI 백그라운드 자동매매 엔진

장중(한국 계좌 KST 09:00~15:30 · 미국 계좌 ET 09:30~16:00, 평일) 30초 간격으로:
  1. running 상태의 가상계좌 조회 (SQLite)
  2. 전략 조건 파싱 (Strategy.settings JSON)
  3. 실시간 시세 조회 (MarketDataProvider)
  4. 시그널 평가 (SignalEngine)
  5. 리스크 관리 (SL / TP / 트레일링스톱 / 최대보유일)
  6. 자동매매 실행 + 로그 기록 (SQLite 직접 기록)
  7. 포지션 현재가 / peakPrice 갱신
"""

import asyncio
import copy
import json
import logging
import math
import time
import uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

import db as appdb  # 공용 앱 DB 어댑터(Supabase Postgres)
from engine import virtual_scheduled_orders as vso
from engine import virtual_contributions as vcontrib
from engine.contributions import contribution_settings

from engine import trade_reason as tr
from engine import us_market_calendar
from engine.universe_pit import is_us_symbol
from engine.live_signal_utils import (
    count_holding_sessions,
    evaluate_live_strategy_signals,
    resolve_live_universe,
)
from engine.listing_status import (
    ListingStatus, is_buy_allowed, is_sell_allowed, write_audit_log,
    get_stock_listing_status, get_stocks_by_status, sync_trading_halt,
)

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────
_KST = timezone(timedelta(hours=9))
# 미국 동부 — 서머타임(DST)이 있어 고정 오프셋으로 대체할 수 없다.
_ET = ZoneInfo("America/New_York")
REFRESH_INTERVAL = 30          # 장중 시그널 평가 간격 (초)
HALT_RESUME_SWEEP_INTERVAL = 600  # 거래정지 종목 재개 감지 스윕 간격 (초)

FEE_RATE = 0.00015             # 수수료 0.015%
TAX_RATE = 0.0015              # 증권거래세 0.15% (2025년~, 백테스트 엔진 기본값과 동일)
MARKET_SLIPPAGE = 0.0005       # 시장가 슬리피지 0.05%
# [통화, 2026-08-26] 미국 종목(USD 계좌)은 달러 정산 규칙을 쓴다 — 호가 $0.01(소수 유지),
# 증권거래세 0(백테스트 엔진 US 레인과 동일 계약), 수수료 동률에 센트 절사.
# 판정은 심볼 형태(universe_pit.is_us_symbol)다 — 통화 격리 가드로 계좌 통화와 일치한다.


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


def _filled_price(price: float, side: str, us: bool = False) -> float:
    raw = price * (1 + MARKET_SLIPPAGE) if side == "BUY" else price * (1 - MARKET_SLIPPAGE)
    if us:
        return max(0.01, round(raw, 2))  # 센트 단위, 정수 절사 금지
    return _round_tick(max(1, raw))


def _fee(filled: float, qty: int, us: bool = False) -> float:
    if us:
        return math.floor(filled * qty * FEE_RATE * 100) / 100  # 센트 절사
    return math.floor(filled * qty * FEE_RATE)


def _tax(filled: float, qty: int, us: bool = False) -> float:
    if us:
        return 0.0  # 미국 시장에는 증권거래세(매도세)가 없다
    return math.floor(filled * qty * TAX_RATE)


def _buy_cost(filled: float, qty: int, us: bool = False) -> float:
    return filled * qty + _fee(filled, qty, us)


def _sell_proceeds(filled: float, qty: int, us: bool = False) -> float:
    return filled * qty - _fee(filled, qty, us) - _tax(filled, qty, us)


def _realized_pnl(sell_price: float, avg_buy: float, qty: int, fee: float, tax: float) -> float:
    return (sell_price - avg_buy) * qty - fee - tax


def _price_display(price: float, symbol: str) -> str:
    """사유 문구용 가격 표기 — 한국은 원 단위 정수, 미국은 달러 소수점 유지."""
    if is_us_symbol(str(symbol)):
        return f"${price:,.2f}"
    return f"{int(price):,}원"


def _merge_exit_reason(existing: Optional[str], reason: str) -> str:
    """청산 사유 둘을 하나의 세그먼트 페이로드로 잇는다(" + " 구분).

    엔진의 조건 사유는 인코딩된 세그먼트 문자열이라, 문자열 덧셈으로 이으면 페이로드가
    깨져 프론트가 디코딩하지 못하고 원문 JSON이 카드에 노출된다(2026-09-13 사고)."""
    if not existing:
        return reason
    return tr.encode(tr.join(
        [tr.segments_of(existing), tr.segments_of(reason)], [tr.SEP_AND]
    ))


def _coerce_numeric(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _db_now() -> datetime:
    """DateTime 컬럼에 넣을 tz-aware 현재시각(UTC). (Postgres timestamp — psycopg가 native 처리)"""
    return datetime.now(timezone.utc)


def _parse_db_datetime(value) -> Optional[datetime]:
    """DateTime 컬럼 값 파싱 — Postgres(datetime)·구 SQLite(epoch ms 정수)·ISO 문자열 모두 지원."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
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

def _is_market_hours(now: Optional[datetime] = None) -> bool:
    """한국(KRX) 정규장 — 평일 09:00~15:30 KST. now는 테스트 주입용."""
    now = now.astimezone(_KST) if now is not None else datetime.now(_KST)
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return 900 <= t <= 1530


def _is_us_market_hours(now: Optional[datetime] = None) -> bool:
    """미국 정규장 — 평일 09:30~16:00 ET(서머타임 자동 반영). now는 테스트 주입용.

    미국 계좌(USD)의 자동매매는 이 시간에만 돈다(2026-08-26). 종전에는 루프 전체가
    KST 게이트라 미국 계좌는 시세가 갱신되지 않는 시간에만 깨어 사실상 거래가
    일어나지 않았다. 프리마켓·애프터마켓은 제외한다 — 시세 소스(토스 US)가 주간거래
    시각을 별도 규약으로 다루고, 백테스트(정규장 종가 기준)와 눈높이를 맞춘다.
    휴장일·조기 종료일은 토스 공식 장 운영 달력(engine/us_market_calendar)이 정본이다
    — 공휴일이면 정규장 세션이 null로 오고, 조기 종료일(추수감사절 다음날 등)은
    종료 시각이 13:00 ET로 내려와 그대로 반영된다. 달력 조회가 실패하면(자격증명·
    네트워크) 아래 고정 규칙으로 진행한다(fail-open) — 달력 장애로 자동매매가 조용히
    멈추는 편이 더 나쁘고, 휴장일 오작동은 시세 신선도 방어(_fresh_price_map)가 막는다.
    """
    now = now.astimezone(_ET) if now is not None else datetime.now(_ET)
    calendar_says = us_market_calendar.is_open(now)
    if calendar_says is not None:
        return calendar_says
    if now.weekday() >= 5:
        return False
    t = now.hour * 100 + now.minute
    return 930 <= t <= 1600


def _account_is_usd(account: dict) -> bool:
    """계좌 통화가 USD인가 — 시장 시간·거래일 판정의 정본(VirtualAccount.currency)."""
    return (account.get("currency") or "KRW") == "USD"


def _market_now(account: dict) -> datetime:
    """계좌 시장의 현재 시각 — 거래일(today) 산출 기준."""
    return datetime.now(_ET if _account_is_usd(account) else _KST)


def _account_market_open(account: dict, now: Optional[datetime] = None) -> bool:
    return (
        _is_us_market_hours(now) if _account_is_usd(account) else _is_market_hours(now)
    )


def _is_strategy_execution_window(
    execution_timing: str,
    account: Optional[dict] = None,
    now: Optional[datetime] = None,
) -> bool:
    """전략 시그널을 집행하는 시각 창 — 계좌 시장의 시계로 판정한다.

    한국 계좌: next_open=09:00~09:05 KST, current_close=15:30 KST.
    미국 계좌: next_open=개장 후 5분, current_close=정규장 종료 분(ET) —
    [2026-09-05] 종전에는 KST 고정이라 미국 계좌는 자기 장중(KST 밤~새벽)에
    이 창을 한 번도 지나지 못해 전략 매수·매도 시그널이 매 틱 전부 지워졌다
    (리스크 청산·지정가 체결만 살아 있었다).
    """
    if account is not None and _account_is_usd(account):
        return _is_us_strategy_execution_window(execution_timing, now)
    now = now.astimezone(_KST) if now is not None else datetime.now(_KST)
    t = now.hour * 100 + now.minute
    if execution_timing == "current_close":
        return t == 1530
    return 900 <= t <= 905


def _is_us_strategy_execution_window(
    execution_timing: str, now: Optional[datetime] = None
) -> bool:
    """미국 계좌의 집행 창(ET). 조기 종료일은 달력의 종료 시각(13:00 ET 등)을 따른다."""
    now = now.astimezone(_ET) if now is not None else datetime.now(_ET)
    session = us_market_calendar.regular_session(now)
    if session is not None:
        start, end = session
    else:
        start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    minute = now.replace(second=0, microsecond=0)
    if execution_timing == "current_close":
        return minute == end.replace(second=0, microsecond=0)
    return start <= minute <= start + timedelta(minutes=5)


# 정기 납입 매수의 사유(회차 종류별) — VirtualMarketLog.reason에 세그먼트로 실린다.
CONTRIBUTION_REASON = {
    vcontrib.START: tr.CONTRIBUTION_START_BUY,
    vcontrib.DEPOSIT: tr.CONTRIBUTION_DEPOSIT_BUY,
    vcontrib.CAPPED: tr.CONTRIBUTION_CAPPED_BUY,
}


def _contribution_plan(dsl: dict, entry_group: dict, exit_group: dict, risk: dict,
                       account_id: str) -> Optional[tuple]:
    """전략의 정액 적립 계획 (납입액, 주기). 없거나 계산할 수 없는 조합이면 None.

    백테스트 엔진과 같은 계약이다(backtest_engine._run_contribution_backtest) — 지정 종목 전략에서만,
    매수·매도 조건·랭킹·손절과 섞이지 않았을 때만 납입한다. 섞인 전략에 조용히 돈을 넣으면
    백테스트에 없던 계좌가 된다.
    """
    try:
        plan = contribution_settings(risk)
    except ValueError as e:
        logger.warning("[VirtualTrader] 계좌 %s: 적립 설정을 읽을 수 없어 납입하지 않습니다 — %s", account_id, e)
        return None
    if plan is None:
        return None
    mixed = (
        entry_group.get("conditions") or exit_group.get("conditions") or risk.get("ranking_metric")
        or any(_coerce_numeric(risk.get(k)) > 0 for k in (
            "stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_holding_days"))
    )
    if dsl.get("backtest_mode") != "single_asset" or mixed:
        logger.warning("[VirtualTrader] 계좌 %s: 조건·랭킹·손절과 섞인 적립 설정은 납입하지 않습니다", account_id)
        return None
    return plan


def _fresh_price_map(quotes: dict, today: str) -> dict[str, float]:
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
        self._last_halt_sweep: Optional[float] = None  # time.monotonic() 기준
        self._daily_signal_cache: dict[tuple[str, str, str], list[dict]] = {}

    # ── 생명주기 ──────────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[VirtualTrader] 시작 (간격: %ds)", REFRESH_INTERVAL)

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
                kr_open = _is_market_hours()
                if kr_open:
                    # 거래정지 재개 스윕은 KRX 전용 관심사(KIS 종목상태코드)다.
                    await self._sweep_suspended_resume()
                if kr_open or _is_us_market_hours():
                    # 계좌별로 자기 시장의 개장 여부를 다시 본다(_refresh_all).
                    await self._refresh_all()
                else:
                    logger.debug("[VirtualTrader] 장외 시간(한국·미국 모두), 대기")
            except Exception as e:
                logger.error("[VirtualTrader] 루프 예외: %s", e, exc_info=True)
            await asyncio.sleep(REFRESH_INTERVAL)

    async def _sweep_suspended_resume(self):
        """TRADING_SUSPENDED 종목의 거래 재개를 감지해 NORMAL로 복원한다.

        재개 감지는 시세의 거래정지 플래그(sync_trading_halt)로만 이뤄지는데,
        정지 종목이 모든 계좌의 추적 목록에서 빠지면(filterMonitorableSymbols가 차단)
        시세를 아무도 조회하지 않아 영원히 정지 상태로 남는다 — 이를 주기 스윕으로 보정.
        """
        now = time.monotonic()
        if self._last_halt_sweep is not None and now - self._last_halt_sweep < HALT_RESUME_SWEEP_INTERVAL:
            return
        self._last_halt_sweep = now

        suspended = await asyncio.to_thread(get_stocks_by_status, ListingStatus.TRADING_SUSPENDED)
        symbols = [s["symbol"] for s in suspended]
        if not symbols:
            return

        quotes = await self._mdp.get_prices(symbols)
        halt_flags = {
            sym: q.trading_halted
            for sym, q in quotes.items()
            if getattr(q, "trading_halted", None) is not None
        }
        if halt_flags:
            changed = await asyncio.to_thread(sync_trading_halt, halt_flags)
            if changed:
                logger.info("[VirtualTrader] 거래정지 재개 스윕: %s", changed)

    async def _refresh_all(self):
        """running 상태 계좌 전체 순회"""
        accounts = await asyncio.to_thread(self._fetch_running_accounts)
        if not accounts:
            return
        # 자기 시장이 열린 계좌만 돈다 — 미국 계좌는 ET 정규장, 한국 계좌는 KST 정규장.
        accounts = [a for a in accounts if _account_market_open(a)]
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
        con = appdb.connect()
        try:
            rows = con.execute("""
                SELECT
                    a.id, a."currentCash", a."strategyId", a."tradingMode", a.currency,
                    s.symbols, s.id AS "stateId"
                FROM "VirtualMarketState" s
                JOIN "VirtualAccount" a ON a.id = s."accountId"
                WHERE s.status = 'running'
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def _fetch_strategy(self, strategy_id: str) -> Optional[dict]:
        con = appdb.connect()
        try:
            row = con.execute('SELECT settings FROM "Strategy" WHERE id = ?', (strategy_id,)).fetchone()
            if row:
                return json.loads(row["settings"])
            return None
        finally:
            con.close()

    def _fetch_positions(self, account_id: str) -> list[dict]:
        con = appdb.connect()
        try:
            rows = con.execute(
                'SELECT * FROM "VirtualPosition" WHERE "accountId" = ?', (account_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def _fetch_pending_orders(self, account_id: str) -> list[dict]:
        con = appdb.connect()
        try:
            rows = con.execute(
                'SELECT * FROM "VirtualOrder" WHERE "accountId" = ? AND status = \'PENDING\'',
                (account_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()

    def _fetch_scheduled_orders(self, account_id: str) -> list[dict]:
        """미집행 예약 주문(신호 후 N거래일 지연 체결 큐)."""
        return vso.fetch_open(account_id)

    def _fetch_today_logs(self, account_id: str, today: str) -> set[str]:
        """오늘 기록된 (symbol_signalType_action) 집합 반환 — 하루 1회 중복 방지용"""
        con = appdb.connect()
        try:
            rows = con.execute(
                'SELECT symbol, "signalType", action FROM "VirtualMarketLog" '
                "WHERE \"accountId\" = ? AND date = ? AND action IN ('auto_executed', 'notified')",
                (account_id, today),
            ).fetchall()
            return {f"{r['symbol']}_{r['signalType']}_{r['action']}" for r in rows}
        finally:
            con.close()

    def _fetch_current_cash(self, account_id: str) -> float:
        con = appdb.connect()
        try:
            row = con.execute('SELECT "currentCash" FROM "VirtualAccount" WHERE id = ?', (account_id,)).fetchone()
            return row[0] if row else 0.0
        finally:
            con.close()

    def _fetch_stock_names(self, symbols: list[str]) -> dict[str, str]:
        """Stock 테이블에서 종목명 조회. 없으면 symbol을 fallback으로 사용."""
        if not symbols:
            return {}
        con = None
        try:
            con = appdb.connect()
            placeholders = ",".join("?" * len(symbols))
            rows = con.execute(
                f'SELECT symbol, name FROM "Stock" WHERE symbol IN ({placeholders})',
                symbols,
            ).fetchall()
            result = {r[0]: r[1] for r in rows if r[1]}
            missing = [symbol for symbol in symbols if symbol not in result]
            if missing:
                from engine.universe_pit import etf_name_map, us_name_map
                result.update(etf_name_map(missing))
                result.update(us_name_map([s for s in missing if is_us_symbol(s)]))
            return result
        except Exception:
            return {}
        finally:
            if con is not None:
                con.close()

    def _fetch_delisting_policy(self, account_id: str) -> str:
        """계좌의 상장폐지 처리 정책 조회. 기본 AUTO_LIQUIDATE."""
        con = None
        try:
            con = appdb.connect()
            row = con.execute(
                'SELECT "delistingPolicy" FROM "VirtualAccount" WHERE id = ?', (account_id,)
            ).fetchone()
            return row[0] if row and row[0] else "AUTO_LIQUIDATE"
        except Exception:
            return "AUTO_LIQUIDATE"
        finally:
            if con is not None:
                con.close()

    # ── 계좌 새로고침 ─────────────────────────────────────────────────────────

    async def _refresh_account(self, account: dict):
        account_id = account["id"]
        trading_mode = account["tradingMode"]
        symbols: list[str] = json.loads(account["symbols"])
        strategy_id = account["strategyId"]
        # 거래일은 계좌 시장의 날짜다 — 시세 날짜 대조(_fresh_price_map)·일일 로그
        # dedupe·시그널 캐시가 모두 이 값을 쓴다. 미국 계좌에 KST 날짜를 쓰면
        # 미국 장중(= KST 밤~새벽, 날짜가 하루 앞섬)에 모든 시세가 스테일로 걸러진다.
        today = _market_now(account).strftime("%Y-%m-%d")

        # 1. 전략 조건 파싱
        entry_group = {}
        exit_group = {}
        risk = {}
        position_size_pct = 10
        max_positions = 5
        stop_loss_pct = 0.0
        take_profit_pct = 0.0
        trailing_stop_pct = 0.0
        max_holding_days = 0
        dsl = {}

        if strategy_id:
            dsl = await asyncio.to_thread(self._fetch_strategy, strategy_id) or {}
            if dsl:
                entry_group = dsl.get("entry") or {}
                exit_group = dsl.get("exit") or {}
                risk = dsl.get("risk") or {}
                position_size_pct = _coerce_numeric(risk.get("position_size_pct"), 10.0)
                max_positions = int(_coerce_numeric(risk.get("max_positions"), 5.0))
                stop_loss_pct = _coerce_numeric(risk.get("stop_loss_pct"))
                take_profit_pct = _coerce_numeric(risk.get("take_profit_pct"))
                trailing_stop_pct = _coerce_numeric(risk.get("trailing_stop_pct"))
                max_holding_days = int(_coerce_numeric(risk.get("max_holding_days")))

        # 2. Resolve the actual strategy universe independently from display symbols.
        positions = await asyncio.to_thread(self._fetch_positions, account_id)
        pending_orders = await asyncio.to_thread(self._fetch_pending_orders, account_id)
        execution_timing = risk.get("execution_timing") or "next_open"
        # 신호 후 N거래일 지연 체결(백테스트 execution_delay_days와 같은 뜻) — 자동매매는 예약 주문
        # 큐(engine/virtual_scheduled_orders.py)로 대응한다. 지연 1(기본)이면 종전과 같이 즉시 집행.
        execution_delay_days = max(1, int(_coerce_numeric(risk.get("execution_delay_days"), 1.0)))
        delay_queue_active = execution_timing == "next_open" and execution_delay_days > 1
        scheduled_orders = (
            await asyncio.to_thread(self._fetch_scheduled_orders, account_id) if strategy_id else []
        )
        signal_symbols = await asyncio.to_thread(resolve_live_universe, dsl, symbols)
        # [통화 격리, 2026-08-26] 자동매매는 주문 라우트를 거치지 않고 DB에 직접 쓰므로
        # 같은 가드를 여기서 건다 — 계좌 통화와 다른 시장의 종목은 **매수 후보에서**
        # 제외한다(환율 변환이 없어 잔고·손익이 무의미해진다). 보유 포지션은 손대지
        # 않는다: 리스크 청산·전략 매도가 계속 동작해야 한다(TS 가드와 같은 계약).
        _want_us = _account_is_usd(account)
        _cross = [s for s in signal_symbols if is_us_symbol(s) != _want_us]
        if _cross:
            signal_symbols = [s for s in signal_symbols if is_us_symbol(s) == _want_us]
            logger.warning(
                "[VirtualTrader] 계좌 %s(%s): 통화가 다른 종목 %d개를 매수 후보에서 제외(%s…)",
                account_id, "USD" if _want_us else "KRW", len(_cross), ", ".join(_cross[:3]),
            )

        # 정액 적립식 — 납입 계획이 있으면 지정 종목은 신호가 없어도 납입일에 산다.
        contribution_plan = _contribution_plan(dsl, entry_group, exit_group, risk, account_id)

        # next_open signals depend only on completed bars, so evaluate the full universe
        # once per day before requesting live prices for actionable symbols.
        if execution_timing == "next_open":
            strategy_key = json.dumps(dsl, sort_keys=True, ensure_ascii=True)
            cache_key = (account_id, today, strategy_key)
            cached = self._daily_signal_cache.get(cache_key)
            if cached is None:
                cached = await asyncio.to_thread(
                    self._evaluate_signals,
                    signal_symbols,
                    entry_group,
                    exit_group,
                    risk,
                    {},
                    today,
                )
                self._daily_signal_cache = {
                    key: value
                    for key, value in self._daily_signal_cache.items()
                    if key[1] == today
                }
                self._daily_signal_cache[cache_key] = copy.deepcopy(cached)
            signals = copy.deepcopy(cached)
            actionable = [
                signal["symbol"] for signal in signals
                if signal.get("entry_signal") or signal.get("exit_signal")
            ]
            quote_symbols = list(dict.fromkeys(
                actionable
                + (signal_symbols if contribution_plan else [])
                + [p["symbol"] for p in positions]
                + [order["symbol"] for order in pending_orders]
                + [order["symbol"] for order in scheduled_orders]
            ))
        else:
            quote_symbols = list(dict.fromkeys(
                signal_symbols
                + [p["symbol"] for p in positions]
                + [order["symbol"] for order in pending_orders]
                + [order["symbol"] for order in scheduled_orders]
            ))

        # 2.5. Fetch live prices only after next_open candidates have been selected.
        quotes = await self._mdp.get_prices(quote_symbols)

        # 2.6. 거래정지 플래그(KIS 종목상태코드 58) → Stock.listingStatus 동기화
        #      DART 공시 폴링이 놓친 거래정지 종목을 시세 경로에서 자동 보정한다.
        halt_flags = {
            sym: q.trading_halted
            for sym, q in quotes.items()
            if getattr(q, "trading_halted", None) is not None
        }
        if halt_flags:
            halt_changed = await asyncio.to_thread(sync_trading_halt, halt_flags)
            if halt_changed:
                logger.info("[VirtualTrader] 거래정지 상태 동기화: %s", halt_changed)

        price_map: dict[str, float] = _fresh_price_map(quotes, today)
        if quotes and not price_map:
            logger.debug("[VirtualTrader] 계좌 %s: 오늘(%s) 시세 없음 — 휴장일 또는 스테일 데이터, 매매 보류", account_id, today)
        name_map: dict[str, str] = await asyncio.to_thread(self._fetch_stock_names, quote_symbols)

        # current_close signals require today's live quote in the indicator row.
        if execution_timing != "next_open":
            signals = await asyncio.to_thread(
                self._evaluate_signals,
                signal_symbols,
                entry_group,
                exit_group,
                risk,
                quotes,
                today,
            )

        strategy_execution_allowed = _is_strategy_execution_window(execution_timing, account)
        if not strategy_execution_allowed:
            for signal in signals:
                signal["entry_signal"] = False
                signal["exit_signal"] = False

        # 3.4 정액 적립식 — 체결 창이고 오늘 시세가 있으면(=거래일) 새 납입 주기인지 보고 입금·매수한다.
        if contribution_plan and trading_mode == "auto" and strategy_execution_allowed and price_map:
            await asyncio.to_thread(
                self._run_contribution, account_id, contribution_plan, signal_symbols,
                today, price_map, name_map,
            )

        # Ranking portfolios replace their target set only on configured rebalance days.
        ranking_rebalance = (
            risk.get("ranking_metric") == "return"
            and strategy_execution_allowed
            and (risk.get("rebalancing_period") or "none") != "none"
            and any(signal.get("rebalance_due") for signal in signals)
            and any(signal.get("ranking_ready") for signal in signals)
        )
        if ranking_rebalance:
            target_symbols = {
                signal["symbol"] for signal in signals if signal.get("entry_signal")
            }
            for pos in positions:
                if pos["symbol"] in target_symbols:
                    continue
                signal = next(
                    (item for item in signals if item["symbol"] == pos["symbol"]),
                    None,
                )
                if signal is None:
                    signal = {
                        "symbol": pos["symbol"],
                        "entry_signal": False,
                        "exit_signal": False,
                    }
                    signals.append(signal)
                signal["exit_signal"] = True
                signal["exit_reason"] = tr.encode([tr.part(tr.REBALANCE_DROPOUT)])

        # 3.5. 신호 후 N거래일 지연 체결: 전략 신호(진입·매도·리밸런싱 편출)는 바로 집행하지 않고
        #      예약 주문 큐에 넣는다. 아래 리스크 청산·강제청산은 큐를 거치지 않는다(백테스트와 동일).
        #      같은 계좌·종목·방향의 미집행 예약이 있거나 이미 보유(매수)/미보유(매도)면 만들지 않는다.
        if delay_queue_active:
            open_sides = {(o["symbol"], o["side"]) for o in scheduled_orders}
            held_symbols = {p["symbol"] for p in positions}
            for sig in signals:
                sym = sig["symbol"]
                for flag, side, stype, reason_key in (
                    ("entry_signal", "BUY", "entry", "entry_reason"),
                    ("exit_signal", "SELL", "exit", "exit_reason"),
                ):
                    if not sig.get(flag):
                        continue
                    sig[flag] = False
                    held = sym in held_symbols
                    if (side == "BUY" and held) or (side == "SELL" and not held) or (sym, side) in open_sides:
                        continue
                    stock_name = name_map.get(sym) or sym
                    new_id = await asyncio.to_thread(
                        vso.enqueue, account_id, strategy_id, sym, stock_name, side, stype,
                        today, execution_delay_days, sig.get(reason_key),
                    )
                    if new_id:
                        open_sides.add((sym, side))
                        await asyncio.to_thread(
                            self._log_signal, account_id, today, sym, price_map.get(sym, 0),
                            stype, sig.get(reason_key), "scheduled", None, stock_name,
                        )
                        logger.info("[VirtualTrader] 예약 %s %s %s (지연 %d거래일)", account_id, side, sym, execution_delay_days)

        # 4. 리스크 관리
        risk_exits: dict[str, str] = {}
        for pos in positions:
            current_price = price_map.get(pos["symbol"], 0)
            if not current_price:
                continue
            avg = pos["avgPrice"]
            pnl_pct = (current_price - avg) / avg * 100

            if stop_loss_pct > 0 and pnl_pct <= -stop_loss_pct:
                risk_exits[pos["symbol"]] = tr.encode([tr.part(
                    tr.LIVE_STOP_LOSS, f"{pnl_pct:.1f}", stop_loss_pct
                )])
                continue
            if take_profit_pct > 0 and pnl_pct >= take_profit_pct:
                risk_exits[pos["symbol"]] = tr.encode([tr.part(
                    tr.LIVE_TAKE_PROFIT, f"{pnl_pct:.1f}", take_profit_pct
                )])
                continue
            if trailing_stop_pct > 0:
                peak = pos.get("peakPrice") or avg
                dd_pct = (current_price - peak) / peak * 100
                if dd_pct <= -trailing_stop_pct:
                    # 최고가는 금액 인자(money) — 통화 표기는 렌더러가 계좌 통화로 만든다.
                    risk_exits[pos["symbol"]] = tr.encode([tr.part(
                        tr.LIVE_TRAILING_STOP, peak, f"{dd_pct:.1f}", money=[0]
                    )])
                    continue
            if max_holding_days > 0:
                opened_dt = _parse_db_datetime(pos.get("openedAt"))
                if opened_dt is not None:
                    holding_days = await asyncio.to_thread(
                        count_holding_sessions,
                        self._loader,
                        pos["symbol"],
                        opened_dt,
                        today,
                        quotes.get(pos["symbol"]),
                    )
                    if holding_days >= max_holding_days:
                        risk_exits[pos["symbol"]] = tr.encode([tr.part(
                            tr.LIVE_MAX_HOLDING, holding_days, max_holding_days
                        )])

        # 리스크 종료를 시그널에 병합
        for sym, reason in risk_exits.items():
            found = next((s for s in signals if s["symbol"] == sym), None)
            if found:
                found["exit_signal"] = True
                found["exit_reason"] = _merge_exit_reason(found.get("exit_reason"), reason)
            else:
                price = price_map.get(sym, 0)
                signals.append({"symbol": sym, "close": price, "entry_signal": False, "exit_signal": True, "exit_reason": reason})

        # 4.5. 상장 상태 체크: 거래 제한 + 강제청산 (보유 포지션 종목 포함)
        delistingPolicy = await asyncio.to_thread(self._fetch_delisting_policy, account_id)
        status_map: dict[str, str] = {}
        for sym in quote_symbols:
            try:
                status = await asyncio.to_thread(get_stock_listing_status, sym)
            except Exception as error:
                logger.debug("[VirtualTrader] listing status unavailable %s: %s", sym, error)
                status = ListingStatus.NORMAL
            status_map[sym] = status
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
                        sig["exit_reason"] = tr.encode([tr.part(tr.LIVE_FORCED_LIQUIDATION, status)])
                    else:
                        price = price_map.get(sym, 0)
                        signals.append({
                            "symbol": sym, "close": price,
                            "entry_signal": False, "exit_signal": True,
                            "exit_reason": tr.encode([tr.part(tr.LIVE_FORCED_LIQUIDATION, status)]),
                        })
                    logger.info("[VirtualTrader] 강제청산 예약 %s %s (상태: %s)", account_id, sym, status)

            # TRADING_SUSPENDED: 매도도 차단 (DB에서 강제청산 불가)
            if status == ListingStatus.TRADING_SUSPENDED:
                if sig:
                    sig["exit_signal"] = False
                    sig["entry_signal"] = False

        executed_today = await asyncio.to_thread(self._fetch_today_logs, account_id, today)

        # 4.7. 예약 주문 집행 — 신호일 뒤 delayDays-1 거래 세션이 지난 첫 집행 창에서 시장가 집행.
        #      창을 놓치면 다음 창으로 이월. 매도를 먼저 집행해 슬롯·현금을 확보한다.
        if scheduled_orders:
            positions_dirty = await self._execute_scheduled_orders(
                account, scheduled_orders, strategy_id, trading_mode, today, price_map, quotes,
                status_map, name_map, positions, executed_today, max_positions, position_size_pct,
                strategy_execution_allowed,
            )
            if positions_dirty:
                positions = await asyncio.to_thread(self._fetch_positions, account_id)

        # 5. 매매 실행

        # Exits must release slots and cash before ranked replacements are bought.
        signals.sort(key=lambda signal: not signal.get("exit_signal", False))
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
                        # 사유 종류는 템플릿으로 판별하고, 감사 로그에는 한국어 문장을 남긴다.
                        if tr.first_template(sig.get("exit_reason")) == tr.LIVE_FORCED_LIQUIDATION:
                            await asyncio.to_thread(
                                write_audit_log, account_id, sym,
                                "AUTO_LIQUIDATE", None, None,
                                pos["quantity"], float(close), tr.text(sig.get("exit_reason")),
                            )
                        executed_today.add(f"{sym}_exit_auto_executed")
                        logger.info("[VirtualTrader] 매도 %s %s %d주 @%s", account_id, sym, pos["quantity"], _price_display(close, sym))
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
                        logger.info("[VirtualTrader] 매수 %s %s @%s", account_id, sym, _price_display(close, sym))
                elif f"{sym}_entry_notified" not in executed_today:
                    await asyncio.to_thread(
                        self._log_signal, account_id, today, sym, close,
                        "entry", sig.get("entry_reason"), "notified", None, stock_name
                    )
                    executed_today.add(f"{sym}_entry_notified")

        # 6. PENDING 지정가 주문 체결
        for order in pending_orders:
            current_price = price_map.get(order["symbol"], 0)
            if not current_price:
                continue
            side = order["side"]
            # 지정가 대기 주문도 상장 상태 게이트를 거친다 — 가격만 보고 체결하면
            # 주문 접수 뒤 거래정지·상장폐지된 종목이 그대로 체결된다.
            status = status_map.get(order["symbol"], ListingStatus.NORMAL)
            if (side == "BUY" and not is_buy_allowed(status)) or (
                side == "SELL" and not is_sell_allowed(status)
            ):
                logger.info(
                    "[VirtualTrader] 지정가 체결 차단 %s %s %s (상태: %s)",
                    account_id, side, order["symbol"], status,
                )
                continue
            limit = order["price"]
            fillable = (side == "BUY" and current_price <= limit) or (side == "SELL" and current_price >= limit)
            if not fillable:
                continue
            await asyncio.to_thread(self._fill_pending_order, account_id, order, current_price)

        # 7. 포지션 현재가 + peakPrice 갱신
        await asyncio.to_thread(self._update_positions, account_id, price_map, quotes)

        # 8. lastRefreshed 갱신
        await asyncio.to_thread(self._update_last_refreshed, account_id, today)

    # ── 예약 주문 집행 ────────────────────────────────────────────────────────

    async def _execute_scheduled_orders(
        self, account: dict, scheduled_orders: list[dict], strategy_id: Optional[str],
        trading_mode: str, today: str, price_map: dict[str, float], quotes: dict,
        status_map: dict[str, str], name_map: dict[str, str], positions: list[dict],
        executed_today: set[str], max_positions: int, position_size_pct: float,
        execution_window_open: bool,
    ) -> bool:
        """집행 시점에 보유·슬롯·현금·상장 상태를 다시 검사한다(예약 뒤 사정이 바뀔 수 있다).
        반환값은 포지션이 바뀌었는지(호출부가 positions를 다시 읽는다)."""
        account_id = account["id"]
        dirty = False
        for order in sorted(scheduled_orders, key=lambda o: o["side"] != "SELL"):
            sym = order["symbol"]
            side = order["side"]
            stype = "entry" if side == "BUY" else "exit"
            if order.get("strategyId") and order["strategyId"] != strategy_id:
                await asyncio.to_thread(vso.resolve, order["id"], vso.STATUS_CANCELLED, vso.RES_STRATEGY_CHANGED)
                continue
            if not execution_window_open:
                continue
            close = price_map.get(sym, 0)
            if not close:
                continue
            sessions = await asyncio.to_thread(
                vso.sessions_since, self._loader, sym, order["signalDate"], today, quotes.get(sym)
            )
            if not vso.is_due(order, sessions):
                continue
            status = status_map.get(sym, ListingStatus.NORMAL)
            if (side == "BUY" and not is_buy_allowed(status)) or (side == "SELL" and not is_sell_allowed(status)):
                continue  # 거래 가능일까지 이월(백테스트의 거래 불가일 이월과 동일)
            stock_name = name_map.get(sym) or order.get("name") or sym
            reason = _merge_exit_reason(order.get("reason"), tr.encode([tr.part(
                tr.LIVE_DELAYED_FILL, int(order["delayDays"]), order["signalDate"]
            )]))
            pos = next((p for p in positions if p["symbol"] == sym), None)

            async def _skip(code: str):
                await asyncio.to_thread(vso.resolve, order["id"], vso.STATUS_SKIPPED, code)
                await asyncio.to_thread(
                    self._log_signal, account_id, today, sym, close, stype, reason, "skipped", None, stock_name
                )

            if side == "SELL":
                if not pos:
                    await _skip(vso.RES_NO_POSITION)
                    continue
                if trading_mode != "auto":
                    if f"{sym}_exit_notified" not in executed_today:
                        await asyncio.to_thread(
                            self._log_signal, account_id, today, sym, close, "exit", reason, "notified", None, stock_name
                        )
                        executed_today.add(f"{sym}_exit_notified")
                    await asyncio.to_thread(vso.resolve, order["id"], vso.STATUS_NOTIFIED)
                    continue
                if f"{sym}_exit_auto_executed" in executed_today:
                    await _skip(vso.RES_ALREADY_EXITED_TODAY)
                    continue
                order_id = await asyncio.to_thread(
                    self._execute_sell, account_id, sym, stock_name, close, pos["quantity"], pos["avgPrice"]
                )
                if not order_id:
                    continue  # DB 오류 — 다음 틱에 재시도
                await asyncio.to_thread(
                    self._log_signal, account_id, today, sym, close, "exit", reason, "auto_executed", order_id, stock_name
                )
                executed_today.add(f"{sym}_exit_auto_executed")
                await asyncio.to_thread(vso.resolve, order["id"], vso.STATUS_EXECUTED, None, order_id)
                dirty = True
                logger.info("[VirtualTrader] 예약 매도 %s %s %d주 @%s", account_id, sym, pos["quantity"], _price_display(close, sym))
                continue

            # BUY
            if pos:
                await _skip(vso.RES_ALREADY_HELD)
                continue
            if trading_mode != "auto":
                if f"{sym}_entry_notified" not in executed_today:
                    await asyncio.to_thread(
                        self._log_signal, account_id, today, sym, close, "entry", reason, "notified", None, stock_name
                    )
                    executed_today.add(f"{sym}_entry_notified")
                await asyncio.to_thread(vso.resolve, order["id"], vso.STATUS_NOTIFIED)
                continue
            pos_count = await asyncio.to_thread(self._count_positions, account_id)
            if pos_count >= max_positions:
                await _skip(vso.RES_MAX_POSITIONS)
                continue
            current_cash = await asyncio.to_thread(self._fetch_current_cash, account_id)
            order_id = await asyncio.to_thread(
                self._execute_buy, account_id, sym, stock_name, close, current_cash, position_size_pct
            )
            if not order_id:
                await _skip(vso.RES_INSUFFICIENT_CASH)
                continue
            await asyncio.to_thread(
                self._log_signal, account_id, today, sym, close, "entry", reason, "auto_executed", order_id, stock_name
            )
            executed_today.add(f"{sym}_entry_auto_executed")
            await asyncio.to_thread(vso.resolve, order["id"], vso.STATUS_EXECUTED, None, order_id)
            dirty = True
            logger.info("[VirtualTrader] 예약 매수 %s %s @%s", account_id, sym, _price_display(close, sym))
        return dirty

    # ── 시그널 평가 (동기, to_thread에서 실행) ────────────────────────────────

    def _evaluate_signals(
        self,
        symbols: list[str],
        entry_group: dict,
        exit_group: dict,
        risk: dict,
        quotes: dict,
        execution_date: str | None = None,
    ) -> list[dict]:
        try:
            return evaluate_live_strategy_signals(
                self._loader,
                symbols,
                quotes,
                entry_group,
                exit_group,
                risk,
                self._ai_engine,
                execution_date,
            )
        except Exception as error:
            logger.warning("[VirtualTrader] signal evaluation failed: %s", error, exc_info=True)
            return []

    # ── 매매 실행 (동기, to_thread에서 실행) ─────────────────────────────────

    def _run_contribution(
        self, account_id: str, plan: tuple, symbols: list[str], today: str,
        price_map: dict[str, float], name_map: dict[str, str],
    ) -> None:
        """새 납입 회차면 입금을 기록하고 계좌 현금을 지정 종목에 균등하게 나눠 산다.

        1주도 못 산 몫은 계좌 현금에 남아 다음 회차 예산에 합쳐진다(백테스트 장부의 잔돈 이월과
        같은 방향 — 다만 종목별이 아니라 계좌 단위로 합쳐진다).
        """
        amount, period = plan
        buyable = [s for s in symbols if s in price_map]
        if not buyable:
            return
        con = appdb.connect()
        try:
            round_ = vcontrib.claim_round(con, account_id, today, amount, period, _db_now())
        except Exception as e:
            con.rollback()
            logger.error("[VirtualTrader] 계좌 %s 정기 납입 기록 오류: %s", account_id, e)
            return
        finally:
            con.close()
        if round_ is None:
            return
        logger.info("[VirtualTrader] 계좌 %s 정기 납입 %s: 입금 %.0f, 매수 예산 %.0f",
                    account_id, round_.kind, round_.credited, round_.cash)
        budget = round_.cash / len(buyable)
        reason = tr.encode([tr.part(CONTRIBUTION_REASON[round_.kind])])
        for sym in buyable:
            stock_name = name_map.get(sym) or sym
            order_id = self._execute_buy(account_id, sym, stock_name, price_map[sym], budget, 100.0)
            # 납입 매수도 매수다 — 신호 로그는 유형이 entry가 아니면 '매도'로 그린다. 구분은 사유 문구가 한다.
            self._log_signal(
                account_id, today, sym, price_map[sym], "entry", reason,
                "auto_executed" if order_id else "skipped", order_id, stock_name,
            )

    def _execute_buy(
        self,
        account_id: str,
        symbol: str,
        name: str,
        price: float,
        current_cash: float,
        position_size_pct: float,
    ) -> Optional[str]:
        us = is_us_symbol(symbol)
        invest = current_cash * (position_size_pct / 100)
        filled = _filled_price(price, "BUY", us)
        # 수수료 포함 총비용이 투자금 안에 들어오도록 수량 산정 (100% 투자 시에도 매수 가능)
        qty = int(invest // (filled * (1 + FEE_RATE)))
        if qty <= 0:
            return None
        cost = _buy_cost(filled, qty, us)
        if cost > current_cash:
            return None
        fee = _fee(filled, qty, us)

        order_id = str(uuid.uuid4())
        now_ms = _db_now()

        con = appdb.connect()
        try:
            con.execute("""
                INSERT INTO "VirtualOrder" (id, "accountId", symbol, name, side, type, quantity, price, "filledPrice", fee, status, "filledAt", "createdAt")
                VALUES (?, ?, ?, ?, 'BUY', 'MARKET', ?, ?, ?, ?, 'FILLED', ?, ?)
            """, (order_id, account_id, symbol, name, qty, price, filled, fee, now_ms, now_ms))

            con.execute("""
                UPDATE "VirtualAccount" SET "currentCash" = "currentCash" - ?, "updatedAt" = ? WHERE id = ?
            """, (cost, now_ms, account_id))

            existing = con.execute(
                'SELECT quantity, "avgPrice", "peakPrice" FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
                (account_id, symbol)
            ).fetchone()

            if existing:
                new_qty = existing[0] + qty
                new_avg = (existing[1] * existing[0] + filled * qty) / new_qty
                new_peak = max(existing[2] or new_avg, price)
                con.execute("""
                    UPDATE "VirtualPosition" SET quantity = ?, "avgPrice" = ?, "peakPrice" = ?, "updatedAt" = ?
                    WHERE "accountId" = ? AND symbol = ?
                """, (new_qty, new_avg, new_peak, now_ms, account_id, symbol))
            else:
                pos_id = str(uuid.uuid4())
                peak = max(filled, price)
                con.execute("""
                    INSERT INTO "VirtualPosition" (id, "accountId", symbol, name, quantity, "avgPrice", "peakPrice", "openedAt", "updatedAt")
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
        price: float,
        quantity: int,
        avg_buy_price: float,
    ) -> Optional[str]:
        us = is_us_symbol(symbol)
        filled = _filled_price(price, "SELL", us)
        fee = _fee(filled, quantity, us)
        tax = _tax(filled, quantity, us)
        proceeds = _sell_proceeds(filled, quantity, us)
        pnl = _realized_pnl(filled, avg_buy_price, quantity, fee, tax)

        order_id = str(uuid.uuid4())
        now_ms = _db_now()

        con = appdb.connect()
        try:
            con.execute("""
                INSERT INTO "VirtualOrder" (id, "accountId", symbol, name, side, type, quantity, price, "filledPrice", fee, tax, "avgBuyPrice", "realizedPnl", status, "filledAt", "createdAt")
                VALUES (?, ?, ?, ?, 'SELL', 'MARKET', ?, ?, ?, ?, ?, ?, ?, 'FILLED', ?, ?)
            """, (order_id, account_id, symbol, name, quantity, price, filled, fee, tax, avg_buy_price, pnl, now_ms, now_ms))

            con.execute("""
                UPDATE "VirtualAccount" SET "currentCash" = "currentCash" + ?, "updatedAt" = ? WHERE id = ?
            """, (proceeds, now_ms, account_id))

            pos = con.execute(
                'SELECT quantity FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
                (account_id, symbol)
            ).fetchone()

            if pos:
                new_qty = pos[0] - quantity
                if new_qty <= 0:
                    con.execute(
                        'DELETE FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
                        (account_id, symbol)
                    )
                else:
                    con.execute(
                        'UPDATE "VirtualPosition" SET quantity = ?, "updatedAt" = ? WHERE "accountId" = ? AND symbol = ?',
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

    def _fill_pending_order(self, account_id: str, order: dict, current_price: float):
        side = order["side"]
        qty = order["quantity"]
        filled = order["price"]  # 지정가로 체결
        us = is_us_symbol(str(order["symbol"]))
        fee = _fee(filled if us else int(filled), qty, us)
        now_ms = _db_now()

        con = appdb.connect()
        try:
            # 다른 체결 경로(브라우저 fill 라우트)와의 이중 체결 방지:
            # status='PENDING' 조건부 UPDATE가 행 잠금으로 원자적 선점 → 실패(rowcount 0) 시 아무것도 하지 않는다.
            # (SQLite의 BEGIN IMMEDIATE 대신 psycopg 트랜잭션 + Postgres 행 잠금이 동일 보장)
            if side == "BUY":
                claimed = con.execute("""
                    UPDATE "VirtualOrder" SET status = 'FILLED', "filledPrice" = ?, fee = ?, "filledAt" = ?
                    WHERE id = ? AND status = 'PENDING'
                """, (filled, fee, now_ms, order["id"])).rowcount
                if not claimed:
                    con.rollback()
                    return

                existing = con.execute(
                    'SELECT quantity, "avgPrice", "peakPrice" FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
                    (account_id, order["symbol"])
                ).fetchone()

                if existing:
                    new_qty = existing[0] + qty
                    new_avg = (existing[1] * existing[0] + filled * qty) / new_qty
                    new_peak = max(existing[2] or new_avg, current_price)
                    con.execute("""
                        UPDATE "VirtualPosition" SET quantity = ?, "avgPrice" = ?, "currentPrice" = ?, "peakPrice" = ?, "updatedAt" = ?
                        WHERE "accountId" = ? AND symbol = ?
                    """, (new_qty, new_avg, current_price, new_peak, now_ms, account_id, order["symbol"]))
                else:
                    pos_id = str(uuid.uuid4())
                    peak = max(filled if us else int(filled), current_price)
                    con.execute("""
                        INSERT INTO "VirtualPosition" (id, "accountId", symbol, name, quantity, "avgPrice", "currentPrice", "peakPrice", "openedAt", "updatedAt")
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (pos_id, account_id, order["symbol"], order.get("name") or order["symbol"],
                          qty, filled, current_price, peak, now_ms, now_ms))

            else:  # SELL
                pos = con.execute(
                    'SELECT quantity, "avgPrice" FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
                    (account_id, order["symbol"])
                ).fetchone()
                if not pos or pos[0] < qty:
                    # 보유 수량 부족 → 주문 취소 (fill 라우트와 동일한 처리)
                    con.execute(
                        'UPDATE "VirtualOrder" SET status = \'CANCELLED\' WHERE id = ? AND status = \'PENDING\'',
                        (order["id"],)
                    )
                    con.commit()
                    return

                avg_buy = pos[1]
                _f = filled if us else int(filled)
                tax = _tax(_f, qty, us)
                proceeds = _sell_proceeds(_f, qty, us)
                pnl = _realized_pnl(_f, avg_buy, qty, fee, tax)

                claimed = con.execute("""
                    UPDATE "VirtualOrder" SET status = 'FILLED', "filledPrice" = ?, fee = ?, tax = ?,
                    "avgBuyPrice" = ?, "realizedPnl" = ?, "filledAt" = ? WHERE id = ? AND status = 'PENDING'
                """, (filled, fee, tax, avg_buy, pnl, now_ms, order["id"])).rowcount
                if not claimed:
                    con.rollback()
                    return

                con.execute("""
                    UPDATE "VirtualAccount" SET "currentCash" = "currentCash" + ?, "updatedAt" = ? WHERE id = ?
                """, (proceeds, now_ms, account_id))

                new_qty = pos[0] - qty
                if new_qty <= 0:
                    con.execute(
                        'DELETE FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
                        (account_id, order["symbol"])
                    )
                else:
                    con.execute(
                        'UPDATE "VirtualPosition" SET quantity = ?, "updatedAt" = ? WHERE "accountId" = ? AND symbol = ?',
                        (new_qty, now_ms, account_id, order["symbol"])
                    )

            con.commit()
        except Exception as e:
            con.rollback()
            logger.error("[VirtualTrader] pending fill 오류 %s: %s", order["id"], e)
        finally:
            con.close()

    def _count_positions(self, account_id: str) -> int:
        con = appdb.connect()
        try:
            row = con.execute(
                'SELECT COUNT(*) FROM "VirtualPosition" WHERE "accountId" = ?', (account_id,)
            ).fetchone()
            return row[0] if row else 0
        finally:
            con.close()

    def _update_positions(self, account_id: str, price_map: dict[str, float], quotes: dict):
        con = appdb.connect()
        now_ms = _db_now()
        try:
            positions = con.execute(
                'SELECT symbol, "peakPrice", "avgPrice" FROM "VirtualPosition" WHERE "accountId" = ?', (account_id,)
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
                    UPDATE "VirtualPosition" SET "currentPrice" = ?, "peakPrice" = ?, "updatedAt" = ?
                    WHERE "accountId" = ? AND symbol = ?
                """, (price, new_peak, now_ms, account_id, sym))
            con.commit()
        except Exception as e:
            con.rollback()
            logger.error("[VirtualTrader] 포지션 갱신 오류 %s: %s", account_id, e)
        finally:
            con.close()

    def _update_last_refreshed(self, account_id: str, today: str):
        con = appdb.connect()
        now_ms = _db_now()
        try:
            con.execute("""
                UPDATE "VirtualMarketState" SET "lastRefreshed" = ?, "updatedAt" = ? WHERE "accountId" = ?
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
        now_ms = _db_now()
        con = appdb.connect()
        try:
            con.execute("""
                INSERT INTO "VirtualMarketLog" (id, "accountId", date, symbol, "stockName", "signalType", reason, price, action, "orderId", "createdAt")
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, account_id, date, symbol, stock_name, signal_type, reason, price, action, order_id, now_ms))
            con.commit()
        except Exception as e:
            logger.error("[VirtualTrader] 로그 기록 오류: %s", e)
        finally:
            con.close()
