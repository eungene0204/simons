#!/usr/bin/env python3
"""LangSmith Dataset 업로드·갱신 — 전략 대화 Agent 대표 입력 21개.

    python scripts/langsmith_dataset.py --dry-run   # 전송 없이 내용만 확인
    python scripts/langsmith_dataset.py             # 업로드(멱등 — 있으면 갱신)

필요 환경변수: LANGSMITH_API_KEY (LANGSMITH_ENDPOINT는 self-hosted일 때만).
LANGSMITH_TRACING과 무관하다 — 이 스크립트는 추적이 꺼져 있어도 동작한다.

**외부 전송이다.** --dry-run 없이 실행하면 데이터셋 입력이 LangSmith로 나간다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# 키·리전은 .env가 정본이다(백엔드는 main.py가 같은 파일을 읽는다). 이걸 빼면 셸에
# export한 사람만 쓸 수 있고, 그러지 않으면 "API_KEY가 없습니다"로 끝난다.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from observability.dataset import (  # noqa: E402
    DATASET_NAME,
    EXAMPLES,
    as_langsmith_examples,
)


def _print_preview() -> None:
    print(f"Dataset: {DATASET_NAME}  ({len(EXAMPLES)}개 예시)\n")
    by_category: dict = {}
    for row in as_langsmith_examples():
        by_category.setdefault(row["metadata"].get("category", "기타"), []).append(row)
    for category, rows in sorted(by_category.items()):
        print(f"[{category}]")
        for row in rows:
            labels = {k: v for k, v in row["metadata"].items()
                      if k not in ("category",) and v}
            print(f"  · {row['inputs']['user_input']}")
            if labels:
                print(f"      {json.dumps(labels, ensure_ascii=False)}")
        print()


def _upload() -> int:
    if not os.environ.get("LANGSMITH_API_KEY"):
        print("LANGSMITH_API_KEY가 없습니다 — 업로드할 수 없습니다.", file=sys.stderr)
        return 1
    from langsmith import Client

    client = Client()
    rows = as_langsmith_examples()

    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        existing = {
            (example.inputs or {}).get("user_input"): example
            for example in client.list_examples(dataset_id=dataset.id)
        }
        print(f"기존 데이터셋 갱신 | id={dataset.id} 기존 예시={len(existing)}개")
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="널스탁 전략 대화 Agent 대표 입력 — 유니버스별 생성·수정·"
                        "대화 제어·규제 게이트·테마 해석",
        )
        existing = {}
        print(f"데이터셋 생성 | id={dataset.id}")

    created = updated = 0
    for row in rows:
        user_input = row["inputs"]["user_input"]
        found = existing.get(user_input)
        if found is None:
            client.create_example(
                dataset_id=dataset.id, inputs=row["inputs"],
                outputs=row["outputs"] or None, metadata=row["metadata"],
            )
            created += 1
        else:
            client.update_example(
                example_id=found.id, inputs=row["inputs"],
                outputs=row["outputs"] or None, metadata=row["metadata"],
            )
            updated += 1
    print(f"완료 — 생성 {created}건, 갱신 {updated}건")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="전송 없이 업로드될 내용만 출력")
    args = parser.parse_args()
    _print_preview()
    if args.dry_run:
        print("--dry-run — 전송하지 않았습니다.")
        return 0
    return _upload()


if __name__ == "__main__":
    raise SystemExit(main())
