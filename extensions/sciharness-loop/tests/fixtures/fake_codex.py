#!/usr/bin/env python3
"""An adversarial process exercising the production Docker launcher."""
import json
import os
import sys
from pathlib import Path
import time
import runpy

print(json.dumps({"type": "fixture_started"}), flush=True)

prompt = sys.stdin.read()
if "HANG" in prompt:
    print(json.dumps({"type": "fixture_hanging"}), flush=True)
    time.sleep(60)
runpy.run_path("/opt/sciharness/assert_isolation.py")
expect = {}
expect_path = Path("/input/project/fixture-expect.json")
if expect_path.is_file():
    expect = json.loads(expect_path.read_text(encoding="utf-8"))
if expect.get("codex_agents_md"):
    assert Path("/tmp/codex/AGENTS.md").is_file()
if expect.get("codex_skills"):
    assert Path("/tmp/codex/skills").is_dir()
schema = json.loads(Path("/input/schema.json").read_text())
context = json.loads(Path("/input/context.json").read_text())
assert context["project"]["root"] == "/input/project"
assert not Path("/var/run/docker.sock").exists()
assert not Path("/project").exists()
try:
    Path("/root/.codex/auth.json").read_bytes()
except (FileNotFoundError, PermissionError):
    pass
else:
    raise AssertionError("host auth unexpectedly readable")
assert not Path("/input/project/.sci").exists()
try:
    Path("/input/project/docs/STATE.md").write_text("hostile overwrite")
except OSError:
    pass
else:
    raise AssertionError("input mount unexpectedly writable")
try:
    Path("/forbidden-write").write_text("hostile root write")
except OSError:
    pass
else:
    raise AssertionError("container root unexpectedly writable")
if "title" in schema["properties"]:
    result = {"title": "Isolated pilot", "task": "SYMLINK" if "SYMLINK" in prompt else "pilot",
              "rationale": "Exercise the isolated executor"}
    if "action" in schema["properties"]:
        result["action"] = "explore"
else:
    Path("/work/proposal.md").write_text("Container fixture; no scientific conclusion.")
    Path("/work/artifacts").mkdir()
    Path("/work/artifacts/log.txt").write_text("read-only input enforced\n")
    if "SYMLINK" in prompt:
        os.symlink("/input/project/docs/STATE.md", "/work/artifacts/escape")
    result = {"summary": "Isolated pilot", "limitations": "Synthetic fixture",
              "checks": ["read-only input enforced"], "needs_human_review": True}
Path("/work/result.json").write_text(json.dumps(result))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 0}}))
