#!/usr/bin/env python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend_root = Path(__file__).resolve().parent.parent / "backend"
    backend_script = backend_root / "scripts" / "run_xau_plan_tracker.py"
    return subprocess.call(
        [sys.executable, str(backend_script), *sys.argv[1:]],
        cwd=backend_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
