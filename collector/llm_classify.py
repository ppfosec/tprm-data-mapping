"""LLM-based reading of a vendor's privacy policy and DPA, in place of the
regex heuristics in classify.py.

Regex catches keyword mentions but can't tell "we process biometric data"
from "the input of biometric data to the Services" (a customer warning, not
a product feature) or "your credit card" (an individual consumer's, not the
enterprise's) without a lot of hand-tuned hedge patterns that still don't
generalise. A model reading the actual document, with the actual vendor and
its category as context, does this the way a human reviewer would.

This is optional and additive: if ANTHROPIC_API_KEY isn't set, or the call
fails for any reason, classify() returns None and the caller falls back to
the regex classifier in classify.py. Every claim this returns must be
grounded in a verbatim quote from the source text -- anything the model
returns that doesn't actually appear in the document is dropped rather than
trusted, same principle as the rest of this collector: show the reviewer the
exact sentence, never assert without one.
"""

from __future__ import annotations

import json
import os
import re
import sys

import classify as classify_mod
import requests

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"
MAX_DOC_CHARS = 15_000
TIMEOUT = 60

def log(*args: object) -> None:
    print(*args, file=sys.stderr, flush=True)

CATEGORY_LIST = "\n".join(f"- {t['key']}: {t['label']}" for t in classify_mod.TAGS)
TAG_BY_KEY = {t["key"]: t for t in classify_mod.TAGS}

PROMPT = """You are helping a compliance officer evaluate a third-party vendor for a \
third-party risk management (TPRM) review. Their organization is an ENTERPRISE \
customer of this vendor -- under the vendor's standard commercial agreement and Data \
Processing Agreement (DPA) -- not an individual signing up for a personal plan.

Vendor: {name} ({category})

Below is the vendor's own published Privacy Policy and Data Processing Agreement, \
normalised to one sentence per line, exactly as collected from their website. Read it \
the way a careful compliance reviewer would: distinguish a genuine claim that the \
vendor's PRODUCT processes a given data type on behalf of an enterprise customer from:
- hedged or conditional language ("if you choose to...", "you may optionally submit...")
- data about the vendor's own individual/consumer end users (e.g. a self-serve personal \
plan paid by personal credit card) rather than the enterprise customer's data
- the vendor acting as an independent controller for its own purposes (its own billing, \
marketing, recruiting) rather than as a processor on behalf of the customer
- legal boilerplate defining a contract term (e.g. "'Sensitive Data' means...") rather \
than an admission of processing it
- a plain denial ("we do not knowingly collect data from children")

=== PRIVACY POLICY ===
{privacy}

=== DATA PROCESSING AGREEMENT ===
{dpa}
=== END OF DOCUMENTS ===

For each of these data categories, decide whether the text above genuinely indicates \
this vendor's product processes it as part of the enterprise customer relationship:

{categories}

Respond with ONLY a JSON object, no markdown fences, no commentary, in exactly this shape:
{{"tags": [{{"key": "<category key>", "present": true|false, "confidence": "stated"|"conditional", \
"quote": "<a verbatim sentence copied exactly from the documents above supporting this, or empty \
string if present is false>", "reasoning": "<one sentence specific to this vendor and this data type>"}}]}}

Include one entry for every category listed, even when present is false. "stated" means the \
text plainly asserts the product does this; "conditional" means it is hedged, optional, describes \
an individual consumer relationship, or is boilerplate/definitional rather than a real claim.
"""


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _grounded(quote: str, haystacks: dict[str, str]) -> str | None:
    """Which doc kind actually contains this quote, or None if it's not a real match."""
    if not quote or len(quote.strip()) < 8:
        return None
    needle = _normalize(quote)
    for kind, text in haystacks.items():
        if needle in _normalize(text):
            return kind
    return None


def classify(vendor_name: str, vendor_category: str, texts: dict[str, str]) -> dict | None:
    """Same return shape as classify.classify(): {tags, max_sensitivity, sensitivity_score}.
    Returns None if the API key is missing or anything about the call/response is wrong --
    the caller is expected to fall back to the regex classifier in that case."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    docs = {k: v for k, v in texts.items() if k in ("privacy", "dpa") and v}
    if not docs:
        return None

    prompt = PROMPT.format(
        name=vendor_name, category=vendor_category, categories=CATEGORY_LIST,
        privacy=docs.get("privacy", "(not published / not readable as text)")[:MAX_DOC_CHARS],
        dpa=docs.get("dpa", "(not published / not readable as text)")[:MAX_DOC_CHARS],
    )

    try:
        r = requests.post(
            API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=dict(
                model=MODEL, max_tokens=2000,
                messages=[dict(role="user", content=prompt)],
            ),
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            log(f"    llm_classify: http {r.status_code}: {r.text[:200]}")
            return None
        raw = r.json()["content"][0]["text"].strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        parsed = json.loads(raw)
        entries = parsed["tags"]
    except Exception as e:
        log(f"    llm_classify: {type(e).__name__}: {e}")
        return None

    tags = []
    for e in entries:
        key = e.get("key")
        tag_def = TAG_BY_KEY.get(key)
        if not tag_def or not e.get("present"):
            continue
        source = _grounded(e.get("quote", ""), docs)
        if not source:
            log(f"    llm_classify: dropped ungrounded claim for {key!r} (quote not found in source)")
            continue
        reasoning = (e.get("reasoning") or "").strip()
        tags.append(dict(
            key=key, label=tag_def["label"], sensitivity=tag_def["sensitivity"],
            why=tag_def["why"] + (f" This vendor: {reasoning}" if reasoning else ""),
            source=source, matched=None, excerpt=e["quote"].strip(),
            confidence="stated" if e.get("confidence") == "stated" else "conditional",
        ))

    tags.sort(key=lambda t: (-classify_mod.SENSITIVITY_RANK[t["sensitivity"]], t["confidence"]))
    stated = [t for t in tags if t["confidence"] == "stated"]
    max_sensitivity = stated[0]["sensitivity"] if stated else "low"
    return dict(
        tags=tags,
        max_sensitivity=max_sensitivity,
        sensitivity_score=classify_mod.SENSITIVITY_SCORE[max_sensitivity],
        method="llm",
    )
