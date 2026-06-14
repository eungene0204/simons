"""수정주가(adjusted price) 가드 테스트 — preprocess_data의 코퍼레이트 액션 sanitizer.

소스 데이터는 정방향 액면분할만 조정돼 있고 역분할/감자/정지후재개/오류프린트는 미조정이라
±30% 가격제한을 넘는 불가능한 일간 점프가 남는다. 이게 가짜 손절·가짜 수익을 만들므로
엔진이 역조정/중립화로 연속적인 수정주가 시계열을 보게 만든다.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.loader import DataLoader

LIMIT = 0.31  # 한국 일간 가격제한 ±30% (+여유). 조정 후 이 안에 들어와야 함.


def _series(closes):
    closes = list(map(float, closes))
    return pd.DataFrame({
        "date": pd.date_range("2018-01-01", periods=len(closes)),
        "open": closes, "high": closes, "low": closes, "close": closes,
    })


def _max_abs_ret(df):
    c = df["close"].to_numpy(dtype=float)
    return float(np.max(np.abs(c[1:] / c[:-1] - 1)))


def test_reverse_split_back_adjusted():
    # 10:1 역분할(상승 점프)이 과거 역조정되어 불연속이 사라져야 한다
    out = DataLoader._sanitize_corporate_actions(_series([100] * 20 + [1000] * 20))
    assert _max_abs_ret(out) <= LIMIT


def test_forward_split_back_adjusted():
    # 정방향 분할(하락 점프)도 마찬가지
    out = DataLoader._sanitize_corporate_actions(_series([1000] * 20 + [100] * 20))
    assert _max_abs_ret(out) <= LIMIT


def test_split_then_rally_is_adjusted_not_left():
    # 점프 직후 가격이 계속 움직여도(랠리) 점프 자체는 조정돼야 한다
    out = DataLoader._sanitize_corporate_actions(
        _series([100] * 20 + [500, 600, 720, 864, 1000] + [1000] * 10)
    )
    assert _max_abs_ret(out) <= LIMIT


def test_transient_bad_print_neutralised():
    # 하루짜리 오류 프린트는 양옆 보간으로 중립화
    out = DataLoader._sanitize_corporate_actions(_series([100] * 20 + [5000] + [100] * 20))
    assert _max_abs_ret(out) <= LIMIT


def test_normal_series_untouched():
    closes = [100, 102, 101, 103, 99, 100, 104] * 5
    out = DataLoader._sanitize_corporate_actions(_series(closes))
    assert np.allclose(out["close"].to_numpy(), np.array(closes, dtype=float))


def test_delisting_crash_preserved():
    # 정리매매(시계열 끝 하락 크래시)는 실제 손실이므로 보존돼야 한다 (역조정 금지)
    closes = [100] * 30 + [10]
    out = DataLoader._sanitize_corporate_actions(_series(closes))
    assert out["close"].to_numpy()[-1] == 10.0          # 마지막 크래시가 남아있다
    assert out["close"].to_numpy()[0] == 100.0          # 과거가 역조정되지 않았다


def test_ohlc_scaled_together():
    # 역조정 시 open/high/low/close가 같은 비율로 스케일되어 바 내부 정합성 유지
    closes = [100] * 20 + [1000] * 20
    df = _series(closes)
    df["high"] = df["close"] * 1.05
    df["low"] = df["close"] * 0.95
    out = DataLoader._sanitize_corporate_actions(df)
    assert np.allclose(out["high"].to_numpy() / out["close"].to_numpy(), 1.05)
    assert np.allclose(out["low"].to_numpy() / out["close"].to_numpy(), 0.95)
