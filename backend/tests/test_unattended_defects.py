"""무인 실행 결함 대기열(2026-11-26) — 기록·중복 방지·닫기·요약."""
from __future__ import annotations

from scripts import unattended_defects as ud


def test_add_dedup_close_and_summary(tmp_path):
    q = tmp_path / "q.jsonl"
    assert ud.summary(q) is None

    a = ud.add("news", "interpretation", "2026-11-25/04-pcb-rsi", "문장", "업종 칸이 낌", "b44064ce7dd6", path=q)
    assert ud.add("news", "interpretation", "2026-11-25/04-pcb-rsi", "문장", "업종 칸이 낌", path=q) == a
    ud.add("myth", "data", "2026-11-26/indexdrop", "문장2", "가격 미수정", path=q)

    assert len(ud.open_items(q)) == 2
    assert ud.summary(q) == "[무인 실행 결함] 수리 대기 2건(해석 1·데이터 1) — /trace-triage 로 확인"

    assert ud.close(a, "커밋 abc", path=q)
    assert not ud.close("nope", "x", path=q)
    assert [i["kind"] for i in ud.open_items(q)] == ["data"]
    closed = [i for i in ud.load(q) if i["id"] == a][0]
    assert closed["status"] == "fixed" and closed["closed_by"] == "커밋 abc"


def test_cli_roundtrip(tmp_path, capsys):
    q = tmp_path / "q.jsonl"
    assert ud.main(["--queue", str(q), "add", "--source", "myth", "--kind", "engine",
                    "--slug", "s", "--prompt", "p", "--symptom", "빈자리"]) == 0
    ident = capsys.readouterr().out.strip()
    assert ud.main(["--queue", str(q), "list"]) == 0
    assert "빈자리" in capsys.readouterr().out
    assert ud.main(["--queue", str(q), "close", ident, "--by", "wontfix 사유", "--status", "wontfix"]) == 0
    assert ud.main(["--queue", str(q), "list"]) == 0
    assert "열린 결함 없음" in capsys.readouterr().out
