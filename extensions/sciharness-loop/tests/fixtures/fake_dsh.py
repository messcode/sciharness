#!/usr/bin/env python3
"""A fake DSH headless CLI for the production adapter/wrapper contract tests.

It verifies the headless invocation, the SciHarness DSH wrapper's patch, and the
non-interactive environment, then delegates the actual result/artifacts to the
adversarial fake Codex fixture.  Expectations arrive as project input
(``/input/project/fixture-expect.json``), not host environment: the runtime
deliberately forwards only credentials to the container.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

GROUPS = {
    "subagents": ("tool-subagent-control", "tool-subagent-list-agents",
                  "tool-subagent", "tool-subagent-fork"),
    "workflow": ("tool-workflow",),
    "web": ("tool-web",),
    "jobs": ("tool-jobs",),
    "goals": ("tool-goal",),
}

prompt = sys.stdin.read()
args = sys.argv[1:]
assert "--profile" in args and "headless" in args, args
assert "--json" in args, args
assert "-" in args, args
assert os.environ.get("DSH_PERMISSION_MODE") == "danger-full-access", os.environ
assert os.environ.get("DSH_HOME") == "/tmp/dsh-home", os.environ
patch_paths = [args[index + 1] for index, value in enumerate(args) if value == "--patch"]
assert patch_paths, args
patch = Path(patch_paths[0]).read_text(encoding="utf-8")
expect = {}
expect_path = Path("/input/project/fixture-expect.json")
if expect_path.is_file():
    expect = json.loads(expect_path.read_text(encoding="utf-8"))
if "dsh_tools" in expect:
    for group, names in GROUPS.items():
        for name in names:
            if group in expect["dsh_tools"]:
                assert "- id: " + name not in patch, (group, patch)
            else:
                assert "- id: " + name in patch and "disabled: true" in patch, (group, patch)
else:
    assert "- id: tool-subagent" in patch and "disabled: true" in patch, patch
    assert "- id: tool-web" in patch, patch
if expect.get("mcp"):
    assert "- insert:" in patch and "dsh-mcp-client" in patch, patch
    assert "mcp-fixture" in patch and "toolCallTimeoutMs" in patch, patch
    assert Path("/tmp/mcp-fixture.json").is_file()
if Path("/input/project/.agents/skills").is_dir():
    assert "- id: skill-filesystem" in patch and "customSkillDirs" in patch, patch

print(json.dumps({"type": "session", "sessionId": "session-fixture"}), flush=True)
codex = subprocess.Popen(["/usr/local/bin/codex"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True)
assert codex.stdin is not None and codex.stdout is not None
codex.stdin.write(prompt)
codex.stdin.close()
for line in codex.stdout:
    sys.stdout.write(line)
    sys.stdout.flush()
code = codex.wait()
if code != 0:
    print(json.dumps({"type": "error", "message": "fake codex failed"}), flush=True)
    raise SystemExit(1)
result = json.loads(Path("/work/result.json").read_text(encoding="utf-8"))
print(json.dumps({"type": "final", "text": json.dumps(result)}), flush=True)
