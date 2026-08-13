"""Cross-check what the legal documents claim against what the job postings show.

Two lists side by side are not an assessment. The useful output is a specific
reconciliation: this sentence in the DPA says one thing, this posting says
another, here is the question to put to the vendor.

Every flag carries the exact source sentence and a live link to the posting, so
the reader checks the claim rather than trusting this file. Nothing here is a
finding of non-compliance -- a contradiction on the surface usually has a boring
explanation, and the point is to make someone go and ask for it.
"""

from __future__ import annotations

import re

import geo

# ---------------------------------------------------------------------------
# provider vocabulary
# ---------------------------------------------------------------------------
# Named third parties that would normally belong on a sub-processor list if they
# touch customer data. `tier` drives severity: infrastructure and model providers
# are the ones whose absence from a published list actually matters.

PROVIDERS = [
    # infrastructure
    ("Amazon Web Services", r"\baws\b|amazon web services|\bec2\b|\bs3\b", "infra"),
    ("Google Cloud", r"google cloud|\bgcp\b|bigquery", "infra"),
    ("Microsoft Azure", r"\bazure\b", "infra"),
    ("Cloudflare", r"cloudflare", "infra"),
    ("Fastly", r"\bfastly\b", "infra"),
    ("Akamai", r"akamai", "infra"),
    ("Oracle Cloud", r"oracle cloud|\boci\b", "infra"),
    ("DigitalOcean", r"digitalocean", "infra"),
    # model / inference
    ("Amazon Bedrock", r"\bbedrock\b", "model"),
    ("Google Vertex AI", r"vertex ai", "model"),
    ("Azure OpenAI", r"azure openai", "model"),
    ("OpenAI", r"\bopenai\b", "model"),
    ("Anthropic", r"anthropic|\bclaude\b", "model"),
    ("Hugging Face", r"hugging ?face", "model"),
    ("Cohere", r"\bcohere\b", "model"),
    ("SageMaker", r"sagemaker", "model"),
    # data platforms
    ("Snowflake", r"snowflake", "data"),
    ("Databricks", r"databricks", "data"),
    ("MongoDB", r"mongodb|atlas", "data"),
    ("Confluent", r"confluent|\bkafka\b", "data"),
    ("Elastic", r"elasticsearch|\belastic\b", "data"),
    ("Redis", r"\bredis\b", "data"),
    ("Pinecone", r"pinecone", "data"),
    # telemetry and support
    ("Datadog", r"datadog", "telemetry"),
    ("Splunk", r"splunk", "telemetry"),
    ("Sentry", r"\bsentry\b", "telemetry"),
    ("New Relic", r"new relic", "telemetry"),
    ("PagerDuty", r"pager ?duty", "telemetry"),
    ("Zendesk", r"zendesk", "support"),
    ("Intercom", r"intercom", "support"),
    ("Salesforce", r"salesforce", "support"),
    ("HubSpot", r"hubspot", "support"),
    ("Twilio", r"twilio", "support"),
    ("Slack", r"\bslack\b", "support"),
    # analytics
    ("Segment", r"\bsegment\b", "analytics"),
    ("Amplitude", r"amplitude", "analytics"),
    ("Mixpanel", r"mixpanel", "analytics"),
    ("Looker", r"\blooker\b", "analytics"),
]

PROVIDER_RE = [(name, re.compile(rx, re.I), tier) for name, rx, tier in PROVIDERS]

TIER_SEVERITY = {
    "infra": "high",
    "model": "high",
    "data": "medium",
    "telemetry": "medium",
    "support": "medium",
    "analytics": "low",
}

# ---------------------------------------------------------------------------
# claim extraction
# ---------------------------------------------------------------------------
# Snapshots are written one sentence per line, so a claim is just a line that
# matches. That is the whole reason for the line format.

DATA_NOUN = re.compile(
    r"personal (data|information)|customer data|customer content|your data|user data|"
    r"the data|account data|payment data",
    re.I,
)

LOCATION_VERB = re.compile(
    r"\b(stored?|hosted?|processed?|located|resides?|remains?|kept|transferred|"
    r"replicated|maintained)\b",
    re.I,
)

# "If you are located in the EEA, see our..." is a pointer to a different notice,
# not a promise about where anything sits. Reader-conditional sentences are the
# main false positive in privacy policies, so they are excluded outright.
READER_CONDITIONAL = re.compile(r"^(if|where|when|unless)\s+(you|your)\b", re.I)

# "To view the measures we apply to data transferred from the EEA, see..." points
# at another page. Navigational sentences mention places without promising anything.
POINTER = re.compile(
    r"^(to (view|learn|read|find|see)|for (more|further)|please (see|refer|visit)|see (our|the)|read more|click|visit)\b",
    re.I,
)


def is_residency_claim(line: str) -> bool:
    if READER_CONDITIONAL.match(line) or POINTER.match(line):
        return False
    return bool(DATA_NOUN.search(line)
                and LOCATION_VERB.search(line)
                and REGION_TOKENS.search(line))


TRANSFER_RE = re.compile(
    r"standard contractual clauses|\bsccs?\b|data privacy framework|\bdpf\b|"
    r"binding corporate rules|\bbcrs?\b|adequacy decision|international transfer|"
    r"transfer(red)? (personal data )?(outside|to a third country)",
    re.I,
)

ACCESS_RE = re.compile(
    r"(personnel|employees|staff|engineers|support|contractors)\b[^.]{0,90}"
    r"(access|process|handle)\b[^.]{0,90}(personal data|customer data|your data)|"
    r"need[- ]to[- ]know|least privilege|access is (limited|restricted)",
    re.I,
)

REGION_TOKENS = re.compile(
    r"european economic area|\beea\b|european union|\beu\b|united states|"
    r"united kingdom|switzerland|canada|australia|singapore|japan|germany|"
    r"ireland|france|netherlands|india|brazil|us-east-\d|us-west-\d|eu-west-\d|"
    r"eu-central-\d|ap-southeast-\d",
    re.I,
)


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def extract_claims(texts: dict[str, str]) -> dict:
    """texts maps doc kind -> snapshot body."""
    claims = dict(residency=[], transfer=[], access=[], providers={}, regions=set())
    for kind, body in texts.items():
        for line in _lines(body):
            if len(line) > 400 or len(line) < 45:
                continue  # headings are not claims
            if is_residency_claim(line):
                claims["residency"].append(dict(kind=kind, text=line))
            if TRANSFER_RE.search(line):
                claims["transfer"].append(dict(kind=kind, text=line))
            if ACCESS_RE.search(line):
                claims["access"].append(dict(kind=kind, text=line))
            for m in REGION_TOKENS.finditer(line):
                claims["regions"].add(m.group(0).lower())
        for name, rx, tier in PROVIDER_RE:
            if rx.search(body):
                claims["providers"].setdefault(name, kind)
    return claims


def providers_in_jobs(job_signals: list[dict]) -> dict[str, list[dict]]:
    """Providers named inside job descriptions, with the posting that named them."""
    out: dict[str, list[dict]] = {}
    for sig in job_signals:
        for ex in sig.get("examples", []):
            blob = f"{ex.get('excerpt','')} {ex.get('matched','')}"
            for name, rx, tier in PROVIDER_RE:
                if rx.search(blob):
                    out.setdefault(name, [])
                    if len(out[name]) < 2 and ex not in out[name]:
                        out[name].append(ex)
    return out


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------

def crosscheck(texts: dict[str, str], docs: list[dict], jobs: dict) -> list[dict]:
    flags: list[dict] = []
    claims = extract_claims(texts)
    doc_url = {d["kind"]: d["url"] for d in docs}
    sub_doc = next((d for d in docs if d["kind"] == "subprocessors"), None)
    tier_of = {name: tier for name, _, tier in PROVIDERS}

    # --- R1: a provider engineering talks about that the published list omits
    #
    # Only run this when a sub-processor list was actually read. Accusing a vendor
    # of omitting a name from a document this collector never parsed would be a
    # fabrication, so a thin or unreadable list produces one honest flag instead.
    list_readable = bool(
        sub_doc and sub_doc.get("path")
        and (sub_doc.get("lines", 0) >= 40 or len(claims["providers"]) >= 3)
    )
    if sub_doc and sub_doc.get("path") and not list_readable:
        flags.append(dict(
            rule="list_unreadable",
            severity="medium",
            headline="Sub-processor list too thin to check against",
            detail=(
                f"The page at {sub_doc['url']} yielded only {sub_doc.get('lines', 0)} lines of "
                f"text, which usually means the actual list is rendered by script or held in "
                f"an embedded table. No comparison against hiring signals is possible, so none "
                f"is reported."
            ),
            claim=None,
            evidence=[dict(kind="doc", excerpt=sub_doc["url"], url=sub_doc["url"])],
            question=(
                "Can you supply the sub-processor list as a document rather than a rendered "
                "page, so it can be reviewed and version-compared?"
            ),
        ))

    if jobs.get("ok") and list_readable:
        named = providers_in_jobs(jobs.get("signals", []))
        listed = claims["providers"]
        for provider, examples in sorted(named.items()):
            if provider in listed:
                continue
            tier = tier_of.get(provider, "low")
            if tier == "low":
                continue
            flags.append(dict(
                rule="subprocessor_gap",
                severity=TIER_SEVERITY[tier],
                headline=f"{provider} appears in hiring, not in the published documents",
                detail=(
                    f"Engineering job descriptions name {provider}, but it does not appear "
                    f"anywhere in the legal documents collected"
                    + (f" including the sub-processor list at {sub_doc['url']}" if sub_doc else
                       ", and no sub-processor list was found at all")
                    + "."
                ),
                claim=None,
                evidence=[dict(kind="job", **e) for e in examples],
                question=(
                    f"Is {provider} a sub-processor? If it is, when was it added to the list, "
                    f"and were customers notified? If it never touches customer data, what "
                    f"is it used for?"
                ),
            ))

    # --- R2: a residency claim against where the company actually hires
    # A board that places only a handful of roles cannot support a claim about where
    # a workforce sits; 6 of 6 non-EEA is noise, not a pattern.
    if jobs.get("ok") and jobs.get("placeable", 0) >= 20:
        non_eea_share = jobs["non_eea"] / jobs["placeable"]
        eu_claims = [c for c in claims["residency"]
                     if re.search(r"eea|european", c["text"], re.I)]
        if eu_claims and non_eea_share > 0.5:
            top = [c for c in list(jobs["countries"])[:4] if c not in geo.EEA]
            flags.append(dict(
                rule="residency_vs_workforce",
                severity="high",
                headline="European residency language, largely non-European workforce",
                detail=(
                    f"{jobs['non_eea']} of {jobs['placeable']} placeable roles name no EEA "
                    f"site — most prominently {', '.join(top[:3])}. Storage location and "
                    f"personnel location are different controls, and only one of them is in "
                    f"the clause."
                ),
                claim=dict(kind=eu_claims[0]["kind"],
                           text=eu_claims[0]["text"],
                           url=doc_url.get(eu_claims[0]["kind"])),
                evidence=[dict(kind="stat",
                               excerpt=f"{c}: {jobs['countries'][c]} open roles")
                          for c in top],
                question=(
                    "Which roles can access production data, and from which countries? "
                    "Does the residency commitment cover support and engineering access, "
                    "or only data at rest?"
                ),
            ))

    # --- R3: limited-access language against round-the-clock rotations
    rotation = [s for s in jobs.get("signals", [])
                if s["key"] in {"follow_the_sun", "round_clock", "oncall", "distributed"}]
    if claims["access"] and rotation:
        labels = ", ".join(sorted({s["label"].lower() for s in rotation}))
        ex = rotation[0].get("examples", [])[:2]
        flags.append(dict(
            rule="access_vs_rotation",
            severity="medium",
            headline="Restricted-access language alongside global rotations",
            detail=(
                f"The documents describe access controls in principle, while postings "
                f"describe {labels}. Both can be true; the reconciliation is what a "
                f"reviewer needs to see."
            ),
            claim=dict(kind=claims["access"][0]["kind"],
                       text=claims["access"][0]["text"],
                       url=doc_url.get(claims["access"][0]["kind"])),
            evidence=[dict(kind="job", **e) for e in ex],
            question=(
                "For out-of-hours incidents, who is on the rotation, where are they, and "
                "is their access to customer data logged and reviewable by the customer?"
            ),
        ))

    # --- R4: no transfer mechanism named anywhere, but hiring spans borders
    if jobs.get("ok") and not claims["transfer"]:
        spread = len([c for c in jobs.get("countries", {}) if c != geo.UNPLACEABLE])
        if spread >= 3:
            flags.append(dict(
                rule="no_transfer_mechanism",
                severity="medium",
                headline="No transfer mechanism named in the documents collected",
                detail=(
                    f"None of the collected documents mention standard contractual clauses, "
                    f"an adequacy decision, the Data Privacy Framework or binding corporate "
                    f"rules, while hiring spans {spread} countries. The mechanism may live in "
                    f"a document this collector did not reach."
                ),
                claim=None,
                evidence=[dict(kind="stat", excerpt=f"{spread} countries in open roles")],
                question=(
                    "Which transfer mechanism applies to our data, and where is it published?"
                ),
            ))

    # --- R5: the sub-processor list exists but cannot be diffed
    if sub_doc and not sub_doc.get("path"):
        flags.append(dict(
            rule="unverifiable_list",
            severity="medium",
            headline="Sub-processor list cannot be captured as text",
            detail=(
                f"The list at {sub_doc['url']} renders in the browser only, so neither this "
                f"collector nor a web archive can preserve what it said on a given date. "
                f"A customer can read it today and cannot prove its contents last quarter."
            ),
            claim=None,
            evidence=[dict(kind="doc", excerpt=sub_doc["url"], url=sub_doc["url"])],
            question=(
                "Can you provide the sub-processor list in a durable format, and commit to "
                "advance notice of changes in the contract rather than on a web page?"
            ),
        ))

    # --- R6: no sub-processor list found at all
    if not sub_doc:
        flags.append(dict(
            rule="no_subprocessor_list",
            severity="high",
            headline="No sub-processor list found",
            detail=(
                "No page matching a sub-processor list was reachable from the vendor's own "
                "legal pages. It may exist behind a login or a trust portal, which is itself "
                "worth noting: an unlisted chain cannot be reviewed before signature."
            ),
            claim=None,
            evidence=[],
            question=(
                "Where is the current sub-processor list published, and how are customers "
                "notified before a new one is added?"
            ),
        ))

    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: order[f["severity"]])
    return flags
