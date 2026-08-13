from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from . import llm
from .config import DATA, FIXTURES, MODE, MODEL, OUT
from .heuristics import library as load_library
from .trace import Trace

DEMO_PATH = FIXTURES / "tprm" / "demo.json"
JUDGMENTS_PATH = FIXTURES / "tprm" / "judgments.json"
HEURISTICS_PATH = FIXTURES / "heuristics" / "JUDGMENT_LIBRARY.md"
EXTERNAL_PATH = DATA / "index.json"
OUTPUT_PATH = DATA / "tprm-intelligence.json"
TRACE_PATH = OUT / "trace.jsonl"
CANDIDATE_PATH = OUT / "candidates" / "judgments.json"


class InvalidFixture(RuntimeError):
    pass


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprint(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def quadrant(maturity: int, value: int) -> str:
    if maturity >= 60 and value >= 60:
        return "mature"
    if maturity >= 60:
        return "opportunistic"
    if value >= 60:
        return "fragile"
    return "unmanaged"


def _validate(demo: dict, judgments: dict, heuristics: dict) -> None:
    dispositions = {"proceed", "proceed_with_conditions", "investigate", "escalate_tradeoff", "stop", "abstain"}
    ids: dict[str, str] = {}
    for group in ("vendors", "teams", "engagements", "evidence", "sources"):
        for row in demo[group]:
            item_id = row["id"]
            if item_id in ids:
                raise InvalidFixture(f"duplicate id {item_id} in {group} and {ids[item_id]}")
            ids[item_id] = group
    vendors = {r["id"] for r in demo["vendors"]}
    teams = {r["id"] for r in demo["teams"]}
    evidence = {r["id"] for r in demo["evidence"]}
    engagements = {r["id"] for r in demo["engagements"]}
    heuristic_ids = {r["id"] for r in heuristics["heuristics"]}
    for eng in demo["engagements"]:
        if eng["vendor_id"] not in vendors or eng["team_id"] not in teams:
            raise InvalidFixture(f"{eng['id']} has an orphan vendor or team")
        missing = set(eng["evidence_ids"]) - evidence
        if missing:
            raise InvalidFixture(f"{eng['id']} has missing evidence: {sorted(missing)}")
    if set(judgments["engagements"]) != engagements:
        raise InvalidFixture("curated judgments must cover every engagement exactly")
    for eng_id, judgment in judgments["engagements"].items():
        if judgment.get("disposition") not in dispositions:
            raise InvalidFixture(f"{eng_id} has an unsupported disposition")
        if not judgment["evidence_ids"] or set(judgment["evidence_ids"]) - evidence:
            raise InvalidFixture(f"{eng_id} judgment is ungrounded")
        if not judgment["heuristic_ids"] or set(judgment["heuristic_ids"]) - heuristic_ids:
            raise InvalidFixture(f"{eng_id} judgment has an unknown heuristic")
    triple_d = demo.get("triple_d", {})
    if triple_d.get("mode") != "replay":
        raise InvalidFixture("the staged Triple D scan must default to replay")
    for event in triple_d.get("events", []):
        if event.get("evidence_id") not in evidence:
            raise InvalidFixture(f"Triple D event {event.get('id')} has missing evidence")
        if event.get("vendor_id") not in vendors:
            raise InvalidFixture(f"Triple D event {event.get('id')} has an unknown vendor")


def _external_portfolio(external: dict) -> list[dict]:
    rows = []
    for vendor in external.get("vendors", []):
        rows.append({
            "id": vendor["id"],
            "name": vendor["name"],
            "category": vendor["category"],
            "public_evidence_only": True,
            "surface": {
                "grade": str(vendor.get("score", {}).get("total", "—")),
                "posture": "public evidence index",
                "confidence": "bounded",
                "summary": f"{len(vendor.get('docs', []))} public documents · {len(vendor.get('crosschecks', []))} open reconciliations",
            },
            "documents": vendor.get("docs", []),
            "findings": vendor.get("crosschecks", []),
            "classification": vendor.get("data_classification", {}),
            "jobs": vendor.get("jobs", {}),
            "drift": vendor.get("drift", []),
        })
    return rows


def judgment_payload(eng: dict, vendor: dict, team: dict, timeline: list[dict], heuristics: dict) -> dict:
    applied = [{k: h[k] for k in ("id", "title", "understand", "do", "uncertainty")}
               for h in heuristics["heuristics"] if h["applies"]]
    return {
        "schema": {
            "disposition": "proceed|proceed_with_conditions|investigate|escalate_tradeoff|stop",
            "headline": "short business recommendation",
            "hypothesis": "one grounded story",
            "alternative": "next plausible explanation",
            "recommendation": "specific intervention",
            "tradeoffs": ["business consequence"],
            "conditions": ["condition"],
            "missing": ["unverified fact"],
            "changes_mind": "evidence that would change the recommendation",
            "confidence": "0.0 to 1.0",
            "evidence_ids": ["only ids supplied below"],
            "heuristic_ids": ["only ids supplied below"],
        },
        "engagement": {k: eng[k] for k in ("id", "title", "intended_use", "process", "status", "business_value", "relationship_maturity", "use_case_exposure", "business_owner", "technical_owner", "decision_authority")},
        "vendor_surface": vendor["surface"],
        "team": team,
        "evidence": timeline,
        "heuristics": applied,
    }


def run(write: bool = True) -> dict:
    demo = _read(DEMO_PATH)
    curated = _read(JUDGMENTS_PATH)
    heuristics = load_library()
    external = _read(EXTERNAL_PATH)
    _validate(demo, curated, heuristics)

    trace = Trace(demo["as_of"] + "T12:00:00Z")
    root = trace.emit("s1_sequence", "cluster", f"Reconstructing {len(demo['engagements'])} engagements",
                      "Purchases, access, data use, intake and vendor changes are ordered before any judgment is applied.")
    evidence_by_id = {r["id"]: r for r in demo["evidence"]}
    vendors = {r["id"]: r for r in demo["vendors"]}
    teams = {r["id"]: r for r in demo["teams"]}
    engagements = []

    for source in demo["engagements"]:
        eng = deepcopy(source)
        vendor = vendors[eng["vendor_id"]]
        team = teams[eng["team_id"]]
        evidence = [evidence_by_id[eid] for eid in eng["evidence_ids"]]
        vendor_evidence = [e for e in demo["evidence"] if e.get("vendor_id") == vendor["id"]]
        timeline = sorted({e["id"]: e for e in [*evidence, *vendor_evidence]}.values(), key=lambda e: (e["date"], e["id"]))
        seq = trace.emit("s1_sequence", "cluster", eng["title"],
                         " → ".join(f"{e['date']} {e['title']}" for e in timeline), root,
                         [e["id"] for e in timeline])
        for event in timeline:
            trace.emit("s1_sequence", "signal", event["title"], event["excerpt"], seq, [event["id"]])

        context = trace.emit("s2_context", "maturity", f"{team['name']} engages {team['maturity']}",
                             team["basis"], seq, [e["id"] for e in evidence if e["source"] == "interactions"],
                             None if team["maturity"] == "unknown" else min(0.95, 0.55 + team["interactions"] * 0.07))
        model_consulted = team["interactions"] >= 2
        if not model_consulted:
            trace.emit("s2_context", "abstention", f"No basis to appraise {team['name']}",
                       "Fewer than two relevant interactions exist. This guard returns before a model request is built.",
                       context, ["TPRM-H-0005"], 0.0)

        if model_consulted:
            judgment = llm.call(eng["id"], judgment_payload(eng, vendor, team, timeline, heuristics))
        else:
            judgment = deepcopy(curated["engagements"][eng["id"]])
        if not set(judgment["evidence_ids"]) <= {e["id"] for e in timeline}:
            raise InvalidFixture(f"{eng['id']} model judgment cites evidence it was not given")
        if not set(judgment["heuristic_ids"]) <= {h["id"] for h in heuristics["heuristics"] if h["applies"]}:
            raise InvalidFixture(f"{eng['id']} model judgment cites an unavailable heuristic")
        synthesis_kind = "abstention" if judgment["disposition"] == "abstain" else "hypothesis"
        hyp = trace.emit("s4_synthesize", synthesis_kind, judgment["headline"],
                         f"{judgment['hypothesis']}\nAlternative: {judgment['alternative']}\nMissing: {'; '.join(judgment['missing'])}",
                         context, judgment["evidence_ids"] + judgment["heuristic_ids"], judgment["confidence"])
        trace.emit("s5_intervene", "recommendation", judgment["disposition"].replace("_", " "),
                   judgment["recommendation"], hyp, judgment["evidence_ids"] + judgment["heuristic_ids"], judgment["confidence"])

        eng.update({
            "vendor": vendor,
            "team": team,
            "timeline": timeline,
            "judgment": judgment,
            "quadrant": quadrant(eng["relationship_maturity"], eng["business_value"]),
            "model_consulted": model_consulted,
            "trace_root": seq,
        })
        engagements.append(eng)

    by_vendor = {
        vendor_id: [e["id"] for e in engagements if e["vendor_id"] == vendor_id]
        for vendor_id in vendors
    }
    triple_d = deepcopy(demo["triple_d"])
    triple_d["events"] = [
        {
            **event,
            "affected_engagements": by_vendor[event["vendor_id"]],
            "recommendations_changed": [
                e["id"] for e in engagements
                if e["vendor_id"] == event["vendor_id"] and e.get("prior_disposition")
            ],
        }
        for event in triple_d["events"]
    ]
    triple_d["changes_detected"] = len(triple_d["events"])
    triple_d["affected_engagements"] = sorted({
        eng_id for event in triple_d["events"] for eng_id in event["affected_engagements"]
    })
    triple_d["recommendations_changed"] = sorted({
        eng_id for event in triple_d["events"] for eng_id in event["recommendations_changed"]
    })

    output = {
        "schema_version": "1.0.0",
        "generated_at": demo["as_of"] + "T12:00:00Z",
        "mode": MODE,
        "model": MODEL,
        "staged": True,
        "platform_name": demo["platform_name"],
        "input_fingerprint": _fingerprint({"demo": demo, "judgments": curated, "heuristics": heuristics}),
        "engagements": engagements,
        "vendors": demo["vendors"],
        "public_vendors": _external_portfolio(external),
        "teams": demo["teams"],
        "evidence": demo["evidence"],
        "sources": demo["sources"],
        "triple_d": triple_d,
        "heuristics": heuristics,
        "trace": trace.nodes,
        "dependency_index": {
            "by_vendor": by_vendor,
            "by_evidence": {evidence_id: [e["id"] for e in engagements if evidence_id in e["evidence_ids"]]
                            for evidence_id in evidence_by_id},
        },
        "summary": {
            "engagements": len(engagements),
            "vendors": len(demo["vendors"]),
            "public_vendors": external.get("vendor_count", len(external.get("vendors", []))),
            "findings": len(demo["evidence"]),
            "abstentions": sum(e["judgment"]["disposition"] == "abstain" for e in engagements),
            "model_steps": sum(e["model_consulted"] for e in engagements),
            "live_calls": llm.live_calls,
        },
    }
    if write:
        OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TRACE_PATH.write_text("\n".join(json.dumps(n, ensure_ascii=False) for n in trace.nodes) + "\n", encoding="utf-8")
    return output


def candidate() -> Path:
    """Create a candidate judgment artifact. Never modifies curated fixtures."""
    CANDIDATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(_read(JUDGMENTS_PATH))
    payload["review_state"] = "candidate"
    payload["reviewed_by"] = "unreviewed"
    payload["source_fingerprint"] = _fingerprint(_read(DEMO_PATH))
    CANDIDATE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return CANDIDATE_PATH
