from __future__ import annotations

import json
from pathlib import Path

from tprm_lens.pipeline import candidate, quadrant, run

ROOT = Path(__file__).resolve().parents[1]


def test_quadrants() -> None:
    assert quadrant(80, 80) == "mature"
    assert quadrant(80, 40) == "opportunistic"
    assert quadrant(40, 80) == "fragile"
    assert quadrant(40, 40) == "unmanaged"


def test_replay_deterministic() -> None:
    assert run(write=False) == run(write=False)


def test_abstention_has_no_model_call() -> None:
    output = run(write=False)
    item = next(e for e in output["engagements"] if e["id"] == "eng_callscribe_cs")
    assert item["judgment"]["disposition"] == "abstain"
    assert item["model_consulted"] is False


def test_triple_d_routes_drift_without_a_live_call() -> None:
    output = run(write=False)
    triple_d = output["triple_d"]
    event = triple_d["events"][0]
    assert triple_d["mode"] == "replay"
    assert event["affected_engagements"] == ["eng_ledger_finance"]
    assert event["recommendations_changed"] == ["eng_ledger_finance"]
    assert output["summary"]["live_calls"] == 0


def test_candidate_never_replaces_curated() -> None:
    curated_path = ROOT / "fixtures" / "tprm" / "judgments.json"
    before = curated_path.read_bytes()
    path = candidate()
    assert json.loads(path.read_text())["review_state"] == "candidate"
    assert curated_path.read_bytes() == before


def test_keyless_collector_preserves_reviewed_classification() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "collector"))
    from collect import preserve_curated_classification

    previous = {
        "docs": [{"kind": "privacy", "sha256": "same"}],
        "data_classification": {"method": "llm", "tags": [{"key": "reviewed"}]},
    }
    current = {"method": "heuristic", "tags": []}
    kept = preserve_curated_classification(current, previous, [{"kind": "privacy", "sha256": "same"}])
    assert kept["method"] == "llm"
    assert kept["tags"] == [{"key": "reviewed"}]
    assert kept["preserved_without_key"] is True
    assert kept["source_documents_changed"] is False


def test_imported_library_is_versioned(tmp_path: Path) -> None:
    from tprm_lens.heuristics import SEED, save

    store = tmp_path / "JUDGMENT_LIBRARY.md"
    text = SEED.read_text(encoding="utf-8")
    first = save(text, store)
    assert first["total"] == 7
    save(text.replace("0.1.0", "0.1.1", 1), store)
    assert list(tmp_path.glob("JUDGMENT_LIBRARY.*.md"))
