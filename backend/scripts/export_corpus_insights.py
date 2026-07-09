"""코퍼스 백테스트 결과를 AI 리포트 비교용 컴팩트 데이터로 내보낸다.

Chroma 벡터스토어(backtest_results 컬렉션, build_strategy_corpus.py 산출물)에서
전략 DSL(document) + 실측 지표(metadata)를 꺼내 gzip JSONL로 저장한다.
산출물(advisor/corpus_insights_data.jsonl.gz)은 git에 커밋되어 프로덕션/CI에서도
Chroma 없이 코퍼스 비교(advisor/corpus_insights.py)가 동작하게 한다.

사용:
    python backend/scripts/export_corpus_insights.py
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

_METRIC_KEYS = (
    "total_return", "cagr", "mdd", "volatility", "win_rate",
    "sharpe", "sortino", "calmar", "profit_factor", "trade_count",
    "average_holding_days",
)


def _extract_dsl(document: str) -> dict | None:
    """문서('Strategy DSL: {json}...')에서 첫 JSON 오브젝트를 중괄호 균형으로 추출한다."""
    start = document.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(document)):
        ch = document[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(document[start:idx + 1])
                except json.JSONDecodeError:
                    return None
    return None


def main() -> None:
    import chromadb

    chroma_path = os.getenv("ADVISOR_CHROMA_PATH") or str(_BACKEND_DIR / "advisor" / ".chroma")
    out_path = _BACKEND_DIR / "advisor" / "corpus_insights_data.jsonl.gz"

    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_collection("backtest_results")
    got = collection.get(include=["metadatas", "documents"])

    rows = []
    for metadata, document in zip(got["metadatas"], got["documents"]):
        dsl = _extract_dsl(document or "")
        if dsl is None:
            continue
        metrics = {}
        for key in _METRIC_KEYS:
            value = metadata.get(key)
            try:
                metrics[key] = float(value)
            except (TypeError, ValueError):
                continue
        if "cagr" not in metrics or "mdd" not in metrics:
            continue
        rows.append({
            "strategy_hash": metadata.get("strategy_hash") or "",
            "metrics": metrics,
            "strategy_dsl": dsl,
        })

    with gzip.open(out_path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(f"[export] {len(rows)}행 → {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
