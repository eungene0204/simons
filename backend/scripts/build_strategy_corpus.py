"""코치 RAG 벡터 코퍼스 오프라인 빌드.

전략 생성(AI 제외) → 현행 엔진으로 백테스트(병렬, 체크포인트 재개) →
bge-m3 임베딩 → ChromaDB 적재(기존 컬렉션 하드 삭제 후 재구축).

사용:
    KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
        python backend/scripts/build_strategy_corpus.py --count 2000 --workers 8

중단 시 같은 명령으로 재실행하면 체크포인트(백테스트 결과)부터 이어서 진행한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 엔진 데드락 가드(없으면 polars/omp 기동 데드락). 워커 spawn에도 상속되도록 import 전에 설정.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from corpus.generator import generate_strategies  # noqa: E402
from corpus.nl_templates import render_description  # noqa: E402
from engine.nl_parser import ParsedStrategy  # noqa: E402
from engine.strategy_converter import _load_universe, to_backtest_request  # noqa: E402
from vector_memory.identity import strategy_hash_for  # noqa: E402


# ── 메트릭 추출(엔진 결과 퍼센트 → 분수 통일) ────────────────────────────────
# 엔진은 cagr/mdd/volatility/winRate/totalReturn을 퍼센트로 반환한다. riskLevel 임계
# (normalization._risk_level: MDD<=-0.30, vol>=0.35)와 정합하도록 분수로 통일한다.
# sharpe/sortino/calmar/profit_factor는 비율이라 그대로 둔다.

def _extract_metrics(res: Dict[str, Any]) -> Dict[str, Any]:
    def pct(key: str) -> float:
        try:
            return float(res.get(key) or 0.0) / 100.0
        except (TypeError, ValueError):
            return 0.0

    win = res.get("winRate") or 0.0
    try:
        win = float(win)
    except (TypeError, ValueError):
        win = 0.0
    win = win / 100.0 if win > 1.0 else win  # 퍼센트/분수 양쪽 방어

    def raw(key: str) -> float:
        try:
            return float(res.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "total_return": pct("totalReturn"),
        "cagr": pct("cagr"),
        "mdd": pct("maxDrawdown"),
        "volatility": pct("volatility"),
        "win_rate": win,
        "sharpe": raw("sharpe"),
        "sortino": raw("sortino"),
        "calmar": raw("calmar"),
        "profit_factor": raw("profitFactor"),
        "trade_count": int(raw("trades")),
        "average_holding_days": raw("avgHoldingDays"),
    }


# ── 백테스트 워커(멀티프로세싱) ──────────────────────────────────────────────

_ENGINE = None


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        from backtest_engine import BacktestEngine

        _ENGINE = BacktestEngine()
    return _ENGINE


def _backtest_one(task: Tuple[Dict[str, Any], List[str]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """(strategy_dict, symbols) → (strategy_hash, metrics 또는 None)."""
    strategy_dict, symbols = task
    h = strategy_hash_for(strategy_dict)
    try:
        strategy = ParsedStrategy.model_validate(strategy_dict)
        req = to_backtest_request(strategy, resolve_symbols=False)
        req["symbols"] = symbols
        req["symbol_count"] = len(symbols)
        req["symbols_resolved"] = True
        res = _get_engine().run_backtest(req)
        if not isinstance(res, dict):
            return h, None
        return h, _extract_metrics(res)
    except Exception as exc:  # noqa: BLE001 — 개별 실패는 건너뛰고 계속
        return h, {"_error": str(exc)[:200]}


# ── 심볼 해석 캐시 ────────────────────────────────────────────────────────────

def _universe_key(universe: List[str]) -> str:
    return "_".join(sorted(universe)) if universe else "KOSPI200"


def _resolve_universe_symbols(strategies: List[ParsedStrategy]) -> Dict[str, List[str]]:
    keys = {_universe_key(s.universe) for s in strategies}
    cache: Dict[str, List[str]] = {}
    for key in sorted(keys):
        markets = key.split("_")
        print(f"[corpus] 유니버스 심볼 해석: {key} ...", flush=True)
        cache[key] = _load_universe(markets)
        print(f"[corpus]   → {len(cache[key])}종목", flush=True)
    return cache


# ── 체크포인트 ────────────────────────────────────────────────────────────────

def _load_checkpoint(path: Path) -> Dict[str, Dict[str, Any]]:
    done: Dict[str, Dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                done[row["strategy_hash"]] = row["metrics"]
            except (json.JSONDecodeError, KeyError):
                continue
    return done


# ── 임베딩 + 적재 ─────────────────────────────────────────────────────────────

async def _embed_and_store(
    strategies: List[ParsedStrategy],
    metrics_by_hash: Dict[str, Dict[str, Any]],
    chroma_path: Path,
    *,
    batch_size: int = 128,
) -> int:
    from vector_memory import (
        ChromaVectorMemoryRepository,
        VectorMemoryService,
        normalize_backtest_result,
    )
    from vector_memory.embedding import BgeM3EmbeddingClient

    # 기존 컬렉션 하드 삭제 후 재구축(사용자 확정).
    if chroma_path.exists():
        print(f"[corpus] 기존 벡터스토어 하드 삭제: {chroma_path}", flush=True)
        shutil.rmtree(chroma_path)

    service = VectorMemoryService(
        repository=ChromaVectorMemoryRepository(persist_path=chroma_path),
        embedding_client=BgeM3EmbeddingClient(),
    )

    records = []
    for strategy in strategies:
        h = strategy_hash_for(strategy.model_dump())
        metrics = metrics_by_hash.get(h)
        if not metrics or "_error" in metrics:
            continue
        dsl = strategy.model_dump()
        dsl["description"] = ""  # NL 텍스트는 strategySummary로, DSL은 구조만.
        records.append(
            normalize_backtest_result(
                strategy_dsl=dsl,
                metrics=metrics,
                strategy_summary=render_description(strategy),
            )
        )

    stored = 0
    for start in range(0, len(records), batch_size):
        chunk = records[start : start + batch_size]
        await service.upsert_backtest_memories(chunk)
        stored += len(chunk)
        print(f"[corpus] 적재 {stored}/{len(records)}", flush=True)
    return stored


# ── 메인 ──────────────────────────────────────────────────────────────────────

def _default_chroma_path() -> Path:
    configured = os.getenv("ADVISOR_CHROMA_PATH")
    if configured:
        return Path(configured)
    return _BACKEND_DIR / "advisor" / ".chroma"


def main() -> None:
    parser = argparse.ArgumentParser(description="코치 RAG 벡터 코퍼스 빌드(bge-m3)")
    parser.add_argument("--count", type=int, default=2000, help="생성할 고유 전략 수")
    parser.add_argument("--workers", type=int, default=8, help="백테스트 병렬 워커 수")
    parser.add_argument("--seed", type=int, default=42, help="생성 시드(재현성)")
    parser.add_argument("--chroma-path", type=str, default=None, help="ChromaDB 경로")
    parser.add_argument("--checkpoint", type=str, default=None, help="백테스트 체크포인트 jsonl")
    parser.add_argument("--skip-backtest", action="store_true", help="체크포인트만으로 적재(백테스트 생략)")
    args = parser.parse_args()

    chroma_path = Path(args.chroma_path) if args.chroma_path else _default_chroma_path()
    checkpoint = Path(args.checkpoint) if args.checkpoint else _BACKEND_DIR / "advisor" / "corpus_backtests.jsonl"
    started = time.time()

    print(f"[corpus] 전략 {args.count}개 생성(seed={args.seed}) ...", flush=True)
    strategies = generate_strategies(args.count, seed=args.seed)
    print(f"[corpus] 고유 전략 {len(strategies)}개", flush=True)

    done = _load_checkpoint(checkpoint)
    print(f"[corpus] 체크포인트 기보유: {len(done)}건", flush=True)

    if not args.skip_backtest:
        symbol_cache = _resolve_universe_symbols(strategies)
        pending = [s for s in strategies if strategy_hash_for(s.model_dump()) not in done]
        print(f"[corpus] 백테스트 대상 {len(pending)}건 (워커 {args.workers})", flush=True)

        tasks = [
            (s.model_dump(), symbol_cache[_universe_key(s.universe)])
            for s in pending
        ]
        completed = 0
        with checkpoint.open("a", encoding="utf-8") as ckpt:
            with Pool(processes=args.workers) as pool:
                for h, metrics in pool.imap_unordered(_backtest_one, tasks, chunksize=4):
                    if metrics is None:
                        metrics = {"_error": "no result"}
                    done[h] = metrics
                    ckpt.write(json.dumps({"strategy_hash": h, "metrics": metrics}, ensure_ascii=False) + "\n")
                    ckpt.flush()
                    completed += 1
                    if completed % 50 == 0:
                        elapsed = time.time() - started
                        print(f"[corpus] 백테스트 {completed}/{len(pending)} ({elapsed:.0f}s)", flush=True)

        errors = sum(1 for m in done.values() if "_error" in m)
        print(f"[corpus] 백테스트 완료. 오류 {errors}건", flush=True)

    stored = asyncio.run(_embed_and_store(strategies, done, chroma_path))
    print(f"[corpus] 완료: {stored}건 적재, 총 {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
