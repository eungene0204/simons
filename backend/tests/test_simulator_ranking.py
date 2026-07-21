"""상대강도(수익률 순위) 랭킹 백테스트 검증.

핵심: 진입 신호 없이 ranking_metric="return"만으로 전 종목을 후보로 만들고,
N일 수익률 상위 max_positions 종목만 선정/보유하는지 확인한다.
vectorbt/polars/stockstats가 있는 환경에서만 실행(없으면 skip).
"""

import os

import pytest

pytest.importorskip("vectorbt")
pytest.importorskip("polars")
pytest.importorskip("stockstats")

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from backtest_engine import BacktestEngine  # noqa: E402


def _write_series(data_dir: str, symbol: str, prices: list[float], dates) -> None:
    rows = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "open": float(p),
            "high": float(p + 1),
            "low": float(p - 1),
            "close": float(p),
            "volume": 5_000_000.0,
        }
        for d, p in zip(dates, prices)
    ]
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def _write_series_with_fundamentals(
    data_dir: str, symbol: str, dates, *, pbr: float, roe: float
) -> None:
    """가치+퀄리티(PBR/ROE) 랭킹 테스트용 — 재무 지표가 parquet에 이미 있는 상태를
    시뮬레이션한다(pbr=NaN은 자본잠식 등으로 null 처리된 종목을 나타낸다)."""
    rows = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": 5_000_000.0,
            "pbr": pbr, "roe_or_gpa": roe,
        }
        for d in dates
    ]
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def _value_quality_req(symbols: list[str], **extra_risk) -> dict:
    return {
        "symbols": symbols,
        "entry": {"conditions": [{"id": "price", "params": {"value": 0, "operator": ">"}}]},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 30,
            "max_positions": 2,
            "ranking_enabled": True,
            "liquidity_multiplier": 0,
            **extra_risk,
        },
        "options": {"execution_type": "same_close"},
    }


def test_return_ranking_selects_only_top_k_by_momentum():
    """4종목 중 최근 수익률 상위 2종목(WIN_A/WIN_B)만 매수되고, 하락/횡보주는 매수되지 않는다."""
    dates = pd.date_range(start="2024-01-01", periods=40, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # 상승주: 꾸준히 오름 → 높은 N일 수익률. 횡보/하락주: 낮은 수익률.
    _write_series(data_dir, "RANK_WIN_A", [100 + 3 * i for i in range(40)], dates)
    _write_series(data_dir, "RANK_WIN_B", [100 + 2 * i for i in range(40)], dates)
    _write_series(data_dir, "RANK_FLAT_C", [100.0 for _ in range(40)], dates)
    _write_series(data_dir, "RANK_FALL_D", [100 - 1 * i for i in range(40)], dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RANK_WIN_A", "RANK_WIN_B", "RANK_FLAT_C", "RANK_FALL_D"],
        "entry": {"conditions": []},          # 진입 신호 없음 — 선정 자체가 진입
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)

    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}

    # 상위 수익률 종목만 매수, 횡보/하락주는 절대 매수되지 않음.
    assert buy_symbols <= {"RANK_WIN_A", "RANK_WIN_B"}, f"하위 종목이 매수됨: {buy_symbols}"
    assert "RANK_WIN_A" in buy_symbols, "최상위 수익률 종목이 매수되지 않음"
    assert "RANK_FALL_D" not in buy_symbols
    assert "RANK_FLAT_C" not in buy_symbols


def test_return_ranking_buy_reason_shows_percentile_not_generic():
    """랭킹 매수(선정=진입)는 조건식이 없어 SignalEngine이 사유를 만들지 못하므로,
    과거엔 result_handler의 하드코딩 폴백("매수 조건 충족 (전략 시그널)")으로 뭉개졌다.
    실제로는 그날의 N일 수익률 백분위가 매수 근거이므로 사유에 드러나야 한다."""
    dates = pd.date_range(start="2024-01-01", periods=40, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    _write_series(data_dir, "PCT_WIN_A", [100 + 3 * i for i in range(40)], dates)
    _write_series(data_dir, "PCT_WIN_B", [100 + 2 * i for i in range(40)], dates)
    _write_series(data_dir, "PCT_FLAT_C", [100.0 for _ in range(40)], dates)
    _write_series(data_dir, "PCT_FALL_D", [100 - 1 * i for i in range(40)], dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["PCT_WIN_A", "PCT_WIN_B", "PCT_FLAT_C", "PCT_FALL_D"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)
    buy_conditions = [s["condition"] for s in result["signals"] if s["type"] == "buy"]

    assert buy_conditions, "매수 기록이 없음"
    assert all("최근 5거래일 수익률 상위" in c and "%" in c for c in buy_conditions), (
        f"랭킹 매수 사유가 백분위를 담지 않음: {buy_conditions}"
    )
    assert not any(c == "매수 조건 충족 (전략 시그널)" for c in buy_conditions), (
        f"랭킹 매수가 여전히 추상 폴백 문구로 뭉개짐: {buy_conditions}"
    )


def test_return_ranking_buy_reason_includes_rebalance_note():
    """리밸런싱 랭킹 매수는 사유에 회전 주기·목표 종목 수까지 포함해야 한다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _write_rotation_universe(data_dir, "PCTRB", dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": symbols,
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)
    buy_conditions = [s["condition"] for s in result["signals"] if s["type"] == "buy"]

    assert buy_conditions, "매수 기록이 없음"
    assert any("월간 리밸런싱 상위 2종목 편입 대상" in c for c in buy_conditions), (
        f"리밸런싱 매수 사유에 회전 주기·목표 종목 수 누락: {buy_conditions}"
    )


def test_monthly_rebalancing_rotates_dropouts():
    """월간 리밸런싱: 다음 달 순위에서 빠진 종목은 매도되고, 새로 오른 종목이 편입된다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")  # Jan~Apr
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # STEADY: 내내 상승 → 항상 상위.
    _write_series(data_dir, "RB_STEADY", [100 + 1.0 * i for i in range(100)], dates)
    # EARLY: 1월 급등 후 2월부터 급락 → 2월초 상위, 3월초 탈락.
    early = [100 + 3.0 * i for i in range(31)]
    early += [early[-1] - 3.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RB_EARLY", early, dates)
    # LATE: 1월 횡보, 2월부터 급등 → 2월초 탈락, 3월초 편입.
    late = [100.0 for _ in range(31)] + [100 + 4.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RB_LATE", late, dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RB_STEADY", "RB_EARLY", "RB_LATE"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    # SL/TP 없음 → vbt 네이티브 from_orders(목표비중) 경로로 처리됨.
    result = engine.run_backtest(req)
    buys = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    sells = {s["symbol"] for s in result["signals"] if s["type"] == "sell"}

    # 세 종목 모두 어느 시점엔가 보유됨 → 리밸런싱 재선정이 작동.
    assert {"RB_STEADY", "RB_EARLY", "RB_LATE"} <= buys, f"재선정 누락: {buys}"
    # 급락해 순위에서 빠진 EARLY는 리밸런싱으로 매도됨(SL 없음 → 매도는 리밸런싱이 유일).
    assert "RB_EARLY" in sells, f"탈락 종목이 매도되지 않음: {sells}"


def test_monthly_rebalancing_with_stoploss_uses_signal_path():
    """리밸런싱 + 봉중간 SL이 섞이면 from_signals 커스텀 루프(reconstitution)로 라우팅된다.

    SL을 발동 안 하게 느슨히(-90%) 둬도 회전/재선정은 동일하게 동작해야 한다.
    """
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    _write_series(data_dir, "RBS_STEADY", [100 + 1.0 * i for i in range(100)], dates)
    early = [100 + 3.0 * i for i in range(31)]
    early += [early[-1] - 3.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBS_EARLY", early, dates)
    late = [100.0 for _ in range(31)] + [100 + 4.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBS_LATE", late, dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RBS_STEADY", "RBS_EARLY", "RBS_LATE"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "stop_loss_pct": 90,   # 발동 안 함 → from_signals 경로만 강제
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)
    buys = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    sells = {s["symbol"] for s in result["signals"] if s["type"] == "sell"}

    assert {"RBS_STEADY", "RBS_EARLY", "RBS_LATE"} <= buys, f"재선정 누락: {buys}"
    assert "RBS_EARLY" in sells, f"탈락 종목이 매도되지 않음: {sells}"


def _early_sell_conditions(result) -> list[str]:
    """리밸런싱 탈락 종목(EARLY 계열)의 매도 사유 문자열을 모은다."""
    return [
        s["condition"]
        for s in result["signals"]
        if s["type"] == "sell" and s["symbol"].endswith("EARLY")
    ]


def test_rebalance_dropout_labeled_precisely_pure_path():
    """순수 리밸런싱(SL 없음) 경로: 탈락 매도는 추상적 '전략 매도 조건 충족'이 아니라
    '리밸런싱 제외'로 정확히 라벨링된다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    _write_series(data_dir, "RBL_STEADY", [100 + 1.0 * i for i in range(100)], dates)
    early = [100 + 3.0 * i for i in range(31)]
    early += [early[-1] - 3.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBL_EARLY", early, dates)
    late = [100.0 for _ in range(31)] + [100 + 4.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBL_LATE", late, dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RBL_STEADY", "RBL_EARLY", "RBL_LATE"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)
    conditions = _early_sell_conditions(result)
    assert conditions, "탈락 종목의 매도 기록이 없음"
    assert any("리밸런싱 제외" in c for c in conditions), f"리밸런싱 사유 라벨 누락: {conditions}"
    assert not any("전략 매도 조건 충족" in c for c in conditions), (
        f"리밸런싱 탈락이 추상 라벨로 뭉개짐: {conditions}"
    )


def test_rebalance_dropout_labeled_precisely_custom_loop_path():
    """리밸런싱 + 봉중간 SL 혼합(커스텀 루프) 경로에서도 탈락 매도는 '리밸런싱 제외'로 라벨링된다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    _write_series(data_dir, "RBLS_STEADY", [100 + 1.0 * i for i in range(100)], dates)
    early = [100 + 3.0 * i for i in range(31)]
    early += [early[-1] - 3.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBLS_EARLY", early, dates)
    late = [100.0 for _ in range(31)] + [100 + 4.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBLS_LATE", late, dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RBLS_STEADY", "RBLS_EARLY", "RBLS_LATE"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "stop_loss_pct": 90,   # 발동 안 함 → 커스텀 루프(reconstitution) 경로 강제
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)
    conditions = _early_sell_conditions(result)
    assert conditions, "탈락 종목의 매도 기록이 없음"
    assert any("리밸런싱 제외" in c for c in conditions), f"리밸런싱 사유 라벨 누락: {conditions}"


def _write_rotation_universe(data_dir: str, prefix: str, dates) -> list[str]:
    """리밸런싱 회전 시나리오 3종목: STEADY(내내 상승)·EARLY(1월 급등→2월 급락)·LATE(2월부터 급등)."""
    _write_series(data_dir, f"{prefix}_STEADY", [100 + 1.0 * i for i in range(100)], dates)
    early = [100 + 3.0 * i for i in range(31)]
    early += [early[-1] - 3.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, f"{prefix}_EARLY", early, dates)
    late = [100.0 for _ in range(31)] + [100 + 4.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, f"{prefix}_LATE", late, dates)
    return [f"{prefix}_STEADY", f"{prefix}_EARLY", f"{prefix}_LATE"]


def _rotation_req(symbols: list[str], **extra_risk) -> dict:
    return {
        "symbols": symbols,
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
            **extra_risk,
        },
        "options": {"execution_type": "next_open"},
    }


def _signal_dates(result, symbol: str, side: str) -> list[str]:
    return [s["date"] for s in result["signals"] if s["symbol"] == symbol and s["type"] == side]


def test_next_open_rebalance_fills_on_rebalance_day_pure_path():
    """[회귀] next_open 순수 리밸런싱(from_orders) 경로: 엔진이 신호·랭킹을 이미 1일
    shift해 넘기므로 시뮬레이터가 다시 shift하면 안 된다 — 리밸런싱 회전(편입·편출)은
    그 달 첫 거래일 시가에 체결돼야 한다(이중 shift 시 하루 늦게 체결되던 버그)."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _write_rotation_universe(data_dir, "RBNO", dates)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(_rotation_req(symbols))

    late_buys = _signal_dates(result, "RBNO_LATE", "buy")
    early_sells = _signal_dates(result, "RBNO_EARLY", "sell")
    assert late_buys, "3월 편입 종목의 매수 기록이 없음"
    assert late_buys[0] == "2024-03-01", f"편입이 리밸런싱일에 체결되지 않음: {late_buys[0]}"
    assert early_sells, "3월 편출 종목의 매도 기록이 없음"
    assert early_sells[0] == "2024-03-01", f"편출이 리밸런싱일에 체결되지 않음: {early_sells[0]}"


def test_next_open_rebalance_fills_on_rebalance_day_custom_loop_path():
    """[회귀] next_open 커스텀 루프(reconstitution) 경로: 편출 결정은 전일 정보 기반이므로
    (리스크 청산과 달리) 편입과 같은 리밸런싱일에 체결된다 — 하루 늦게 팔리던 비대칭 제거."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _write_rotation_universe(data_dir, "RBNOL", dates)

    engine = BacktestEngine(data_dir=data_dir)
    # 발동 안 하는 SL로 커스텀 루프 경로 강제
    result = engine.run_backtest(_rotation_req(symbols, stop_loss_pct=90))

    late_buys = _signal_dates(result, "RBNOL_LATE", "buy")
    early_sells = _signal_dates(result, "RBNOL_EARLY", "sell")
    assert late_buys, "3월 편입 종목의 매수 기록이 없음"
    assert late_buys[0] == "2024-03-01", f"편입이 리밸런싱일에 체결되지 않음: {late_buys[0]}"
    assert early_sells, "3월 편출 종목의 매도 기록이 없음"
    assert early_sells[0] == "2024-03-01", f"편출이 리밸런싱일에 체결되지 않음: {early_sells[0]}"


# ──────────────────────────────────────────────────────────────────────────────
# 가치+퀄리티(PBR/ROE) 랭킹 — 자본잠식/적자로 null(NaN)인 종목이 배제되는지 검증
# ──────────────────────────────────────────────────────────────────────────────

def test_value_quality_ranking_excludes_nan_pbr_stock():
    """PBR이 NaN(자본잠식으로 계산 불가)인 종목은 다른 두 종목보다 값이 '낮아' 보여도
    최우선 가치주로 선정되지 않고 배제되어야 한다(과거 fillna(1.0) 센티널이 이를 숨겼음)."""
    dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    _write_series_with_fundamentals(data_dir, "VQ_IMPAIRED", dates, pbr=float("nan"), roe=float("nan"))
    _write_series_with_fundamentals(data_dir, "VQ_VALUE", dates, pbr=1.0, roe=15.0)
    _write_series_with_fundamentals(data_dir, "VQ_GROWTH", dates, pbr=2.0, roe=10.0)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(_value_quality_req(
        ["VQ_IMPAIRED", "VQ_VALUE", "VQ_GROWTH"],
        ranking_weight_value=0.5, ranking_weight_quality=0.5,
    ))

    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert buy_symbols == {"VQ_VALUE", "VQ_GROWTH"}, f"자본잠식 종목이 배제되지 않음: {buy_symbols}"


def test_value_quality_ranking_zero_weight_ignores_nan_factor():
    """가중치가 0인 팩터의 NaN은 종목을 배제하면 안 된다(NaN*0=NaN 전파 버그 회귀 방지).
    PBR 가중치=0이면 PBR이 NaN인 종목도 ROE만으로 정상 랭킹돼야 한다."""
    dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    _write_series_with_fundamentals(data_dir, "ZW_BEST_ROE", dates, pbr=float("nan"), roe=20.0)
    _write_series_with_fundamentals(data_dir, "ZW_MID_ROE", dates, pbr=1.0, roe=5.0)
    _write_series_with_fundamentals(data_dir, "ZW_LOW_ROE", dates, pbr=1.0, roe=1.0)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(_value_quality_req(
        ["ZW_BEST_ROE", "ZW_MID_ROE", "ZW_LOW_ROE"],
        ranking_weight_value=0.0, ranking_weight_quality=1.0,
    ))

    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert buy_symbols == {"ZW_BEST_ROE", "ZW_MID_ROE"}, (
        f"PBR 가중치 0인데도 PBR=NaN 종목이 배제됨: {buy_symbols}"
    )
