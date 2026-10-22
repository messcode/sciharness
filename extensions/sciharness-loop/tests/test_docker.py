"""Real filesystem isolation without an API key or a model invocation.

CI sets SCI_LOOP_TEST_DOCKER=1, so inability to exercise Docker is a failure.
Local runs without a Docker daemon explicitly skip this test.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import plan_and_step, scientific_files, set_policy
from sciharness_loop.controller import Controller
from sciharness_loop.executor import CodexExecutor
from sciharness_loop.storage import LoopError


class DiagnosticExecutor(CodexExecutor):
    """Expose fixture-only transcripts on CI failures; launch code is unchanged."""
    def execute(self, run_id, inputs, work, log, policy):
        try:
            return super().execute(run_id, inputs, work, log, policy)
        except Exception as exc:
            transcript = log.read_text(errors="replace") if log.exists() else "No transcript"
            raise LoopError(str(exc) + "\nContainer fixture transcript:\n" + transcript) from exc


@pytest.fixture(scope="module")
def docker_image():
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
    tag = "sci-loop-test:local"
    subprocess.run([binary, "build", "-t", tag, str(fixtures)], check=True, capture_output=True)
    return tag


def test_real_container_cannot_read_or_write_live_project(project, docker_image, monkeypatch):
    set_policy(project, image=docker_image, network="none")
    # This is an adversarial fixture, not a real API credential.
    monkeypatch.setenv("CODEX_API_KEY", "unused-fixture-key")
    before = scientific_files(project)
    controller = Controller(project, DiagnosticExecutor())
    _, step = plan_and_step(controller)
    assert scientific_files(project) == before
    assert "read-only input enforced" in step["result"]["checks"]
    accepted = controller.accept(step["id"], step["review_hash"], "Container test reviewer")
    assert accepted["state"] == "accepted"


def test_container_symlink_escape_is_not_promoted(project, docker_image, monkeypatch):
    set_policy(project, image=docker_image, network="none")
    monkeypatch.setenv("CODEX_API_KEY", "unused-fixture-key")
    controller = Controller(project, DiagnosticExecutor())
    plan = controller.plan("SYMLINK pilot")
    before = scientific_files(project)
    with pytest.raises(LoopError, match="non-regular"):
        controller.step(plan["id"], plan["review_hash"], "Reviewer")
    assert scientific_files(project) == before
