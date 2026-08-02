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

SENSITIVITY_RANK = {"low": 0, "medium": 1, "high": 2}
SENSITIVITY_SCORE = {"low": 10, "medium": 20, "high": 30}


def classify(texts: dict[str, str]) -> dict:
    """texts: {doc_kind: normalised_body}. Returns tags found plus the overall tier."""
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
                ))
                break  # one example per document is enough

    # keep the highest-sensitivity example per tag key
    best: dict[str, dict] = {}
    for f in found:
        cur = best.get(f["key"])
        if cur is None or SENSITIVITY_RANK[f["sensitivity"]] > SENSITIVITY_RANK[cur["sensitivity"]]:
            best[f["key"]] = f

    tags = sorted(best.values(), key=lambda t: -SENSITIVITY_RANK[t["sensitivity"]])
    max_sensitivity = tags[0]["sensitivity"] if tags else "low"
    return dict(
        tags=tags,
        max_sensitivity=max_sensitivity,
        sensitivity_score=SENSITIVITY_SCORE[max_sensitivity],
    )
