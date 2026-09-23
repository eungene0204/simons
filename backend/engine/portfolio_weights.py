"""포트폴리오 비중 산정(엔진 v16.28) — 시총가중·최소분산·리스크 패리티(ERC)·최대 샤프·최소 CVaR·고정 배분.

시뮬레이터는 리밸런싱일마다 목표 종목 집합(sel)을 정한 뒤 여기서 그 종목들의 비중을 받는다.
동일가중·변동성 역비중(1/σ, v16.14)은 시뮬레이터 안의 종전 경로 그대로이고(결과 비트 동일),
이 모듈은 **그 밖의 방식**만 맡는다.

  market_cap    — 시가총액에 비례(가치 가중). 기준 패널(basis)은 엔진이 신호와 같은 지연으로 넘긴다.
  min_variance  — 최근 N거래일 수익률 공분산으로 분산 최소화(롱온리, 합 1).
  risk_parity   — 위험 기여(ERC) 균등: 0.5·w'Σw − (1/n)Σlog w 최소화 뒤 정규화(Spinu 2013).
  max_sharpe    — 평균 수익률 ÷ 변동성 최대화(롱온리). 모든 평균이 0 이하면 최소분산으로 대체.
  min_cvar      — 최근 N거래일 손실 분포의 CVaR(95%) 최소화(Rockafellar–Uryasev 선형계획).
  fixed         — 사용자가 종목별로 말한 고정 비중(정적 자산배분, 예: 60/40).

자료가 모자라거나(관측 < max(20, 종목 수 + 2)) 해를 못 구하면 None을 돌려주고 호출부가 동일가중으로
떨어진다 — 그 날 수는 ``fallback_days``로 세어 결과 경고에 실린다(조용한 대체 금지).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

OPTIMIZER_METHODS = ("min_variance", "risk_parity", "max_sharpe", "min_cvar")
BASIS_METHODS = ("market_cap", "schedule")   # schedule=전술 자산배분 비중 패널(v16.29)
ENGINE_METHODS = ("equal", "inverse_volatility") + BASIS_METHODS + OPTIMIZER_METHODS + ("fixed",)

CVAR_CONFIDENCE = 0.95
_MIN_OBS = 20
_RIDGE = 1e-8


def _covariance(rows: np.ndarray) -> np.ndarray:
    cov = np.cov(rows, rowvar=False, ddof=1)
    cov = np.atleast_2d(cov)
    n = cov.shape[0]
    return cov + np.eye(n) * (_RIDGE * (np.trace(cov) / n if n else 1.0) + 1e-12)


def min_variance_weights(cov: np.ndarray) -> Optional[np.ndarray]:
    from scipy.optimize import minimize

    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])
    x0 = np.full(n, 1.0 / n)
    res = minimize(lambda w: float(w @ cov @ w), x0, jac=lambda w: 2.0 * cov @ w,
                   method="SLSQP", bounds=[(0.0, 1.0)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                   options={"maxiter": 500, "ftol": 1e-12})
    return _clean(res.x) if res.success else None


def risk_parity_weights(cov: np.ndarray) -> Optional[np.ndarray]:
    from scipy.optimize import minimize

    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])

    def obj(w):
        return 0.5 * float(w @ cov @ w) - np.log(w).sum() / n

    def grad(w):
        return cov @ w - 1.0 / (n * w)

    x0 = np.full(n, 1.0 / n)
    res = minimize(obj, x0, jac=grad, method="L-BFGS-B", bounds=[(1e-8, None)] * n,
                   options={"maxiter": 1000})
    if not res.success:
        return None
    return _clean(res.x / res.x.sum())


def max_sharpe_weights(mean: np.ndarray, cov: np.ndarray) -> Optional[np.ndarray]:
    from scipy.optimize import minimize

    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])
    if not np.any(mean > 0):
        return min_variance_weights(cov)

    def neg_sharpe(w):
        var = float(w @ cov @ w)
        return -float(mean @ w) / np.sqrt(var) if var > 0 else 0.0

    x0 = np.full(n, 1.0 / n)
    res = minimize(neg_sharpe, x0, method="SLSQP", bounds=[(0.0, 1.0)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                   options={"maxiter": 500, "ftol": 1e-12})
    return _clean(res.x) if res.success else None


def min_cvar_weights(rows: np.ndarray, confidence: float = CVAR_CONFIDENCE) -> Optional[np.ndarray]:
    """Rockafellar–Uryasev: min VaR + 1/((1−α)T)·Σu_t, u_t ≥ −r_t·w − VaR, u ≥ 0, w ≥ 0, Σw = 1."""
    from scipy.optimize import linprog

    t, n = rows.shape
    if n == 1:
        return np.array([1.0])
    # 변수 = [w(n), var(1), u(t)]
    c = np.concatenate([np.zeros(n), [1.0], np.full(t, 1.0 / ((1.0 - confidence) * t))])
    a_ub = np.hstack([-rows, -np.ones((t, 1)), -np.eye(t)])
    b_ub = np.zeros(t)
    a_eq = np.concatenate([np.ones(n), [0.0], np.zeros(t)])[None, :]
    bounds = [(0.0, 1.0)] * n + [(None, None)] + [(0.0, None)] * t
    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=[1.0], bounds=bounds, method="highs")
    return _clean(res.x[:n]) if res.success else None


def _clean(w: np.ndarray) -> Optional[np.ndarray]:
    w = np.where(np.isfinite(w), w, 0.0)
    w = np.clip(w, 0.0, None)
    total = w.sum()
    if not total > 0:
        return None
    w = w / total
    w[w < 1e-9] = 0.0
    return w / w.sum()


@dataclass
class AllocationContext:
    """리밸런싱일 비중 산정 재료(엔진이 만든다). 모든 패널은 신호와 같은 지연이 이미 적용돼 있다.

    basis:   (창 행 수, 종목 수) — market_cap 기준값(시총). 창 정렬.
    returns: (확장 행 수, 종목 수) — 일수익률. 창 행 i ↔ returns 행 i + offset.
    fixed:   (종목 수,) — 고정 배분 비율(합 ≤ 1). 종목이 목표 밖이면 무시된다.
    """
    method: str
    basis: Optional[np.ndarray] = None
    returns: Optional[np.ndarray] = None
    offset: int = 0
    lookback: int = 60
    fixed: Optional[np.ndarray] = None
    fallback_days: int = field(default=0)
    applied_days: int = field(default=0)

    def weights(self, i: int, sel: np.ndarray) -> Optional[np.ndarray]:
        """창 행 i, 목표 종목 열 sel의 비중(합 1). 산정 불가면 None(호출부가 동일가중)."""
        sel = np.asarray(sel, dtype=int)
        if len(sel) == 0:
            return None
        out = self._weights(i, sel)
        if out is None or len(out) != len(sel):
            self.fallback_days += 1
            return None
        self.applied_days += 1
        return out

    def _weights(self, i: int, sel: np.ndarray) -> Optional[np.ndarray]:
        if self.method in BASIS_METHODS:
            if self.basis is None:
                return None
            vals = self.basis[i, sel].astype(float)
            if not np.isfinite(vals).all() or not (vals > 0).all():
                return None
            return vals / vals.sum()
        if self.method == "fixed":
            if self.fixed is None:
                return None
            vals = self.fixed[sel].astype(float)
            if not np.isfinite(vals).all() or not (vals > 0).any():
                return None
            return vals / vals.sum()
        if self.method not in OPTIMIZER_METHODS or self.returns is None:
            return None
        end = i + self.offset + 1
        start = max(0, end - self.lookback)
        rows = self.returns[start:end][:, sel].astype(float)
        rows = rows[np.isfinite(rows).all(axis=1)]
        if len(rows) < max(_MIN_OBS, len(sel) + 2):
            return None
        if self.method == "min_cvar":
            return min_cvar_weights(rows)
        cov = _covariance(rows)
        if self.method == "min_variance":
            return min_variance_weights(cov)
        if self.method == "risk_parity":
            return risk_parity_weights(cov)
        if self.method == "max_sharpe":
            return max_sharpe_weights(rows.mean(axis=0), cov)
        return None
