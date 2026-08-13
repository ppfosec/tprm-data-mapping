"""Seed replay cassettes from the reviewed demo judgments.

This is a one-time fixture-authoring tool. It does not call a model and does not
promote candidates. Run it only when the curated judgments and their evidence
have been deliberately reviewed together.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["TPRM_LENS_MODE"] = "replay"

from tprm_lens import llm  # noqa: E402
from tprm_lens.heuristics import library  # noqa: E402
from tprm_lens.pipeline import DEMO_PATH, HEURISTICS_PATH, JUDGMENTS_PATH, judgment_payload  # noqa: E402


def main() -> int:
    demo = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    heuristics = library(HEURISTICS_PATH)
    judgments = json.loads(JUDGMENTS_PATH.read_text(encoding="utf-8"))["engagements"]
    vendors = {v["id"]: v for v in demo["vendors"]}
    teams = {t["id"]: t for t in demo["teams"]}
    evidence = demo["evidence"]
    count = 0
    for eng in demo["engagements"]:
        team = teams[eng["team_id"]]
        if team["interactions"] < 2:
            continue
        vendor = vendors[eng["vendor_id"]]
        timeline = sorted([e for e in evidence if e.get("engagement_id") == eng["id"] or e.get("vendor_id") == vendor["id"]], key=lambda e: (e["date"], e["id"]))
        payload = judgment_payload(eng, vendor, team, timeline, heuristics)
        path = llm.cassette_path(eng["id"], payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"engagement_id": eng["id"], "model": llm.MODEL, "input_key": llm.key(payload), "response": judgments[eng["id"]]}, indent=2, ensure_ascii=False), encoding="utf-8")
        count += 1
    print(f"seeded {count} reviewed replay cassettes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
