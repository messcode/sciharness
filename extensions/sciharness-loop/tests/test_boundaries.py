import dataclasses
import json
import os
import subprocess

import pytest

from conftest import set_policy
from sciharness_loop.controller import Controller
from sciharness_loop.core import sci
from sciharness_loop.executor import CodexExecutor
from sciharness_loop.policy import Policy, load_policy
from sciharness_loop.storage import LoopError, files, lock, safe_path


@pytest.mark.parametrize("values", [
    {"mode": "auto"}, {"permissions": {"start_experiment": "allow"}},
    {"network": "host"}, {"timeout_seconds": True}, {"max_files": 0},
    {"read_files": "*"}, {"read_files": ["../outside"]},
    {"read_files": [".git/config"]}, {"read_files": [".sci/loop/policy.yaml"]},
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

    executor = CodexExecutor()
    monkeypatch.setattr(subprocess, "Popen", Process)
    from types import SimpleNamespace
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="sha256:" + "a" * 64))
    monkeypatch.setattr(executor, "stop", lambda run_id: seen.update(stopped=run_id))
    with pytest.raises(LoopError, match="timed out"):
        executor.execute("a" * 32, tmp_path, tmp_path, tmp_path / "log",
                         Policy(image="codex:local", timeout_seconds=1))
    assert seen["killed"] and seen["stopped"] == "a" * 32
    assert "fake-secret" not in json.dumps(seen["command"])
    assert set(seen["env"]) == {"PATH", "CODEX_API_KEY"}
    metadata = json.loads((tmp_path / "log.json").read_text())
    assert metadata["image"] == "sha256:" + "a" * 64
    assert "fake-secret" not in json.dumps(metadata)


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
