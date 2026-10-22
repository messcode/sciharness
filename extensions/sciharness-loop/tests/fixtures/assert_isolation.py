"""Run by both harness fixtures inside the production runtime boundary."""
from pathlib import Path

assert not Path("/var/run/docker.sock").exists()
assert not Path("/project").exists()
assert not Path("/input/project/.sci").exists()
try:
    Path("/root/.codex/auth.json").read_bytes()
except (FileNotFoundError, PermissionError):
    pass
else:
    raise AssertionError("host credentials readable")
for target in (Path("/input/project/docs/STATE.md"), Path("/forbidden-write")):
    try:
        target.write_text("hostile overwrite")
    except OSError:
        pass
    else:
        raise AssertionError("protected filesystem writable")
if Path("/datasets/pilot").exists():
    try:
        Path("/datasets/pilot/overwrite").write_text("denied")
    except OSError:
        pass
    else:
        raise AssertionError("dataset mount writable")
print("read-only input enforced")
