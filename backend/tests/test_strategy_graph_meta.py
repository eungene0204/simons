"""전략 그래프 공개 메타데이터 — 공개 필드만, 결정론적, 사용자 데이터·진단 정보 없음."""
import json
import subprocess
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.strategy_graph_meta_routes import router
from strategy_conversation.registry.indicator_registry import REGISTRY
from strategy_conversation.registry.public_metadata import build_public_metadata


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_returns_public_metadata():
    res = _client().get("/strategy/graph-meta")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"version", "indicators", "bindings", "classes", "concepts"}
    assert body["version"] == build_public_metadata()["version"]


def test_every_registry_leaf_is_exposed_with_public_fields_only():
    meta = build_public_metadata()
    assert set(meta["indicators"]) == set(REGISTRY)
    allowed = {
        "name", "nameEn", "category", "supported", "dataPending", "partialData",
        "unit", "operators", "parameters", "classId", "alternatives",
    }
    for spec_id, item in meta["indicators"].items():
        assert set(item) == allowed, spec_id
        for param in item["parameters"].values():
            assert set(param) == {"minimum", "maximum", "required"}


def test_no_defaults_issues_or_internal_notes_are_exposed():
    """미정 사용자 값을 채울 수 있는 default·recommended_value, 진단 issues, 내부 메모는 제외한다."""
    text = json.dumps(build_public_metadata(), ensure_ascii=False)
    assert '"default"' not in text
    assert "recommended" not in text
    assert "issues" not in text
    assert '"notes"' not in text
    assert '"synonyms"' not in text
    assert "default_parameters" not in text


def test_engine_bindings_point_back_to_canonical_leaves():
    meta = build_public_metadata()
    assert meta["bindings"]["technical_signal:rsi"] == "technical.rsi"
    assert meta["bindings"]["fundamental_filter:per"] == "fundamental.per"
    assert meta["bindings"]["ranking:return"] == "ranking.return"
    for leaf in meta["bindings"].values():
        assert leaf in REGISTRY


def test_shared_engine_binding_maps_to_the_generic_leaf():
    """볼린저 밴드 지정 변형 8개가 같은 엔진 조건을 공유 — 색인은 일반 잎을 대표로 둔다."""
    meta = build_public_metadata()
    assert meta["bindings"]["technical_signal:bollinger_bands"] == "technical.bollinger_bands"


def test_concepts_and_classes_carry_relations_only():
    meta = build_public_metadata()
    golden = next(c for c in meta["concepts"] if c["id"] == "concept.golden_cross")
    assert golden["expandsTo"] == "technical.ma_crossover"
    assert set(golden) == {"id", "name", "supported", "expandsTo", "requires"}
    rsi = meta["indicators"]["technical.rsi"]
    class_ids = {c["id"] for c in meta["classes"]}
    assert rsi["classId"] in class_ids
    for cls in meta["classes"]:
        assert set(cls) == {"id", "name", "parent", "description"}


def test_metadata_is_deterministic():
    first = json.dumps(build_public_metadata(), sort_keys=True, ensure_ascii=False)
    second = json.dumps(build_public_metadata(), sort_keys=True, ensure_ascii=False)
    assert first == second


def test_metadata_module_does_not_import_llm_clients():
    """그래프 메타데이터 생성이 LLM 레인을 끌어오지 않는다(새 프로세스에서 import 그래프 확인)."""
    code = (
        "import sys;"
        "from strategy_conversation.registry import public_metadata;"
        "public_metadata.build_public_metadata();"
        "bad=[m for m in sys.modules if m.startswith(('llm_backend','openai','ollama','anthropic'))];"
        "print(','.join(bad))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == ""
