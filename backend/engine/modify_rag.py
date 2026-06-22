"""수정 요청 → 동적 few-shot 검색 (RAG)

코퍼스 소스 (병합·dedup):
  1) 합성 코퍼스: engine/data/modify_examples.json (build_modify_corpus.py 생성, 커밋됨)
  2) 학습 코퍼스: <repo>/data/modify_corpus/learned.jsonl (런타임 누적, bind-mount 영속)
합성 JSON이 없으면 하드코딩 _MODIFY_EXAMPLES로 폴백한다(테스트/초기 상태).
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

# ── 학습 기록 대상 필드 (스칼라/enum/유니버스 — 단순 수정 카테고리) ──────────────
# fundamental_filters / entry_signals / exit_signals / description 등 구조화 필드는
# 검색 적합도를 떨어뜨리고 코퍼스를 비대하게 만드므로 학습 기록에서 제외한다.
_SIMPLE_FIELDS = {
    "universe",
    "max_positions",
    "hold_period_days",
    "rebalancing_period",
    "stop_loss_pct",
    "take_profit_pct",
    "trailing_stop_pct",
    "max_mdd_limit_pct",
    "backtest_period",
    "backtest_start_date",
    "backtest_end_date",
    "initial_capital",
    "ranking_lookback_days",
    "fee_rate",
    "slippage_rate",
    "execution_timing",
}

_FIELD_TO_CATEGORY = {
    "max_positions": "max_positions",
    "initial_capital": "initial_capital",
    "stop_loss_pct": "stop_loss",
    "take_profit_pct": "take_profit",
    "trailing_stop_pct": "trailing_stop",
    "max_mdd_limit_pct": "max_mdd",
    "hold_period_days": "hold_period",
    "rebalancing_period": "rebalancing",
    "universe": "universe",
    "backtest_period": "backtest_period",
    "backtest_start_date": "backtest_dates",
    "backtest_end_date": "backtest_dates",
    "ranking_lookback_days": "ranking",
    "fee_rate": "fee",
    "slippage_rate": "slippage",
    "execution_timing": "execution",
}

# 학습 코퍼스 상한(in-memory 코퍼스 크기 기준) — 무한 증식 방지.
_MAX_CORPUS = 3000

_SYNTHETIC_PATH = Path(__file__).parent / "data" / "modify_examples.json"


def _learned_path() -> Path:
    env = os.getenv("MODIFY_CORPUS_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "modify_corpus" / "learned.jsonl"


# 합성 JSON이 없을 때의 폴백 시드 (테스트 호환을 위해 이름 유지).
_MODIFY_EXAMPLES = [
    {"request": "종목을 10개로 줄여줘", "category": "max_positions", "output": {"max_positions": 10}},
    {"request": "최대 20종목으로 설정", "category": "max_positions", "output": {"max_positions": 20}},
    {"request": "초기자금 1억으로 바꿔줘", "category": "initial_capital", "output": {"initial_capital": 100000000.0}},
    {"request": "자금을 5억으로", "category": "initial_capital", "output": {"initial_capital": 500000000.0}},
    {"request": "트레일링 스탑 15%로 설정해줘", "category": "trailing_stop", "output": {"trailing_stop_pct": 15.0}},
    {"request": "최고가 대비 10% 하락 시 청산", "category": "trailing_stop", "output": {"trailing_stop_pct": 10.0}},
    {"request": "KOSPI200으로 진행", "category": "universe", "output": {"universe": ["KOSPI200"]}},
    {"request": "코스닥으로 바꿔줘", "category": "universe", "output": {"universe": ["KOSDAQ"]}},
    {"request": "전체 시장으로", "category": "universe", "output": {"universe": ["KOSPI", "KOSDAQ"]}},
    {"request": "손절 10% 설정", "category": "stop_loss", "output": {"stop_loss_pct": 10.0}},
    {"request": "손절을 -12%로", "category": "stop_loss", "output": {"stop_loss_pct": 12.0}},
    {"request": "익절 20% 설정해줘", "category": "take_profit", "output": {"take_profit_pct": 20.0}},
    {"request": "30% 익절 설정", "category": "take_profit", "output": {"take_profit_pct": 30.0}},
    {"request": "6개월 보유", "category": "hold_period", "output": {"hold_period_days": 126}},
    {"request": "3개월마다 리밸런싱", "category": "rebalancing", "output": {"rebalancing_period": "quarterly"}},
]


def _category_for(simple: dict) -> str:
    keys = [k for k in simple if k in _FIELD_TO_CATEGORY]
    cats = {_FIELD_TO_CATEGORY[k] for k in keys}
    if len(cats) == 1:
        return cats.pop()
    if not cats:
        return "misc"
    return "mixed"


def _load_corpus() -> list[dict]:
    """합성 + 학습 코퍼스를 병합하고 request 텍스트로 dedup한다."""
    corpus: list[dict] = []
    seen: set[str] = set()

    def add(ex: dict) -> None:
        req = (ex.get("request") or "").strip()
        out = ex.get("output")
        if not req or not out or req in seen:
            return
        seen.add(req)
        corpus.append({
            "request": req,
            "category": ex.get("category") or _category_for(out),
            "output": out,
        })

    if _SYNTHETIC_PATH.exists():
        try:
            for ex in json.loads(_SYNTHETIC_PATH.read_text(encoding="utf-8")):
                add(ex)
        except Exception:
            pass

    # 합성 JSON이 없거나 비면 하드코딩 시드로 폴백
    if not corpus:
        for ex in _MODIFY_EXAMPLES:
            add(ex)

    lp = _learned_path()
    if lp.exists():
        try:
            for line in lp.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    add(json.loads(line))
                except Exception:
                    continue
        except Exception:
            pass

    return corpus


class ModifyRAG:
    """수정 요청의 동적 few-shot 검색."""

    def __init__(self):
        self._collection = None
        self._embedder = None
        self._corpus: list[dict] = []
        self._lock = threading.Lock()

    def _init_embedder(self):
        if self._embedder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError("pip install sentence-transformers 필요")
        self._embedder = SentenceTransformer("BAAI/bge-m3")

    def _init_collection(self):
        if self._collection is not None:
            return
        try:
            import chromadb
        except ImportError:
            raise RuntimeError("pip install chromadb 필요")

        client = chromadb.EphemeralClient()
        self._collection = client.get_or_create_collection(
            name="modify_examples",
            metadata={"hnsw:space": "cosine"},
        )

        self._corpus = _load_corpus()
        if self._collection.count() == 0 and self._corpus:
            self._init_embedder()
            requests = [e["request"] for e in self._corpus]
            embeddings = self._embedder.encode(requests, normalize_embeddings=True).tolist()
            self._collection.add(
                ids=[f"modify_ex_{i}" for i in range(len(self._corpus))],
                embeddings=embeddings,
                documents=requests,
                metadatas=[
                    {"category": e["category"], "output_json": json.dumps(e["output"], ensure_ascii=False)}
                    for e in self._corpus
                ],
            )

    def retrieve_examples(self, user_request: str, k: int = 2) -> list[dict]:
        """사용자 요청과 유사한 K개 예시 검색 (chroma metadata에서 직접 복원)."""
        self._init_collection()
        self._init_embedder()

        n = min(k, max(1, self._collection.count()))
        query_embedding = self._embedder.encode([user_request], normalize_embeddings=True).tolist()
        results = self._collection.query(query_embeddings=query_embedding, n_results=n)

        examples: list[dict] = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            for doc, meta in zip(docs, metas):
                try:
                    output = json.loads(meta.get("output_json", "{}"))
                except Exception:
                    output = {}
                examples.append({
                    "request": doc,
                    "category": meta.get("category", "misc"),
                    "output": output,
                })
        return examples

    def record_example(self, user_request: str, output: dict) -> bool:
        """성공한 수정 요청을 학습 코퍼스에 저장한다 (best-effort).

        diff의 단순 필드(non-null)만 추출해 learned.jsonl에 append하고, 컬렉션이
        이미 초기화돼 있으면 라이브로 추가해 다음 요청부터 즉시 검색에 반영한다.
        request 텍스트가 이미 코퍼스에 있으면 무시(dedup).
        """
        req = (user_request or "").strip()
        simple = {k: v for k, v in (output or {}).items() if k in _SIMPLE_FIELDS and v is not None}
        if not req or not simple:
            return False

        category = _category_for(simple)
        record = {"request": req, "category": category, "output": simple}

        with self._lock:
            self._init_collection()
            if len(self._corpus) >= _MAX_CORPUS:
                return False
            if any(e["request"] == req for e in self._corpus):
                return False

            lp = _learned_path()
            try:
                lp.parent.mkdir(parents=True, exist_ok=True)
                with lp.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception:
                return False

            self._corpus.append(record)
            try:
                self._init_embedder()
                emb = self._embedder.encode([req], normalize_embeddings=True).tolist()
                self._collection.add(
                    ids=[f"modify_learned_{int(time.time() * 1000)}_{len(self._corpus)}"],
                    embeddings=emb,
                    documents=[req],
                    metadatas=[{"category": category, "output_json": json.dumps(simple, ensure_ascii=False)}],
                )
            except Exception:
                pass
            return True


_modify_rag: Optional[ModifyRAG] = None


def get_modify_rag() -> ModifyRAG:
    global _modify_rag
    if _modify_rag is None:
        _modify_rag = ModifyRAG()
    return _modify_rag


def record_example(user_request: str, output: dict) -> bool:
    """싱글턴을 통한 학습 기록 (호출부에서 예외 무시 가능)."""
    try:
        return get_modify_rag().record_example(user_request, output)
    except Exception:
        return False


def _fallback_examples() -> list[dict]:
    """RAG(bge-m3/chromadb) 비가용 시 임베딩 없이 쓰는 정적 예시.

    카테고리별 대표 예시를 모두 포함해 어떤 수정 요청이든 few-shot 가이드가 되게 한다.
    합성 JSON이 있으면 그 앞부분, 없으면 하드코딩 시드를 쓴다(둘 다 ~1.5KB 이내).
    """
    try:
        if _SYNTHETIC_PATH.exists():
            data = json.loads(_SYNTHETIC_PATH.read_text(encoding="utf-8"))
            seen: set[str] = set()
            picked: list[dict] = []
            for ex in data:
                cat = ex.get("category")
                if cat and cat not in seen:
                    seen.add(cat)
                    picked.append(ex)
            if picked:
                return picked
    except Exception:
        pass
    return list(_MODIFY_EXAMPLES)


def build_dynamic_modify_prompt(user_request: str, k: int = 2) -> str:
    """사용자 요청에 맞춰 동적으로 few-shot을 구성한 MODIFY_PROMPT 생성.

    RAG(bge-m3/chromadb) 비가용·실패 시 정적 예시로 폴백한다 — RAG는 프롬프트
    크기 최적화일 뿐이므로, 의존성이 없어도 수정 기능 자체는 동작해야 한다.
    """
    rag = get_modify_rag()
    try:
        examples = rag.retrieve_examples(user_request, k=k)
    except Exception:
        examples = _fallback_examples()

    system_part = """현재 전략 JSON이 주어집니다. 사용자 수정 요청을 적용해 변경된 필드만 JSON으로 출력하세요.
변경하지 않는 필드는 반드시 null로 출력하세요. 수정 요청에 없는 내용은 절대 바꾸지 마세요.

## 금액 단위 변환 (initial_capital)
- '1억' → 100000000.0
- '5천만원' → 50000000.0
- '2억 5천만' → 250000000.0
- '1000만원' → 10000000.0

## 예시
"""

    examples_part = ""
    for ex in examples:
        req = ex["request"]
        out = json.dumps(ex["output"], ensure_ascii=False)
        examples_part += f'수정 요청: "{req}"\n출력: {out}\n\n'

    return system_part + examples_part
