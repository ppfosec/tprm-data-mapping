# Sovereignty Drift

Vendor data-sovereignty mapping from public evidence instead of vendor white papers.

A DPA is a claim. A job listing is evidence. This collects both nightly and flags where they
disagree — a sub-processor that engineering talks about but the published list omits, residency
language against a workforce hired somewhere else — and turns each disagreement into a specific
question to put to the vendor.

**It is not a compliance assessment and not an accusation.** A contradiction on the surface usually
has a dull explanation. The point is to hand a reviewer the exact sentence and the exact posting so
they can go and ask for it.

---

## Why there is no server

The collector runs in GitHub Actions and commits what it finds. Two consequences:

- **Git is the diff engine.** Legal pages are normalised to one sentence per line and committed to
  `data/snapshots/`. `git log -p data/snapshots/stripe/dpa.txt` is then a dated record of every
  wording change, and a reworded clause shows as a one-line diff instead of a reflowed paragraph.
  Each run writes a drift report into the Actions job summary.
- **No CORS problems and no hosting bill.** Archive.org's CDX index and vendor domains send no
  CORS headers, so a browser cannot read them. A scheduled job can. The dashboard reads one
  committed JSON file.

```
collector/          fetch, normalise, correlate
  vendors.yaml      the registry — add vendors here
  collect.py        entry point
  correlate.py      the cross-source rules
  signals.py        what to look for in job descriptions
  geo.py            location strings -> countries
data/
  snapshots/        committed plaintext, one sentence per line  <- the evidence
  index.json        everything the dashboard reads
index.html          dashboard
site/               its styles and logic
.github/workflows/  the nightly job
```

## Sources

| Source | What it gives | Notes |
| --- | --- | --- |
| Vendor legal pages | privacy policy, DPA, sub-processor list | discovered by following links, not hardcoded |
| Greenhouse public board API | open roles, locations, full descriptions | no key required; returns sporadic 503s, so requests retry |
| Wayback CDX | revision count and first/last capture per document | rate-limits by IP; failures are reported, never faked |

## The cross-checks

| Rule | Fires when |
| --- | --- |
| `subprocessor_gap` | A provider named in job descriptions is absent from a sub-processor list that was successfully read |
| `residency_vs_workforce` | A genuine residency claim sits alongside a mostly non-EEA workforce (needs ≥20 placeable roles) |
| `access_vs_rotation` | Need-to-know access language alongside follow-the-sun, on-call or 24/7 postings |
| `no_transfer_mechanism` | No SCCs, adequacy, DPF or BCRs named anywhere, while hiring spans ≥3 countries |
| `unverifiable_list` / `list_unreadable` | The sub-processor list is client-rendered or too thin to parse |
| `no_subprocessor_list` | No such page reachable from the vendor's own legal pages |

Two guards matter and are deliberate: `subprocessor_gap` only fires when a list was actually parsed,
because accusing a vendor of omitting a name from a document the collector never read would be a
fabrication. And `residency_vs_workforce` needs a real denominator, because 6 of 6 non-EEA roles is
noise.

## Run it

```bash
pip install -r collector/requirements.txt
cd collector
python collect.py                        # everything
python collect.py --only stripe          # one vendor
python collect.py --skip-archive         # skip Wayback (it throttles hard)
python collect.py --sample 40            # read more job descriptions
```

Then serve the repo root and open it:

```bash
python -m http.server 8000
```

## Add a vendor

Append to `collector/vendors.yaml`. The `legal_candidates` paths are guesses — the collector
verifies each one and then follows links out of whatever answered, so a wrong guess costs a 404 in
the log and nothing else. A Greenhouse board token is the trailing path segment of
`boards.greenhouse.io/<token>`. Boards on other platforms are not supported yet; `collect_jobs` is
where that would go.

## Limitations

- Job-board coverage is Greenhouse only, so vendors on Ashby, Lever or a homegrown board have no
  workforce signal at all. Absence of signal is not absence of exposure.
- Text extraction is heuristic. Client-rendered trust centres yield nothing, and the collector
  records that rather than guessing.
- The index is a measure of the paper trail, not of a vendor. A high score can mean a company
  publishes less, hires more openly, or simply uses Greenhouse while a competitor does not.
- Signal matching is regex over prose. It will produce false positives. Every flag links to its
  source so you can throw it out.

## Licence

MIT for the code. The collected snapshots are the vendors' own published text, retained here for
comparison and quotation.
