"""정액 적립식(DCA, Dollar-Cost Averaging) 장부 — 지정 종목을 주기마다 조건 없이 사 모은다.

일반 백테스트는 '시작 자본 하나'가 전제다: 체결은 vectorbt `from_orders`(init_cash 스칼라)
한 번으로 확정되고, 수익률 지표는 전부 그 시작 자본을 분모로 쓴다. 적립식은 돈이 중간에
들어오므로 그 전제가 둘 다 깨진다 — 그래서 기존 체결 경로를 건드리지 않고 별도 장부로 계산한다
(적립 요청이 아닌 백테스트는 이 모듈을 거치지 않는다 = 결과 불변).

규약
- 납입 일정은 리밸런싱 달력(`compute_rebalance_dates`)과 같다: 각 주기의 **첫 거래일**.
  첫 봉은 초기 자본(1회차)이고, 이후 주기의 첫 거래일마다 `amount`가 들어온다.
- 납입금은 봉이 열리기 전에 들어온 것으로 본다 — 그 봉의 체결가(next_open=시가,
  same_close=종가)로 바로 산다. 달력만으로 정해지는 매수라 신호 지연(룩어헤드) 문제가 없다.
- 납입금은 종목별 예산으로 균등하게 나뉜다. 정수 주 단위로만 사고, 남은 돈은 그 종목 예산에
  현금으로 이월된다(1주 값이 예산보다 비싸면 그 회차는 못 산다 → 다음 회차에 합쳐서 산다).
- 납입일에 거래할 수 없는 종목(상장 전·거래정지)은 거래 가능해지는 첫 봉에 산다.
- 매도는 없다. 기말 보유분은 종가로 평가한다.
- 조건부 납입액(v16.21): 납입일마다 종목의 조건을 봐서 그 회차 납입액을 바꾼다("200일선 아래면
  200만 원", "RSI 30 미만이면 100만 원 더"). 기본액에서 시작해 'set' 규칙이 성립하면 그 금액으로
  바꾸고(여럿이면 가장 큰 금액), 'add' 규칙이 성립하면 더한다. 판정 시점은 일반 매수 신호와 같다 —
  시가 체결(next_open)이면 **전 거래일 종가까지의 값**, 종가 체결이면 당일 종가(미래 참조 금지).
  초기 자본(1회차)에는 규칙을 적용하지 않는다. 종목이 여럿이면 종목별 몫에 종목별로 적용한다.
- 현금 풀(v16.22): "보유 현금의 10% 이내로만 산다"·"항상 일정 수준의 현금을 유지한다"는 **한정된
  현금에서 꺼내 사는** 방식이라 위 납입 장부(돈이 매번 밖에서 들어와 전부 매수)로는 뜻이 없다.
  이 방식은 초기 자본을 첫 봉에 전부 사지 않고 현금으로 들고, 각 주기의 첫 거래일(첫 봉 포함)마다
  그 회차 매수액(기본액·조건부 규칙은 위와 같다)을 **보유 현금에서** 꺼낸다. 회차 매수액은 두
  한도로 깎인다 — ① 그 시점 보유 현금 × 상한 비율 ② 보유 현금 − 현금 하한. 한도에 걸리면 종목별
  몫을 같은 비율로 줄이고, 남은 돈은 풀에 그대로 남는다(종목별 예산 이월 없음). 밖에서 들어오는
  돈이 없으므로 납입 흐름은 첫 봉의 초기 자본 하나뿐이고, 수익률은 일반 백테스트와 같은 뜻이 된다.

수익률
- 시간가중(TWR): 납입 효과를 걷어낸 일간 수익률 r[t] = 평가액[t] ÷ (평가액[t-1] + 납입[t]) − 1.
  총수익률·CAGR·MDD·샤프는 이걸로 계산해 일반 백테스트와 나란히 비교할 수 있게 한다.
- 금액가중(XIRR): 실제 납입 시점·금액을 반영한 연 수익률 — 투자자가 체감하는 수익률.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from engine.rebalance import compute_rebalance_dates

# 납입 주기 — 리밸런싱 달력이 아는 주기 중 '없음'을 뺀 것. 표기 검증용(의미 해석 아님).
CONTRIBUTION_PERIODS = ("daily", "weekly", "monthly", "bimonthly", "quarterly", "semiannual", "yearly")


def contribution_settings(risk_params: Dict[str, Any]) -> "Optional[tuple[float, str]]":
    """요청의 (회차 납입액, 주기). 적립 요청이 아니면 None. 반쪽 요청·표기 오류는 Fail Fast."""
    amount_raw = risk_params.get("contribution_amount")
    period_raw = risk_params.get("contribution_period")
    if amount_raw is None and not period_raw:
        return None
    if amount_raw is None or not period_raw:
        raise ValueError("정액 적립식은 납입액(contribution_amount)과 주기(contribution_period)가 모두 필요합니다.")
    amount = float(amount_raw)
    period = str(period_raw)
    if not np.isfinite(amount) or amount <= 0:
        raise ValueError(f"정액 적립식 납입액은 0보다 커야 합니다: {amount_raw}")
    if period not in CONTRIBUTION_PERIODS:
        raise ValueError(f"지원하지 않는 납입 주기입니다: {period_raw}")
    return amount, period


CONTRIBUTION_RULE_MODES = ("set", "add")


def contribution_rules(risk_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """요청의 조건부 납입액 규칙 [{condition, amount, mode}]. 없으면 빈 목록. 표기 오류는 Fail Fast."""
    rules: List[Dict[str, Any]] = []
    for raw in risk_params.get("contribution_rules") or []:
        condition = raw.get("condition")
        mode = str(raw.get("mode") or "")
        amount = float(raw.get("amount") or 0)
        if not isinstance(condition, dict) or not condition:
            raise ValueError("조건부 납입액 규칙에 조건(condition)이 없습니다.")
        if mode not in CONTRIBUTION_RULE_MODES:
            raise ValueError(f"지원하지 않는 납입액 규칙 방식입니다: {raw.get('mode')}")
        if not np.isfinite(amount) or amount <= 0:
            raise ValueError(f"조건부 납입액은 0보다 커야 합니다: {raw.get('amount')}")
        rules.append({"condition": condition, "amount": amount, "mode": mode})
    return rules


def rule_symbol_flows(
    base_flows: np.ndarray, amount: float, rules: Sequence[Dict[str, Any]],
    rule_hits: Sequence[np.ndarray],
) -> "tuple[np.ndarray, List[int]]":
    """종목별 납입 행렬(거래일 × 종목)과 규칙별 적용 횟수.

    base_flows=규칙 없는 납입 일정(첫 봉=초기 자본), rule_hits[k]=규칙 k가 성립한 (거래일 × 종목)
    불리언 — **체결 시점 규약이 이미 반영된** 값이어야 한다(호출부가 next_open이면 하루 민다).
    회차 납입액은 종목 수로 나눈 몫에 종목별로 적용한다: 몫 = (기본액 → set 최대 → add 합) ÷ 종목 수.
    """
    n_days = len(base_flows)
    n_sym = rule_hits[0].shape[1] if rule_hits else 1
    per_symbol = np.repeat((np.asarray(base_flows, dtype=float) / n_sym)[:, None], n_sym, axis=1)
    counts = [0] * len(rules)
    if not rules:
        return per_symbol, counts
    rounds = np.flatnonzero(np.asarray(base_flows) > 0)
    rounds = rounds[rounds > 0]          # 첫 봉(초기 자본)은 규칙 대상이 아니다
    for t in rounds:
        for j in range(n_sym):
            value = float(amount)
            sets = [r["amount"] for r, hit in zip(rules, rule_hits) if r["mode"] == "set" and hit[t, j]]
            if sets:
                value = max(sets)
            value += sum(r["amount"] for r, hit in zip(rules, rule_hits) if r["mode"] == "add" and hit[t, j])
            per_symbol[t, j] = value / n_sym
            for k, (_r, hit) in enumerate(zip(rules, rule_hits)):
                counts[k] += int(bool(hit[t, j]))
    assert per_symbol.shape == (n_days, n_sym)
    return per_symbol, counts


def withdrawal_settings(risk_params: Dict[str, Any]) -> "Optional[tuple[float, str]]":
    """요청의 (회차 인출액, 주기). 인출 요청이 아니면 None. 반쪽 요청·표기 오류는 Fail Fast."""
    amount_raw = risk_params.get("withdrawal_amount")
    period_raw = risk_params.get("withdrawal_period")
    if amount_raw is None and not period_raw:
        return None
    if amount_raw is None or not period_raw:
        raise ValueError("정기 인출은 인출액(withdrawal_amount)과 주기(withdrawal_period)가 모두 필요합니다.")
    amount = float(amount_raw)
    period = str(period_raw)
    if not np.isfinite(amount) or amount <= 0:
        raise ValueError(f"인출액이 올바르지 않습니다: {amount_raw}")
    if period not in CONTRIBUTION_PERIODS:
        raise ValueError(f"지원하지 않는 인출 주기입니다: {period_raw}")
    return amount, period


def withdrawal_flows(index: pd.Index, amount: float, period: str) -> np.ndarray:
    """거래일별 인출액 — 각 주기의 첫 거래일. **첫 봉은 제외**한다(넣자마자 빼지 않는다)."""
    flows = np.where(compute_rebalance_dates(index, period), float(amount), 0.0)
    if len(flows):
        flows[0] = 0.0
    return flows


def contribution_flows(index: pd.Index, init_cash: float, amount: float, period: str) -> np.ndarray:
    """거래일별 납입액 — 첫 봉은 초기 자본, 이후 각 주기의 첫 거래일은 회차 납입액."""
    flows = np.where(compute_rebalance_dates(index, period), float(amount), 0.0)
    if len(flows):
        flows[0] = float(init_cash)
    return flows


@dataclass
class ContributionLedger:
    """적립 장부 결과. 배열은 전부 거래일 인덱스와 같은 길이다."""
    index: pd.Index
    symbols: List[str]
    flows: np.ndarray                 # 거래일별 납입액
    equity: np.ndarray                # 거래일 종가 기준 평가액(현금 포함)
    cash: np.ndarray                  # 거래일 말 현금
    shares: np.ndarray                # (거래일 × 종목) 보유 주식 수
    close: np.ndarray                 # (거래일 × 종목) 평가 종가
    orders: List[Dict[str, Any]] = field(default_factory=list)   # 체결된 매수·매도(side)
    missed_rounds: int = 0            # 1주 값이 예산보다 비싸 한 주도 못 산 (회차, 종목) 수
    withdrawn_total: float = 0.0      # 실제로 인출한 금액 합
    shortfall_rounds: int = 0         # 보유를 다 팔아도 인출액에 못 미친 회차 수

    @property
    def total_contributed(self) -> float:
        """실제로 넣은 돈만 센다 — 인출(음수 흐름)을 빼면 '원금'이 아니라 순현금흐름이 된다."""
        return float(self.flows[self.flows > 0].sum())

    @property
    def final_value(self) -> float:
        return float(self.equity[-1]) if len(self.equity) else 0.0

    def holding_drawdown_pct(self, col: int) -> float:
        """첫 매수 이후 그 종목 종가의 최대낙폭(%, 음수) — 보유 중 겪은 가격 낙폭."""
        held = np.flatnonzero(self.shares[:, col] > 0)
        if len(held) == 0:
            return 0.0
        prices = self.close[held[0]:, col]
        peak = np.maximum.accumulate(prices)
        with np.errstate(divide="ignore", invalid="ignore"):
            dd = np.where(peak > 0, prices / peak - 1.0, 0.0)
        return float(dd.min() * 100.0)


def simulate_contributions(
    price_df: pd.DataFrame,
    exec_price_df: pd.DataFrame,
    available_df: pd.DataFrame,
    flows: np.ndarray,
    buy_fee_rate: float,
    slippage_rate: float,
    symbol_flows: Optional[np.ndarray] = None,
    withdrawals: Optional[np.ndarray] = None,
    sell_fee_rate: float = 0.0,
    sell_tax: Optional[np.ndarray] = None,
) -> ContributionLedger:
    """납입 일정대로 지정 종목을 균등하게 사 모은다.

    price_df=종가(평가), exec_price_df=체결가, available_df=그 봉에 실제 거래 가능했는가.
    체결 단가 = 체결가 × (1+슬리피지), 수수료 = 체결 금액 × 수수료율 — vectorbt 주문과 같은 식.
    symbol_flows(거래일 × 종목)가 있으면 종목별 납입액을 그대로 쓴다(조건부 납입액, rule_symbol_flows) —
    없으면 flows를 종목 수로 균등 분할한다(종전 동작).

    withdrawals(거래일별 인출액, v16.33)가 있으면 그 봉에서 **미집행 현금 → 보유 평가액 비례 매도**
    순으로 돈을 만들어 내보낸다(매도 수수료·거래세 차감). 보유를 다 팔아도 모자라면 만들 수 있는
    만큼만 내보내고 그 회차를 shortfall로 센다 — 조용히 빚을 내지 않는다.
    """
    symbols = list(price_df.columns)
    n_days, n_sym = price_df.shape
    if symbol_flows is not None:
        symbol_flows = np.asarray(symbol_flows, dtype=float)
        flows = symbol_flows.sum(axis=1)
    close = price_df.to_numpy(dtype=float)
    exec_px = exec_price_df.to_numpy(dtype=float)
    avail = available_df.to_numpy(dtype=bool)
    dates = pd.DatetimeIndex(price_df.index).strftime("%Y-%m-%d")

    budget = np.zeros(n_sym)             # 종목별 미집행 현금
    held = np.zeros(n_sym)
    pending = np.zeros(n_sym, dtype=bool)  # 납입이 들어왔고 아직 매수를 시도하지 않은 종목
    round_no = 0
    shares = np.zeros((n_days, n_sym))
    cash = np.zeros(n_days)
    orders: List[Dict[str, Any]] = []
    missed = 0

    withdraw = (np.zeros(n_days) if withdrawals is None
                else np.asarray(withdrawals, dtype=float))
    tax_vec = (np.zeros(n_days) if sell_tax is None else np.asarray(sell_tax, dtype=float))
    withdrawn_total = 0.0
    shortfall_rounds = 0
    withdraw_round = 0

    for t in range(n_days):
        if flows[t] > 0:
            round_no += 1
            budget += symbol_flows[t] if symbol_flows is not None else flows[t] / n_sym
            pending[:] = True
        if withdraw[t] > 0:
            withdraw_round += 1
            raised, want = 0.0, float(withdraw[t])
            # ① 미집행 현금부터 — 종목별 예산에서 비례로 뺀다.
            pool = float(budget.sum())
            if pool > 0:
                take = min(want, pool)
                budget -= budget * (take / pool)
                raised += take
            # ② 모자라면 보유를 평가액 비례로 판다(그 봉에 거래 가능한 종목만).
            if want - raised > 1e-9:
                sellable = np.flatnonzero((held > 0) & avail[t] & np.isfinite(exec_px[t]) & (exec_px[t] > 0))
                values = held[sellable] * exec_px[t, sellable] * (1.0 - slippage_rate)
                total_value = float(values.sum())

                def _sell(j: int, target: float) -> float:
                    """종목 j에서 target원어치를 판다(1주 단위, 남은 보유 한도). 실제 순수령액 반환."""
                    unit = exec_px[t, j] * (1.0 - slippage_rate)
                    net_unit = unit * (1.0 - sell_fee_rate - float(tax_vec[t]))
                    if net_unit <= 0 or target <= 1e-9:
                        return 0.0
                    qty = int(min(held[j], np.ceil(target / net_unit - 1e-9)))
                    if qty < 1:
                        return 0.0
                    gross = qty * unit
                    fee = gross * sell_fee_rate
                    tax = gross * float(tax_vec[t])
                    held[j] -= qty
                    orders.append({
                        "date": dates[t], "symbol": symbols[j], "round": withdraw_round,
                        "price": float(unit), "quantity": qty, "fee": float(fee + tax), "side": "sell",
                    })
                    return gross - fee - tax

                if total_value > 0:
                    # 1차: 보유 평가액 비례로 나눠 판다(한 종목만 털지 않는다).
                    for k, j in enumerate(sellable):
                        need = want - raised
                        if need <= 1e-9:
                            break
                        share = need if len(sellable) == 1 else want * float(values[k]) / total_value
                        raised += _sell(int(j), min(share, need))
                    # 2차: 비례 몫이 보유 한도에 걸려 모자랐으면 남은 보유에서 마저 채운다 —
                    # 팔 것이 남았는데 '부족한 회차'로 세면 거짓 고지가 된다.
                    for j in sellable:
                        need = want - raised
                        if need <= 1e-9:
                            break
                        if held[j] > 0:
                            raised += _sell(int(j), need)
                # 인출액을 넘겨 만든 돈은 그대로 현금(예산)으로 남긴다.
                if raised > want:
                    budget[0] += raised - want
                    raised = want
            withdrawn_total += raised
            if raised < want - 1e-6:
                shortfall_rounds += 1
        for j in np.flatnonzero(pending & avail[t]):
            pending[j] = False
            unit = exec_px[t, j] * (1.0 + slippage_rate)
            if not np.isfinite(unit) or unit <= 0:
                continue
            qty = int(np.floor(budget[j] / (unit * (1.0 + buy_fee_rate)) + 1e-9))
            if qty < 1:
                missed += 1
                continue
            fee = qty * unit * buy_fee_rate
            budget[j] -= qty * unit + fee
            held[j] += qty
            orders.append({
                "date": dates[t], "symbol": symbols[j], "round": round_no,
                "price": float(unit), "quantity": qty, "fee": float(fee), "side": "buy",
            })
        shares[t] = held
        cash[t] = budget.sum()

    equity = cash + (shares * close).sum(axis=1)
    # 인출은 밖으로 나간 돈이라 납입의 반대 부호로 흐름에 싣는다(TWR·XIRR이 같은 배열을 본다).
    net_flows = np.asarray(flows, dtype=float) - withdraw
    return ContributionLedger(
        index=price_df.index, symbols=symbols, flows=net_flows,
        equity=equity, cash=cash, shares=shares, close=close, orders=orders, missed_rounds=missed,
        withdrawn_total=float(withdrawn_total), shortfall_rounds=int(shortfall_rounds),
    )


def cash_pool_settings(risk_params: Dict[str, Any], init_cash: float) -> "Optional[tuple[float, Optional[float]]]":
    """현금 풀 요청의 (현금 하한 금액, 단일 매수 상한 비율[0~1] 또는 None). 풀 요청이 아니면 None.

    하한은 초기 자본 대비 %(`cash_reserve_pct`) 또는 금액(`cash_reserve_amount`) — 둘 다 없으면 0.
    표기 오류(음수·100% 이상·초기 자본 이상)는 Fail Fast: 조용히 깎으면 다른 전략이 된다.
    """
    if str(risk_params.get("contribution_funding") or "") != "cash_pool":
        return None
    reserve_pct = risk_params.get("cash_reserve_pct")
    reserve_amount = risk_params.get("cash_reserve_amount")
    if reserve_pct is not None and reserve_amount is not None:
        raise ValueError("현금 하한은 비율(cash_reserve_pct)과 금액(cash_reserve_amount) 중 하나만 지정합니다.")
    reserve = 0.0
    if reserve_pct is not None:
        pct = float(reserve_pct)
        if not np.isfinite(pct) or pct < 0 or pct >= 100:
            raise ValueError(f"현금 하한 비율은 0 이상 100 미만이어야 합니다: {reserve_pct}")
        reserve = float(init_cash) * pct / 100.0
    elif reserve_amount is not None:
        reserve = float(reserve_amount)
        if not np.isfinite(reserve) or reserve < 0 or reserve >= float(init_cash):
            raise ValueError(f"현금 하한은 0 이상이고 초기 자본보다 작아야 합니다: {reserve_amount}")
    cap = risk_params.get("max_buy_cash_pct")
    cap_ratio: Optional[float] = None
    if cap is not None:
        cap_pct = float(cap)
        if not np.isfinite(cap_pct) or cap_pct <= 0 or cap_pct > 100:
            raise ValueError(f"단일 매수 상한 비율은 0 초과 100 이하여야 합니다: {cap}")
        cap_ratio = cap_pct / 100.0
    return reserve, cap_ratio


def simulate_cash_pool(
    price_df: pd.DataFrame,
    exec_price_df: pd.DataFrame,
    available_df: pd.DataFrame,
    round_mask: np.ndarray,
    symbol_targets: np.ndarray,
    init_cash: float,
    reserve: float,
    cap_ratio: Optional[float],
    buy_fee_rate: float,
    slippage_rate: float,
) -> "tuple[ContributionLedger, int]":
    """보유 현금에서 꺼내 사는 적립 장부. (장부, 한도에 걸려 매수액이 깎인 회차 수)를 돌려준다.

    round_mask=매수 회차인 봉, symbol_targets=(거래일 × 종목) 그 회차에 **사고 싶은** 금액.
    회차마다 총 매수액을 min(요청, 보유 현금×상한, 보유 현금−하한)으로 깎고 종목별 몫을 같은 비율로
    줄인다. 납입일에 거래할 수 없는 종목의 몫은 거래 가능해지는 첫 봉에 산다(그때의 한도를 다시 본다).
    """
    symbols = list(price_df.columns)
    n_days, n_sym = price_df.shape
    close = price_df.to_numpy(dtype=float)
    exec_px = exec_price_df.to_numpy(dtype=float)
    avail = available_df.to_numpy(dtype=bool)
    dates = pd.DatetimeIndex(price_df.index).strftime("%Y-%m-%d")

    pool = float(init_cash)
    held = np.zeros(n_sym)
    alloc = np.zeros(n_sym)                # 회차에서 배정받고 아직 집행하지 못한 종목별 금액
    round_no = 0
    shares = np.zeros((n_days, n_sym))
    cash = np.zeros(n_days)
    orders: List[Dict[str, Any]] = []
    missed = 0
    limited = 0

    for t in range(n_days):
        if round_mask[t]:
            round_no += 1
            want = np.asarray(symbol_targets[t], dtype=float)
            total = float(want.sum())
            limit = max(0.0, pool - reserve)
            if cap_ratio is not None:
                limit = min(limit, pool * cap_ratio)
            if total > limit + 1e-9:
                limited += 1
            scale = min(1.0, limit / total) if total > 0 else 0.0
            alloc = want * scale             # 직전 회차의 미집행분은 버린다(현금은 풀에 남아 있다)
        for j in np.flatnonzero((alloc > 0) & avail[t]):
            budget = min(float(alloc[j]), max(0.0, pool - reserve))
            alloc[j] = 0.0
            unit = exec_px[t, j] * (1.0 + slippage_rate)
            if not np.isfinite(unit) or unit <= 0:
                continue
            qty = int(np.floor(budget / (unit * (1.0 + buy_fee_rate)) + 1e-9))
            if qty < 1:
                missed += 1
                continue
            fee = qty * unit * buy_fee_rate
            pool -= qty * unit + fee
            held[j] += qty
            orders.append({
                "date": dates[t], "symbol": symbols[j], "round": round_no,
                "price": float(unit), "quantity": qty, "fee": float(fee), "side": "buy",
            })
        shares[t] = held
        cash[t] = pool

    flows = np.zeros(n_days)
    if n_days:
        flows[0] = float(init_cash)          # 밖에서 들어온 돈은 초기 자본 하나뿐이다
    equity = cash + (shares * close).sum(axis=1)
    ledger = ContributionLedger(
        index=price_df.index, symbols=symbols, flows=flows, equity=equity, cash=cash,
        shares=shares, close=close, orders=orders, missed_rounds=missed,
    )
    return ledger, limited


def time_weighted_returns(equity: Sequence[float], flows: Sequence[float]) -> np.ndarray:
    """납입 효과를 걷어낸 일간 수익률 — 납입은 봉이 열리기 전에 들어온 것으로 본다."""
    eq = np.asarray(equity, dtype=float)
    fl = np.asarray(flows, dtype=float)
    base = np.concatenate([[0.0], eq[:-1]]) + fl
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.where(base > 0, eq / base - 1.0, 0.0)
    return rets


def money_weighted_return(index: pd.Index, flows: Sequence[float], final_value: float) -> Optional[float]:
    """금액가중 연 수익률(XIRR, 소수). 납입=유출, 인출·기말 평가액=유입. 해가 없으면 None.

    연 단위는 실제 경과일 ÷ 365.25(지표의 달력 기준 연수와 같은 규약). 이분법으로 푼다 —
    부호가 섞이면(정기 인출) 단조성이 보장되지 않으므로 구간에 해가 없으면 None을 돌려준다.
    """
    fl = np.asarray(flows, dtype=float)
    # 인출로 자산이 소진되면 기말 평가액이 0일 수 있다 — 그래도 인출 흐름으로 해가 정의된다.
    if len(fl) == 0 or final_value < 0 or fl[fl > 0].sum() <= 0:
        return None
    days = (pd.DatetimeIndex(index) - pd.Timestamp(index[0])).days.to_numpy(dtype=float)
    years = days / 365.25
    end = years[-1]
    if end <= 0:
        return None
    paid = fl > 0
    amounts, offsets = fl[paid], end - years[paid]
    taken = fl < 0
    out_amounts, out_offsets = -fl[taken], end - years[taken]

    def _npv(rate: float) -> float:
        grown = (amounts * (1.0 + rate) ** offsets).sum()
        returned = (out_amounts * (1.0 + rate) ** out_offsets).sum() if len(out_amounts) else 0.0
        return float(grown - returned - final_value)

    lo, hi = -0.9999, 1.0
    while _npv(hi) < 0 and hi < 1e6:
        hi *= 2.0
    if _npv(lo) > 0 or _npv(hi) < 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _npv(mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2.0


def contributed_benchmark_equity(bench_returns: Sequence[float], flows: Sequence[float]) -> np.ndarray:
    """같은 날 같은 금액을 벤치마크에 넣었을 때의 평가액(비용 없음 — 기존 벤치마크와 같은 규약).

    목돈 1회 투자 곡선과 적립 곡선을 나란히 놓으면 구조적으로 불공정하다 — 벤치마크에도
    같은 납입 일정을 적용한다. 납입은 그 봉의 수익률을 온전히 받는다(봉 시작 전 납입).
    """
    rets = np.nan_to_num(np.asarray(bench_returns, dtype=float), nan=0.0)
    cum = np.cumprod(1.0 + rets)
    prev_cum = np.concatenate([[1.0], cum[:-1]])
    units = np.cumsum(np.asarray(flows, dtype=float) / prev_cum)
    return cum * units
