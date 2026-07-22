import pandas as pd

from engine import data_coverage


def _group(*cids):
    return {"conditions": [{"type": "filter", "id": c, "params": {"operator": "<", "value": 10}} for c in cids]}


def test_tracked_metrics_only_data_dependent():
    entry = {"conditions": [
        {"id": "per", "params": {}},
        {"id": "rsi", "params": {}},          # 기술지표 → 추적 안 함
        {"id": "market_cap", "params": {}},
    ]}
    exit_ = {"conditions": [{"id": "roe_or_gpa", "params": {}}]}
    assert data_coverage.tracked_metrics(entry, exit_) == ["per", "market_cap", "roe_or_gpa"]


def test_tracked_metrics_dedup_and_empty():
    entry = {"conditions": [{"id": "per", "params": {}}, {"id": "per", "params": {}}]}
    assert data_coverage.tracked_metrics(entry, None) == ["per"]
    assert data_coverage.tracked_metrics(None, None) == []


def test_symbol_stats_column_present_and_absent():
    pdf = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=4),
        "per": [None, 8.0, 9.0, None],
    })
    stats = data_coverage.symbol_stats(pdf, ["per", "pbr"])
    assert stats["per"]["rows_total"] == 4
    assert stats["per"]["rows_valid"] == 2
    assert stats["per"]["first_valid"] == "2020-01-02"
    assert stats["per"]["last_valid"] == "2020-01-03"
    # 컬럼 없음 → valid 0 (백필 안 된 과거 parquet)
    assert stats["pbr"]["rows_valid"] == 0
    assert stats["pbr"]["first_valid"] is None


def test_symbol_stats_date_as_index():
    # preprocess_data 이후처럼 date가 인덱스일 때도 동작해야 한다.
    pdf = pd.DataFrame({"per": [7.0, 8.0]}, index=pd.to_datetime(["2021-05-01", "2021-05-02"]))
    stats = data_coverage.symbol_stats(pdf, ["per"])
    assert stats["per"]["rows_valid"] == 2
    assert stats["per"]["first_valid"] == "2021-05-01"


def test_accumulator_classifies_used_partial_unused():
    acc = data_coverage.CoverageAccumulator(["per", "pbr", "market_cap"])
    # sym1: per full, pbr half, market_cap none
    acc.fold({
        "per": {"rows_total": 10, "rows_valid": 10, "first_valid": "2015-01-01", "last_valid": "2020-01-01"},
        "pbr": {"rows_total": 10, "rows_valid": 5, "first_valid": "2017-01-01", "last_valid": "2020-01-01"},
        "market_cap": {"rows_total": 10, "rows_valid": 0, "first_valid": None, "last_valid": None},
    })
    # sym2: per full, pbr none, market_cap none
    acc.fold({
        "per": {"rows_total": 10, "rows_valid": 10, "first_valid": "2014-01-01", "last_valid": "2021-01-01"},
        "pbr": {"rows_total": 10, "rows_valid": 0, "first_valid": None, "last_valid": None},
        "market_cap": {"rows_total": 10, "rows_valid": 0, "first_valid": None, "last_valid": None},
    })
    report = acc.build()
    by_key = {m["key"]: m for m in report["metrics"]}

    # per: 20/20 rows, 2/2 symbols → used
    assert by_key["per"]["status"] == "used"
    assert by_key["per"]["periodCoveragePct"] == 100.0
    assert by_key["per"]["availableFrom"] == "2014-01-01"

    # pbr: 5/20 rows(25%), 1/2 symbols → partial + low-coverage warning
    assert by_key["pbr"]["status"] == "partial"
    assert by_key["pbr"]["periodCoveragePct"] == 25.0
    assert any("PBR" in w and "25.0%" in w for w in report["warnings"])

    # market_cap: no data anywhere → unused
    assert by_key["market_cap"]["status"] == "unused"
    assert "시가총액" in report["unusedData"]
    assert any("시가총액" in w and "존재하지 않아" in w for w in report["warnings"])

    assert report["baseData"] == ["시가", "고가", "저가", "종가", "거래량"]


def test_symbol_stats_counts_negative_excluded():
    # per가 NaN인 4행 중, EPS가 존재하고 ≤0인 2행만 '음수 제외'로 분리해야 한다.
    # 나머지 NaN(EPS 결측)은 진짜 결측이므로 제외 카운트에서 빠진다.
    pdf = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=5),
        "per": [None, None, 8.0, None, 9.0],
        "eps": [-100.0, 0.0, 500.0, None, 400.0],  # 적자·손익분기·흑자·결측·흑자
    })
    stats = data_coverage.symbol_stats(pdf, ["per"])
    assert stats["per"]["rows_valid"] == 2
    # EPS<=0(적자/BEP)인 2행만 음수 제외. EPS 결측(index 3)은 진짜 결측.
    assert stats["per"]["rows_excluded_negative"] == 2


def test_symbol_stats_roe_uses_equity_fallback():
    # roe_or_gpa는 total_equity 우선, 없으면 bps로 근사(fetcher와 동일).
    pdf_eq = pd.DataFrame({
        "roe_or_gpa": [None, 12.0],
        "total_equity": [-50.0, 3000.0],
        "bps": [10000.0, 20000.0],  # total_equity가 있으면 bps는 무시돼야 함
    })
    assert data_coverage.symbol_stats(pdf_eq, ["roe_or_gpa"])["roe_or_gpa"]["rows_excluded_negative"] == 1

    pdf_bps = pd.DataFrame({"roe_or_gpa": [None, None], "bps": [-1.0, 5000.0]})
    # bps<=0인 1행만 제외(두 번째는 roe 결측이지만 bps>0 → 진짜 결측).
    assert data_coverage.symbol_stats(pdf_bps, ["roe_or_gpa"])["roe_or_gpa"]["rows_excluded_negative"] == 1


def test_symbol_stats_no_denom_column_degrades_to_zero():
    # 분모 컬럼이 없으면(백필 안 된 과거 parquet) 음수 제외를 판정할 수 없어 0.
    pdf = pd.DataFrame({"per": [None, 8.0]})
    assert data_coverage.symbol_stats(pdf, ["per"])["per"]["rows_excluded_negative"] == 0


def test_unused_metric_all_negative_gets_corrected_warning():
    # 값이 존재했으나 전부 적자라 unused가 된 경우, '존재하지 않아'가 아니라
    # 적자 사유로 정정된 경고가 나가야 한다.
    acc = data_coverage.CoverageAccumulator(["per"])
    acc.fold({"per": {"rows_total": 10, "rows_valid": 0, "rows_excluded_negative": 10,
                      "first_valid": None, "last_valid": None}})
    report = acc.build()
    m = report["metrics"][0]
    assert m["status"] == "unused"
    assert m["negativeExcludedRows"] == 10
    assert not any("존재하지 않아" in w for w in report["warnings"])
    assert any("적자" in w and "결측이 아니라" in w for w in report["warnings"])


def test_material_negative_exclusion_emits_separate_warning():
    # used/partial이어도 음수 제외 비중이 임계치 이상이면 결측과 구분한 라인을 낸다.
    acc = data_coverage.CoverageAccumulator(["per"])
    # 70% valid, 30% 적자 제외 → status=partial(<95%), 음수 경고도 함께.
    acc.fold({"per": {"rows_total": 100, "rows_valid": 70, "rows_excluded_negative": 30,
                      "first_valid": "2019-01-01", "last_valid": "2020-01-01"}})
    report = acc.build()
    m = report["metrics"][0]
    assert m["negativeExcludedPct"] == 30.0
    assert any("30.0%" in w and "결측과는 별개" in w for w in report["warnings"])


def test_no_negative_exclusion_warning_below_threshold():
    # 음수 제외가 임계치 미만이면 별도 경고를 내지 않는다(노이즈 방지).
    acc = data_coverage.CoverageAccumulator(["per"])
    acc.fold({"per": {"rows_total": 100, "rows_valid": 98, "rows_excluded_negative": 2,
                      "first_valid": "2019-01-01", "last_valid": "2020-01-01"}})
    report = acc.build()
    assert report["metrics"][0]["negativeExcludedRows"] == 2
    assert not any("별개" in w for w in report["warnings"])


def test_accumulator_symbol_partial_warning():
    # 기간 커버리지는 높지만(≥60%) 일부 종목만 데이터 있음 → 종목 커버리지 경고.
    acc = data_coverage.CoverageAccumulator(["roe_or_gpa"])
    for _ in range(9):  # 9종목 완전
        acc.fold({"roe_or_gpa": {"rows_total": 10, "rows_valid": 10, "first_valid": "2019-01-01", "last_valid": "2020-01-01"}})
    acc.fold({"roe_or_gpa": {"rows_total": 10, "rows_valid": 0, "first_valid": None, "last_valid": None}})  # 1종목 없음
    report = acc.build()
    m = report["metrics"][0]
    assert m["status"] == "partial"
    assert m["symbolCoveragePct"] == 90.0
    assert m["periodCoveragePct"] == 90.0  # 90/100
    assert any("일부 종목" in w for w in report["warnings"])
