"""수정 요청 → 동적 few-shot 검색 (RAG)"""
import json
from typing import Optional

_MODIFY_EXAMPLES = [
    {
        "request": "종목을 10개로 줄여줘",
        "category": "max_positions",
        "output": {"max_positions": 10},
    },
    {
        "request": "최대 20종목으로 설정",
        "category": "max_positions",
        "output": {"max_positions": 20},
    },
    {
        "request": "초기자금 1억으로 바꿔줘",
        "category": "initial_capital",
        "output": {"initial_capital": 100000000.0},
    },
    {
        "request": "자금을 5억으로",
        "category": "initial_capital",
        "output": {"initial_capital": 500000000.0},
    },
    {
        "request": "트레일링 스탑 15%로 설정해줘",
        "category": "trailing_stop",
        "output": {"trailing_stop_pct": 15.0},
    },
    {
        "request": "최고가 대비 10% 하락 시 청산",
        "category": "trailing_stop",
        "output": {"trailing_stop_pct": 10.0},
    },
    {
        "request": "KOSPI200으로 진행",
        "category": "universe_kospi200",
        "output": {"universe": ["KOSPI200"]},
    },
    {
        "request": "코스닥으로 바꿔줘",
        "category": "universe_kosdaq",
        "output": {"universe": ["KOSDAQ"]},
    },
    {
        "request": "전체 시장으로",
        "category": "universe_all",
        "output": {"universe": ["KOSPI", "KOSDAQ"]},
    },
    {
        "request": "손절 10% 설정",
        "category": "stop_loss",
        "output": {"stop_loss_pct": 10.0},
    },
    {
        "request": "손절을 -12%로",
        "category": "stop_loss",
        "output": {"stop_loss_pct": 12.0},
    },
    {
        "request": "익절 20% 설정해줘",
        "category": "take_profit",
        "output": {"take_profit_pct": 20.0},
    },
    {
        "request": "30% 익절 설정",
        "category": "take_profit",
        "output": {"take_profit_pct": 30.0},
    },
    {
        "request": "6개월 보유",
        "category": "hold_period",
        "output": {"hold_period_days": 126},
    },
    {
        "request": "3개월마다 리밸런싱",
        "category": "rebalancing",
        "output": {"rebalancing_period": "quarterly"},
    },
]


class ModifyRAG:
    """수정 요청의 동적 few-shot 검색"""

    def __init__(self):
        self._collection = None
        self._embedder = None

    def _init_embedder(self):
        """bge-m3 임베더 초기화"""
        if self._embedder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError("pip install sentence-transformers 필요")
        self._embedder = SentenceTransformer("BAAI/bge-m3")

    def _init_collection(self):
        """Chroma 컬렉션 초기화"""
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

        # 코퍼스에 데이터 없으면 삽입
        if self._collection.count() == 0:
            self._init_embedder()
            requests = [ex["request"] for ex in _MODIFY_EXAMPLES]
            embeddings = self._embedder.encode(requests, normalize_embeddings=True).tolist()
            self._collection.add(
                ids=[f"modify_ex_{i}" for i in range(len(_MODIFY_EXAMPLES))],
                embeddings=embeddings,
                documents=requests,
                metadatas=[{"category": ex["category"]} for ex in _MODIFY_EXAMPLES],
            )

    def retrieve_examples(self, user_request: str, k: int = 2) -> list[dict]:
        """사용자 요청과 유사한 K개 예시 검색"""
        self._init_collection()
        self._init_embedder()

        query_embedding = self._embedder.encode([user_request], normalize_embeddings=True).tolist()
        results = self._collection.query(query_embeddings=query_embedding, n_results=k)

        examples = []
        if results and results.get("ids"):
            for idx in results["ids"][0]:
                example_idx = int(idx.split("_")[-1])
                examples.append(_MODIFY_EXAMPLES[example_idx])
        return examples


_modify_rag: Optional[ModifyRAG] = None


def get_modify_rag() -> ModifyRAG:
    global _modify_rag
    if _modify_rag is None:
        _modify_rag = ModifyRAG()
    return _modify_rag


def build_dynamic_modify_prompt(user_request: str, k: int = 2) -> str:
    """사용자 요청에 맞춰 동적으로 few-shot을 구성한 MODIFY_PROMPT 생성"""
    rag = get_modify_rag()
    examples = rag.retrieve_examples(user_request, k=k)

    # 시스템 지시 (공통)
    system_part = """현재 전략 JSON이 주어집니다. 사용자 수정 요청을 적용해 변경된 필드만 JSON으로 출력하세요.
변경하지 않는 필드는 반드시 null로 출력하세요. 수정 요청에 없는 내용은 절대 바꾸지 마세요.

## 금액 단위 변환 (initial_capital)
- '1억' → 100000000.0
- '5천만원' → 50000000.0
- '2억 5천만' → 250000000.0
- '1000만원' → 10000000.0

## 예시
"""

    # 검색된 예시만 포함
    examples_part = ""
    for ex in examples:
        req = ex["request"]
        out = json.dumps(ex["output"], ensure_ascii=False)
        examples_part += f'수정 요청: "{req}"\n출력: {out}\n\n'

    return system_part + examples_part
