from __future__ import annotations

import re
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import FIXTURES

SEED = FIXTURES / "heuristics" / "JUDGMENT_LIBRARY.md"
STORE = Path(os.getenv("TPRM_LENS_HEURISTICS", "var/heuristics/JUDGMENT_LIBRARY.md"))
ENTRY = re.compile(r"^##\s+([A-Z]+-H-\d+):\s+(.+)$")
FIELD = re.compile(r"^-\s+([^:]+):\s*(.+)$")
SECTION = re.compile(r"^###\s+(.+)$")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def parse(text: str) -> list[dict]:
    records: list[dict] = []
    current = None
    section = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if current is not None and section:
            body = "\n".join(buffer).strip()
            if body:
                current["sections"][section] = body
        buffer = []

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            match = ENTRY.match(line)
            current = None
            section = None
            if match:
                current = {"id": match.group(1), "title": match.group(2), "fields": {}, "sections": {}}
                records.append(current)
            continue
        if current is None:
            continue
        sec = SECTION.match(line)
        if sec:
            flush(); section = _slug(sec.group(1)); continue
        field = FIELD.match(line)
        if field and section is None:
            current["fields"][_slug(field.group(1))] = field.group(2).strip("` ")
        elif section:
            buffer.append(line)
    flush()
    shaped = []
    for record in records:
        fields = record.pop("fields")
        stages = [s.strip() for s in fields.get("stages", "").split(",") if s.strip() and s.strip() != "none"]
        sections = record["sections"]
        shaped.append({
            **record,
            "status": fields.get("status", "unknown"),
            "version": fields.get("version", ""),
            "areas": [a.strip() for a in fields.get("grc_areas", "").split(",") if a.strip()],
            "approved_by": fields.get("approved_by", ""),
            "stages": stages,
            "applies": bool(stages),
            "basis": "bound" if stages else "carried",
            "use_when": sections.get("use_when", ""),
            "understand": sections.get("understand", ""),
            "do": sections.get("do", ""),
            "uncertainty": sections.get("uncertainty", ""),
            "provenance": sections.get("provenance", ""),
        })
    return shaped


def active_path() -> Path:
    return STORE if STORE.exists() else SEED


def library(path: Path | None = None) -> dict:
    path = path or active_path()
    text = path.read_text(encoding="utf-8")
    header = {}
    for line in text.splitlines():
        if line.startswith("##"):
            break
        match = FIELD.match(line)
        if match:
            header[_slug(match.group(1))] = match.group(2).strip("` ")
    records = parse(text)
    return {
        "version": header.get("library_version", ""),
        "published": header.get("last_published", ""),
        "source": "imported" if path == STORE else header.get("source", "shipped"),
        "total": len(records),
        "applied": sum(r["applies"] for r in records),
        "heuristics": records,
    }


def save(text: str, store: Path = STORE) -> dict:
    records = parse(text)
    if not records:
        raise ValueError("no canonical heuristic entries found")
    store.parent.mkdir(parents=True, exist_ok=True)
    if store.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = store.with_name(f"JUDGMENT_LIBRARY.{stamp}.md")
        suffix = 1
        while archive.exists():
            archive = store.with_name(f"JUDGMENT_LIBRARY.{stamp}.{suffix}.md")
            suffix += 1
        shutil.copy2(store, archive)
    temp = store.with_suffix(".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(store)
    return library(store)
