# Contributing

This repository is a deterministic product demonstrator. Changes should preserve evidence lineage, explicit uncertainty and the ability to run without an API key.

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/check.py
```

The quality gate lints Python, compiles the source tree, rebuilds the replay artifact, verifies product invariants, runs tests, checks the browser JavaScript and confirms generated files are committed.

## Change boundaries

- `fixtures/tprm/` contains fictional enterprise evidence and reviewed demo judgments.
- `fixtures/cassettes/` contains replay responses keyed to their exact inputs.
- `data/index.json` and `data/snapshots/` belong to Triple D's external collector.
- `data/tprm-intelligence.json` and `site/embedded.js` are generated. Rebuild them after changing fixtures, heuristics or the pipeline.
- `out/candidates/` is unreviewed and ignored. Candidate generation never promotes judgment.

Live and record modes are deliberate operations. A key in the environment is inert unless `TPRM_LENS_MODE` is explicitly set to `live` or `record`.

## Pull requests

Keep changes focused and describe the user-facing decision or safety property they preserve. Run `python scripts/check.py` before pushing. Do not add private heuristics, real internal evidence, API keys or invented internal stories about public vendors.
