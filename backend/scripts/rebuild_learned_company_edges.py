"""학습 어휘집의 related_company 엣지를 네이버 금융 분류 기반으로 재구축한다(마이그레이션).

FR-STR-071 개정(2026-07-27 사용자 지시): 관련 기업 엣지는 뉴스 동시언급이 아니라
네이버 금융 분류 수록 종목으로 만들고 자동 verified로 등록한다. 이 스크립트는 개정
이전에 뉴스 검색으로 학습된 기존 항목('다이어트' 노이즈 사고)을 새 계약으로 재구축한다:
  - pending 기업 엣지 제거(뉴스 동시언급 노이즈)
  - verified·rejected 기업 엣지 보존(콘솔 결정·출처 교차지지 존중, rejected 부활 금지)
  - 네이버 분류 매핑(LLM이 분류 이름 닫힌 목록에서 선택 — engine.term_grounding.
    _naver_company_edges 재사용)으로 수록 종목을 verified 편입
개념 엣지(related_to 등)는 건드리지 않는다. 재실행해도 같은 결과(멱등).

실행: cd backend && python3 scripts/rebuild_learned_company_edges.py [--dry-run] [--only 용어]
로컬 Ollama(STRATEGY_INTERPRETER_MODEL) 필요 — dev는 `ollama serve` 선행.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _ollama_chat(system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
    """신규 Ollama 호출 규약 — /api/chat + think:false(<think> 누출 사고 재발 방지).

    num_ctx는 앱 추론 본경로와 같은 값을 쓴다(FR-STR-019o ⑥) — 같은 9B 슬롯이라
    다른 값을 보내면 dev 서버가 keep_alive=-1로 고정해 둔 러너를 갈아끼우려다
    이 스크립트가 무한 대기한다.
    """
    from engine.nl_parser import _OLLAMA_NUM_CTX

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("STRATEGY_INTERPRETER_MODEL", "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M")
    body = json.dumps({
        "model": model, "stream": False, "think": False,
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_msg}],
        "options": {"temperature": 0, "num_predict": max_tokens,
                    "num_ctx": _OLLAMA_NUM_CTX},
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    return (data.get("message") or {}).get("content", "")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    from engine import term_grounding as tg
    from engine.naver_theme_live import fetch_group_index

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="저장 없이 변경 내용만 출력")
    ap.add_argument("--only", help="이 용어 하나만 재구축")
    args = ap.parse_args()

    path = tg._LEXICON_PATH
    lexicon = tg._load_lexicon(path)
    groups = fetch_group_index()
    print(f"네이버 분류 {len(groups)}개 수집, 어휘집 {len(lexicon)}항목")

    for key, entry in lexicon.items():
        if args.only and key != tg._term_key(args.only):
            continue
        term = entry.get("term") or key
        old = entry.get("edges") or []
        old_company = [e for e in old if e.get("type") == "related_company"]
        keep = [e for e in old
                if e.get("type") != "related_company"
                or e.get("status") in ("verified", "rejected")]
        new_edges = tg._naver_company_edges(term, entry.get("definition"), groups, _ollama_chat)
        seen = {e.get("target") for e in keep if e.get("type") == "related_company"}
        added = [e for e in new_edges if e["target"] not in seen]
        dropped = len(old) - len(keep)
        print(f"- {term}: 기업엣지 {len(old_company)}개 → pending 제거 {dropped}, "
              f"네이버 편입 {len(added)} (유지 {len(old_company) - dropped})")
        if not args.dry_run:
            entry["edges"] = keep + added
            tg._save_entry(path, key, entry)

    if args.dry_run:
        print("dry-run — 저장하지 않음")


if __name__ == "__main__":
    main()
