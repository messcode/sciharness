"""One bounded research action, review, and resumable append-only promotion."""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path

from .core import sci
from .executor import CodexExecutor
from .policy import load_policy
from .storage import (
    LoopError, copy_new, digest, file_hash, files, lock, read_json, run_path, safe_path, write_json,
)


PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {key: {"type": "string"} for key in ("title", "task", "rationale")},
    "required": ["title", "task", "rationale"],
}
RESULT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"}, "limitations": {"type": "string"},
        "checks": {"type": "array", "items": {"type": "string"}},
        "needs_human_review": {"type": "boolean"},
    },
    "required": ["summary", "limitations", "checks", "needs_human_review"],
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Controller:
    def __init__(self, root: Path, executor=None):
        self.root = root
        self.base = safe_path(root, ".sci/loop")
        self.policy = load_policy(root)
        self._executor = executor

    @property
    def executor(self):
        if self._executor is None:
            self._executor = CodexExecutor()
        return self._executor

    def require(self, action):
        if self.policy.mode == "record_only":
            raise LoopError("record_only: explicitly enable suggest or step in policy.yaml")
        if action == "step" and self.policy.mode != "step":
            raise LoopError("suggest mode cannot execute or accept research steps")

    def load(self, run_id):
        value = read_json(safe_path(run_path(self.base, run_id), "checkpoint.json"))
        if value.get("schema_version") != 1 or value.get("id") != run_id:
            raise LoopError("unsupported or mismatched checkpoint")
        return value

    def save(self, value, state, **fields):
        value.update(fields)
        value["state"] = state
        value["updated"] = now()
        value.setdefault("history", []).append({"state": state, "at": value["updated"]})
        write_json(run_path(self.base, value["id"]) / "checkpoint.json", value)
        return value

    def snapshot(self):
        context = sci(self.root, "context")
        # Machine routing is context, never a substitute for scientific evidence.
        context["project"]["root"] = "/input/project"
        selected = list(dict.fromkeys(self.policy.read_files + context["read_first"]))
        if len(selected) > self.policy.max_files:
            raise LoopError("too many input files")
        contents = {}
        total = len(json.dumps(context).encode())
        for relative in selected:
            path = safe_path(self.root, relative)
            if path.relative_to(self.root).parts[0] in (".git", ".sci"):
                raise LoopError("Git metadata and loop state cannot be agent inputs")
            if not path.is_file():
                raise LoopError("input must be an existing regular file: " + relative)
            if path.stat().st_size + total > self.policy.max_input_bytes:
                raise LoopError("input budget exceeded; select fewer/smaller read_files")
            contents[relative] = path.read_bytes()
            total += len(contents[relative])
        identity = {name: hashlib.sha256(data).hexdigest()
                    for name, data in contents.items()}
        identity["context"] = digest(context)
        identity["configuration"] = file_hash(safe_path(self.root, ".sci.yaml"))
        selected_hash = digest({k: v for k, v in identity.items() if k != "context"})
        return context, contents, digest(identity), selected_hash

    def new_run(self, kind, task, snapshot, **extra):
        context, contents, fingerprint, selected_hash = snapshot
        run_id = uuid.uuid4().hex  # Execution IDs are separate from scientific IDs.
        folder = run_path(self.base, run_id)
        inputs, work = folder / "input", folder / "work"
        prompt = (
            "You are performing ONE human-controlled SciHarness research action.\n"
            "Read /input/context.json and the explicitly selected files in /input/project.\n"
            "Scientific records and data are read-only. Do not invent scientific IDs.\n"
            "Do not start formal experiments, freeze designs, approve figures, or make final decisions.\n"
            "Preserve evidence, failed checks, and uncertainty. Structural checks do not verify science.\n"
        )
        if kind == "plan":
            prompt += (
                "Suggest ONE bounded exploratory action addressing the request below. "
                "Return title, task (specific scope and completion criteria), and rationale. "
                "Write no other files. Formal tests require a separate human-led workflow.\n"
            )
        else:
            prompt += (
                "Execute only the approved exploratory task below. Write proposal.md with motivation, "
                "methods, findings, failed checks, limitations, and evidence paths. "
                "Put scripts, exact commands, raw logs, and useful outputs in artifacts/. "
                "All writes must stay in /work. Return summary, limitations, checks, "
                "and needs_human_review. Your checks are reported claims awaiting human review.\n"
            )
        prompt += "\nREQUEST / APPROVED TASK:\n" + task
        if len(prompt.encode()) + sum(len(v) for v in contents.values()) + len(
            json.dumps(context).encode()
        ) > self.policy.max_input_bytes:
            raise LoopError("task and context exceed input budget")
        value = {
            "schema_version": 1, "id": run_id, "kind": kind, "created": now(),
            "policy": asdict(self.policy), "policy_hash": self.policy.fingerprint,
            "input_hash": fingerprint, "selected_input_hash": selected_hash, "task": task, **extra,
        }
        self.save(value, "prepared")
        inputs.mkdir()
        work.mkdir()
        for relative, data in contents.items():
            path = safe_path(inputs / "project", relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        write_json(inputs / "context.json", context)
        write_json(inputs / "schema.json", PLAN_SCHEMA if kind == "plan" else RESULT_SCHEMA)
        (inputs / "prompt.txt").write_text(prompt, encoding="utf-8")
        return value

    def execute(self, value):
        folder = run_path(self.base, value["id"])
        self.save(value, "running")
        executor = None
        try:
            executor = self.executor
            executor.execute(value["id"], folder / "input", folder / "work",
                             folder / "executor.log", self.policy)
            executor.stop(value["id"])  # No live writer may survive finalization.
            manifest = files(folder / "work", self.policy.max_output_bytes, self.policy.max_files)
            result = read_json(folder / "work" / "result.json")
            schema = PLAN_SCHEMA if value["kind"] == "plan" else RESULT_SCHEMA
            self.validate_result(result, schema)
            if value["kind"] == "plan":
                if set(manifest) != {"result.json"}:
                    raise LoopError("suggest executor produced unapproved artifacts")
                return self.save(value, "suggested", result=result, manifest=manifest,
                                 review_hash=digest({"result": result, "inputs": value["input_hash"],
                                                     "policy": value["policy_hash"]}))
            if "proposal.md" not in manifest:
                raise LoopError("step must produce proposal.md")
            if any(p not in ("result.json", "proposal.md") and not p.startswith("artifacts/")
                   for p in manifest):
                raise LoopError("step wrote outside the permitted artifact layout")
            (folder / "work" / "proposal.md").read_text(encoding="utf-8")
            return self.save(value, "pending_review", result=result, manifest=manifest,
                             review_hash=digest({"manifest": manifest, "plan": value["plan"],
                                                 "inputs": value["input_hash"],
                                                 "policy": value["policy_hash"]}))
        except (Exception, KeyboardInterrupt) as exc:
            state = "failed"
            error = str(exc) or "interrupted"
            try:
                if executor is not None:
                    executor.stop(value["id"])
            except Exception as stop_error:
                state = "recovery_required"
                error += "; cannot confirm executor stopped: " + str(stop_error)
            self.save(value, state, error=error)
            raise LoopError("{}; execution {} retained".format(str(exc) or "interrupted", value["id"])) from exc

    @staticmethod
    def validate_result(result, schema):
        if not isinstance(result, dict) or set(result) != set(schema["required"]):
            raise LoopError("executor result fields do not match schema")
        for name, rule in schema["properties"].items():
            value = result[name]
            kind = rule["type"]
            if (kind == "string" and (not isinstance(value, str) or not value.strip())) or (
                kind == "boolean" and type(value) is not bool
            ) or (kind == "array" and (not isinstance(value, list) or not all(
                isinstance(x, str) and x.strip() for x in value
            ))):
                raise LoopError("invalid executor result: " + name)
        if "title" in result and (len(result["title"]) > 160 or len(result["task"]) > 16000):
            raise LoopError("plan title/task exceeds the bounded action size")

    def plan(self, task):
        self.require("plan")
        if not task.strip() or len(task) > 16000:
            raise LoopError("provide a bounded task (1–16000 characters)")
        with lock(self.base):
            self.require_idle()
            return self.execute(self.new_run("plan", task, self.snapshot()))

    def require_idle(self):
        unfinished = [v["id"] for v in self.status()["runs"]
                      if v["state"] in ("prepared", "running", "recovery_required", "applying")]
        if unfinished:
            raise LoopError("recover unfinished execution(s) before new work: " + ", ".join(unfinished))

    def check_policy(self, value):
        if self.policy.fingerprint != value["policy_hash"]:
            raise LoopError("policy changed; create and review a new plan")

    def check_inputs(self, value):
        snapshot = self.snapshot()
        if snapshot[2] != value["input_hash"]:
            raise LoopError("project inputs changed; create and review a new plan")
        return snapshot

    @staticmethod
    def approval(value, review_hash, by):
        if not by or not by.strip() or review_hash != value.get("review_hash"):
            raise LoopError("explicit --by and the current --review-hash are required")
        return {"by": by.strip(), "review_hash": review_hash, "at": now()}

    def step(self, plan_id, review_hash, by, retry_of=None):
        self.require("step")
        with lock(self.base):
            self.require_idle()
            plan = self.load(plan_id)
            if plan["kind"] != "plan" or plan["state"] != "suggested":
                raise LoopError("step requires a suggested plan")
            self.check_policy(plan)
            self.verify_work(plan)
            approval = self.approval(plan, review_hash, by)
            if retry_of:
                previous = self.load(retry_of)
                if previous.get("plan") != plan_id or previous["state"] not in ("failed", "interrupted"):
                    raise LoopError("retry requires a failed/interrupted step of the same plan")
                self.executor.stop(retry_of)
            prior = [v for v in self.status()["runs"] if v.get("plan") == plan_id]
            if prior and (not retry_of or prior[-1]["id"] != retry_of):
                raise LoopError("plan already executed; recover/review it or explicitly retry its last failure")
            value = self.new_run("step", plan["result"]["task"], self.check_inputs(plan),
                                 plan=plan_id, title=plan["result"]["title"],
                                 execution_approval=approval, retry_of=retry_of)
            return self.execute(value)

    def verify_work(self, value):
        folder = run_path(self.base, value["id"])
        actual = files(safe_path(folder, "work"), self.policy.max_output_bytes, self.policy.max_files)
        if actual != value["manifest"]:
            raise LoopError("artifacts changed after checkpoint; review is stale")

    def recover(self, run_id):
        # Recovery may stop a container even after the operator disabled Loop.
        with lock(self.base):
            value = self.load(run_id)
            if value["state"] not in ("running", "prepared", "recovery_required", "applying"):
                raise LoopError("only an unfinished execution needs recovery")
            if value["state"] not in ("prepared", "applying"):
                self.executor.stop(run_id)
            message = "operator recovered an interrupted execution"
            if value["state"] == "applying":
                message += "; partial Exploration retained for manual review"
            return self.save(value, "interrupted", error=message)

    def accept(self, run_id, review_hash, by):
        self.require("step")
        with lock(self.base):
            value = self.load(run_id)
            if value["kind"] != "step" or value["state"] not in ("pending_review", "applying", "accepted"):
                raise LoopError("only a completed, reviewable step can be accepted")
            self.check_policy(value)
            approval = self.approval(value, review_hash, by)
            self.verify_work(value)
            if value["state"] == "accepted":
                return value
            if value["state"] == "pending_review":
                self.check_inputs(value)
                self.save(value, "applying", acceptance=approval)
            elif self.snapshot()[3] != value["selected_input_hash"]:
                raise LoopError("selected inputs changed during acceptance; recover and make a new plan")
            # On recovery, applying retains the original approval. Revalidate
            # structure, but the context now legitimately includes the new X ID.
            sci(self.root, "validate")
            return self.promote(value)

    def promote(self, value):
        """Journaled, idempotent creation. Never replace an existing record."""
        folder = run_path(self.base, value["id"])
        work = folder / "work"
        title = value["title"] + " (loop " + value["id"] + ")"
        if "record" not in value:
            # Detect a crash after `sci new` but before the checkpoint write.
            matches = [r for r in sci(self.root, "context")["active"]["explorations"]
                       if r["title"] == title]
            if len(matches) > 1:
                raise LoopError("ambiguous recovery records; human inspection required")
            if matches:
                created = {"id": matches[0]["id"], "record": matches[0]["path"],
                           "outputs": "outputs/explorations/" + matches[0]["id"]}
            else:
                created = sci(self.root, "new", "exploration", title)
            self.save(value, "applying", record={k: created[k] for k in ("id", "record", "outputs")})
        record = value["record"]
        outputs = safe_path(self.root, record["outputs"] + "/loop-" + value["id"])
        outputs.mkdir(parents=True, exist_ok=True)
        # Copy by bytes with a no-clobber check; files remain inert evidence.
        for relative in value["manifest"]:
            source = safe_path(work, relative)
            target = safe_path(outputs, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_new(source, target)
        note = safe_path(self.root, record["record"])
        marker = "<!-- sci-loop execution: {} -->".format(value["id"])
        appendix = (
            "\n\n" + marker + "\n\n## Reviewed exploratory result\n\n"
            + (work / "proposal.md").read_text(encoding="utf-8")
            + "\n\nExecution provenance: `.sci/loop/runs/" + value["id"] + "/checkpoint.json`.\n"
            + "Evidence bundle: `" + outputs.relative_to(self.root).as_posix() + "/`.\n"
            + "Agent-reported checks require scientific review; acceptance is not a formal conclusion.\n"
        )
        text = note.read_text(encoding="utf-8")
        if marker in text:
            if not text.endswith(appendix):
                raise LoopError("promoted note was edited; refusing to overwrite it")
        else:
            temporary = safe_path(note.parent, "NOTE.md.loop-tmp")
            temporary.write_text(text + appendix, encoding="utf-8")
            temporary.replace(note)
        validation = sci(self.root, "validate")
        return self.save(value, "accepted", validation=validation)

    def status(self, run_id=None):
        if run_id:
            return self.load(run_id)
        directory = safe_path(self.base, "runs")
        runs = []
        if directory.exists():
            for path in directory.iterdir():
                if path.is_symlink() or not path.is_dir():
                    raise LoopError("unexpected execution state entry")
                runs.append(self.load(path.name))
        keys = ("id", "kind", "state", "created", "updated", "plan", "retry_of", "review_hash", "error")
        return {"mode": self.policy.mode, "runs": [
            {key: value[key] for key in keys if key in value}
            for value in sorted(runs, key=lambda v: v["created"])
        ]}
