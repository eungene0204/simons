"""홍보 CF 2편 모션그래픽 재료를 만든다: data.json(실제 KOSPI 지수·KOSPI200 종가/등락률) + logo.png(투명 로고).

사용: uv run --frozen --project backend python cf2_assets.py <out_dir>   (저장소 루트에서)
데이터는 로컬 data/(프로덕션에서 pull한 parquet)에서 읽기만 한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
from PIL import Image

ROOT = Path(__file__).resolve().parents[5]


def data_json() -> dict:
    k = pl.read_parquet(ROOT / "data/index/KOSPI.parquet").sort("date")
    out = {"kospi_daily": [[r["date"].strftime("%Y-%m-%d"), r["open"], r["high"], r["low"], r["close"]] for r in k.tail(260).iter_rows(named=True)]}
    wk = k.filter(pl.col("date") >= pl.datetime(2005, 1, 1)).group_by_dynamic("date", every="1w").agg(pl.col("close").last()).sort("date")
    out["kospi_weekly"] = [[r["date"].strftime("%Y-%m-%d"), r["close"]] for r in wk.iter_rows(named=True)]
    master = {s["symbol"]: s for s in json.loads((ROOT / "data/stock-master.json").read_text())["stocks"]}
    rows = []
    for s in json.loads((ROOT / "data/kospi200-cache.json").read_text())["symbols"]:
        try:
            o = pl.read_parquet(ROOT / f"data/ohlcv/{s}.parquet", columns=["date", "close", "change"]).sort("date").tail(61)
        except Exception:
            continue
        if o.height < 61:
            continue
        c, m = o["close"].to_list(), master.get(s, {})
        rows.append({"s": s, "n": m.get("name", s), "sec": m.get("sector") or m.get("industry") or "", "c": c[-1],
                     "ch": round(o["change"][-1], 2), "cap": (m.get("shares") or 0) * c[-1], "spark": [round(x / c[0], 4) for x in c]})
    out["k200"] = rows
    return out


def logo_png(path: Path):
    im = Image.open(ROOT / "public/nullStock.png").convert("RGB").crop((510, 215, 910, 545)).resize((800, 660), Image.LANCZOS)
    a = np.asarray(im).astype(float)
    lum = (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]) / 255
    alpha = np.clip((lum - 0.2) * 2.2 + 0.18, 0, 1) * (lum > 0.12)  # 검은 배경을 지운다(NullstockLogoMark와 같은 방식)
    Image.fromarray(np.dstack([np.full(lum.shape + (3,), (240, 122, 74)), alpha * 255]).astype("uint8"), "RGBA").save(path)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    d = data_json()
    (out / "data.json").write_text(json.dumps(d, ensure_ascii=False))
    logo_png(out / "logo.png")
    print(f"data.json — KOSPI {d['kospi_daily'][-1][0]}, KOSPI200 {len(d['k200'])}종목 · logo.png")
