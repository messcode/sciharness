import dataclasses
import json
import os
import subprocess
import sys
import time

import pytest

from conftest import set_policy
from sciharness_loop.controller import Controller
from sciharness_loop.core import sci
from sciharness_loop.executor import CodexExecutor
from sciharness_loop.policy import Policy, load_policy
from sciharness_loop.storage import LoopError, files, lock, safe_path


def fake_docker(tmp_path):
    """Create a controlled docker CLI that never talks to a daemon."""
    log = tmp_path / "docker-calls.log"
    gate = tmp_path / "gate"
    created = tmp_path / "container-created"
    script = tmp_path / "docker"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys, time\n"
        "log = pathlib.Path({log!r})\n"
        "gate = pathlib.Path({gate!r})\n"
        "created = pathlib.Path({created!r})\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['--host', 'unix:///var/run/docker.sock']:\n"
        "    args = args[2:]\n"
        "with log.open('a') as stream:\n"
        "    stream.write(args[0] + '\\n')\n"
        "if args[:2] == ['image', 'inspect']:\n"
        "    print('sha256:' + 'a' * 64)\n"
        "    sys.exit(0)\n"
        "if args[0] == 'create':\n"
        "    while gate.exists():\n"
        "        time.sleep(0.02)\n"
        "    created.write_text('created')\n"
        "    print('b' * 64)\n"
        "    sys.exit(0)\n"
        "if args[0] == 'start':\n"
        "    sys.stdin.buffer.read()\n"
        "    sys.exit(0)\n"
        "if args[0] == 'rm':\n"
        "    sys.stderr.write('Error response from daemon: No such container\\n')\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n".format(log=str(log), gate=str(gate), created=str(created))
    )
    script.chmod(0o755)
    return log, gate, created


@pytest.mark.parametrize("values", [
    {"mode": "auto"}, {"permissions": {"start_experiment": "allow"}},
    {"network": "host"}, {"timeout_seconds": True}, {"max_files": 0},
    {"read_files": "*"}, {"read_files": ["../outside"]},
    {"read_files": [".git/config"]}, {"read_files": [".sci/loop/policy.yaml"]},
    {"read_files": ["vendor/.git/config"]},
    {"read_files": ["vendor/.sci/loop/policy.yaml"]},
    {"image": "--privileged"}, {"max_input_bytes": 10_000_001},
    {"read_files": ["/etc/passwd"]}, {"read_files": ["..\\outside"]},
])
def test_policy_fails_closed(project, values):
    set_policy(project, **values)
    with pytest.raises(LoopError):
        load_policy(project)


def test_symlinked_inputs_and_state_rejected(project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "alias").symlink_to(outside, target_is_directory=True)
    set_policy(project, read_files=["alias/file.txt"])
    with pytest.raises(LoopError, match="symlinks"):
        load_policy(project)
    (project / ".sci/loop/policy.yaml").unlink()
    (project / ".sci/loop").rmdir()
    (project / ".sci/loop").symlink_to(outside, target_is_directory=True)
    with pytest.raises(LoopError, match="symlinks"):
        Controller(project)


def test_fifo_rejected_without_opening(tmp_path):
    os.mkfifo(tmp_path / "fifo")
    with pytest.raises(LoopError, match="non-regular"):
        files(tmp_path, 1000, 10)


def test_symlinked_directory_in_artifacts_rejected(tmp_path):
    (tmp_path / "link").symlink_to("/tmp", target_is_directory=True)
    with pytest.raises(LoopError, match="non-regular"):
        files(tmp_path, 1000, 10)


def test_os_lock_excludes_second_process_and_releases_on_crash(tmp_path):
    script = (
        "import fcntl,sys; f=open(sys.argv[1], 'a'); "
        "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)"
    )
    import sys
    with lock(tmp_path):
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "lock")],
                                capture_output=True)
        assert result.returncode != 0
    # Lock files are intentionally retained, but no stale lock blocks recovery.
    with lock(tmp_path):
        pass


def test_executor_missing_docker_never_falls_back(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(LoopError, match="no host fallback"):
        CodexExecutor()


def test_docker_command_exposes_only_snapshot_and_result_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")
    executor = CodexExecutor()
    inputs, work = tmp_path / "input", tmp_path / "work"
    policy = Policy(mode="step", image="trusted-codex:1")
    command = executor.command("a" * 32, inputs, work, policy)
    assert command[:3] == ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
    assert command.count("--mount") == 2
    assert "type=bind,src={},dst=/input,readonly".format(inputs) in command
    assert "type=bind,src={},dst=/work".format(work) in command
    for flag in ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                 "--pids-limit=128", "--pull=never", "--network=bridge"):
        assert flag in command
    assert "/input/schema.json" in command
    assert "/work/result.json" in command
    assert "--privileged" not in command
    assert "--network=none" in executor.command(
        "b" * 32, inputs, work, dataclasses.replace(policy, network="none"))


def test_missing_auth_fails_before_spawn(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    with pytest.raises(LoopError, match="CODEX_API_KEY"):
        CodexExecutor().execute("a" * 32, tmp_path, tmp_path, tmp_path / "log", Policy())


def test_timeout_kills_process_and_stops_container(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")
    monkeypatch.setenv("CODEX_API_KEY", "fake-secret-never-logged")
    (tmp_path / "prompt.txt").write_text("bounded pilot")
    seen = {}

    class Process:
        returncode = None
        killed = False

        def __init__(self, command, **kwargs):
            seen["command"] = command
            seen["env"] = kwargs["env"]

        def communicate(self, *args, **kwargs):
            if not self.killed:
                raise subprocess.TimeoutExpired("docker", 1)

        def kill(self):
            self.killed = True
            seen["killed"] = True

    def docker_run(command, **kwargs):
        from types import SimpleNamespace
        if "inspect" in command:
            return SimpleNamespace(returncode=0, stdout="sha256:" + "a" * 64, stderr="")
        if "create" in command:
            return SimpleNamespace(returncode=0, stdout="b" * 64 + "\n", stderr="")
        raise AssertionError(command)

    executor = CodexExecutor()
    monkeypatch.setattr(subprocess, "Popen", Process)
    monkeypatch.setattr(subprocess, "run", docker_run)
    monkeypatch.setattr(executor, "stop", lambda run_id: seen.update(stopped=run_id))
    with pytest.raises(LoopError, match="timed out"):
        executor.execute("a" * 32, tmp_path, tmp_path, tmp_path / "log",
                         Policy(image="codex:local", timeout_seconds=1))
    assert seen["killed"] and seen["command"][:3] == [
        "/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
    assert seen["command"][3:5] == ["start", "--attach"]
    # The controller owns stop: execute itself must not stop, so a successful
    # run is stopped exactly once before evidence is collected.
    assert "stopped" not in seen
    executor.stop("a" * 32)
    assert seen["stopped"] == "a" * 32
    assert "fake-secret" not in json.dumps(seen["command"])
    assert set(seen["env"]) == {"PATH", "CODEX_API_KEY"}
    metadata = json.loads((tmp_path / "log.json").read_text())
    assert metadata["image"] == "sha256:" + "a" * 64
    assert metadata["container_id"] == "b" * 64
    assert "fake-secret" not in json.dumps(metadata)


def test_executor_creates_before_starting(tmp_path, monkeypatch):
    log, _gate, _created = fake_docker(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("CODEX_API_KEY", "fake")
    inputs, work = tmp_path / "input", tmp_path / "work"
    inputs.mkdir()
    work.mkdir()
    (inputs / "prompt.txt").write_text("pilot")
    executor = CodexExecutor()
    executor.execute("a" * 32, inputs, work, tmp_path / "executor.log",
                     Policy(image="fake:local"))
    executor.stop("a" * 32)
    calls = log.read_text().splitlines()
    assert calls[:3] == ["image", "create", "start"], calls
    assert calls[-1] == "rm"


def test_orphan_create_cannot_start_after_recovery(tmp_path, monkeypatch):
    log, gate, created = fake_docker(tmp_path)
    gate.write_text("hold")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("CODEX_API_KEY", "fake")
    inputs, work = tmp_path / "input", tmp_path / "work"
    inputs.mkdir()
    work.mkdir()
    (inputs / "prompt.txt").write_text("pilot")
    runner = tmp_path / "runner.py"
    runner.write_text(
        "from pathlib import Path\n"
        "from sciharness_loop.executor import CodexExecutor\n"
        "from sciharness_loop.policy import Policy\n"
        "root = Path({root!r})\n"
        "CodexExecutor().execute('a' * 32, root / 'input', root / 'work',\n"
        "                        root / 'executor.log', Policy(image='fake:local'))\n".format(
            root=str(tmp_path))
    )
    env = {"PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", ""),
           "CODEX_API_KEY": "fake"}
    process = subprocess.Popen([sys.executable, str(runner)], env=env)
    try:
        for _ in range(200):
            if log.exists() and "create" in log.read_text().splitlines():
                break
            time.sleep(0.02)
        else:
            pytest.fail("docker create was not invoked")
        process.kill()
        process.wait()
        # Recover while the orphaned create is still pending.
        CodexExecutor().stop("a" * 32)
        assert "rm" in log.read_text().splitlines()
        gate.unlink()
        for _ in range(300):
            if created.exists():
                break
            time.sleep(0.02)
        else:
            pytest.fail("orphaned docker create did not complete")
        assert "start" not in log.read_text().splitlines()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        gate.unlink(missing_ok=True)


def test_invalid_execution_path_is_rejected(enabled):
    with pytest.raises(LoopError, match="execution ID"):
        Controller(enabled).status("../../outside")
    with pytest.raises(LoopError):
        safe_path(enabled, "/etc/passwd")


def test_project_code_cannot_shadow_host_core(project, monkeypatch):
    shadow = project / "sciharness"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise RuntimeError('executed untrusted project code')")
    monkeypatch.setenv("PYTHONPATH", str(project))
    assert sci(project, "context")["ok"]
