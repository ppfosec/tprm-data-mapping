from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(condition: object, label: str, detail: str = "") -> None:
    mark = "ok" if condition else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


def load() -> dict:
    return json.loads((ROOT / "data" / "tprm-intelligence.json").read_text(encoding="utf-8"))


def verify_data(data: dict) -> None:
    print("data contract")
    check(data["schema_version"] == "1.0.0", "schema version is explicit")
    check(data["staged"] is True, "internal intelligence is visibly staged")
    check(len(data["engagements"]) == 4, "four curated engagements")
    check(len(data["public_vendors"]) >= 8, "real public-evidence portfolio preserved")
    evidence = {e["id"] for e in data["evidence"]}
    heuristics = {h["id"] for h in data["heuristics"]["heuristics"]}
    for e in data["engagements"]:
        j = e["judgment"]
        check(bool(j["evidence_ids"]) and set(j["evidence_ids"]) <= evidence,
              f"{e['id']} recommendation is evidence-grounded")
        check(bool(j["heuristic_ids"]) and set(j["heuristic_ids"]) <= heuristics,
              f"{e['id']} recommendation names its heuristics")


def verify_stories(data: dict) -> None:
    print("hero invariants")
    by_id = {e["id"]: e for e in data["engagements"]}
    sales, crm = by_id["eng_nimbus_sales"], by_id["eng_nimbus_crm"]
    check(sales["vendor_id"] == crm["vendor_id"], "Nimbus is the same vendor in both stories")
    check(sales["vendor"]["surface"] == crm["vendor"]["surface"], "Nimbus Vendor Surface is shared")
    check(sales["quadrant"] == "fragile" and crm["quadrant"] == "mature",
          "context moves Nimbus from Fragile to Mature")
    check(sales["judgment"]["disposition"] != crm["judgment"]["disposition"],
          "same vendor receives different interventions")
    sales_order = [e["id"] for e in sales["timeline"]]
    check(sales_order.index("CARD-28") < sales_order.index("PR-104") and
          sales_order.index("CRM-221") < sales_order.index("PR-104"),
          "Sales purchase and production data precede intake")
    crm_order = [e["id"] for e in crm["timeline"]]
    check(crm_order.index("KB-CRM-LAB") < crm_order.index("IDP-804") and
          crm_order.index("CRM-244") < crm_order.index("IDP-804"),
          "CRM boundary and synthetic data precede access")
    ledger = by_id["eng_ledger_finance"]
    check("VS-LED-DRIFT-2" in ledger["judgment"]["evidence_ids"] and
          "CON-204" in ledger["judgment"]["evidence_ids"],
          "LedgerLoop drift reopens existing renewal work")
    check(ledger.get("prior_disposition") != ledger["judgment"]["disposition"] and
          bool(ledger.get("recommendation_changed_on")),
          "LedgerLoop visibly carries the changed recommendation")
    callscribe = by_id["eng_callscribe_cs"]
    check(callscribe["judgment"]["disposition"] == "abstain" and not callscribe["model_consulted"],
          "CallScribe abstains with no maturity model call")


def verify_replay(data: dict) -> None:
    print("keyless replay")
    check(data["mode"] == "replay" and data["summary"]["live_calls"] == 0,
          "default output makes zero live calls")
    check(data["dependency_index"]["by_vendor"]["vendor_nimbus"] ==
          ["eng_nimbus_sales", "eng_nimbus_crm"],
          "new vendor evidence identifies both affected Nimbus engagements")
    before = (ROOT / "data" / "tprm-intelligence.json").read_text(encoding="utf-8")
    env = os.environ.copy(); env.pop("ANTHROPIC_API_KEY", None); env["PYTHONPATH"] = "src"; env["TPRM_LENS_MODE"] = "replay"
    subprocess.run([sys.executable, "-m", "tprm_lens.cli", "run"], cwd=ROOT, env=env, check=True,
                   stdout=subprocess.DEVNULL)
    after = (ROOT / "data" / "tprm-intelligence.json").read_text(encoding="utf-8")
    check(before == after, "replay is byte-identical")
    candidate = ROOT / "out" / "candidates" / "judgments.json"
    subprocess.run([sys.executable, "-m", "tprm_lens.cli", "candidate"], cwd=ROOT, env=env, check=True,
                   stdout=subprocess.DEVNULL)
    c = json.loads(candidate.read_text(encoding="utf-8"))
    curated = json.loads((ROOT / "fixtures" / "tprm" / "judgments.json").read_text(encoding="utf-8"))
    check(c["review_state"] == "candidate" and curated["review_state"] == "curated",
          "one-shot output cannot promote itself")


def verify_viewer(data: dict) -> None:
    print("viewer")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "site" / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
    embedded = (ROOT / "site" / "embedded.js").read_text(encoding="utf-8")
    for tab in ("Insights", "Findings", "Risk intelligence", "Heuristics", "Reasoning"):
        check(tab in html, f"{tab} tab exists")
    check("prefers-reduced-motion" in css, "reduced-motion support")
    check("@media(max-width:480px)" in css, "390px-class mobile layout")
    check("TPRM_EMBEDDED_DATA" in js and len(embedded) > 1000, "standalone viewer embeds full artifact")
    check("Same vendor. Different decision." in html, "hero product thesis is visible")
    check("localStorage" in js and "data-dismiss" in js, "reviewer dismissals are reversible")
    check((ROOT / "fixtures" / "heuristics" / "JUDGMENT_LIBRARY.md").exists(),
          "human-reviewable judgment library is the source")
    check(all(e["id"] in embedded for e in data["engagements"]), "embedded data covers every engagement")
    check('tabindex="0"' in js and 'e.key==="Escape"' in js, "keyboard detail and dismissal controls")


def verify_http() -> None:
    print("http delivery")
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass
    previous = Path.cwd()
    try:
        os.chdir(ROOT)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(base + "/index.html") as response:
            html = response.read().decode("utf-8")
        with urllib.request.urlopen(base + "/data/tprm-intelligence.json") as response:
            payload = json.loads(response.read().decode("utf-8"))
        check("Same vendor. Different decision." in html, "viewer serves over HTTP")
        check(payload["summary"]["engagements"] == 4, "unified artifact serves over HTTP")
    finally:
        if "server" in locals():
            server.shutdown(); server.server_close()
        os.chdir(previous)


def main() -> int:
    data = load()
    verify_data(data); verify_stories(data); verify_replay(data); verify_viewer(data); verify_http()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
