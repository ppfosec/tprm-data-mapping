#!/usr/bin/env python3
"""Collect public sovereignty evidence for each vendor in vendors.yaml.

Run by GitHub Actions on a schedule. Two outputs:

  data/snapshots/<vendor>/<doc>.txt   normalised plaintext, one sentence per line
  data/index.json                     everything the dashboard reads

The snapshots are the point. They are committed, so `git log -p` on a file is a
dated, tamper-evident record of every wording change in a privacy policy or DPA.
One sentence per line means a reworded clause shows up as a one-line diff instead
of a reflowed paragraph.

Nothing here needs credentials. Every source is public.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import pathlib
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

import correlate
import geo
import signals as sig_mod

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
DRIFT_LOG = DATA / "drift-log.json"
MAX_HUNKS_PER_EVENT = 6
MAX_LOG_EVENTS = 300

UA = "sovereignty-drift/0.1 (public policy monitoring; +https://github.com/)"
HEADERS = {"User-Agent": UA, "Accept-Language": "en"}
TIMEOUT = 30

GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
CDX = "https://web.archive.org/cdx/search/cdx"

DOC_PATTERNS = [
    ("subprocessors", re.compile(
        r"sub[-_]?processor|service[-_ ]providers?|third[-_ ]part(y|ies)[-_ ]list|"
        r"vendor[-_ ]list", re.I)),
    ("dpa", re.compile(r"\bdpa\b|data[-_ ]processing[-_ ](addendum|agreement)", re.I)),
    ("privacy", re.compile(r"privacy[-_ ](policy|statement|notice)|/privacy", re.I)),
    ("terms", re.compile(r"terms[-_ ]of[-_ ](service|use)|commercial[-_ ]terms", re.I)),
]

EXPECTED_KINDS = {"privacy", "dpa", "subprocessors"}

DOC_LABEL = {
    "privacy": "Privacy policy",
    "dpa": "Data processing agreement",
    "subprocessors": "Sub-processor list",
    "terms": "Terms",
    "other": "Other legal page",
}

log = lambda *a: print(*a, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------
# fetching
# ----------------------------------------------------------------------------

RETRY_STATUS = {429, 500, 502, 503, 504}


def get(url, retries=3, **kw):
    """Public endpoints here throttle unpredictably -- Greenhouse returns a random
    503 often enough that a single attempt is not a measurement."""
    delay = 1.0
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
            if r.status_code not in RETRY_STATUS:
                return r
            last = r
        except requests.RequestException as e:
            last = e
        if attempt < retries - 1:
            time.sleep(delay)
            delay *= 2.5
    if isinstance(last, Exception):
        raise last
    return last


def classify(url: str) -> str | None:
    for kind, rx in DOC_PATTERNS:
        if rx.search(url):
            return kind
    return None


def discover_docs(vendor: dict) -> list[dict]:
    """Verify the seed URLs, then follow links out of whatever answered.

    Legal pages almost always link to each other -- a privacy policy points at
    the DPA, the DPA points at the sub-processor list -- so one live seed is
    usually enough to find the rest.
    """
    site = vendor["site"].rstrip("/")
    host = urlparse(site).netloc.replace("www.", "")
    found: dict[str, dict] = {}
    to_scan = []

    for path in vendor.get("legal_candidates", []):
        url = site + path
        try:
            r = get(url, allow_redirects=True)
        except requests.RequestException as e:
            log(f"    seed {path} -> {type(e).__name__}")
            continue
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            log(f"    seed {path} -> {r.status_code}")
            continue
        kind = classify(r.url) or classify(path) or "other"
        found.setdefault(kind, dict(kind=kind, url=r.url, html=r.text))
        to_scan.append(r.text)
        log(f"    seed {path} -> 200 [{kind}]")

    # follow links out of the pages that answered
    missing = EXPECTED_KINDS - set(found)
    for html in to_scan:
        if not missing:
            break
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            if not missing:
                break
            href = urljoin(site, a["href"].split("#")[0])
            if urlparse(href).netloc.replace("www.", "") != host:
                continue
            kind = classify(href)
            if kind not in missing:
                continue
            try:
                r = get(href, allow_redirects=True)
            except requests.RequestException:
                continue
            if r.status_code != 200:
                continue
            found[kind] = dict(kind=kind, url=r.url, html=r.text)
            missing.discard(kind)
            log(f"    linked -> {kind}: {r.url}")
            time.sleep(0.4)

    return list(found.values())


# ----------------------------------------------------------------------------
# normalising for diffable snapshots
# ----------------------------------------------------------------------------

BOILERPLATE = re.compile(
    r"^(cookie|accept all|manage preferences|skip to|menu|search|sign in|log in|"
    r"get started|contact sales|©|copyright)",
    re.I,
)


def to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return main.get_text("\n")


def to_lines(text: str) -> str:
    """One sentence per line, so a reworded clause is a one-line diff."""
    out = []
    for block in text.split("\n"):
        block = re.sub(r"\s+", " ", block).strip()
        if len(block) < 3 or BOILERPLATE.match(block):
            continue
        # split on sentence ends, keeping the terminator
        for piece in re.split(r"(?<=[.!?;:])\s+(?=[A-Z(])", block):
            piece = piece.strip()
            if piece:
                out.append(piece)
    # collapse consecutive duplicates (nav echoes)
    deduped = [l for i, l in enumerate(out) if i == 0 or l != out[i - 1]]
    return "\n".join(deduped) + "\n"


def strip_header(text: str) -> str:
    """Drop the two '# source / # collected' comment lines this collector writes."""
    parts = text.split("\n\n", 1)
    return parts[1] if len(parts) == 2 and parts[0].startswith("# source:") else text


def diff_lines(old_body: str, new_body: str) -> list[dict]:
    """Sentence-level before/after pairs for a wording change. One sentence per
    line means a reworded clause is a 'replace' opcode of size 1-1 -- exactly the
    quote a reviewer wants -- rather than a reflowed-paragraph diff."""
    old_lines = [l for l in old_body.splitlines() if l.strip()]
    new_lines = [l for l in new_body.splitlines() if l.strip()]
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    hunks = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        olds, news = old_lines[i1:i2], new_lines[j1:j2]
        for k in range(max(len(olds), len(news))):
            hunks.append(dict(
                before=olds[k] if k < len(olds) else None,
                after=news[k] if k < len(news) else None,
            ))
            if len(hunks) >= MAX_HUNKS_PER_EVENT:
                return hunks
    return hunks


def write_snapshot(vendor_id: str, kind: str, url: str, body: str) -> dict:
    d = SNAPSHOTS / vendor_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{kind}.txt"

    diff = None
    if path.exists():
        old_body = strip_header(path.read_text(encoding="utf-8"))
        if old_body.strip() != body.strip():
            diff = diff_lines(old_body, body)

    header = f"# source: {url}\n# collected: {datetime.now(timezone.utc).date().isoformat()}\n\n"
    path.write_text(header + body, encoding="utf-8")
    return dict(
        kind=kind,
        url=url,
        path=str(path.relative_to(ROOT)),
        lines=body.count("\n"),
        chars=len(body),
        sha256=hashlib.sha256(body.encode()).hexdigest()[:16],
        diff=diff,
    )


def load_drift_log(new_events: list[dict]) -> list[dict]:
    """Merge this run's change events into the persisted log and write it back.

    The log is the point: index.json only ever holds the current state, so
    without this file 'what changed since two weeks ago' would not survive
    past the next run."""
    existing = []
    if DRIFT_LOG.exists():
        try:
            existing = json.loads(DRIFT_LOG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []

    merged = {e["id"]: e for e in existing}
    for e in new_events:
        merged[e["id"]] = e

    events = sorted(merged.values(), key=lambda e: e["date"], reverse=True)[:MAX_LOG_EVENTS]
    DRIFT_LOG.write_text(json.dumps(events, indent=2, ensure_ascii=False))
    return events


# ----------------------------------------------------------------------------
# wayback
# ----------------------------------------------------------------------------

def prune_snapshots(vendor_id: str, keep: set[str]) -> None:
    """Delete snapshots for documents that were not collected this run.

    A page that moved, was reclassified or was taken down must disappear from the
    tree, otherwise the git history stops being an honest record of what the
    vendor publishes today."""
    d = SNAPSHOTS / vendor_id
    if not d.exists():
        return
    for f in d.glob("*.txt"):
        if f.stem not in keep:
            f.unlink()
            log(f"    pruned stale snapshot: {f.name}")


def archive_history(url: str) -> dict:
    """Distinct-content captures for one URL. Blocked or throttled is reported, not faked."""
    target = re.sub(r"^https?://", "", url)
    params = dict(
        url=target, output="json", fl="timestamp,digest",
        collapse="digest", filter="statuscode:200", limit="500",
    )
    try:
        r = get(CDX, params=params)
        if r.status_code != 200:
            return dict(ok=False, reason=f"http {r.status_code}")
        rows = r.json()
    except Exception as e:
        return dict(ok=False, reason=type(e).__name__)
    body = rows[1:] if rows and rows[0] and rows[0][0] == "timestamp" else rows
    stamps = sorted(x[0] for x in body if x and x[0])
    if not stamps:
        return dict(ok=True, captures=0, revisions=0, first=None, last=None)
    fmt = lambda t: f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    return dict(
        ok=True,
        captures=len(stamps),
        revisions=max(0, len(stamps) - 1),
        first=fmt(stamps[0]),
        last=fmt(stamps[-1]),
    )


# ----------------------------------------------------------------------------
# job boards
# ----------------------------------------------------------------------------

def collect_jobs(vendor: dict, sample: int) -> dict:
    board = vendor.get("board") or {}
    if board.get("type") != "greenhouse":
        return dict(ok=False, reason="no supported board")
    try:
        r = get(GREENHOUSE.format(token=board["token"]))
        if r.status_code != 200:
            return dict(ok=False, reason=f"http {r.status_code}")
        jobs = r.json().get("jobs", [])
    except Exception as e:
        return dict(ok=False, reason=type(e).__name__)

    tally: dict[str, int] = {}
    placeable = eea = unplaceable = 0
    for j in jobs:
        cs = geo.countries_of((j.get("location") or {}).get("name"))
        if not cs:
            unplaceable += 1
            continue
        placeable += 1
        if cs & geo.EEA:
            eea += 1
        for c in cs:
            tally[c] = tally.get(c, 0) + 1

    pool = [j for j in jobs if sig_mod.ROLE_HINT.search(j.get("title", ""))][:sample]
    if not pool:
        pool = jobs[:sample]

    grouped: dict[str, dict] = {}
    scanned = 0
    for j in pool:
        try:
            d = get(f"{GREENHOUSE.format(token=board['token'])}/{j['id']}").json()
        except Exception:
            continue
        text = to_text(d.get("content", "").replace("&lt;", "<").replace("&gt;", ">"))
        text = re.sub(r"\s+", " ", text)
        scanned += 1
        for hit in sig_mod.scan(text):
            g = grouped.setdefault(
                hit["key"],
                dict(key=hit["key"], label=hit["label"], severity=hit["severity"],
                     why=hit["why"], count=0, examples=[]),
            )
            g["count"] += 1
            if len(g["examples"]) < 3:
                g["examples"].append(dict(
                    title=d.get("title"),
                    location=(d.get("location") or {}).get("name"),
                    url=d.get("absolute_url"),
                    matched=hit["matched"],
                    excerpt=hit["excerpt"],
                ))
        time.sleep(0.15)

    order = {"high": 0, "medium": 1, "low": 2}
    found = sorted(grouped.values(), key=lambda g: (order[g["severity"]], -g["count"]))

    return dict(
        ok=True,
        total=len(jobs),
        placeable=placeable,
        unplaceable=unplaceable,
        eea=eea,
        non_eea=placeable - eea,
        countries=dict(sorted(tally.items(), key=lambda kv: -kv[1])),
        scanned=scanned,
        signals=found,
    )


# ----------------------------------------------------------------------------
# index
# ----------------------------------------------------------------------------

def score(vendor_row: dict) -> dict:
    """A public-evidence index, 0-100. Higher means more exposure visible in public
    sources or less of it verifiable. It measures the paper trail, not the vendor."""
    jobs = vendor_row["jobs"]
    docs = vendor_row["docs"]

    if jobs.get("ok") and jobs["placeable"]:
        footprint = round(25 * (jobs["non_eea"] / jobs["placeable"]))
    else:
        footprint = 25  # a board that names no country tells you nothing, so assume nothing

    weight = sum(sig_mod.SEVERITY_WEIGHT[s["severity"]] * min(s["count"], 4)
                 for s in jobs.get("signals", []))
    access = min(25, round(weight * 1.2))

    published = {d["kind"] for d in docs} & EXPECTED_KINDS
    diffable = {d["kind"] for d in docs if d.get("path")} & EXPECTED_KINDS
    # A sub-processor list that exists but is client-rendered is half a document:
    # a customer can read it today and cannot prove what it said last quarter.
    credit = (len(published) + len(diffable)) / (2 * len(EXPECTED_KINDS))
    transparency = round(25 * (1 - credit))

    revs = [d["archive"]["revisions"] for d in docs
            if d.get("archive", {}).get("ok") and d["archive"].get("revisions") is not None]
    if revs:
        record = max(0, 25 - min(25, round(sum(revs) / len(revs))))
    else:
        record = 25

    total = footprint + access + transparency + record
    return dict(total=total, footprint=footprint, access=access,
                transparency=transparency, record=record)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="collect a single vendor id")
    ap.add_argument("--sample", type=int, default=26, help="job descriptions to read per vendor")
    ap.add_argument("--skip-archive", action="store_true", help="skip Wayback lookups")
    args = ap.parse_args()

    vendors = yaml.safe_load((pathlib.Path(__file__).parent / "vendors.yaml").read_text())
    if args.only:
        vendors = [v for v in vendors if v["id"] == args.only]
        if not vendors:
            sys.exit(f"no vendor with id {args.only}")

    DATA.mkdir(exist_ok=True)
    rows = []
    today = datetime.now(timezone.utc).date().isoformat()
    new_events = []

    for v in vendors:
        log(f"\n[{v['id']}]")
        docs = []
        texts = {}
        for doc in discover_docs(v):
            body = to_lines(to_text(doc["html"]))
            thin = len(body) < 400
            if thin:
                # Trust centres are commonly client-rendered, so the sub-processor
                # list a customer is pointed at cannot be diffed by anyone without
                # a headless browser. Record that rather than dropping the doc.
                rec = dict(kind=doc["kind"], url=doc["url"], path=None, lines=0,
                           chars=len(body), sha256=None,
                           note="published but not extractable as text (client-rendered)", diff=None)
                log(f"    {doc['kind']}: client-rendered, no diffable text")
            else:
                rec = write_snapshot(v["id"], doc["kind"], doc["url"], body)
                rec["note"] = None
                texts[doc["kind"]] = body
                if rec["diff"]:
                    new_events.append(dict(
                        id=f"{v['id']}-{doc['kind']}-{today}",
                        vendor_id=v["id"], vendor_name=v["name"],
                        document=doc["kind"], document_label=DOC_LABEL.get(doc["kind"], doc["kind"]),
                        date=today, url=rec["url"], hunks=rec["diff"],
                    ))
                    log(f"    {doc['kind']}: {len(rec['diff'])} line(s) changed since last run")
                del rec["diff"]
            rec["archive"] = (dict(ok=False, reason="skipped") if args.skip_archive
                              else archive_history(doc["url"]))
            if not thin:
                log(f"    {doc['kind']}: {rec['lines']} lines, archive={rec['archive']}")
            docs.append(rec)
            time.sleep(0.5)

        prune_snapshots(v["id"], {d["kind"] for d in docs if d.get("path")})

        jobs = collect_jobs(v, args.sample)
        log(f"    jobs: {jobs.get('total', '-')} roles, "
            f"{len(jobs.get('signals', []))} signals, scanned {jobs.get('scanned', 0)}")

        row = dict(
            id=v["id"], name=v["name"], category=v["category"],
            hq=v["hq"], hq_iso=v.get("hq_iso"), site=v["site"],
            docs=docs, jobs=jobs,
        )
        row["crosschecks"] = correlate.crosscheck(texts, docs, jobs)
        row["score"] = score(row)
        log(f"    crosschecks: {len(row['crosschecks'])} "
            f"({', '.join(f['rule'] for f in row['crosschecks']) or 'none'})")
        rows.append(row)

    drift_log = load_drift_log(new_events)
    by_vendor: dict[str, list] = {}
    for ev in drift_log:
        by_vendor.setdefault(ev["vendor_id"], []).append(ev)
    for row in rows:
        row["drift"] = by_vendor.get(row["id"], [])[:6]

    index = dict(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        vendor_count=len(rows),
        signal_catalogue=[
            dict(key=s["key"], label=s["label"], severity=s["severity"], why=s["why"])
            for s in sig_mod.SIGNALS
        ],
        vendors=rows,
    )
    (DATA / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False))
    log(f"\nwrote {DATA / 'index.json'} ({len(rows)} vendors)")


if __name__ == "__main__":
    main()
