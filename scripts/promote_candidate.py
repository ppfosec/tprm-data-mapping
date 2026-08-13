"""Promote a reviewed candidate judgment into the curated fixture."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tprm_lens import llm  # noqa: E402
from tprm_lens.heuristics import library  # noqa: E402
from tprm_lens.pipeline import (  # noqa: E402
    CANDIDATE_PATH, DEMO_PATH, HEURISTICS_PATH, JUDGMENTS_PATH,
    judgment_payload, run,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--reviewer")
    args = parser.parse_args()
    if not args.approve or not args.reviewer:
        parser.error("promotion requires --approve and --reviewer NAME")
    candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    if candidate.get("review_state") != "candidate":
        raise SystemExit("refusing to promote an artifact not marked candidate")
    candidate["review_state"] = "curated"
    candidate["reviewed_by"] = args.reviewer
    candidate["reviewed_on"] = datetime.now(timezone.utc).date().isoformat()
    backup = JUDGMENTS_PATH.with_name(
        f"judgments.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    shutil.copy2(JUDGMENTS_PATH, backup)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cassette_backup = ROOT / "var" / "cassette-backups" / stamp
    cassette_backup.mkdir(parents=True, exist_ok=True)
    demo = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    heuristics = library(HEURISTICS_PATH)
    vendors = {v["id"]: v for v in demo["vendors"]}
    teams = {t["id"]: t for t in demo["teams"]}
    cassette_paths = []
    for eng in demo["engagements"]:
        team = teams[eng["team_id"]]
        if team["interactions"] < 2:
            continue
        vendor = vendors[eng["vendor_id"]]
        timeline = sorted(
            [e for e in demo["evidence"] if e.get("engagement_id") == eng["id"] or e.get("vendor_id") == vendor["id"]],
            key=lambda e: (e["date"], e["id"]),
        )
        payload = judgment_payload(eng, vendor, team, timeline, heuristics)
        cassette = llm.cassette_path(eng["id"], payload)
        shutil.copy2(cassette, cassette_backup / cassette.name)
        cassette.write_text(json.dumps({
            "engagement_id": eng["id"], "model": llm.MODEL,
            "input_key": llm.key(payload), "response": candidate["engagements"][eng["id"]],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        cassette_paths.append(cassette)
    temp = JUDGMENTS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(JUDGMENTS_PATH)
    try:
        run(write=False)
    except Exception:
        shutil.copy2(backup, JUDGMENTS_PATH)
        for cassette in cassette_paths:
            shutil.copy2(cassette_backup / cassette.name, cassette)
        raise
    print(f"promoted candidate reviewed by {args.reviewer}; prior fixture archived at {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
