import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sciharness_loop.core import sci  # noqa: E402
from sciharness_loop.storage import LoopError  # noqa: E402


@pytest.fixture
def project(tmp_path):
    import subprocess
    target = tmp_path / "study"
    subprocess.run([sys.executable, "-m", "sciharness.cli", "init", str(target), "--no-git"],
                   check=True, capture_output=True)
    return target


def set_policy(project, **overrides):
    path = project / ".sci/loop/policy.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    policy = {"schema_version": 1, "mode": "step", "image": "test-codex:local", **overrides}
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    return policy


@pytest.fixture
def enabled(project):
    set_policy(project)
    return project


class FakeExecutor:
    """Deterministic test double; never exposed as a CLI execution option."""
    def __init__(self, failure=None, mutate=None):
        self.calls = []
        self.stopped = []
        self.failure = failure
        self.mutate = mutate

    def stop(self, run_id):
        self.stopped.append(run_id)

    def execute(self, run_id, inputs, work, log, policy):
        self.calls.append(run_id)
        log.write_text("raw executor transcript\n")
        schema = json.loads((inputs / "schema.json").read_text())
        if "title" in schema["properties"]:
            result = {"title": "Inspect coverage", "task": "Calculate a small coverage diagnostic.",
                      "rationale": "Check coverage assumptions before any formal experiment."}
        else:
            (work / "proposal.md").write_text(
                "### Motivation\nInspect coverage.\n### Findings\nPilot only.\n"
                "### Limitations\nSynthetic diagnostic; no biological conclusion.\n"
                "### Evidence\nartifacts/diagnostic.txt\n")
            (work / "artifacts").mkdir()
            (work / "artifacts/diagnostic.txt").write_text("command: python diagnostic.py\nresult: 42\n")
            result = {"summary": "Diagnostic completed", "limitations": "Pilot only",
                      "checks": ["Synthetic output inspected"], "needs_human_review": True}
        (work / "result.json").write_text(json.dumps(result))
        if self.mutate:
            self.mutate(work)
        if self.failure:
            raise LoopError(self.failure)


@pytest.fixture
def executor():
    return FakeExecutor()


def scientific_files(project):
    return {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*")
            if p.is_file() and ".sci/loop/" not in p.relative_to(project).as_posix()}


def plan_and_step(controller):
    plan = controller.plan("Inspect coverage with one small pilot.")
    step = controller.step(plan["id"], plan["review_hash"], "Researcher")
    assert sci(controller.root, "validate")["ok"]
    return plan, step
