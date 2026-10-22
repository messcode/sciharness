import datetime as dt
import json

import pytest
import yaml

from conftest import FakeExecutor, scientific_files, set_policy
from sciharness_loop.cli import main
from sciharness_loop.missions import MissionRunner, load_spec, timestamp
from sciharness_loop.storage import LoopError, run_path


class Clock:
    def __init__(self):
        self.value = timestamp("2030-01-01T00:00:00Z")

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class ScriptedExecutor(FakeExecutor):
    def __init__(self, clock, actions=None, seconds=1, callback=None):
        super().__init__()
        self.clock, self.seconds, self.callback = clock, seconds, callback
        self.actions = list(actions or ["explore"] * 100)
        self.limits, self.histories = [], []

    def execute(self, run_id, inputs, work, log, policy):
        self.limits.append((policy.timeout_seconds, policy._deadline_epoch))
        history = inputs / "history.json"
        if history.exists():
            self.histories.append(json.loads(history.read_text()))
        super().execute(run_id, inputs, work, log, policy)
        schema = json.loads((inputs / "schema.json").read_text())
        if "action" in schema["properties"]:
            path = work / "result.json"
            value = json.loads(path.read_text())
            value["action"] = self.actions.pop(0)
            path.write_text(json.dumps(value))
        self.clock.advance(self.seconds)
        if self.callback:
            self.callback(run_id, inputs, work, policy)


def configure(project, tmp_path, **spec):
    set_policy(project, mode="guarded_auto")
    target = tmp_path / "run.yaml"
    target.write_text(yaml.safe_dump({"schema_version": 1, "objective": "Inspect pilot coverage",
                                    "runtime_seconds": 100, "max_cycles": 3, **spec}))
    return target


def runner(project, clock, executor=None):
    return MissionRunner(project, executor or ScriptedExecutor(clock), clock=clock, monotonic=clock)


def approve(instance, value, **kwargs):
    return instance.approve(value["id"], value["review_hash"], "Researcher", **kwargs)


def test_preparation_is_non_executing_and_approval_bound(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    instance = runner(project, clock)
    before = scientific_files(project)
    prepared = instance.prepare(path)
    assert prepared["state"] == "prepared" and not instance.controller.executor.calls
    assert scientific_files(project) == before
    for bad_hash, by in (("wrong", "Me"), (prepared["review_hash"], "")):
        with pytest.raises(LoopError, match="review-hash"):
            instance.approve(prepared["id"], bad_hash, by)
    completed = approve(instance, prepared)
    assert completed["state"] == "completed"
    assert len(completed["cycles"]) == 3
    assert len(instance.controller.executor.calls) == 6
    assert scientific_files(project) == before
    assert (instance.path(prepared["id"]) / "report.md").is_file()


@pytest.mark.parametrize("mode", ["record_only", "suggest", "step"])
def test_runs_require_explicit_autonomy_opt_in(project, tmp_path, mode):
    path = configure(project, tmp_path)
    set_policy(project, mode=mode)
    with pytest.raises(LoopError, match="guarded_auto"):
        runner(project, Clock()).prepare(path)


def test_adaptive_stop_and_approval_request(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    executor = ScriptedExecutor(clock, ["explore", "needs_approval"])
    instance = runner(project, clock, executor)
    value = approve(instance, instance.prepare(path))
    assert value["state"] == "needs_approval"
    assert len(executor.calls) == 3  # plan+step, then a planner pauses.
    with pytest.raises(LoopError):
        approve(instance, value, resume=True)


def test_goal_reached_can_stop_before_experiment(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    instance = runner(project, clock, ScriptedExecutor(clock, ["stop"]))
    value = approve(instance, instance.prepare(path))
    assert value["state"] == "completed" and len(instance.controller.executor.calls) == 1
    assert "step" not in value["cycles"][0]


def test_runtime_budget_is_cumulative_and_limits_each_backend_action(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path, runtime_seconds=6)
    instance = runner(project, clock, ScriptedExecutor(clock, seconds=3))
    value = approve(instance, instance.prepare(path))
    assert value["state"] == "completed"
    assert "budget" in value["stop_reason"]
    assert len(instance.controller.executor.calls) == 2
    assert value["spent_seconds"] == 6
    assert instance.controller.executor.limits == [(6, clock.value), (3, clock.value)]


def test_window_can_end_between_planning_and_execution(project, tmp_path):
    clock = Clock()
    end = dt.datetime.fromtimestamp(clock() + 3, dt.timezone.utc).isoformat()
    path = configure(project, tmp_path, end_at=end)
    instance = runner(project, clock, ScriptedExecutor(clock, seconds=3))
    value = approve(instance, instance.prepare(path))
    assert len(instance.controller.executor.calls) == 1
    assert value["state"] == "completed" and "window" in value["stop_reason"]


def test_stop_margin_does_not_launch_another_action(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path, runtime_seconds=5, stop_margin_seconds=2)
    instance = runner(project, clock, ScriptedExecutor(clock, seconds=3))
    value = approve(instance, instance.prepare(path))
    assert len(instance.controller.executor.calls) == 1
    assert value["state"] == "completed"


def test_future_overnight_window_dispatches_only_when_due_once(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path, timezone="Asia/Shanghai",
                     start_at="2030-01-01T18:00:00", end_at="2030-01-02T08:00:00")
    instance = runner(project, clock)
    value = approve(instance, instance.prepare(path))
    assert value["state"] == "scheduled" and not instance.controller.executor.calls
    assert instance.dispatch() == {"dispatched": []}
    clock.value = timestamp("2030-01-01T18:00:00", "Asia/Shanghai")
    result = instance.dispatch()["dispatched"][0]
    assert result["state"] == "completed"
    assert instance.dispatch() == {"dispatched": []}
    assert len(instance.controller.executor.calls) == 6


def test_missed_window_never_runs_model(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path, start_at="2030-01-02T18:00:00Z",
                     end_at="2030-01-03T08:00:00Z")
    instance = runner(project, clock)
    approve(instance, instance.prepare(path))
    clock.value = timestamp("2030-01-04T00:00:00Z")
    completed = instance.dispatch()["dispatched"][0]
    assert completed["state"] == "completed" and not instance.controller.executor.calls


def test_scheduled_approval_invalidated_by_changes(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path, start_at="2030-01-02T18:00:00Z")
    instance = runner(project, clock)
    value = approve(instance, instance.prepare(path))
    state = project / "docs/STATE.md"
    state.write_text(state.read_text() + "\nNew scientific context\n")
    clock.value = timestamp("2030-01-03T00:00:00Z")
    completed = instance.dispatch()["dispatched"][0]
    assert completed["state"] == "needs_approval" and not instance.controller.executor.calls
    assert completed["id"] == value["id"]


def test_policy_change_during_run_blocks_next_action(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    instance = runner(project, clock)
    instance.controller.executor.callback = lambda *args: set_policy(project, mode="record_only")
    result = approve(instance, instance.prepare(path))
    assert result["state"] == "needs_approval"
    assert len(instance.controller.executor.calls) == 1
    assert "policy changed" in result["stop_reason"]


def test_failed_preparation_is_discoverable_for_mission_recovery(project, tmp_path, monkeypatch):
    clock = Clock()
    path = configure(project, tmp_path)
    instance = runner(project, clock)
    value = instance.prepare(path)
    original = instance.controller.new_run

    def fail_after_preparation(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("input copy interrupted")

    monkeypatch.setattr(instance.controller, "new_run", fail_after_preparation)
    result = approve(instance, value)
    assert result["state"] == "recovery_required"
    assert result["cycles"][0]["plan"]
    recovered = instance.recover(value["id"])
    assert recovered["state"] == "paused" and recovered["spent_seconds"] == 0


def test_operator_pause_is_seen_before_next_backend_action(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    instance = runner(project, clock)
    value = instance.prepare(path)
    instance.controller.executor.callback = lambda *args: instance.pause(value["id"])
    paused = approve(instance, value)
    assert paused["state"] == "paused" and len(instance.controller.executor.calls) == 1
    instance.controller.executor.callback = None
    clock.advance(200)  # Paused time consumes no active budget without an end_at.
    resumed = approve(instance, paused, resume=True)
    assert resumed["state"] == "completed"
    assert resumed["spent_seconds"] == len(instance.controller.executor.calls)
    assert len(resumed["approvals"]) == 2


def test_failure_retains_evidence_and_stops_batch(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    executor = ScriptedExecutor(clock)
    instance = runner(project, clock, executor)
    prepared = instance.prepare(path)
    executor.failure = "diagnostic script failed"
    value = approve(instance, prepared)
    assert value["state"] == "failed" and len(executor.calls) == 1
    child = instance.controller.load(value["cycles"][0]["plan"])
    assert child["state"] == "failed"
    assert (run_path(instance.base, child["id"]) / "executor.log").is_file()


def test_orphan_recovery_retains_reserved_time_and_completed_results(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    instance = runner(project, clock)
    value = instance.prepare(path)
    value["approvals"] = [{"by": "Me", "review_hash": value["review_hash"]}]
    child = instance.controller.new_run("step", "pilot", instance.controller.snapshot(),
                                        title="Pilot", plan="a" * 32, mission=value["id"], cycle=1)
    instance.controller.save(child, "running")
    value["cycles"].append({"number": 1, "state": "executing", "step": child["id"]})
    instance.save(value, "running", spent_seconds=60, reservation=60, active=child["id"])
    with pytest.raises(LoopError, match="unfinished"):
        instance.controller.plan("other work")
    recovered = instance.recover(value["id"])
    assert recovered["state"] == "paused" and recovered["spent_seconds"] == 60
    assert instance.controller.load(child["id"])["state"] == "interrupted"
    assert child["id"] in instance.controller.executor.stopped


def test_unconfirmed_stop_consumes_full_reservation_and_blocks_dispatch(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path)
    instance = runner(project, clock)
    value = instance.prepare(path)

    def broken_stop(run_id):
        raise LoopError("cannot stop container")

    instance.controller.executor.stop = broken_stop
    failed = approve(instance, value)
    assert failed["state"] == "recovery_required"
    assert failed["spent_seconds"] >= 100


def test_later_cycles_receive_bounded_prior_evidence(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path, max_cycles=2)
    executor = ScriptedExecutor(clock)
    instance = runner(project, clock, executor)
    value = approve(instance, instance.prepare(path))
    assert value["state"] == "completed"
    assert executor.histories[0]["prior_cycles"] == []
    assert executor.histories[-1]["prior_cycles"][0]["cycle"] == 1
    step = instance.controller.load(value["cycles"][-1]["step"])
    inputs = run_path(instance.base, step["id"]) / "input"
    assert list((inputs / "prior").rglob("diagnostic.txt"))


def test_reviewed_mission_results_can_be_accepted_sequentially(project, tmp_path):
    clock = Clock()
    path = configure(project, tmp_path, max_cycles=2)
    instance = runner(project, clock)
    value = approve(instance, instance.prepare(path))
    for cycle in value["cycles"]:
        step = instance.controller.load(cycle["step"])
        accepted = instance.controller.accept(step["id"], step["review_hash"], "Reviewer")
        assert accepted["state"] == "accepted"
    assert len(instance.controller.status()["runs"]) == 4
    assert len(list((project / "explorations").glob("X*"))) == 2


def test_mission_acceptance_still_rejects_unrelated_changes(project, tmp_path):
    from sciharness_loop.core import sci
    clock = Clock()
    path = configure(project, tmp_path, max_cycles=1)
    instance = runner(project, clock)
    value = approve(instance, instance.prepare(path))
    step = instance.controller.load(value["cycles"][0]["step"])
    sci(project, "new", "question", "Unrelated research change")
    with pytest.raises(LoopError, match="inputs changed"):
        instance.controller.accept(step["id"], step["review_hash"], "Reviewer")


@pytest.mark.parametrize("overrides", [
    {"runtime_seconds": True}, {"max_cycles": 0}, {"permissions": {"edit_charter": True}},
    {"start_at": "2030-01-02T18:00:00Z", "end_at": "2030-01-02T08:00:00Z"},
    {"timezone": "Not/AZone"}, {"constraints": "anything"},
])
def test_invalid_run_specifications_rejected(project, tmp_path, overrides):
    path = configure(project, tmp_path, **overrides)
    with pytest.raises(LoopError):
        load_spec(path)


def test_dst_requires_unambiguous_times():
    with pytest.raises(LoopError, match="ambiguous"):
        timestamp("2030-11-03T01:30:00", "America/New_York")
    with pytest.raises(LoopError, match="nonexistent"):
        timestamp("2030-03-10T02:30:00", "America/New_York")
    assert timestamp("2030-11-03T01:30:00-04:00") < timestamp("2030-11-03T01:30:00-05:00")


def test_mission_status_cli_is_write_free(project, capsys):
    assert main(["status", "--missions", "--json", "--path", str(project)]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == []
    assert not (project / ".sci/loop").exists()


def test_existing_policy_fingerprint_is_preserved():
    from sciharness_loop.policy import Policy
    from sciharness_loop.storage import digest
    legacy = {"mode": "step", "image": "legacy:1", "read_files": ["docs/CHARTER.md", "docs/STATE.md"],
              "timeout_seconds": 600, "max_input_bytes": 256000, "max_output_bytes": 10000000,
              "max_files": 100, "memory_mb": 2048, "cpus": 2, "network": "bridge"}
    assert Policy(**legacy).fingerprint == digest(legacy)
