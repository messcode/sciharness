"""Approved, budgeted research runs and one-shot execution windows.

These are execution records, not new scientific objects. Results remain staged
for human review through the existing Step acceptance path.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .controller import Controller, PLAN_SCHEMA, RESULT_SCHEMA, now
from .storage import (
    LoopError, digest, is_run_id, lock, read_json, run_path, safe_path, write_json, write_text,
)


@dataclass
class RunSpec:
    objective: str
    runtime_seconds: int
    max_cycles: int
    constraints: list = field(default_factory=list)
    start_at: str | None = None
    end_at: str | None = None
    timezone: str = "UTC"
    stop_margin_seconds: int = 0


def timestamp(value, timezone="UTC"):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        zone = ZoneInfo(timezone)
        if parsed.tzinfo is None:
            local = parsed.replace(tzinfo=zone)
            if local.astimezone(dt.timezone.utc).astimezone(zone).replace(tzinfo=None) != parsed:
                raise ValueError("nonexistent local time")
            if local.utcoffset() != local.replace(fold=1).utcoffset():
                raise ValueError("ambiguous local time; specify a UTC offset")
            parsed = local
        return parsed.timestamp()
    except (ValueError, TypeError, KeyError) as exc:
        raise LoopError("invalid execution-window timestamp: " + str(exc)) from exc


def load_spec(path: Path) -> RunSpec:
    if not path.is_file():
        raise LoopError("run specification not found: " + str(path))
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LoopError("invalid run specification YAML") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise LoopError("run specification requires schema_version: 1")
    allowed = set(RunSpec.__dataclass_fields__) | {"schema_version"}
    if set(raw) - allowed:
        raise LoopError("unknown run specification keys: " + ", ".join(sorted(set(raw) - allowed)))
    try:
        spec = RunSpec(**{k: v for k, v in raw.items() if k != "schema_version"})
    except TypeError as exc:
        raise LoopError("objective, runtime_seconds, and max_cycles are required") from exc
    if not isinstance(spec.objective, str) or not 1 <= len(spec.objective.strip()) <= 16000:
        raise LoopError("run objective must contain 1–16000 characters")
    if not isinstance(spec.constraints, list) or not all(
        isinstance(x, str) and x.strip() and len(x) <= 4000 for x in spec.constraints
    ) or len(spec.constraints) > 32:
        raise LoopError("constraints must be a bounded list of non-empty strings")
    for name, low, high in (("runtime_seconds", 1, 604800), ("max_cycles", 1, 100),
                            ("stop_margin_seconds", 0, 3600)):
        value = getattr(spec, name)
        if type(value) is not int or not low <= value <= high:
            raise LoopError("invalid run limit: " + name)
    if not isinstance(spec.timezone, str):
        raise LoopError("timezone must be an IANA timezone name")
    try:
        ZoneInfo(spec.timezone)
    except (KeyError, ValueError) as exc:
        raise LoopError("unknown execution timezone") from exc
    for name in ("start_at", "end_at"):
        value = getattr(spec, name)
        if value is not None:
            epoch = timestamp(value, spec.timezone)
            setattr(spec, name, dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat())
    if spec.start_at and spec.end_at and timestamp(spec.end_at) <= timestamp(spec.start_at):
        raise LoopError("end_at must be after start_at; specify the next date for overnight runs")
    return spec


MISSION_PLAN_SCHEMA = json.loads(json.dumps(PLAN_SCHEMA))
MISSION_PLAN_SCHEMA["properties"]["action"] = {
    "type": "string", "enum": ["explore", "stop", "needs_approval"]}
MISSION_PLAN_SCHEMA["required"].append("action")


class ApprovalChanged(LoopError):
    pass


class MissionRunner:
    def __init__(self, root, executor=None, *, clock=time.time, monotonic=time.monotonic):
        self.controller = Controller(root, executor)
        self.base = self.controller.base
        self.clock, self.monotonic = clock, monotonic

    def path(self, mission_id):
        if not is_run_id(mission_id):
            raise LoopError("invalid mission ID")
        return safe_path(self.base, "missions/" + mission_id)

    def load(self, mission_id):
        value = read_json(self.path(mission_id) / "checkpoint.json")
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("id") != mission_id or not isinstance(value.get("spec"), dict)
                or not isinstance(value.get("cycles"), list)):
            raise LoopError("corrupt mission checkpoint")
        spec = value["spec"]
        if (value.get("state") not in ("prepared", "scheduled", "running", "paused", "completed",
                                       "failed", "needs_approval", "recovery_required")
                or type(value.get("spent_seconds")) not in (int, float)
                or not math.isfinite(value["spent_seconds"]) or value["spent_seconds"] < 0
                or any(not isinstance(value.get(k), str) or not value[k] for k in
                       ("created", "updated", "review_hash", "policy_hash", "input_hash",
                        "selected_input_hash"))
                or not isinstance(spec.get("objective"), str) or not spec["objective"].strip()
                or type(spec.get("runtime_seconds")) is not int
                or type(spec.get("max_cycles")) is not int
                or type(spec.get("stop_margin_seconds")) is not int
                or not isinstance(spec.get("constraints"), list)
                or not isinstance(spec.get("timezone"), str)
                or any(spec.get(k) is not None and not isinstance(spec[k], str)
                       for k in ("start_at", "end_at"))
                or ("approved_image_id" in value
                    and not isinstance(value["approved_image_id"], str))
                or ("approvals" in value and not isinstance(value["approvals"], list))):
            raise LoopError("corrupt mission state, spec, or budget")
        if any(not isinstance(cycle, dict) or "number" not in cycle or "state" not in cycle
               for cycle in value["cycles"]):
            raise LoopError("corrupt mission cycle list")
        return value

    def status(self, mission_id=None):
        if mission_id:
            value = self.load(mission_id)
            return {**value, "pause_requested": (self.path(mission_id) / "pause-request").exists()}
        directory = safe_path(self.base, "missions")
        if not directory.exists():
            return []
        result = []
        for path in directory.iterdir():
            if path.is_symlink():
                raise LoopError("symlinked mission state")
            if path.is_dir() and is_run_id(path.name):
                # A crash before the checkpoint used to leave an unusable
                # half-prepared directory; it is not a mission and must not
                # block status or new work.
                if not (path / "checkpoint.json").is_file():
                    continue
                value = self.status(path.name)
                result.append({k: value[k] for k in ("id", "state", "created", "updated",
                                                    "spent_seconds", "stop_reason", "pause_requested")})
        return sorted(result, key=lambda v: v["created"])

    def save(self, value, state=None, **fields):
        value.update(fields)
        value["state"] = state or value["state"]
        value["updated"] = now()
        value.setdefault("history", []).append({"state": value["state"], "at": value["updated"],
                                                 "stop_reason": value.get("stop_reason")})
        write_json(self.path(value["id"]) / "checkpoint.json", value)
        self.report(value)
        return value

    def report(self, value):
        rows = ["# Preliminary research run", "", value["spec"]["objective"], "",
                "State: {}. Stop reason: {}.".format(value["state"], value.get("stop_reason")),
                "Consumed/reserved runtime: {:.3f} / {} seconds.".format(
                    value["spent_seconds"], value["spec"]["runtime_seconds"]), "",
                "Results and agent-reported checks require human scientific review.", ""]
        if value.get("approved_image_id"):
            rows[-1:-1] = ["", "Approved harness image: `{}`.".format(value["approved_image_id"]), ""]
        for cycle in value["cycles"]:
            rows.extend(["## Cycle {} — {}".format(cycle["number"], cycle["state"]), ""])
            for kind in ("plan", "step"):
                if kind in cycle:
                    child = self.controller.load(cycle[kind])
                    rows.append("- {}: `{}` ({})".format(kind, child["id"], child["state"]))
                    if child.get("result"):
                        rows.extend(["", json.dumps(child["result"], ensure_ascii=False), ""])
                    if child.get("error"):
                        rows.extend(["", "Failure: " + child["error"], ""])
                    rows.append("Evidence: `.sci/loop/runs/{}/`.".format(child["id"]))
        write_text(self.path(value["id"]) / "report.md", "\n".join(rows) + "\n")

    def require_mode(self):
        if self.controller.policy.mode != "guarded_auto":
            raise LoopError("budgeted runs require explicit mode: guarded_auto")

    def prepare(self, spec_path):
        self.require_mode()
        spec = load_spec(Path(spec_path))
        with lock(self.base):
            self.controller.require_idle()
            snapshot = self.controller.snapshot()
            mission_id = uuid.uuid4().hex
            spec_data = asdict(spec)
            value = {"schema_version": 1, "id": mission_id, "created": now(),
                     "state": "prepared", "spec": spec_data, "cycles": [], "spent_seconds": 0,
                     "stop_reason": None, "policy_hash": self.controller.policy.fingerprint,
                     "input_hash": snapshot[2], "selected_input_hash": snapshot[3],
                     "review_hash": digest({"spec": spec_data, "inputs": snapshot[2],
                                            "policy": self.controller.policy.fingerprint})}
            # Journal the mission before copying input. A crash during the copy
            # then leaves a valid, non-blocking prepared mission rather than an
            # unreadable directory that blocks every later command.
            value = self.save(value)
            folder = self.path(mission_id)
            (folder / "input").mkdir(parents=True)
            write_json(folder / "input/context.json", snapshot[0])
            for relative, content in snapshot[1].items():
                path = safe_path(folder / "input/project", relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            return value

    def check(self, value):
        try:
            self.controller.check_policy(value)
        except LoopError as exc:
            raise ApprovalChanged(str(exc)) from exc
        snapshot = self.controller.snapshot()
        if snapshot[2] != value["input_hash"]:
            original = read_json(self.path(value["id"]) / "input/context.json")
            if (snapshot[3] != value["selected_input_hash"] or not
                    self.controller.mission_context_ok({"mission": value["id"]}, snapshot[0], original)):
                raise ApprovalChanged("mission inputs/context changed; prepare a new approved run")
        return snapshot

    def approve(self, mission_id, review_hash, by, *, resume=False):
        self.require_mode()
        with lock(self.base):
            value = self.load(mission_id)
            allowed = ("paused", "failed") if resume else ("prepared",)
            if value["state"] not in allowed:
                raise LoopError("mission is not ready for " + ("resumption" if resume else "approval"))
            self.check(value)
            approval = self.controller.approval(value, review_hash, by)
            image_id = self.controller.executor.resolve_image(self.controller.policy)
            previous_image = value.get("approved_image_id")
            if previous_image and previous_image != image_id:
                raise ApprovalChanged("approved harness image changed; prepare a new run")
            spec = value["spec"]
            if spec["end_at"] and self.clock() >= timestamp(spec["end_at"]):
                raise LoopError("execution window already ended; prepare a new run")
            (self.path(mission_id) / "pause-request").unlink(missing_ok=True)
            value.setdefault("approvals", []).append(approval)
            value["approved_image_id"] = image_id
            self.save(value, "scheduled", stop_reason=None)
        if not spec["start_at"] or self.clock() >= timestamp(spec["start_at"]):
            return self.run(mission_id)
        return value

    def pause(self, mission_id):
        value = self.load(mission_id)
        if value["state"] not in ("scheduled", "running"):
            raise LoopError("only scheduled/running missions can be paused")
        # A control signal, not a checkpoint rewrite; the active runner owns
        # the project lock and observes this file without accepting agent input.
        write_json(self.path(mission_id) / "pause-request", {"requested_at": now()})
        return {"id": mission_id, "pause_requested": True}

    def recover(self, mission_id):
        with lock(self.base):
            value = self.load(mission_id)
            if value["state"] not in ("running", "recovery_required"):
                raise LoopError("only unfinished missions need recovery")
            try:
                for row in self.controller.status()["runs"]:
                    if row.get("mission") != mission_id:
                        continue
                    child = self.controller.load(row["id"])
                    if child["state"] in ("prepared", "running", "recovery_required"):
                        if child["state"] != "prepared":
                            self.controller.executor.stop(child["id"])
                        self.controller.save(child, "interrupted", error="mission recovery retained partial evidence")
            except Exception as exc:
                self.save(value, "recovery_required", error=str(exc))
                raise
            if value["cycles"] and value["cycles"][-1]["state"] not in ("completed", "stopped"):
                value["cycles"][-1]["state"] = "interrupted"
            # A lost action's full reservation remains charged. We cannot infer
            # its actual runtime safely after controller death.
            return self.save(value, "paused", active=None, reservation=None,
                             stop_reason="recovered; unconfirmed runtime reservation retained")

    def dispatch(self):
        self.require_mode()
        completed, errors = [], []
        try:
            rows = self.status()
        except LoopError as exc:
            return {"dispatched": [], "errors": [{"id": None, "error": str(exc)}]}
        for row in rows:
            if row["state"] != "scheduled":
                continue
            try:
                value = self.load(row["id"])
                start = value["spec"]["start_at"]
                if not start or self.clock() >= timestamp(start):
                    completed.append(self.run(value["id"]))
            except (Exception, KeyboardInterrupt) as exc:
                errors.append({"id": row["id"], "error": str(exc) or "interrupted"})
        return {"dispatched": completed, "errors": errors}

    def history_inputs(self, value, snapshot, reserve_bytes=12000):
        history, extra = [], {}
        # Select whole files from at most three prior cycles; raw evidence is
        # retained even when omitted from the next model's bounded context.
        available = max(0, self.controller.policy.max_input_bytes -
                        sum(len(v) for v in snapshot[1].values()) -
                        len(json.dumps(snapshot[0])) - reserve_bytes)
        for cycle in value["cycles"][-4:-1]:
            for kind in ("plan", "step"):
                if kind not in cycle:
                    continue
                child = self.controller.load(cycle[kind])
                result = child.get("result", {})
                summary = {k: str(v)[:1000] for k, v in result.items()}
                item = {"cycle": cycle["number"], "kind": kind, "state": child["state"],
                        "result_excerpt": summary, "error": str(child.get("error", ""))[:1000],
                        "selected_files": [], "omitted_files": []}
                if child["state"] in ("suggested", "pending_review", "accepted"):
                    self.controller.verify_work(child)
                    for relative in child["manifest"]:
                        source = safe_path(run_path(self.base, child["id"]) / "work", relative)
                        size = source.stat().st_size
                        if size <= available and len(extra) + len(snapshot[1]) + 1 < self.controller.policy.max_files:
                            target = "prior/{}/{}".format(child["id"], relative)
                            extra[target] = source.read_bytes()
                            available -= size
                            item["selected_files"].append("/input/" + target)
                        else:
                            item["omitted_files"].append(relative)
                history.append(item)
        extra["history.json"] = json.dumps({"prior_cycles": history,
                                           "excerpts_only": True}, ensure_ascii=False).encode()
        return extra

    def action(self, value, cycle, kind, task, snapshot, *, plan=None, title=None):
        remaining = value["spec"]["runtime_seconds"] - value["spent_seconds"]
        deadline = value["deadline_epoch"]
        allowance = min(self.controller.policy.timeout_seconds, remaining, deadline - self.clock())
        if allowance <= 0:
            raise LoopError("execution budget exhausted before action")
        image_id = value.get("approved_image_id")
        if not image_id:
            raise LoopError("mission has no approved harness image")
        schema = MISSION_PLAN_SCHEMA if kind == "plan" else RESULT_SCHEMA
        reserve = len(task.encode()) + len(json.dumps(schema).encode()) + 32000
        child = self.controller.new_run(
            kind, task, snapshot, schema=MISSION_PLAN_SCHEMA if kind == "plan" else None,
            additional_inputs=self.history_inputs(value, snapshot, reserve),
            mission=value["id"], cycle=cycle["number"],
            **({"plan": plan, "title": title, "execution_approval": value["approvals"][-1]}
               if kind == "step" else {}))
        cycle[kind] = child["id"]
        value["spent_seconds"] += allowance
        self.save(value, active=child["id"], reservation=allowance)
        started = self.monotonic()
        execution_policy = replace(self.controller.policy, timeout_seconds=allowance,
                                   image=image_id,
                                   _deadline_epoch=min(deadline, self.clock() + allowance),
                                   _cancel_file=str(self.path(value["id"]) / "pause-request"))
        try:
            return self.controller.execute(child, execution_policy)
        finally:
            elapsed = max(0, self.monotonic() - started)
            if self.controller.load(child["id"])["state"] == "recovery_required":
                elapsed = max(allowance, elapsed)
            value["spent_seconds"] += elapsed - allowance
            self.save(value, active=None, reservation=None)

    def run(self, mission_id):
        self.require_mode()
        with lock(self.base):
            value = self.load(mission_id)
            if value["state"] != "scheduled":
                raise LoopError("only an approved scheduled mission can run")
            spec = value["spec"]
            if spec["start_at"] and self.clock() < timestamp(spec["start_at"]):
                return value
            if not value.get("approvals"):
                raise LoopError("mission has no execution approval")
            self.controller.require_idle(ignore_mission=mission_id)
            try:
                self.check(value)
            except LoopError as exc:
                return self.save(value, "needs_approval", stop_reason=str(exc))
            image_id = self.controller.executor.resolve_image(self.controller.policy)
            approved_image = value.get("approved_image_id")
            if approved_image and approved_image != image_id:
                return self.save(value, "needs_approval",
                                 stop_reason="approved harness image changed; prepare a new run")
            value["approved_image_id"] = image_id
            deadline = (timestamp(spec["end_at"]) if spec["end_at"] else
                        self.clock() + max(0, spec["runtime_seconds"] - value["spent_seconds"]))
            self.save(value, "running", deadline_epoch=deadline, stop_reason=None)
            pause_file = self.path(mission_id) / "pause-request"
            while True:
                remaining = spec["runtime_seconds"] - value["spent_seconds"]
                if pause_file.exists():
                    return self.save(value, "paused", stop_reason="operator requested pause")
                if remaining <= spec["stop_margin_seconds"]:
                    return self.save(value, "completed", stop_reason="runtime budget exhausted")
                if self.clock() >= deadline - spec["stop_margin_seconds"]:
                    return self.save(value, "completed", stop_reason="execution window ended")
                if len(value["cycles"]) >= spec["max_cycles"]:
                    return self.save(value, "completed", stop_reason="cycle limit reached")
                cycle = {"number": len(value["cycles"]) + 1, "state": "planning"}
                value["cycles"].append(cycle)
                self.save(value)
                try:
                    snapshot = self.check(value)
                    task = ("Approved research objective:\n" + spec["objective"] +
                            "\nConstraints:\n" + "\n".join(spec["constraints"]) +
                            "\nSelect ONE next exploratory action within this scope. Return action=explore, "
                            "stop if complete/unproductive, or needs_approval if the scope must change. "
                            "Do not repeat a failed/completed action without a new reason. "
                            "All final results remain staged for human review.")
                    plan = self.action(value, cycle, "plan", task, snapshot)
                    if plan["result"]["action"] != "explore":
                        cycle["state"] = "stopped"
                        state = "needs_approval" if plan["result"]["action"] == "needs_approval" else "completed"
                        return self.save(value, state, stop_reason=plan["result"]["rationale"])
                    if (pause_file.exists() or self.clock() >= deadline - spec["stop_margin_seconds"]
                            or value["spent_seconds"] >= spec["runtime_seconds"] - spec["stop_margin_seconds"]):
                        cycle["state"] = "not_executed"
                        continue
                    cycle["state"] = "executing"
                    self.save(value)
                    self.action(value, cycle, "step", task + "\nApproved next action:\n" +
                                plan["result"]["task"], self.check(value), plan=plan["id"],
                                title=plan["result"]["title"])
                    cycle["state"] = "completed"
                    self.save(value)
                except (Exception, KeyboardInterrupt) as exc:
                    cycle["state"] = "failed"
                    # Recover even a preparation that failed after writing its
                    # child checkpoint but before returning its ID to us.
                    for row in self.controller.status()["runs"]:
                        if (row.get("mission") == mission_id and row.get("cycle") == cycle["number"]
                                and row["kind"] not in cycle):
                            cycle[row["kind"]] = row["id"]
                    child = self.controller.load(cycle["step"] if "step" in cycle else cycle["plan"]) if (
                        "step" in cycle or "plan" in cycle) else {}
                    if child.get("state") in ("prepared", "running", "recovery_required"):
                        state, reason = "recovery_required", str(exc)
                    elif isinstance(exc, ApprovalChanged):
                        state, reason = "needs_approval", str(exc)
                    elif pause_file.exists() or isinstance(exc, KeyboardInterrupt):
                        state, reason = "paused", "operator interrupted execution"
                    elif self.clock() >= deadline or value["spent_seconds"] >= spec["runtime_seconds"]:
                        state, reason = "completed", "time limit reached; partial evidence retained"
                    else:
                        state, reason = "failed", str(exc)
                    return self.save(value, state, stop_reason=reason)
