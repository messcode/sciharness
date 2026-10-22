import dataclasses
import json
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from conftest import set_policy
from sciharness_loop.adapters import CodexAdapter, DeepSeekAdapter, adapter_for
from sciharness_loop.controller import Controller, PLAN_SCHEMA
from sciharness_loop.deepseek_runner import Runner
from sciharness_loop.executor import HarnessExecutor, make_executor
from sciharness_loop.policy import Policy, load_policy
from sciharness_loop.runtime import DockerRuntime, REQUIRED_CAPABILITIES
from sciharness_loop.storage import LoopError
from sciharness_loop.watchdog import supervise


@contextmanager
def api(responses):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, self.headers.get("Authorization"), body))
            response = responses.pop(0)
            data = json.dumps({"model": "fixture-model", "usage": {"total_tokens": 3},
                               "choices": [response]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port), received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def response(name, arguments, call_id="call-1"):
    return {"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments)}}]}}


def test_real_deepseek_tool_loop_over_http_protocol(tmp_path):
    inputs, work = tmp_path / "input", tmp_path / "work"
    inputs.mkdir()
    work.mkdir()
    (inputs / "schema.json").write_text(json.dumps(PLAN_SCHEMA))
    final = {"title": "Pilot", "task": "Inspect coverage", "rationale": "Check assumptions"}
    responses = [response("write_file", {"path": "script.py", "content": "print(42)\n"}),
                 response("shell", {"command": "python3 script.py", "timeout_seconds": 2}, "call-2"),
                 response("finish", final, "call-3")]
    with api(responses) as (url, received):
        result = Runner("selected-model", url, "fixture-key", input_root=inputs,
                        work=work).run("A bounded test")
    assert result == final and json.loads((work / "result.json").read_text()) == final
    assert len(received) == 3
    assert received[0][0] == "/chat/completions" and received[0][1] == "Bearer fixture-key"
    assert received[0][2]["model"] == "selected-model"
    assert received[0][2]["thinking"] == {"type": "disabled"}
    messages = received[-1][2]["messages"]
    assert [v["tool_call_id"] for v in messages if v["role"] == "tool"] == ["call-1", "call-2"]
    assert "42" in messages[-1]["content"]
    assert "fixture-key" not in json.dumps(received[-1][2])


def test_deepseek_incomplete_and_invalid_output_never_succeeds(tmp_path):
    (tmp_path / "schema.json").write_text(json.dumps(PLAN_SCHEMA))
    truncated = {"finish_reason": "length", "message": {"role": "assistant", "content": "{}"}}
    with api([truncated]) as (url, _):
        with pytest.raises(ValueError, match="incomplete"):
            Runner("fixture", url, "fake", input_root=tmp_path, work=tmp_path).run("pilot")
    with api([response("finish", {"title": "missing fields"})]) as (url, _):
        with pytest.raises(ValueError, match="required fields"):
            Runner("fixture", url, "fake", input_root=tmp_path, work=tmp_path).run("pilot")
    assert not (tmp_path / "result.json").exists()


def test_deepseek_context_and_turn_limits_fail_closed(tmp_path):
    (tmp_path / "schema.json").write_text(json.dumps(PLAN_SCHEMA))
    instance = Runner("fixture", "https://api.deepseek.com", "unused",
                      input_root=tmp_path, work=tmp_path, context_bytes=10)
    with pytest.raises(ValueError, match="context budget"):
        instance.run("pilot")
    instance = Runner("fixture", "https://api.deepseek.com", "unused",
                      input_root=tmp_path, work=tmp_path, max_turns=0)
    with pytest.raises(ValueError, match="turn budget"):
        instance.run("pilot")


def test_deepseek_file_tools_respect_selected_paths(tmp_path):
    inputs, work = tmp_path / "input", tmp_path / "work"
    inputs.mkdir()
    work.mkdir()
    instance = Runner("fixture", "https://api.deepseek.com", "unused", input_root=inputs, work=work)
    with pytest.raises(ValueError):
        instance.call_tool("write_file", {"path": str(inputs / "new"), "content": "denied"})
    (work / "escape").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="symlinks"):
        instance.call_tool("read_file", {"path": "escape"})
    with pytest.raises(ValueError, match="traversal"):
        instance.path("../outside")


def test_model_and_provider_credentials_are_adapter_specific():
    codex = CodexAdapter().invocation(Policy(model="chosen-codex-model"))
    deepseek = DeepSeekAdapter().invocation(Policy(backend="deepseek", model="chosen-deepseek-model"))
    assert codex.credentials == ("CODEX_API_KEY",) and "chosen-codex-model" in codex.args
    assert deepseek.credentials == ("DEEPSEEK_API_KEY",) and "chosen-deepseek-model" in deepseek.args
    assert "codex" not in deepseek.entrypoint and not deepseek.environment
    with pytest.raises(LoopError, match="unsupported"):
        adapter_for("unknown")


@pytest.mark.parametrize("backend", ["codex", "deepseek"])
def test_same_controller_contract_for_both_harnesses(enabled, executor, monkeypatch, backend):
    from sciharness_loop import controller as module
    set_policy(enabled, backend=backend, model="explicit-model")
    seen = []

    class Runtime:
        capabilities = REQUIRED_CAPABILITIES

        def execute(self, run_id, inputs, work, log, policy, invocation):
            seen.append(invocation)
            executor.execute(run_id, inputs, work, log, policy)

        def stop(self, run_id):
            executor.stop(run_id)

    monkeypatch.setattr(module, "make_executor", lambda policy, root: HarnessExecutor(
        adapter_for(policy.backend), Runtime(), root))
    instance = Controller(enabled)
    plan = instance.plan("pilot")
    step = instance.step(plan["id"], plan["review_hash"], "Researcher")
    assert step["state"] == "pending_review"
    assert instance.accept(step["id"], step["review_hash"], "Reviewer")["state"] == "accepted"
    assert all(item.backend == backend for item in seen)
    assert len(executor.stopped) == 2


def test_insufficient_runtime_capabilities_are_rejected():
    with pytest.raises(LoopError, match="capabilities"):
        HarnessExecutor(CodexAdapter(), SimpleNamespace(capabilities=frozenset({"stop"})))


@pytest.mark.parametrize("options", [
    {"backend": "unknown"}, {"runtime": "shell"}, {"backend": "deepseek"},
    {"base_url": "http://remote.example"}, {"base_url": "https://user:password@example.com"},
    {"_deadline_epoch": 1}, {"max_turns": False}, {"read_mounts": {"all": "."}},
    {"read_mounts": {"control": ".sci/loop"}}, {"read_mounts": {"../escape": "data/subset"}},
])
def test_backend_and_runtime_configuration_fails_closed(project, options):
    set_policy(project, **options)
    with pytest.raises(LoopError):
        load_policy(project)


def test_data_mounts_are_read_only_and_never_copy_large_data(project, executor, monkeypatch):
    folder = project / "data/subset"
    folder.mkdir()
    (folder / "reads.bin").write_bytes(b"x" * 300000)
    set_policy(project, read_mounts={"pilot": "data/subset"})
    instance = Controller(project, executor)
    plan = instance.plan("pilot")
    inputs = instance.base / "runs" / plan["id"] / "input"
    assert not (inputs / "project/data").exists()
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")
    runtime = DockerRuntime()
    runtime.mounts = {"pilot": folder}
    command = runtime.command("a" * 32, inputs, inputs, instance.policy,
                              CodexAdapter().invocation(instance.policy))
    assert "type=bind,src={},dst=/datasets/pilot,readonly".format(folder) in command


def test_deadline_and_pause_are_enforced_by_runtime_before_more_waiting(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")
    instance = DockerRuntime()
    with pytest.raises(LoopError, match="deadline"):
        instance.remaining(dataclasses.replace(Policy(), _deadline_epoch=1), 30)
    pause = tmp_path / "pause"
    pause.write_text("requested")
    with pytest.raises(LoopError, match="pause"):
        instance.wait_process(object(), b"prompt", dataclasses.replace(Policy(), _cancel_file=str(pause)))


def test_independent_watchdog_stops_container_at_deadline(tmp_path, monkeypatch):
    seen = []

    def docker(command, **kwargs):
        seen.append(command)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(subprocess, "run", docker)
    result = supervise("/usr/bin/docker", "a" * 64, 10, tmp_path / "ready", tmp_path / "cancel",
                       clock=lambda: 10)
    assert result == "deadline"
    assert seen[-1][-3:] == ["rm", "--force", "a" * 64]
    assert json.loads((tmp_path / "ready").read_text())["deadline"] == 10


def test_watchdog_retries_unconfirmed_stop_and_records_failure(tmp_path, monkeypatch, capsys):
    results = iter([SimpleNamespace(returncode=1, stderr=b"daemon down"),
                    SimpleNamespace(returncode=0, stderr=b"")])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: next(results))
    assert supervise("/usr/bin/docker", "a" * 64, 10, tmp_path / "ready", tmp_path / "cancel",
                     clock=lambda: 10, wait=lambda seconds: None) == "deadline"
    assert "deadline_stop_pending" in capsys.readouterr().out


def test_watchdog_inspect_timeout_does_not_drop_the_deadline(tmp_path, monkeypatch):
    times = iter([0, 10])

    def docker(command, **kwargs):
        if "inspect" in command:
            raise subprocess.TimeoutExpired("docker", 1)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(subprocess, "run", docker)
    assert supervise("/usr/bin/docker", "a" * 64, 10, tmp_path / "ready", tmp_path / "cancel",
                     clock=lambda: next(times), wait=lambda seconds: None) == "deadline"


def test_executor_factory_uses_configured_harness(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")
    assert make_executor(Policy(backend="deepseek", model="chosen")).adapter.__class__ is DeepSeekAdapter
