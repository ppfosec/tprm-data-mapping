"""Signals scanned in public job descriptions.

Each one is a claim a hiring manager made in public that bears on where data can
travel. Severity is about how directly the signal contradicts a clean residency
story, not about whether the practice is bad -- follow-the-sun support is good
engineering and a transfer at the same time.
"""

import re

SIGNALS = [
    dict(
        key="follow_the_sun",
        label="Follow-the-sun support",
        severity="high",
        pattern=r"follow[-\s]the[-\s]sun",
        why="A rotation that hands the same production access around the globe every eight hours.",
    ),
    dict(
        key="anywhere",
        label="Location-agnostic hiring",
        severity="high",
        pattern=r"work from anywhere|from anywhere in the world|hire anywhere|anywhere in the country",
        why="Staff placement is unconstrained, so staff location relative to your data is too.",
    ),
    dict(
        key="oncall",
        label="On-call access",
        severity="high",
        pattern=r"on[-\s]?call|pager ?duty|incident response rotation",
        why="Out-of-hours production access, granted broadly and audited thinly.",
    ),
    dict(
        key="brokered_inference",
        label="Brokered inference",
        severity="high",
        pattern=r"\bbedrock\b|vertex ai|azure openai|sagemaker",
        why="Model calls cross a third party's boundary before reaching the model.",
    ),
    dict(
        key="replication",
        label="Cross-region replication",
        severity="high",
        pattern=r"multi[-\s]?region|cross[-\s]region replication|failover|disaster recovery",
        why="Resilience design moves copies by default, and failover does not ask permission.",
    ),
    dict(
        key="travel",
        label="Travel expected",
        severity="high",
        pattern=r"travel (up to|approximately|roughly)? ?\d{1,2}\s?%|willing(ness)? to travel|international travel|frequent travel",
        why="Access travels with the person. A laptop holding production credentials crossing a border is an unlogged transfer.",
    ),
    dict(
        key="distributed",
        label="Distributed across time zones",
        severity="high",
        pattern=r"globally distributed|distributed (team|across time zones)|across (multiple )?time zones|any time ?zone",
        why="Deliberately spread across zones, so the people touching your tenant are as well.",
    ),
    dict(
        key="customer_data",
        label="Customer data in scope",
        severity="high",
        pattern=r"production access|prod access|access to customer data|customer data at scale",
        why="The posting says out loud that this seat touches your records.",
    ),
    dict(
        key="round_clock",
        label="Round-the-clock coverage",
        severity="medium",
        pattern=r"24/7|24x7|around the clock",
        why="Continuous coverage from one time zone is rare; assume more than one.",
    ),
    dict(
        key="gov_enclave",
        label="Government enclave",
        severity="low",
        pattern=r"gov ?cloud|fedramp|\bil[2-6]\b|impact level|itar",
        why="A separate sovereign estate exists, which confirms the commercial one is not it.",
    ),
    dict(
        key="named_region",
        label="Named cloud region",
        severity="low",
        pattern=r"us-east-1|us-west-2|eu-central-1|eu-west-1|ap-southeast-\d",
        why="Engineering names the regions it actually runs in, checkable against the sales claim.",
    ),
    dict(
        key="nationality",
        label="Nationality restriction",
        severity="low",
        pattern=r"security clearance|u\.?s\.? citizen|us person|must be a citizen",
        why="Some roles are nationality-gated, which means the rest are deliberately not.",
    ),
    dict(
        key="sovereignty_work",
        label="Sovereignty workstream",
        severity="low",
        pattern=r"data residency|sovereign|schrems|cross[-\s]border transfer|data localisation|data localization",
        why="They are staffing the problem, which is a good sign and an admission it is open.",
    ),
    dict(
        key="named_tooling",
        label="Named internal tooling",
        severity="low",
        pattern=r"\bzendesk\b|\bsalesforce\b|\bintercom\b|\bsnowflake\b|\bdatabricks\b|\bsegment\b",
        why="An internal stack named in a posting is a sub-processor hint to check against the published list.",
    ),
]

for _s in SIGNALS:
    _s["re"] = re.compile(_s["pattern"], re.I)

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

# Roles most likely to describe access to customer systems.
ROLE_HINT = re.compile(
    r"security|privacy|compliance|legal|infrastructure|platform|site reliability|\bsre\b|"
    r"support|solutions|architect|\bdata\b|trust|operations|devops|network|cloud",
    re.I,
)


def scan(text):
    """Return every signal present in one description, with a quoted excerpt."""
    hits = []
    for sig in SIGNALS:
        m = sig["re"].search(text)
        if not m:
            continue
        start = max(0, m.start() - 110)
        end = min(len(text), m.end() + 110)
        hits.append(
            dict(
                key=sig["key"],
                label=sig["label"],
                severity=sig["severity"],
                why=sig["why"],
                matched=m.group(0),
                excerpt=text[start:end].strip(),
            )
        )
    return hits
