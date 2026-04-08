from __future__ import annotations

from typing import Optional


def tick_size(price: int) -> int:
    if price < 1000:
        return 1
    if price < 5000:
        return 5
    if price < 10000:
        return 10
    if price < 50000:
        return 50
    if price < 100000:
        return 100
    if price < 500000:
        return 500
    return 1000


def round_down_to_tick(price: float) -> int:
    tick = tick_size(int(price))
    return int(price // tick) * tick


def round_up_to_tick(price: float) -> int:
    tick = tick_size(int(price))
    return int(-(-price // tick)) * tick


def _parse_int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _parse_rate(value: object, fallback_rate: float) -> float:
    try:
        parsed = abs(float(value or 0))
        return parsed / 100 if parsed > 0 else fallback_rate
    except (TypeError, ValueError):
        return fallback_rate


def build_vi_display(record: dict | None) -> Optional[dict]:
    if not record:
        return None

    static_base = _parse_int(record.get("vi_stnd_prc"))
    dynamic_base = _parse_int(record.get("vi_dmc_stnd_prc"))
    triggered_price = _parse_int(record.get("vi_prc"))

    if static_base > 0:
        reference_price = static_base
        rate = _parse_rate(record.get("vi_dprt"), 0.10)
        kind = "static"
    elif dynamic_base > 0:
        reference_price = dynamic_base
        rate = _parse_rate(record.get("vi_dmc_dprt"), 0.06)
        kind = "dynamic"
    else:
        return None

    return {
        "kind": kind,
        "referencePrice": reference_price,
        "triggeredPrice": triggered_price,
        "upper": round_up_to_tick(reference_price * (1 + rate)),
        "lower": round_down_to_tick(reference_price * (1 - rate)),
        "rate": rate,
        "raw": {
            "vi_cls_code": record.get("vi_cls_code"),
            "vi_kind_code": record.get("vi_kind_code"),
            "cntg_vi_hour": record.get("cntg_vi_hour"),
            "vi_cncl_hour": record.get("vi_cncl_hour"),
            "vi_prc": record.get("vi_prc"),
            "vi_stnd_prc": record.get("vi_stnd_prc"),
            "vi_dprt": record.get("vi_dprt"),
            "vi_dmc_stnd_prc": record.get("vi_dmc_stnd_prc"),
            "vi_dmc_dprt": record.get("vi_dmc_dprt"),
            "vi_count": record.get("vi_count"),
        },
    }
