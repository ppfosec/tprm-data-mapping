"""Run the repository's deterministic quality gate on every supported platform."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ["data/tprm-intelligence.json", "site/embedded.js"]


def run(*command: str, env: dict[str, str] | None = None) -> None:
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env["TPRM_LENS_MODE"] = "replay"
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    run(sys.executable, "-m", "ruff", "check", "collector", "src", "scripts", "tests", env=env)
    run(sys.executable, "-m", "compileall", "-q", "collector", "src", "scripts", "tests", env=env)
    run(sys.executable, "-m", "tprm_lens.cli", "run", env=env)
    run(sys.executable, "scripts/embed_viewer.py", env=env)
    run(sys.executable, "scripts/verify.py", env=env)
    run(sys.executable, "-m", "pytest", env=env)

    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required to syntax-check the standalone viewer")
    run(node, "--check", "site/app.js", env=env)

    run("git", "diff", "--exit-code", "HEAD", "--", *GENERATED, env=env)
    run("git", "diff", "--check", env=env)
    print("quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
