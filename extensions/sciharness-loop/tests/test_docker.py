"""Real filesystem isolation without an API key or a model invocation.

CI sets SCI_LOOP_TEST_DOCKER=1, so inability to exercise Docker is a failure.
Local runs without a Docker daemon explicitly skip this test.
"""
import os
import shutil
import subprocess
import sys
import time
import json
from pathlib import Path

import pytest

from conftest import plan_and_step, scientific_files, set_policy
from sciharness_loop.controller import Controller
from sciharness_loop.executor import make_executor
from sciharness_loop.missions import MissionRunner
from sciharness_loop.storage import LoopError


class DiagnosticExecutor:
    """Expose fixture-only transcripts on CI failures; launch code is unchanged."""
    def __init__(self, policy, root):
        self.executor = make_executor(policy, root)

    def stop(self, run_id):
        return self.executor.stop(run_id)

    def execute(self, run_id, inputs, work, log, policy):
        try:
            return self.executor.execute(run_id, inputs, work, log, policy)
        except Exception as exc:
            transcript = log.read_text(errors="replace") if log.exists() else "No transcript"
            raise LoopError(str(exc) + "\nContainer fixture transcript:\n" + transcript) from exc


@pytest.fixture(scope="module")
def docker_image(tmp_path_factory):
    binary = shutil.which("docker")
    ready = binary and subprocess.run(
        [binary, "--host", "unix:///var/run/docker.sock", "info"],
        capture_output=True, timeout=30,
    ).returncode == 0
    if not ready:
        if os.environ.get("SCI_LOOP_TEST_DOCKER") == "1":
            pytest.fail("Docker isolation is mandatory in this CI job")
        pytest.skip("local Docker daemon unavailable; isolation job exercises real containers")
    fixtures = Path(__file__).parent / "fixtures"
    build = tmp_path_factory.mktemp("loop-container-fixture")
    shutil.copytree(fixtures, build, dirs_exist_ok=True)
    shutil.copy2(Path(__file__).parents[1] / "src/sciharness_loop/deepseek_runner.py", build / "deepseek_runner.py")
    shutil.copy2(Path(__file__).parents[1] / "src/sciharness_loop/dsh_runner.py", build / "dsh_runner.py")
    tag = "sci-loop-test:local"
    subprocess.run([binary, "build", "-t", tag, str(build)], check=True, capture_output=True)
    return tag


@pytest.mark.parametrize("backend", ["codex", "deepseek", "dsh"])
def test_real_container_cannot_read_or_write_live_project(project, docker_image, monkeypatch, backend):
    dataset = project / "data/subset"
    dataset.mkdir()
    set_policy(project, image=docker_image, network="none", backend=backend,
               model="fixture-model", base_url="http://127.0.0.1:17651" if backend == "deepseek" else "",
               read_mounts={"pilot": "data/subset"})
    # This is an adversarial fixture, not a real API credential.
    monkeypatch.setenv("CODEX_API_KEY", "unused-fixture-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-fixture-key")
    before = scientific_files(project)
    controller = Controller(project)
    controller._executor = DiagnosticExecutor(controller.policy, project)
    _, step = plan_and_step(controller)
    assert scientific_files(project) == before
    assert "read-only input enforced" in step["result"]["checks"]
    accepted = controller.accept(step["id"], step["review_hash"], "Container test reviewer")
    assert accepted["state"] == "accepted"


@pytest.mark.parametrize("backend", ["codex", "deepseek", "dsh"])
def test_real_budgeted_cycle_uses_same_review_boundary(project, docker_image, monkeypatch, backend, tmp_path):
    import yaml
    set_policy(project, mode="guarded_auto", image=docker_image, network="none", backend=backend,
               model="fixture-model", base_url="http://127.0.0.1:17651" if backend == "deepseek" else "")
    monkeypatch.setenv("CODEX_API_KEY", "unused-fixture-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-fixture-key")
    spec = tmp_path / "run.yaml"
    spec.write_text(yaml.safe_dump({"schema_version": 1, "objective": "Inspect one synthetic pilot",
                                    "runtime_seconds": 60, "max_cycles": 1}))
    runner = MissionRunner(project)
    prepared = runner.prepare(spec)
    before = scientific_files(project)
    result = runner.approve(prepared["id"], prepared["review_hash"], "Fixture reviewer")
    logs = "\n".join(p.read_text(errors="replace") for p in (project / ".sci/loop/runs").glob("*/executor.log"))
    assert result["state"] == "completed", (result, logs)
    assert result["cycles"][0]["state"] == "completed", (result, logs)
    step = runner.controller.load(result["cycles"][0]["step"])
    assert step["state"] == "pending_review"
    assert scientific_files(project) == before


@pytest.mark.parametrize("backend", ["codex", "deepseek", "dsh"])
def test_deadline_survives_controller_process_death(docker_image, tmp_path, monkeypatch, backend):
    inputs, work = tmp_path / "input", tmp_path / "work"
    (inputs / "project/docs").mkdir(parents=True)
    work.mkdir()
    (inputs / "project/docs/STATE.md").write_text("Immutable input")
    from sciharness_loop.controller import PLAN_SCHEMA
    (inputs / "schema.json").write_text(json.dumps(PLAN_SCHEMA))
    (inputs / "context.json").write_text(json.dumps({"project": {"root": "/input/project"}}))
    (inputs / "prompt.txt").write_text("HANG")
    run_id = "e" * 32 if backend == "codex" else "f" * 32
    script = tmp_path / "host_controller.py"
    script.write_text(
        "from pathlib import Path\nimport time\n"
        "from sciharness_loop.executor import make_executor\n"
        "from sciharness_loop.policy import Policy\n"
        "root = Path({root!r})\n"
        "policy = Policy(image={image!r}, backend={backend!r}, model='fixture-model',\n"
        "  base_url={url!r}, network='none', timeout_seconds=30, _deadline_epoch=time.time()+10)\n"
        "make_executor(policy).execute({run!r}, root/'input', root/'work', root/'executor.log', policy)\n".format(
            root=str(tmp_path), image=docker_image, backend=backend, run=run_id,
            url="http://127.0.0.1:17651" if backend == "deepseek" else ""))
    env = {"PATH": os.environ.get("PATH", ""), "CODEX_API_KEY": "unused-fixture-key",
           "DEEPSEEK_API_KEY": "unused-fixture-key"}
    process = subprocess.Popen([sys.executable, str(script)], env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    docker = [shutil.which("docker"), "--host", "unix:///var/run/docker.sock"]
    try:
        armed = tmp_path / "watchdog-ready.json"
        until = time.monotonic() + 8
        while not armed.exists() and time.monotonic() < until and process.poll() is None:
            time.sleep(0.05)
        assert armed.exists(), "deadline supervisor was not armed"
        target = "sci-loop-" + run_id
        # Confirm execution actually began before killing the controller.
        until = time.monotonic() + 3
        while time.monotonic() < until:
            running = subprocess.run(docker + ["inspect", "--format", "{{.State.Running}}", target],
                                     capture_output=True, text=True)
            transcript = tmp_path / "executor.log"
            if (running.stdout.strip() == "true" and transcript.exists()
                    and "fixture_hanging" in transcript.read_text(errors="replace")):
                break
            time.sleep(0.05)
        else:
            pytest.fail("harness did not start")
        process.kill()
        process.wait()
        time.sleep(0.2)
        still_running = subprocess.run(docker + ["inspect", "--format", "{{.State.Running}}", target],
                                       capture_output=True, text=True)
        assert still_running.stdout.strip() == "true", "work ended before its deadline was exercised"
        until = time.monotonic() + 13
        while time.monotonic() < until:
            exists = subprocess.run(docker + ["inspect", target], capture_output=True)
            if exists.returncode and b"No such" in exists.stderr:
                break
            time.sleep(0.1)
        else:
            pytest.fail("orphan container outlived its independent deadline")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        subprocess.run(docker + ["rm", "--force", "sci-loop-" + run_id], capture_output=True)


@pytest.mark.parametrize("backend", ["codex", "deepseek", "dsh"])
def test_container_symlink_escape_is_not_promoted(project, docker_image, monkeypatch, backend):
    set_policy(project, image=docker_image, network="none", backend=backend,
               model="fixture-model", base_url="http://127.0.0.1:17651" if backend == "deepseek" else "")
    monkeypatch.setenv("CODEX_API_KEY", "unused-fixture-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-fixture-key")
    controller = Controller(project)
    controller._executor = DiagnosticExecutor(controller.policy, project)
    plan = controller.plan("SYMLINK pilot")
    before = scientific_files(project)
    with pytest.raises(LoopError, match="non-regular"):
        controller.step(plan["id"], plan["review_hash"], "Reviewer")
    assert scientific_files(project) == before


def test_dsh_receives_read_only_project_skills(project, docker_image, monkeypatch):
    folder = project / ".agents/skills/scientific-research"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\nname: scientific-research\ndescription: Fixture skill\n---\n",
        encoding="utf-8")
    set_policy(project, image=docker_image, network="none", backend="dsh",
               model="fixture-model", skills=["scientific-research"])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-fixture-key")
    controller = Controller(project)
    controller._executor = DiagnosticExecutor(controller.policy, project)
    plan = controller.plan("Skill pilot")
    step = controller.step(plan["id"], plan["review_hash"], "Researcher")
    assert step["state"] == "pending_review"


def test_dsh_forwards_only_the_mcp_allowlist_patch(project, docker_image, monkeypatch):
    set_policy(project, image=docker_image, network="none", backend="dsh",
               model="fixture-model",
               mcp={"servers": [{
                   "name": "fixture",
                   "command": ["/opt/sciharness/mcp_fixture_server.py"],
                   "tools": ["lookup"],
                   "timeout_seconds": 5,
               }]})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-fixture-key")
    monkeypatch.setenv("FIXTURE_EXPECT_MCP", "1")
    controller = Controller(project)
    controller._executor = DiagnosticExecutor(controller.policy, project)
    plan = controller.plan("MCP pilot")
    step = controller.step(plan["id"], plan["review_hash"], "Researcher")
    assert step["state"] == "pending_review"
