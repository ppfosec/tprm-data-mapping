# TPRM Lens

A vendor questionnaire tells you what a vendor says. It does not tell you why Sales bought ten seats before Procurement saw the request, whether the CRM team has already bounded the same product to synthetic data, who can accept the remaining trade-off, or what happened to the contract owner who left six weeks before renewal.

TPRM Lens works on that second problem.

The unit is an **engagement**: one vendor, one team, one intended use and the organizational process around it. Vendor evidence still matters. **Data Drift Detector (Triple D)** is the named external sensing engine. It watches DPAs, privacy policies, subprocessors, public hiring signals, workforce geography and wording drift. TPRM Lens routes those Vendor Surface changes into affected engagements and reads them against business value, ownership, team engagement, relationship maturity and organizational history.

The same vendor can therefore produce different answers. That is the demo.

## The staged story

Nimbus AI has one Vendor Surface grade and two engagements:

- Sales Enablement bought seats, authenticated users and uploaded customer transcripts before intake. The recommendation contains the material data path without reflexively breaking a useful sales workflow.
- CRM Platform defined a synthetic-data lab boundary, requested review and only then granted access. The recommendation preserves that boundary and lets the evaluation proceed.

LedgerLoop shows a vendor term changing while a renewal still names a departed owner. CallScribe shows the senior answer when intended use and relationship history are missing: abstain, ask three questions and spend no model call inventing maturity.

The LedgerLoop sequence is also the Triple D demo. A replay scan compares the committed snapshots, catches a 30-day subprocessor notice becoming an online-list update, identifies the Finance renewal as affected and shows the recommendation change. Triple D detects the change. TPRM Lens decides what the organization should do about it.

All internal organizations, people, messages, contracts and vendors in those four engagements are fictional. The separate eight-vendor portfolio is real **public evidence only**. No fictional internal story is attached to a real company.

## Run it for free

```powershell
$env:PYTHONPATH = "src"
$env:TPRM_LENS_MODE = "replay"
python -m tprm_lens.cli run
python scripts/embed_viewer.py
python scripts/verify.py
```

Open `index.html` directly, or serve the repository root:

```powershell
python -m http.server 8000
```

Replay is the default. It reads reviewed, input-keyed responses from `fixtures/cassettes/`, makes zero network calls and produces byte-identical output. An API key sitting in the environment does nothing unless `TPRM_LENS_MODE` is explicitly set to `live` or `record`.

| Mode | What happens | Writes reviewed fixtures? |
| --- | --- | --- |
| `replay` | Reuses committed reasoning. No key, network or cost. | No |
| `live` | Reasons fresh from the four staged engagements. | No |
| `record` | Reasons fresh and records new input-keyed cassettes. | Cassettes only |

If evidence, heuristics, prompt, schema or model changes, replay raises a missing-cassette error. It does not quietly reuse an answer produced for a different case.

## Where AI belongs

Sequence reconstruction, known-owner resolution, stable joins and document diffs are deterministic. They are inexpensive and easier to review that way.

The model receives one engagement and only the evidence retrieved for it. It synthesizes the coherent risk story, alternative explanation, business trade-offs and recommended intervention. Every material conclusion carries stable evidence and heuristic IDs. Deterministic facts win if model prose disagrees.

Fewer than two relevant team interactions triggers a code guard before a model request exists. The system returns `unknown` maturity and an explicit abstention. Restraint is part of the product, not a disclaimer added after generation.

## Heuristics

`fixtures/heuristics/JUDGMENT_LIBRARY.json` uses the same library concepts as Risk Lens: stable IDs, versions, provenance, publication status, product relevance and stage bindings. TPRM-specific entries are visibly proposed. A published heuristic can be carried without being executed when it is not relevant to this Lens.

No private heuristic enters this public repository. Public publication remains a separate review and approval event.

## Data flow

```text
data/index.json                    real public Vendor Surface
collector/                         Triple D collection, normalization and public-evidence diffs
fixtures/tprm/demo.json            fictional internal source records
fixtures/heuristics/               public/proposed judgment rules
fixtures/cassettes/                recorded synthesis, keyed to exact inputs
             │
             ▼
src/tprm_lens/pipeline.py          sequence → context → synthesis → intervention
             │
             ├── data/tprm-intelligence.json
             ├── out/trace.jsonl
             └── site/embedded.js  complete standalone viewer fallback
```

The external collector still owns `data/index.json`. The judgment pipeline writes a separate artifact, so a collection run cannot replace curated engagement intelligence. The collector also preserves reviewed LLM classifications when a no-key run falls back to regex, marking when the source documents have changed.

In the viewer, select **Vendor Surface · Triple D** or use the Triple D pulse in the header. **Replay scan** animates the committed collect → normalize → diff → reconcile → route sequence. It makes no request, uses no API key and does not alter reviewed judgment. A real scheduled collection can replace the public evidence artifact; the same dependency index then identifies which engagements need their heuristics reapplied.

## One-shot Codex scans

```powershell
python -m tprm_lens.cli candidate
```

This writes `out/candidates/judgments.json`. Candidate output is explicitly unreviewed and cannot overwrite `fixtures/tprm/judgments.json`. Promotion is intentionally a human review step: confirm evidence IDs, heuristic IDs, trade-offs and intervention wording, then deliberately update the curated fixture and record matching cassettes.

After that review, promotion is explicit and recoverable:

```powershell
python scripts/promote_candidate.py --approve --reviewer "Your Name"
```

The prior curated file is archived. A failed pipeline validation restores it.

## Verification

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
pytest
python scripts/verify.py
```

The verifier proves the actual demo claims:

- Nimbus is the same vendor with the same Vendor Surface in both engagements.
- Sales purchase and production data use precede intake.
- CRM Platform's lab boundary and synthetic dataset precede access.
- Context moves Nimbus from `Fragile` to `Mature` and changes the intervention.
- LedgerLoop drift reopens the renewal already in flight.
- Triple D preserves the exact before/after language and routes the change to the affected engagement.
- CallScribe abstains without a maturity model call.
- Every recommendation cites existing evidence and heuristics.
- Replay is byte-identical, keyless and unable to promote candidate judgment.
- The viewer contains desktop, mobile, keyboard, reduced-motion and standalone behavior.

## Repository layout

```text
collector/             real public-evidence collection and correlation
data/                  raw Vendor Surface plus unified derived intelligence
fixtures/tprm/         staged internal evidence and reviewed judgments
fixtures/heuristics/   public/proposed library snapshot
fixtures/cassettes/    free, reproducible model responses
src/tprm_lens/         pipeline, trace, execution modes
site/                  one-page visual workbench
scripts/               embedding, cassette seeding and verification
tests/                 determinism and safety invariants
```

## What this is not

This is not a production TPRM suite, a compliance assessment, legal advice or an autonomous approval engine. There is no authentication, multitenancy or live enterprise connector. The point is to show what TPRM judgment looks like after the questionnaire stops being the center of the work.

The platform name is also a working label. The three intended views are Risk Lens, TPRM Lens and Control Lens; shared packaging can wait until the third Lens proves what is genuinely shared.
