"""KG 개념 인식 히트율 실측 하니스 — 시드 확장이 전략 agent 성능에 준 효과를 수치화.

'성능'의 정의(전략 agent가 KG를 읽는 3개 지점과 1:1 대응):
  ① 인식률   — find_concepts가 질의에서 개념을 결정적으로 잡는 비율(LLM/검색 불필요)
  ② 섹터해석률 — resolve_sector_from_text가 정본 섹터까지 닿는 비율(되묻기 생략)
  ③ 종목목록률 — theme_listed_companies가 검증된 종목 유니버스를 내는 비율(종목 지정 백테스트 가능)

어휘 코퍼스 = judal 테마명(사용자들이 실제로 쓰는 테마 어휘의 대용) + 시드 개념명·동의어.
질의 템플릿("{용어} 관련주")로 감싸 실사용 형태로 측정한다.

비교군은 git 이력의 시드 파일을 그대로 로드해 만든다(동일 코퍼스·동일 코드·시드만 교체):
  cd backend && python3 scripts/qa_kg_concept_hits.py [비교할 커밋 해시...]
기본 비교군: e53ae648(감사 전 45노드 시드) vs 워킹트리 현재.

주의: 카탈로그·어휘집 오버레이는 현재 파일로 고정한다 — 시드 효과만 분리 측정.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_BASELINE_COMMITS = ["e53ae648"]  # 누락 연결 감사 시작 전(45노드)
QUERY_TEMPLATE = "{term} 관련주"


def _strip_count_paren(name: str) -> str:
    return re.sub(r"\([^)]*\)$", "", name).strip()


def build_corpus() -> list[str]:
    """judal 테마명(제외 목록 반영 전 원어휘 대용으로 카탈로그 수록분)+현재 시드 용어."""
    terms: set[str] = set()

    catalog = json.loads((BASE_DIR / "data" / "kg-theme-catalog.json").read_text(encoding="utf-8"))
    for theme in catalog.get("themes", []):
        # '반도체 제품(SOC)' 류 괄호 표기는 괄호 안팎을 각각 용어로 취급
        name = theme.get("name", "")
        terms.add(_strip_count_paren(name))
        for inner in re.findall(r"\(([^)]*)\)", name):
            for tok in inner.split("/"):
                if len(tok.strip()) >= 2:
                    terms.add(tok.strip())
        terms.update(s for s in theme.get("synonyms", []) if len(s) >= 2)

    seed = json.loads((BASE_DIR / "data" / "knowledge-graph.json").read_text(encoding="utf-8"))
    for node in seed.get("nodes", []):
        terms.add(node.get("name", ""))
        terms.update(node.get("synonyms", []))

    return sorted(t for t in terms if len(t) >= 2)


def measure(seed_path: Path, corpus: list[str]) -> dict:
    """주어진 시드 파일로 그래프를 재합성해 3개 지표를 측정한다."""
    import engine.knowledge_graph as kg

    original = kg._SEED_PATH
    kg._SEED_PATH = seed_path
    kg._CACHED = None
    try:
        from engine.knowledge_graph import (
            get_graph,
            resolve_sector_from_text,
            theme_listed_companies,
        )

        graph = get_graph()
        n_nodes = sum(1 for nid in graph.nodes if not nid.startswith(("sector:", "company:", "etf:", "theme:", "learned:")))
        recognized = sector_resolved = stock_listed = 0
        seed_hits = catalog_hits = 0
        for term in corpus:
            query = QUERY_TEMPLATE.format(term=term)
            found = graph.find_concepts(query)
            if found:
                recognized += 1
                if found[0]["id"].startswith("theme:"):
                    catalog_hits += 1
                else:
                    seed_hits += 1
            if resolve_sector_from_text(query):
                sector_resolved += 1
            theme = theme_listed_companies(query)
            if theme and theme.get("companies"):
                stock_listed += 1
        total = len(corpus)
        return {
            "seed_concept_nodes": n_nodes,
            "corpus": total,
            "recognized": recognized,
            "recognized_seed": seed_hits,
            "recognized_catalog": catalog_hits,
            "sector_resolved": sector_resolved,
            "stock_listed": stock_listed,
        }
    finally:
        kg._SEED_PATH = original
        kg._CACHED = None


def seed_from_commit(commit: str) -> Path:
    content = subprocess.run(
        ["git", "show", f"{commit}:data/knowledge-graph.json"],
        capture_output=True, text=True, check=True, cwd=BASE_DIR, encoding="utf-8",
    ).stdout
    tmp = Path(tempfile.mkstemp(suffix=f"-seed-{commit}.json")[1])
    tmp.write_text(content, encoding="utf-8")
    return tmp


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:5.1f}%" if d else "n/a"


def main() -> None:
    commits = sys.argv[1:] or DEFAULT_BASELINE_COMMITS
    corpus = build_corpus()
    print(f"코퍼스: {len(corpus)}개 용어(질의 템플릿 '{QUERY_TEMPLATE}')\n")

    rows = []
    for commit in commits:
        rows.append((f"시드@{commit}", measure(seed_from_commit(commit), corpus)))
    rows.append(("시드@현재(워킹트리)", measure(BASE_DIR / "data" / "knowledge-graph.json", corpus)))

    header = f"{'구성':24} {'개념노드':>6} {'①인식':>8} {'(시드/카탈)':>12} {'②섹터해석':>8} {'③종목목록':>8}"
    print(header)
    print("-" * len(header))
    for label, m in rows:
        print(
            f"{label:24} {m['seed_concept_nodes']:>8} "
            f"{pct(m['recognized'], m['corpus']):>8} "
            f"{('(' + str(m['recognized_seed']) + '/' + str(m['recognized_catalog']) + ')'):>12} "
            f"{pct(m['sector_resolved'], m['corpus']):>8} "
            f"{pct(m['stock_listed'], m['corpus']):>8}"
        )

    base, cur = rows[0][1], rows[-1][1]
    print("\n=== 시드 확장 효과(첫 비교군 → 현재) ===")
    for key, name in [("recognized", "① 결정적 인식"), ("sector_resolved", "② 섹터 해석"),
                      ("stock_listed", "③ 종목 목록")]:
        delta = cur[key] - base[key]
        print(f"{name}: {base[key]} → {cur[key]}  ({'+' if delta >= 0 else ''}{delta}건, "
              f"{pct(base[key], base['corpus'])} → {pct(cur[key], cur['corpus'])})")


if __name__ == "__main__":
    main()
