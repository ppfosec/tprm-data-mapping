"""What kind of data a vendor's own privacy policy and DPA say they process.

A compliance reviewer's first question about a vendor is not "is this vendor
good" -- it is "what does this vendor touch, and how sensitive is it." This
scans the same normalised text the collector already snapshots and tags it
against a small, fixed taxonomy. Nothing here is a legal classification of
what the vendor actually does; it is a reading of what the vendor's own
published text admits to, same as everything else in this collector.
"""

import re

TAGS = [
    dict(
        key="business_contact", label="Business contact information", sensitivity="low",
        pattern=r"\b(business )?contact information\b|\bname,? (?:and )?email\b|\bwork email\b",
        why="Names, work emails and similar identifiers -- present in nearly every SaaS privacy policy.",
    ),
    dict(
        key="account_usage", label="Account & usage data", sensitivity="low",
        pattern=r"\busage data\b|\blog data\b|\bdevice identifier|\bcookies?\b|\bip address\b",
        why="Login activity, device and session data -- routine telemetry, not by itself sensitive.",
    ),
    dict(
        key="financial", label="Financial / payment data", sensitivity="medium",
        pattern=r"\bpayment card\b|\bcredit card\b|\bbank account\b|\bbilling information\b|\bpayment information\b",
        why="Card or bank details -- a breach here has direct financial consequences for the data subject.",
    ),
    dict(
        key="precise_location", label="Precise location", sensitivity="medium",
        pattern=r"\bprecise location\b|\bgeolocation data\b|\bgps (?:data|coordinates)\b",
        why="Where someone actually is, not just which country they signed up from.",
    ),
    dict(
        key="employment_hr", label="Employment / HR data", sensitivity="medium",
        pattern=r"\bbackground check\b|\bemployment history\b|\bhuman resources\b|\bhr information\b",
        why="Job history and HR records -- regulated as employee data in most jurisdictions.",
    ),
    dict(
        key="health", label="Health data", sensitivity="high",
        pattern=r"\bhealth information\b|\bmedical (?:information|record)\b|\b(?:protected health information|phi)\b",
        why="Health records are a GDPR Article 9 / HIPAA-adjacent special category almost everywhere.",
    ),
    dict(
        key="biometric", label="Biometric data", sensitivity="high",
        pattern=r"\bbiometric\b|\bfacial recognition\b|\bfingerprint\b|\bvoiceprint\b",
        why="Biometric identifiers are irrevocable if exposed -- a special category under GDPR Article 9.",
    ),
    dict(
        key="government_id", label="Government ID", sensitivity="high",
        pattern=r"\bgovernment[- ]issued id\b|\bpassport number\b|\bsocial security number\b|\bnational identification\b|\btax identification number\b",
        why="Passport, national ID or tax numbers -- enables identity theft directly if leaked.",
    ),
    dict(
        key="children", label="Children's data", sensitivity="high",
        pattern=r"\bchildren under (?:the age of )?(?:13|16|18)\b|\bcoppa\b|\bparental consent\b",
        why="Processing minors' data triggers COPPA / GDPR-K obligations most vendors would rather not have.",
    ),
    dict(
        key="special_category", label="Special-category data (GDPR Art. 9)", sensitivity="high",
        pattern=r"racial or ethnic origin|religious belief|trade union membership|sexual orientation|political opinion",
        why="GDPR's own list of special categories -- the highest bar for lawful processing.",
    ),
]

for _t in TAGS:
    _t["re"] = re.compile(_t["pattern"], re.I)

# Privacy policies almost universally deny collecting children's data in the
# same breath they mention it ("we do not knowingly collect ... from children
# under 13"). One sentence per line means that denial is the whole line, so a
# same-line negation check catches it without needing real parsing.
NEGATION = re.compile(r"\bnot\b|\bno longer\b|\bnever\b|\bdo not\b|\bdoes not\b|\bwithout knowingly\b|\bexcludes?\b", re.I)

# A privacy policy usually covers the marketing website AND the product, and
# it hedges constantly: "the input of special category data to the Services,
# which include..." is GitLab warning customers not to paste sensitive data
# into an issue, not GitLab's product processing biometrics as a feature.
# Mentioning a data type conditionally is not the same claim as processing it
# -- catch the common hedge phrasings so those mentions get a lower-confidence
# "conditional" tag that does not, by itself, drive the sensitivity score.
HEDGE = re.compile(
    r"\bif you choose\b|\bif applicable\b|\bthe input of\b|\byou (?:may |might )?"
    r"(?:choose to |elect to |decide to )?(?:input|provide|submit|upload|enter)\b|"
    r"\bto the extent (?:you|permitted)\b|\bat your discretion\b|\bshould you provide\b|"
    r"\byou can separately consent\b|\bwith your consent\b|"
    r"\bif you purchase\b|\byour (?:personal )?credit card\b|\bself[- ]serve\b|\bself[- ]service\b|"
    r"\bas an? (?:independent )?controller\b|\backing as (?:a |an )?controller\b|"
    r"\bfor (?:its|our) own (?:business )?purposes\b",
    re.I,
)

# Legal boilerplate that defines a term or states a scope rather than
# admitting the vendor processes something: "'Sensitive Data' means genetic
# data, biometric data..." is drafting a defined term for the contract, not
# a claim that this vendor's product touches genetic data.
DEFINITIONAL = re.compile(
    r"\bas defined (?:under|in|by)\b|\bwithin the meaning of\b|\bfor (?:the )?purposes? of this\b|"
    r"\bnot limited to\b|\bmeans\b.{0,3}(?:genetic|biometric|racial|health|religious)",
    re.I,
)

SENSITIVITY_RANK = {"low": 0, "medium": 1, "high": 2}
SENSITIVITY_SCORE = {"low": 10, "medium": 20, "high": 30}
CONFIDENCE_RANK = {"conditional": 0, "stated": 1}


def classify(texts: dict[str, str]) -> dict:
    """texts: {doc_kind: normalised_body}. Returns tags found plus the overall tier.

    Only "stated" tags (the vendor's text asserts this plainly) drive
    max_sensitivity / sensitivity_score. "Conditional" tags -- hedged on the
    customer doing something first, defining a contract term, or describing
    the vendor's own controller-role processing rather than what it does for
    an enterprise customer -- are still returned for a reviewer to see, but
    don't by themselves make a vendor look riskier than its policy actually
    claims."""
    found = []
    for kind, body in texts.items():
        if kind not in ("privacy", "dpa", "terms", "other"):
            continue
        lines = body.splitlines()
        for tag in TAGS:
            for line in lines:
                m = tag["re"].search(line)
                if not m or NEGATION.search(line):
                    continue
                found.append(dict(
                    key=tag["key"], label=tag["label"], sensitivity=tag["sensitivity"],
                    why=tag["why"], source=kind, matched=m.group(0), excerpt=line.strip(),
                    confidence="conditional" if HEDGE.search(line) or DEFINITIONAL.search(line) else "stated",
                ))
                break  # one example per document is enough

    # keep one example per tag key: prefer a stated mention over a conditional
    # one, and among equals prefer the one already recorded
    best: dict[str, dict] = {}
    for f in found:
        cur = best.get(f["key"])
        if cur is None or CONFIDENCE_RANK[f["confidence"]] > CONFIDENCE_RANK[cur["confidence"]]:
            best[f["key"]] = f

    tags = sorted(best.values(), key=lambda t: (-SENSITIVITY_RANK[t["sensitivity"]], t["confidence"]))
    stated = [t for t in tags if t["confidence"] == "stated"]
    max_sensitivity = stated[0]["sensitivity"] if stated else "low"
    return dict(
        tags=tags,
        max_sensitivity=max_sensitivity,
        sensitivity_score=SENSITIVITY_SCORE[max_sensitivity],
        method="heuristic",
    )
