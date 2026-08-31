"""prod(x86 로컬 엔진) ↔ Modal CPU 워커 백테스트 결과 동일성 게이트.

백테스트 실행 장소를 Vultr 박스 → Modal 워커로 옮겨도 답이 바뀌지 않는지
실제 데이터로 전수 대조한다. 전략 픽스처는 기존 동일성 게이트
(qa_backtest_equivalence.build_strategies)를 재사용한다.

2단계 사용 (기준측과 대조측이 같은 요청을 쓰도록 요청 자체를 덤프에 내장한다):
  1) 기준 덤프 — **prod 박스(x86·정본 데이터)에서** 실행:
       python3 scripts/qa_backtest_modal_equivalence.py --dump /tmp/eq_dump.json [--symbols 120] [--only rsi,ma]
  2) 대조 — 아무 곳에서(MODAL_KEY/MODAL_SECRET env 필요):
       python3 scripts/qa_backtest_modal_equivalence.py --compare /tmp/eq_dump.json \
           --url https://<org>--simons-backtest-run-backtest.modal.run

종료 코드: 불일치·에러가 하나라도 있으면 1.

주의: 로컬 Mac(ARM)에서 --dump 하면 x86과의 ULP 차이(알려진 노이즈)로 미세 불일치가
날 수 있다 — 기준 덤프는 반드시 x86(prod 컨테이너)에서 뜬다.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import qa_backtest_equivalence as eq  # noqa: E402


def normalize(res: dict) -> dict:
    """Modal 워커의 응답 경로(json round-trip, numpy→float)와 같은 정규화를 양쪽에 적용."""
    return json.loads(json.dumps(res, default=float))


def to_comparable(res: dict) -> str:
    return eq.comparable(normalize(res), drop_rebalance=False)


def _prune_volatile(obj):
    """실행 시간류 필드 제거(잡 결과 대조용) — 값 자체는 결정적이어야 한다."""
    if isinstance(obj, dict):
        return {k: _prune_volatile(v) for k, v in obj.items()
                if not any(t in k.lower() for t in ("elapsed", "timing", "executiontime", "duration"))}
    if isinstance(obj, list):
        return [_prune_volatile(v) for v in obj]
    return obj


def job_comparable(res: dict) -> str:
    return json.dumps(_prune_volatile(normalize(res)), sort_keys=True, default=str, ensure_ascii=False)


# 잡 픽스처 — 기존 게이트(qa_backtest_equivalence --wfa)와 같은 전략·범위 조합.
WFA_FIXTURES = [("rsi", {"risk.stop_loss_pct": [5, 10]}),
                ("ma_cross", {"risk.stop_loss_pct": [5, 10]})]
OPT_FIXTURE = ("rsi", {"risk.stop_loss_pct": [5, 10]}, "sharpe", 5)


def build_job_requests(strategies: dict) -> dict:
    """이름 → {kind, payload}. payload는 워커 계약과 동일(요청 재생을 위해 덤프에 내장)."""
    jobs = {}
    for name, ranges in WFA_FIXTURES:
        if name in strategies:
            jobs[f"wfa:{name}"] = {"kind": "wfa", "payload": {
                "base_request": strategies[name], "ranges": ranges,
                "method": "grid", "n_splits": 3, "train_pct": 0.6}}
    opt_name, opt_ranges, metric, trials = OPT_FIXTURE
    if opt_name in strategies:
        jobs[f"opt:{opt_name}"] = {"kind": "opt", "payload": {
            "base_request": strategies[opt_name], "user_prompt": None,
            "ranges": opt_ranges, "target_metric": metric, "n_trials": trials}}
    return jobs


def run_job_local(engine, kind: str, payload: dict) -> dict:
    if kind == "wfa":
        from engine.walk_forward import WalkForwardAnalyzer

        kwargs = {k: v for k, v in payload.items()}
        return WalkForwardAnalyzer(engine).analyze(**kwargs)
    from ai.local_optimization_agent import LocalOptimizationAgent

    return LocalOptimizationAgent(engine).run_optimization_loop(**payload)


JOB_SLUG = {"wfa": "run-walk-forward", "opt": "run-optimize"}


def do_dump(path: str, n_symbols: int, only: str, jobs: bool = False) -> int:
    from backtest_engine import BacktestEngine

    kospi200 = json.load(open(ROOT / "data" / "kospi200-cache.json"))["symbols"]
    symbols = kospi200[:n_symbols]
    strategies = eq.build_strategies(symbols, kospi200)
    if only:
        keys = [k.strip() for k in only.split(",") if k.strip()]
        strategies = {n: r for n, r in strategies.items() if any(k in n for k in keys)}

    os.environ["BACKTEST_PHASE1_WORKERS"] = "1"  # 기준은 단일 경로(풀 동일성은 기존 게이트가 보증)
    engine = BacktestEngine()
    out = {}

    if jobs:
        # 잡 모드: 최적화·워크포워드 픽스처만 덤프(단일 실행 동일성은 기본 모드가 담당)
        os.environ["WALK_FORWARD_WORKERS"] = "1"
        job_reqs = build_job_requests(strategies)
        print(f"[EQ-MODAL] 잡 기준 덤프: {len(job_reqs)}개 · 종목 {n_symbols}", flush=True)
        for name, row in job_reqs.items():
            t0 = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                res = run_job_local(engine, row["kind"], dict(row["payload"]))
            out[name] = {"kind": row["kind"], "payload": normalize(row["payload"]),
                         "comparable": job_comparable(res), "status": res.get("status")}
            print(f"[EQ-MODAL] dump {name:28s} status={res.get('status')} {time.time()-t0:6.1f}s", flush=True)
    else:
        print(f"[EQ-MODAL] 기준 덤프: 전략 {len(strategies)}개 · 종목 {n_symbols}", flush=True)
        for name, req in strategies.items():
            t0 = time.time()
            res = eq.run_quiet(engine, req)
            out[name] = {
                "request": normalize(req),
                "comparable": to_comparable(res),
                "trades": int(res.get("trades") or 0),
            }
            print(f"[EQ-MODAL] dump {name:28s} trades={out[name]['trades']:>5} {time.time()-t0:5.1f}s", flush=True)
    Path(path).write_text(json.dumps(out, ensure_ascii=False))
    print(f"[EQ-MODAL] saved → {path}", flush=True)
    return 0


def do_compare(path: str, url: str) -> int:
    import httpx

    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    headers = {"Modal-Key": key, "Modal-Secret": secret} if key and secret else {}
    dump = json.loads(Path(path).read_text())
    failures = 0
    print(f"[EQ-MODAL] 대조: 전략 {len(dump)}개 → {url}", flush=True)
    for name, row in dump.items():
        t0 = time.time()
        try:
            if "kind" in row:  # 잡 픽스처 — 함수 슬러그 치환 URL로 전송
                job_url = url.replace("run-backtest", JOB_SLUG[row["kind"]])
                resp = httpx.post(job_url, json=row["payload"], headers=headers,
                                  timeout=httpx.Timeout(connect=60.0, read=3800.0, write=120.0, pool=60.0))
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                remote = job_comparable(resp.json())
            else:
                resp = httpx.post(url, json=row["request"], headers=headers,
                                  timeout=httpx.Timeout(connect=60.0, read=700.0, write=120.0, pool=60.0))
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                remote = to_comparable(resp.json())
            same = remote == row["comparable"]
        except Exception as exc:
            failures += 1
            print(f"[EQ-MODAL] FAIL {name:28s} ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        mark = "OK " if same else "FAIL"
        note = " (거래 없음)" if row.get("trades") == 0 else ""
        detail = f"trades={row['trades']:>5}" if "trades" in row else f"status={row.get('status')}"
        print(f"[EQ-MODAL] {mark} {name:28s} {detail} {time.time()-t0:6.1f}s{note}", flush=True)
        if not same:
            failures += 1
            print(f"       diff {eq.first_diff(row['comparable'], remote)}", flush=True)
    print(f"[EQ-MODAL] {'불일치/에러 ' + str(failures) + '건' if failures else '전수 일치'}", flush=True)
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", type=str, default="")
    ap.add_argument("--compare", type=str, default="")
    ap.add_argument("--url", type=str, default="")
    ap.add_argument("--symbols", type=int, default=120)
    ap.add_argument("--only", type=str, default="")
    ap.add_argument("--jobs", action="store_true",
                    help="최적화·워크포워드 잡 픽스처 모드(덤프 시에만 의미 — 대조는 덤프 내용을 따름)")
    args = ap.parse_args()
    if args.dump:
        return do_dump(args.dump, args.symbols, args.only, jobs=args.jobs)
    if args.compare:
        if not args.url:
            print("--compare 에는 --url 이 필요합니다", file=sys.stderr)
            return 2
        return do_compare(args.compare, args.url)
    print("--dump 또는 --compare 중 하나를 지정하세요", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
