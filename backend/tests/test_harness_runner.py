import json
import sys

sys.path.append("backend")

from harness.runner import evaluate_result, run_suite


class FakeEngine:
    def __init__(self, data_dir=None):
        self.data_dir = data_dir

    def run_backtest(self, request):
        symbol = request["symbols"][0]

        if symbol == "CONFIG_TEST":
            return {
                "totalReturn": 5.0,
                "trades": 1,
                "signals": [
                    {"type": "buy", "date": "2024-01-01", "price": 105.0}
                ],
                "warnings": [],
                "dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            }

        if symbol == "ZERO_TRADE_TEST":
            return {
                "totalReturn": 0.0,
                "trades": 0,
                "signals": [],
                "warnings": [
                    "매매 기록이 생성되지 않았습니다. 매수 조건 또는 유동성/포지션 설정을 확인해 주세요."
                ],
                "dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
            }

        return {
            "totalReturn": 3.0,
            "trades": 1,
            "signals": [
                {"type": "buy", "date": "2024-01-01", "price": 100.0},
                {"type": "sell", "date": "2024-01-06", "price": 110.0, "condition": "보유 기간 만료 (5일 보유)"},
            ],
            "warnings": [],
            "dates": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06"],
        }


def test_evaluate_result_reports_missing_signal_match():
    case = {
        "id": "missing_signal",
        "expect": {
            "signals_include": [
                {"type": "sell", "condition_contains": "손절매"}
            ]
        },
    }
    result = {
        "signals": [{"type": "sell", "condition": "익절매"}],
        "warnings": [],
        "dates": [],
    }

    failures = evaluate_result(case, result)

    assert failures
    assert "signals_include" in failures[0]


def test_run_suite_uses_defaults_and_case_expectations(tmp_path):
    suite = {
        "suite_name": "fake_smoke",
        "defaults": {
          "data_dir": "backend/tests/data",
          "request": {
              "period": "FULL",
              "exit": {"logic": "AND", "conditions": []}
          }
        },
        "cases": [
            {
                "id": "config_same_close_entry",
                "request": {
                    "symbols": ["CONFIG_TEST"],
                    "entry": {"logic": "AND", "conditions": [{"id": "price", "params": {"value": 102, "operator": ">"}}]}
                },
                "expect": {
                    "signal_count": {"equals": 1},
                    "signals_include": [{"type": "buy", "date": "2024-01-01", "price": 105.0}]
                }
            },
            {
                "id": "zero_trade_warning",
                "request": {
                    "symbols": ["ZERO_TRADE_TEST"],
                    "entry": {"logic": "AND", "conditions": [{"id": "price", "params": {"value": 1000, "operator": ">"}}]}
                },
                "expect": {
                    "signal_count": {"equals": 0},
                    "warnings_include": ["매매 기록이 생성되지 않았습니다."]
                }
            }
        ]
    }
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(json.dumps(suite, ensure_ascii=False), encoding="utf-8")

    report = run_suite(str(suite_path), engine_factory=FakeEngine)

    assert report["totals"] == {"cases": 2, "passed": 2, "failed": 0}
    assert report["cases"][0]["summary"]["signal_count"] == 1
    assert report["cases"][1]["summary"]["warning_count"] == 1
