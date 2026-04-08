from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.vi_utils import build_vi_display


def test_build_vi_display_uses_static_reference_from_kis():
    result = build_vi_display({
        "vi_prc": "3985",
        "vi_stnd_prc": "3620",
        "vi_dprt": "10.00",
        "vi_dmc_stnd_prc": "0",
        "vi_dmc_dprt": "0.00",
    })

    assert result == {
        "kind": "static",
        "referencePrice": 3620,
        "triggeredPrice": 3985,
        "upper": 3985,
        "lower": 3255,
        "rate": 0.1,
        "raw": {
            "vi_cls_code": None,
            "vi_kind_code": None,
            "cntg_vi_hour": None,
            "vi_cncl_hour": None,
            "vi_prc": "3985",
            "vi_stnd_prc": "3620",
            "vi_dprt": "10.00",
            "vi_dmc_stnd_prc": "0",
            "vi_dmc_dprt": "0.00",
            "vi_count": None,
        },
    }


def test_build_vi_display_falls_back_to_dynamic_reference_when_static_missing():
    result = build_vi_display({
        "vi_prc": "344",
        "vi_stnd_prc": "0",
        "vi_dprt": "0.00",
        "vi_dmc_stnd_prc": "368",
        "vi_dmc_dprt": "-6.52",
    })

    assert result["kind"] == "dynamic"
    assert result["referencePrice"] == 368
    assert result["upper"] == 392
    assert result["lower"] == 344
