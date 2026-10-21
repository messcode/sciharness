"""Integration uses only the public sci CLI JSON contract."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .storage import LoopError


def find_root(path: Path) -> Path:
    path = path.resolve()
    for candidate in (path, *path.parents):
        if (candidate / ".sci.yaml").is_file():
            return candidate
    raise LoopError("not a SciHarness project")


def sci(root: Path, *args) -> dict:
    # Research files must never shadow the installed Core on Python's module
    # search path. All project routing is explicit through --path, not cwd.
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "sciharness.cli", *args, "--path", str(root), "--json"],
            cwd=Path(__file__).parent, env=env, capture_output=True, text=True, timeout=60,
        )
    except subprocess.SubprocessError as exc:
        raise LoopError("sci {} did not complete: {}".format(args[0], exc)) from exc
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise LoopError("sci returned invalid JSON") from exc
    if result.returncode or not value.get("ok") or value.get("schema_version") != 1:
        raise LoopError("sci {} failed: {}".format(args[0], value.get("diagnostics")))
    return value
