"""Two requests cannot commit against the same superseded server draft."""
import pytest

from engine.nl_parser import ParsedStrategy
from strategy_conversation.conversation.versioning import RevisionConflict, RevisionLedger

DRAFT = "same-draft-identity-123456"


def test_newer_request_supersedes_old_inflight_commit(tmp_path):
    ledger = RevisionLedger(tmp_path)
    old = ledger.begin(DRAFT, 0, None, None)
    current = ledger.begin(DRAFT, 0, None, None)
    with pytest.raises(RevisionConflict):
        ledger.commit(DRAFT, old, ParsedStrategy(max_positions=9))
    committed = ledger.commit(DRAFT, current, ParsedStrategy(max_positions=12))
    assert committed["revision"] == 1


def test_revision_survives_new_ledger_instance(tmp_path):
    parsed = ParsedStrategy(max_positions=12)
    ledger = RevisionLedger(tmp_path)
    version = ledger.commit(DRAFT, ledger.begin(DRAFT, 0, None, None), parsed)
    reloaded = RevisionLedger(tmp_path)
    ticket = reloaded.begin(DRAFT, version["revision"], version["state_hash"], parsed.model_dump())
    assert ticket["revision"] == 1
    with pytest.raises(RevisionConflict):
        reloaded.begin(DRAFT, 0, None, None)


def test_forged_baseline_cannot_use_current_revision(tmp_path):
    ledger = RevisionLedger(tmp_path)
    parsed = ParsedStrategy(max_positions=12)
    version = ledger.commit(DRAFT, ledger.begin(DRAFT, 0, None, None), parsed)
    with pytest.raises(RevisionConflict):
        ledger.begin(DRAFT, 1, version["state_hash"], ParsedStrategy(max_positions=10).model_dump())


def test_commit_cannot_be_repeated(tmp_path):
    ledger = RevisionLedger(tmp_path)
    ticket = ledger.begin(DRAFT, 0, None, None)
    ledger.commit(DRAFT, ticket, ParsedStrategy())
    with pytest.raises(RevisionConflict):
        ledger.commit(DRAFT, ticket, ParsedStrategy())


def test_distinct_drafts_do_not_conflict(tmp_path):
    ledger = RevisionLedger(tmp_path)
    left = ledger.begin(DRAFT, 0, None, None)
    right = ledger.begin("other-draft-identity-123456", 0, None, None)
    assert ledger.commit(DRAFT, left, ParsedStrategy())["revision"] == 1
    assert ledger.commit("other-draft-identity-123456", right, ParsedStrategy())["revision"] == 1
