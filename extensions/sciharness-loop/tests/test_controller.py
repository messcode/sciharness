import json
import subprocess
from pathlib import Path

import pytest

from conftest import FakeExecutor, plan_and_step, scientific_files, set_policy
from sciharness_loop.cli import main
from sciharness_loop.controller import Controller
from sciharness_loop.core import sci
from sciharness_loop.storage import LoopError, run_path, write_json


def crash_after_new(controller, step, monkeypatch):
    import sciharness_loop.controller as module
    actual = module.sci

    def interrupted(root, *args):
        result = actual(root, *args)
        if args[0] == "new":
            raise RuntimeError("after_new")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(module, "sci", interrupted)
        with pytest.raises(RuntimeError, match="after_new"):
            controller.accept(step["id"], step["review_hash"], "Reviewer")


def test_default_status_and_record_only_do_not_write(project, executor, capsys):
    before = scientific_files(project)
    controller = Controller(project, executor)
    assert controller.status() == {"mode": "record_only", "runs": []}
    with pytest.raises(LoopError, match="record_only"):
        controller.plan("pilot")
    assert not (project / ".sci/loop").exists()
    assert scientific_files(project) == before
    assert executor.calls == []
    assert main(["status", "--path", str(project), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


def test_suggest_cannot_execute_or_accept(project, executor):
    set_policy(project, mode="suggest")
    controller = Controller(project, executor)
    before = scientific_files(project)
    plan = controller.plan("Inspect coverage")
    assert plan["state"] == "suggested"
    for operation in (lambda: controller.step(plan["id"], plan["review_hash"], "Me"),
                      lambda: controller.accept(plan["id"], plan["review_hash"], "Me")):
        with pytest.raises(LoopError, match="suggest mode"):
            operation()
    assert scientific_files(project) == before


def test_plan_step_review_then_accept_via_real_core(enabled, executor):
    before = scientific_files(enabled)
    controller = Controller(enabled, executor)
    plan, step = plan_and_step(controller)
    assert step["state"] == "pending_review"
    assert scientific_files(enabled) == before
    assert step["execution_approval"]["review_hash"] == plan["review_hash"]
    # New controller/session restores all state from disk, without chat history.
    controller = Controller(enabled, executor)
    accepted = controller.accept(step["id"], step["review_hash"], "Reviewer")
    assert accepted["state"] == "accepted"
    assert accepted["record"]["id"] == "X001"
    assert accepted["acceptance"]["by"] == "Reviewer"
    note = (enabled / accepted["record"]["record"]).read_text()
    assert "Pilot only" in note
    outputs = enabled / accepted["record"]["outputs"] / ("loop-" + step["id"])
    assert (outputs / "artifacts/diagnostic.txt").read_text().endswith("result: 42\n")
    assert sci(enabled, "validate")["ok"]
    for path, data in before.items():
        assert (enabled / path).read_bytes() == data
    assert controller.accept(step["id"], step["review_hash"], "Reviewer") == accepted
    assert len(sci(enabled, "context")["active"]["explorations"]) == 1


@pytest.mark.parametrize("review_hash,by", [(None, "Human"), ("wrong", "Human"), (None, None)])
def test_execution_needs_exact_approval(enabled, executor, review_hash, by):
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect coverage")
    with pytest.raises(LoopError, match="review-hash"):
        controller.step(plan["id"], review_hash, by)
    assert len(executor.calls) == 1


def test_accept_needs_review_of_result(enabled, executor):
    controller = Controller(enabled, executor)
    plan, step = plan_and_step(controller)
    with pytest.raises(LoopError, match="review-hash"):
        controller.accept(step["id"], plan["review_hash"], "Researcher")
    assert not sci(enabled, "context")["active"]["explorations"]


@pytest.mark.parametrize("point", ["before_execution", "before_acceptance"])
def test_changed_inputs_invalidate_approval(enabled, executor, point):
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect coverage")
    if point == "before_acceptance":
        step = controller.step(plan["id"], plan["review_hash"], "Me")
    state = enabled / "docs/STATE.md"
    state.write_text(state.read_text() + "\nHuman update.\n")
    with pytest.raises(LoopError, match="inputs changed"):
        if point == "before_execution":
            controller.step(plan["id"], plan["review_hash"], "Me")
        else:
            controller.accept(step["id"], step["review_hash"], "Me")


@pytest.mark.parametrize("name", ["context", "configuration"])
def test_selected_file_names_do_not_collide_with_fingerprints(enabled, executor, name):
    selected = enabled / name
    selected.write_text("before", encoding="utf-8")
    set_policy(enabled, read_files=["docs/CHARTER.md", "docs/STATE.md", name])
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect one selected input")
    selected.write_text("after", encoding="utf-8")
    with pytest.raises(LoopError, match="inputs changed"):
        Controller(enabled, executor).step(plan["id"], plan["review_hash"], "Me")


def test_changed_policy_requires_new_plan(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect coverage")
    set_policy(enabled, timeout_seconds=90)
    with pytest.raises(LoopError, match="policy changed"):
        Controller(enabled, executor).step(plan["id"], plan["review_hash"], "Me")


def test_changed_artifacts_reject_stale_review(enabled, executor):
    controller = Controller(enabled, executor)
    _, step = plan_and_step(controller)
    folder = run_path(controller.base, step["id"])
    (folder / "work/artifacts/diagnostic.txt").write_text("changed")
    with pytest.raises(LoopError, match="artifacts changed"):
        controller.accept(step["id"], step["review_hash"], "Me")


@pytest.mark.parametrize("bad", [
    lambda work: (work / "proposal.md").unlink() if (work / "proposal.md").exists() else None,
    lambda work: (work / "experiments").mkdir(),  # Empty directories do not carry evidence.
])
def test_empty_directories_are_not_promoted(enabled, executor, bad):
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect coverage")
    executor.mutate = bad
    if "unlink" in bad.__code__.co_names:
        with pytest.raises(LoopError, match="proposal.md"):
            controller.step(plan["id"], plan["review_hash"], "Me")
    else:
        step = controller.step(plan["id"], plan["review_hash"], "Me")
        assert "experiments" not in step["manifest"]


@pytest.mark.parametrize("mutation,match", [
    (lambda w: (w / "STATE.md").write_text("unauthorized"), "layout"),
    (lambda w: (w / "artifacts/escape").symlink_to("/etc/passwd"), "non-regular"),
    (lambda w: (w / "result.json").write_text('{"summary":"bad"}'), "fields"),
    (lambda w: (w / "proposal.md").write_bytes(b"\xff"), "utf-8"),
])
def test_malformed_or_escaping_step_retains_failure(enabled, executor, mutation, match):
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect coverage")
    executor.mutate = mutation
    before = scientific_files(enabled)
    with pytest.raises(LoopError, match=match):
        controller.step(plan["id"], plan["review_hash"], "Me")
    assert scientific_files(enabled) == before
    failed = controller.status()["runs"][-1]
    assert failed["state"] == "failed" and failed["error"]
    assert (run_path(controller.base, failed["id"]) / "executor.log").exists()


def test_failure_retry_keeps_both_attempts_and_requires_explicit_retry(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect coverage")
    executor.failure = "timeout"
    with pytest.raises(LoopError, match="timeout"):
        controller.step(plan["id"], plan["review_hash"], "Me")
    failed = controller.status()["runs"][-1]
    executor.failure = None
    with pytest.raises(LoopError, match="already executed"):
        controller.step(plan["id"], plan["review_hash"], "Me")
    retry = controller.step(plan["id"], plan["review_hash"], "Me", retry_of=failed["id"])
    assert retry["retry_of"] == failed["id"]
    assert controller.load(failed["id"])["state"] == "failed"
    assert failed["id"] in executor.stopped
    assert len(controller.status()["runs"]) == 3


def test_running_checkpoint_can_be_recovered_with_disabled_loop(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("Inspect coverage")
    checkpoint = controller.load(plan["id"])
    controller.save(checkpoint, "running")  # Simulate controller death.
    set_policy(enabled, mode="record_only")
    recovered = Controller(enabled, executor).recover(plan["id"])
    assert recovered["state"] == "interrupted"
    assert executor.stopped[-1] == plan["id"]


def test_unfinished_execution_blocks_new_work_until_recovered(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")
    controller.save(controller.load(plan["id"]), "running")
    with pytest.raises(LoopError, match="unfinished"):
        controller.plan("another pilot")
    controller.recover(plan["id"])
    assert controller.plan("another pilot")["state"] == "suggested"


def test_cannot_retry_until_container_stop_confirmed(enabled, executor, monkeypatch):
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")

    def cannot_stop(run_id):
        raise LoopError("daemon unavailable")

    monkeypatch.setattr(executor, "stop", cannot_stop)
    with pytest.raises(LoopError):
        controller.step(plan["id"], plan["review_hash"], "Me")
    run = controller.status()["runs"][-1]
    assert run["state"] == "recovery_required"
    with pytest.raises(LoopError, match="unfinished"):
        controller.step(plan["id"], plan["review_hash"], "Me", retry_of=run["id"])
    monkeypatch.setattr(executor, "stop", lambda run_id: None)
    assert controller.recover(run["id"])["state"] == "interrupted"


def test_agent_cannot_bypass_result_review(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")

    def claim_no_review(work):
        path = work / "result.json"
        result = json.loads(path.read_text())
        result["needs_human_review"] = False
        path.write_text(json.dumps(result))

    executor.mutate = claim_no_review
    step = controller.step(plan["id"], plan["review_hash"], "Me")
    assert step["state"] == "pending_review"
    assert not sci(enabled, "context")["active"]["explorations"]


@pytest.mark.parametrize("crash_point", ["after_new", "after_copy"])
def test_acceptance_resumes_without_duplicate_ids_or_lost_evidence(enabled, executor, monkeypatch,
                                                                 crash_point):
    import sciharness_loop.controller as module
    controller = Controller(enabled, executor)
    _, step = plan_and_step(controller)
    actual_sci = module.sci
    actual_save = controller.save

    def interrupted_sci(root, *args):
        result = actual_sci(root, *args)
        if crash_point == "after_new" and args[0] == "new":
            raise RuntimeError("controller died after allocation")
        return result

    def interrupted_save(value, state, **fields):
        if crash_point == "after_copy" and state == "accepted":
            raise RuntimeError("controller died after promotion")
        return actual_save(value, state, **fields)

    with monkeypatch.context() as patch:
        patch.setattr(module, "sci", interrupted_sci)
        patch.setattr(controller, "save", interrupted_save)
        with pytest.raises(RuntimeError, match="died"):
            controller.accept(step["id"], step["review_hash"], "Reviewer")
    recovered = Controller(enabled, executor).accept(step["id"], step["review_hash"], "Reviewer")
    assert recovered["state"] == "accepted"
    assert recovered["record"]["id"] == "X001"
    assert len(sci(enabled, "context")["active"]["explorations"]) == 1
    assert len(list((enabled / ".sci/ids").rglob("X001*"))) == 1


def test_modified_promoted_evidence_not_overwritten_on_resume(enabled, executor, monkeypatch):
    controller = Controller(enabled, executor)
    _, step = plan_and_step(controller)
    actual = controller.save

    def crash(value, state, **fields):
        if state == "accepted":
            raise RuntimeError("crash")
        return actual(value, state, **fields)

    monkeypatch.setattr(controller, "save", crash)
    with pytest.raises(RuntimeError):
        controller.accept(step["id"], step["review_hash"], "Me")
    partial = controller.load(step["id"])
    path = enabled / partial["record"]["outputs"] / ("loop-" + step["id"]) / "proposal.md"
    path.write_text("human edit")
    with pytest.raises(LoopError, match="overwrite"):
        Controller(enabled, executor).accept(step["id"], step["review_hash"], "Me")
    assert path.read_text() == "human edit"


def test_resumed_acceptance_still_checks_selected_inputs_and_can_be_abandoned(enabled, executor,
                                                                           monkeypatch):
    controller = Controller(enabled, executor)
    _, step = plan_and_step(controller)
    actual = controller.save

    def crash(value, state, **fields):
        if state == "accepted":
            raise RuntimeError("crash")
        return actual(value, state, **fields)

    monkeypatch.setattr(controller, "save", crash)
    with pytest.raises(RuntimeError):
        controller.accept(step["id"], step["review_hash"], "Me")
    state_path = enabled / "docs/STATE.md"
    state_path.write_text(state_path.read_text() + "\nHuman changed the research context.\n")
    resumed = Controller(enabled, executor)
    with pytest.raises(LoopError, match="selected inputs changed"):
        resumed.accept(step["id"], step["review_hash"], "Me")
    recovered = resumed.recover(step["id"])
    assert recovered["state"] == "interrupted"
    assert "partial Exploration retained" in recovered["error"]
    assert (enabled / recovered["record"]["record"]).is_file()
    assert resumed.plan("A new pilot under the revised context")["state"] == "suggested"


def test_resumed_acceptance_rejects_unrelated_context_changes(enabled, executor, monkeypatch):
    controller = Controller(enabled, executor)
    _, step = plan_and_step(controller)
    crash_after_new(controller, step, monkeypatch)
    sci(enabled, "new", "question", "New research priority")
    with pytest.raises(LoopError, match="context changed"):
        Controller(enabled, executor).accept(step["id"], step["review_hash"], "Reviewer")


def test_resumed_acceptance_rejects_another_new_exploration(enabled, executor, monkeypatch):
    controller = Controller(enabled, executor)
    _, step = plan_and_step(controller)
    crash_after_new(controller, step, monkeypatch)
    sci(enabled, "new", "exploration", "Unrelated exploration")
    with pytest.raises(LoopError, match="context changed"):
        Controller(enabled, executor).accept(step["id"], step["review_hash"], "Reviewer")


def test_whitespace_title_does_not_duplicate_allocation(enabled, executor, monkeypatch):
    def leading_title(work):
        path = work / "result.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        result["title"] = "  Inspect coverage"
        path.write_text(json.dumps(result), encoding="utf-8")

    controller = Controller(enabled, executor)
    executor.mutate = leading_title
    plan = controller.plan("Inspect coverage")
    executor.mutate = None
    step = controller.step(plan["id"], plan["review_hash"], "Me")
    crash_after_new(controller, step, monkeypatch)
    accepted = Controller(enabled, executor).accept(
        step["id"], step["review_hash"], "Reviewer")
    assert accepted["record"]["id"] == "X001"
    assert len(sci(enabled, "context")["active"]["explorations"]) == 1


def test_successful_run_stops_executor_once(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")
    assert executor.stopped == [plan["id"]]


def test_loop_state_is_git_ignored(enabled, executor):
    subprocess.run(["git", "init", "-q"], cwd=enabled, check=True)
    controller = Controller(enabled, executor)
    controller.plan("pilot")
    assert (enabled / ".sci/loop/.gitignore").is_file()
    status = subprocess.run(
        ["git", "-C", str(enabled), "status", "--short", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert ".sci/loop/.gitignore" in status
    assert ".sci/loop/policy.yaml" in status
    assert ".sci/loop/lock" not in status
    assert ".sci/loop/runs/" not in status


def test_relative_root_is_resolved(enabled, executor, monkeypatch):
    monkeypatch.chdir(enabled.parent)
    controller = Controller(Path(enabled.name), executor)
    assert controller.root == enabled.resolve()
    assert controller.plan("pilot")["state"] == "suggested"


def test_corrupt_checkpoint_fields_error_explicitly(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")
    path = run_path(controller.base, plan["id"]) / "checkpoint.json"
    write_json(path, {"schema_version": 1, "id": plan["id"], "state": "suggested"})
    with pytest.raises(LoopError, match="corrupt checkpoint"):
        controller.status(plan["id"])
    with pytest.raises(LoopError, match="corrupt checkpoint"):
        controller.status()


def test_stray_run_entries_do_not_block_status_or_plan(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")
    (controller.base / "runs" / ".DS_Store").write_text("finder", encoding="utf-8")
    assert controller.status()["runs"][0]["id"] == plan["id"]
    assert controller.plan("another pilot")["state"] == "suggested"


def test_id_allocation_uses_existing_core_ledger(enabled, executor):
    sci(enabled, "new", "exploration", "Existing research")
    controller = Controller(enabled, executor)
    _, step = plan_and_step(controller)
    accepted = controller.accept(step["id"], step["review_hash"], "Me")
    assert accepted["record"]["id"] == "X002"


def test_cli_error_is_json_and_status_can_restore(enabled, executor, capsys, monkeypatch):
    import sciharness_loop.controller as module
    monkeypatch.setattr(module, "make_executor", lambda *args: executor)
    assert main(["plan", "--task", "Inspect coverage", "--path", str(enabled), "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)["result"]
    assert main(["step", "--plan", plan["id"], "--path", str(enabled), "--json"]) == 1
    assert "review-hash" in json.loads(capsys.readouterr().out)["error"]
    assert main(["status", plan["id"], "--path", str(enabled), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["state"] == "suggested"


def test_long_task_rejected_before_executor(enabled, executor):
    controller = Controller(enabled, executor)
    with pytest.raises(LoopError, match="bounded task"):
        controller.plan("x" * 16001)
    assert not executor.calls


def test_input_budget_failure_does_not_corrupt_status(enabled, executor):
    set_policy(enabled, max_input_bytes=10)
    controller = Controller(enabled, executor)
    with pytest.raises(LoopError, match="input budget"):
        controller.plan("pilot")
    assert controller.status()["runs"] == []


def test_output_budget_rejects_before_promotion(enabled):
    executor = FakeExecutor()
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")
    executor.mutate = lambda w: (w / "artifacts/huge").write_bytes(b"x" * 10_000_001)
    with pytest.raises(LoopError, match="artifact budget"):
        controller.step(plan["id"], plan["review_hash"], "Me")


def test_corrupt_checkpoint_errors_explicitly(enabled, executor):
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")
    path = run_path(controller.base, plan["id"]) / "checkpoint.json"
    write_json(path, {"schema_version": 99, "id": plan["id"]})
    with pytest.raises(LoopError, match="unsupported"):
        controller.status(plan["id"])


def test_source_files_not_selected_are_not_copied(enabled, executor):
    (enabled / "data/private.bin").write_bytes(b"never send this")
    controller = Controller(enabled, executor)
    plan = controller.plan("pilot")
    folder = run_path(controller.base, plan["id"]) / "input/project"
    assert not (folder / "data/private.bin").exists()
    assert {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()} == {
        "docs/CHARTER.md", "docs/STATE.md"}
