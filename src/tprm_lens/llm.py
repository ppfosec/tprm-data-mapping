from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config import FIXTURES, MODE, MODEL

CASSETTES = FIXTURES / "cassettes"
SYSTEM = """You are a senior TPRM practitioner. Synthesize one vendor engagement from the supplied, grounded records. The vendor surface is an input, not the verdict. Consider intended use, sequence, business value, team engagement, relationship maturity, ownership, and explicit heuristics. Recommend a business intervention and its trade-offs. Never invent a fact or evidence id. Return JSON only."""
FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
live_calls = 0


class MissingCassette(RuntimeError):
    pass


def key(payload: dict) -> str:
    raw = json.dumps({"model": MODEL, "system": SYSTEM, "payload": payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cassette_path(engagement_id: str, payload: dict) -> Path:
    return CASSETTES / f"judgment.{engagement_id}.{key(payload)}.json"


def call(engagement_id: str, payload: dict) -> dict:
    global live_calls
    path = cassette_path(engagement_id, payload)
    if MODE == "replay":
        if not path.exists():
            raise MissingCassette(
                f"No recorded judgment for {engagement_id} ({key(payload)}). "
                f"The evidence, heuristics, prompt, schema or model changed; run a deliberate record scan."
            )
        return json.loads(path.read_text(encoding="utf-8"))["response"]
    if MODE == "record" and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError("Install the live extra: pip install -e .[live]") from exc
    client = Anthropic()
    live_calls += 1
    response = client.messages.create(
        model=MODEL,
        max_tokens=2200,
        temperature=0.2,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    parsed = json.loads(FENCE.sub("", text).strip())
    if MODE == "record":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"engagement_id": engagement_id, "model": MODEL, "input_key": key(payload), "response": parsed}, indent=2, ensure_ascii=False), encoding="utf-8")
    return parsed
