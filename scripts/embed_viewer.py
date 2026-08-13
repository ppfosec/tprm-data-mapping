from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "tprm-intelligence.json"
TARGET = ROOT / "site" / "embedded.js"


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    TARGET.write_text(
        "globalThis.TPRM_EMBEDDED_DATA=" +
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"embedded {len(payload['engagements'])} engagements and {len(payload['trace'])} trace nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
