from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import MODE
from .heuristics import save
from .pipeline import candidate, run


def main() -> int:
    parser = argparse.ArgumentParser(prog="tprm-lens")
    parser.add_argument("command", choices=["run", "candidate", "library"])
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    if args.command == "candidate":
        print(candidate())
        return 0
    if args.command == "library":
        if not args.path:
            parser.error("library requires a path to JUDGMENT_LIBRARY.md")
        result = save(Path(args.path).read_text(encoding="utf-8"))
        print(json.dumps({"version": result["version"], "heuristics": result["total"], "source": result["source"]}, indent=2))
        return 0
    output = run()
    print(json.dumps({"mode": MODE, **output["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
