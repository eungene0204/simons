"""종목 분석 품질 검수 (샘플링) — 인프라 게이트 스캐폴드.

과제 6. 전 종목을 사람이 검수할 수 없으므로 그룹별로 샘플링해 종목 분석 결과의
품질을 점검한다. 살아있는 백엔드(/stock/analyze)·MLX LLM·뉴스 DB·parquet 가
필요하므로 CI 에선 결정적으로 못 돈다 → 서버가 없으면 정상 종료(skip)한다.

샘플 그룹(로컬 parquet 로 계산 가능한 것 위주):
  대형주/소형주(가용 시), 거래량 하위, 적자(ROE<0), 최근 급등/급락, 무작위(수동검수)

품질 자동 점검(휴리스틱 — 사람 검수 보조용 플래그):
  종목명/티커 일치 · 가격데이터 활용 · 재무데이터 활용 · 뉴스 활용 · 리스크 설명 ·
  데이터부족 시 솔직한가 · 환각(없는 시가총액을 숫자로 언급 등) 의심

실행: python scripts/qa_stock_analysis_quality.py [--n 3] [--backend http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("POLARS_MAX_THREADS", "1")

from stock_analysis.stock_master import by_ticker, load_master  # noqa: E402

OHLCV_DIR = ROOT / "data" / "ohlcv"


def _ping(backend: str) -> bool:
    try:
        urllib.request.urlopen(f"{backend}/docs", timeout=3)
        return True
    except Exception:
        try:
            urllib.request.urlopen(backend, timeout=3)
            return True
        except Exception:
            return False


def _analyze(backend: str, ticker: str) -> dict | None:
    data = json.dumps({"symbol": ticker}).encode()
    req = urllib.request.Request(
        f"{backend}/stock/analyze", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}", "_body": e.read().decode(errors="ignore")[:200]}
    except Exception as e:
        return {"_error": str(e)}


# ── 샘플링 ───────────────────────────────────────────────────────────────
def _available_tickers() -> set[str]:
    if not OHLCV_DIR.exists():
        return set()
    return {p.stem for p in OHLCV_DIR.glob("*.parquet")}


def _sample_groups(n: int) -> dict[str, list[str]]:
    """parquet 가 있는 종목을 그룹별로 n개씩 샘플링. 계산 불가 그룹은 무작위(수동검수)."""
    avail = _available_tickers()
    master = [e for e in load_master() if e.ticker in avail]
    random.seed(20260612)
    if not master:
        return {}

    import polars as pl

    pool = random.sample(master, min(len(master), 400))
    rows: list[tuple[str, float, float, float]] = []  # ticker, recent_return, volume, roe
    for e in pool:
        try:
            df = pl.read_parquet(OHLCV_DIR / f"{e.ticker}.parquet").tail(20)
            if df.height < 5:
                continue
            close = df["close"].to_list()
            ret = (close[-1] / close[0] - 1.0) * 100 if close[0] else 0.0
            vol = float(df["volume"].mean() or 0)
            roe = float(df["roe_or_gpa"].tail(1).item()) if "roe_or_gpa" in df.columns else 0.0
            rows.append((e.ticker, ret, vol, roe))
        except Exception:
            continue

    if not rows:
        return {"무작위": [e.ticker for e in random.sample(master, min(n, len(master)))]}

    by_ret = sorted(rows, key=lambda r: r[1])
    by_vol = sorted(rows, key=lambda r: r[2])
    return {
        "최근_급락": [r[0] for r in by_ret[:n]],
        "최근_급등": [r[0] for r in by_ret[-n:]],
        "거래량_하위": [r[0] for r in by_vol[:n]],
        "적자_의심(ROE<0)": [r[0] for r in rows if r[3] < 0][:n],
        "무작위_수동검수": [r[0] for r in random.sample(rows, min(n, len(rows)))],
    }


# ── 품질 점검 ─────────────────────────────────────────────────────────────
def _check(ticker: str, res: dict) -> dict:
    master = by_ticker(ticker)
    metrics = res.get("metrics") or {}
    signals = res.get("signals") or {}
    expl = res.get("explanation") or ""
    missing = res.get("missing_data") or []
    rec = res.get("recommendation")

    flags: list[str] = []
    name_ok = master is not None and res.get("name") == master.stock_name
    ticker_ok = res.get("symbol") == ticker
    if not name_ok:
        flags.append(f"종목명 불일치(got={res.get('name')}, expect={master.stock_name if master else '?'})")
    if not ticker_ok:
        flags.append(f"티커 불일치(got={res.get('symbol')})")

    price_used = metrics.get("current_price") is not None
    fin_used = any(metrics.get(k) is not None for k in ("per", "pbr", "roe", "debt_ratio"))
    news_used = bool(res.get("news_summary")) or signals.get("news_sentiment") is not None
    risk_explained = bool(res.get("risk_factors")) or signals.get("risk") is not None

    # 솔직함: 데이터 부족이면 INSUFFICIENT_DATA + missing_data 명시해야 함
    honest = True
    if rec == "INSUFFICIENT_DATA" and not missing:
        honest = False
        flags.append("INSUFFICIENT_DATA 인데 missing_data 비어있음(불성실)")

    # 환각 휴리스틱: 없는 시가총액을 숫자로 언급
    if metrics.get("market_cap") is None and re.search(r"시가총액[^.]{0,8}[\d조억]", expl):
        flags.append("환각의심: 없는 시가총액을 수치로 언급")
    # missing 인 지표를 설명이 단정적으로 수치 언급
    for label, key in [("PER", "per"), ("PBR", "pbr"), ("ROE", "roe")]:
        if metrics.get(key) is None and re.search(rf"{label}\s*\d", expl):
            flags.append(f"환각의심: 없는 {label} 를 수치로 언급")

    return {
        "ticker": ticker,
        "name": res.get("name"),
        "recommendation": rec,
        "confidence": res.get("confidence"),
        "name_ok": name_ok,
        "ticker_ok": ticker_ok,
        "price_used": price_used,
        "fin_used": fin_used,
        "news_used": news_used,
        "risk_explained": risk_explained,
        "honest_missing": honest,
        "missing_data": missing,
        "flags": flags,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=3, help="그룹당 샘플 수")
    ap.add_argument("--out", default="docs/stock_analysis_quality_report.md")
    args = ap.parse_args()

    if not _ping(args.backend):
        print(
            f"[SKIP] 백엔드({args.backend}) 미응답 — 품질 검수는 살아있는 서버가 필요합니다.\n"
            "       서버 기동: KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 POLARS_MAX_THREADS=1 "
            "uvicorn main:app (backend/) 후 재실행.",
            file=sys.stderr,
        )
        return 0  # 인프라 없음은 실패가 아니라 skip

    groups = _sample_groups(args.n)
    if not groups:
        print("[SKIP] 로컬 parquet(data/ohlcv) 가 없어 샘플링 불가.", file=sys.stderr)
        return 0

    lines = ["# 종목 분석 품질 검수 리포트 (샘플링)\n", f"- 백엔드: {args.backend}\n"]
    total_flags = 0
    for group, tickers in groups.items():
        lines.append(f"\n## {group} ({len(tickers)}종목)\n")
        for t in tickers:
            res = _analyze(args.backend, t)
            if res is None or "_error" in (res or {}):
                lines.append(f"- `{t}` ❌ 호출 실패: {res.get('_error') if res else 'None'}")
                continue
            c = _check(t, res)
            total_flags += len(c["flags"])
            badge = "🚩" if c["flags"] else "✅"
            used = "".join(k for k, v in [("가", c["price_used"]), ("재", c["fin_used"]),
                                          ("뉴", c["news_used"]), ("리", c["risk_explained"])] if v)
            lines.append(
                f"- {badge} `{t}` {c['name']} — {c['recommendation']}(conf={c['confidence']}) "
                f"[활용:{used or '없음'}] missing={c['missing_data']}"
            )
            for f in c["flags"]:
                lines.append(f"    - ⚠️ {f}")

    lines.append(f"\n---\n총 플래그: **{total_flags}건** (사람 검수 필요 항목)")
    out = ROOT / args.out
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"리포트 저장: {out} (플래그 {total_flags}건)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
