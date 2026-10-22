"""Docker lifecycle and enforced limits; independent of model or harness."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
import sys
import time

from .adapters import Invocation
from typing import Protocol
from .storage import LoopError, write_json


REQUIRED_CAPABILITIES = frozenset({"isolation", "stop", "deadline", "readonly_inputs"})


class ExecutionRuntime(Protocol):
    capabilities: frozenset

    def execute(self, run_id, inputs, work, log, policy, invocation): ...

    def stop(self, run_id): ...


class DockerRuntime:
    """Local Docker daemon is trusted; no unsandboxed fallback is permitted."""

    capabilities = REQUIRED_CAPABILITIES

    def __init__(self):
        binary = shutil.which("docker")
        if not binary:
            raise LoopError("Docker is required for isolated execution; no host fallback")
        self.docker = [binary, "--host", "unix:///var/run/docker.sock"]
        self.watchdogs = {}

    @staticmethod
    def name(run_id):
        return "sci-loop-" + run_id

    def stop(self, run_id):
        # A missing container is already stopped; a daemon failure is not.
        # --rm can also race this cleanup while the container is being removed.
        result = subprocess.run(
            self.docker + ["rm", "--force", self.name(run_id)],
            capture_output=True, timeout=30,
        )
        stderr = result.stderr
        tolerated = (b"No such container", b"is already in progress")
        if result.returncode and not any(marker in stderr for marker in tolerated):
            raise LoopError("cannot confirm executor stopped: " + stderr.decode(errors="replace"))
        if result.returncode and b"is already in progress" in stderr:
            until = time.monotonic() + 3
            while time.monotonic() < until:
                inspected = subprocess.run(self.docker + ["inspect", "--format", "{{.State.Running}}",
                                                          self.name(run_id)], capture_output=True, timeout=10)
                if ((not inspected.returncode and inspected.stdout.strip() == b"false")
                        or (inspected.returncode and b"No such" in inspected.stderr)):
                    break
                time.sleep(0.05)
            else:
                raise LoopError("container removal pending; cannot confirm executor stopped")
        if run_id in self.watchdogs:
            process, cancel = self.watchdogs.pop(run_id)
            cancel.write_text("stopped", encoding="utf-8")
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    @staticmethod
    def remaining(policy, maximum):
        if policy._deadline_epoch:
            maximum = min(maximum, policy._deadline_epoch - time.time())
        if maximum <= 0:
            raise LoopError("execution deadline reached before launch")
        return maximum

    def resolve_image(self, policy, timeout=30):
        """Return the immutable local image ID for the policy image/tag."""
        if not policy.image:
            raise LoopError("policy.image must name a trusted, locally built harness image")
        inspected = subprocess.run(
            self.docker + ["image", "inspect", "--format", "{{.Id}}", policy.image],
            capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        if inspected.returncode or not inspected.stdout.strip().startswith("sha256:"):
            raise LoopError("trusted harness image is not available locally")
        return inspected.stdout.strip()

    def arm_watchdog(self, run_id, container_id, log, policy):
        """A separate supervisor still stops the container if the controller dies."""
        ready, cancel = log.with_name("watchdog-ready.json"), log.with_name("watchdog-cancel")
        ready.unlink(missing_ok=True)
        cancel.unlink(missing_ok=True)
        command = [sys.executable, str(Path(__file__).with_name("watchdog.py")),
                   "--docker", self.docker[0], "--container", container_id,
                   "--deadline", str(policy._deadline_epoch), "--ready", str(ready),
                   "--cancel", str(cancel)]
        with log.with_name("watchdog.log").open("wb") as stream:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True,
                                       env={"PATH": os.environ.get("PATH", "")})
        self.watchdogs[run_id] = (process, cancel)
        until = time.monotonic() + self.remaining(policy, 3)
        while not ready.exists():
            if process.poll() is not None or time.monotonic() >= until:
                raise LoopError("deadline watchdog failed to arm; harness was not started")
            time.sleep(0.02)
        if process.poll() is not None:
            raise LoopError("deadline watchdog exited after arming; harness was not started")
        self.remaining(policy, 1)

    def wait_process(self, process, prompt, policy):
        until = time.monotonic() + policy.timeout_seconds
        pending = prompt
        while True:
            if policy._cancel_file and Path(policy._cancel_file).exists():
                raise LoopError("pause requested")
            remaining = min(until - time.monotonic(), self.remaining(policy, 1))
            if remaining <= 0:
                raise subprocess.TimeoutExpired("harness", policy.timeout_seconds)
            try:
                process.communicate(pending, timeout=min(1, remaining))
                return
            except subprocess.TimeoutExpired:
                pending = None

    def command(self, run_id, inputs, work, policy, invocation: Invocation):
        if not policy.image:
            raise LoopError("policy.image must name a trusted, locally built harness image")
        for path in (inputs, work):
            if "," in str(path):
                raise LoopError("Docker mount paths cannot contain commas")
        command = self.docker + [
            # Creating and starting are separate operations: a container may
            # exist without ever running, so recovery can remove it before any
            # start is issued.
            "create", "--rm", "--pull=never", "--name", self.name(run_id), "-i",
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user", "{}:{}".format(os.getuid(), os.getgid()),
            "--pids-limit=128", "--memory={}m".format(policy.memory_mb),
            "--cpus={}".format(policy.cpus), "--network=" + policy.network,
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m,mode=1777",
            "--env", "HOME=/tmp/home", "--workdir", "/work",
            "--mount", "type=bind,src={},dst=/input,readonly".format(inputs),
            "--mount", "type=bind,src={},dst=/work".format(work),
        ]
        for value in invocation.environment + invocation.credentials:
            command.extend(["--env", value])
        for alias, source in getattr(self, "mounts", {}).items():
            if "," in str(source):
                raise LoopError("Docker mount paths cannot contain commas")
            command.extend(["--mount", "type=bind,src={},dst=/datasets/{},readonly".format(
                source, alias)])
        command.extend(["--entrypoint", invocation.entrypoint, policy.image, *invocation.args])
        return command

    def start_command(self, container_id):
        return self.docker + ["start", "--attach", "--interactive", container_id]

    def execute(self, run_id, inputs, work, log, policy, invocation):
        for credential in invocation.credentials:
            if not os.environ.get(credential):
                raise LoopError("set {} for this invocation (never store it in policy)".format(credential))
        prompt = (inputs / "prompt.txt").read_bytes()
        # Pass only a narrow environment to Docker; no inherited host auth,
        # Docker config, proxy, or arbitrary service credentials. The container
        # itself receives only the explicit --env values below.
        env = {"PATH": os.environ.get("PATH", ""), **{key: os.environ[key] for key in invocation.credentials}}
        command = self.command(run_id, inputs, work, policy, invocation)
        # Execute the exact inspected image, even if its mutable tag moves later.
        image_id = self.resolve_image(policy, self.remaining(policy, 30))
        command[command.index("--entrypoint") + 2] = image_id
        metadata = {
            "backend": "docker-" + invocation.backend, "image": image_id, "command": command,
            "credential_env": list(invocation.credentials), "credential_value": "not recorded",
        }
        write_json(log.with_suffix(".json"), metadata)
        created = subprocess.run(command, capture_output=True, text=True,
                                 encoding="utf-8", timeout=self.remaining(policy, 60), env=env)
        if created.returncode:
            raise LoopError("cannot create executor container: " + (
                created.stderr.strip() or "Docker exited {}".format(created.returncode)))
        container_id = created.stdout.strip().splitlines()[-1] if created.stdout.strip() else ""
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise LoopError("unexpected container ID from docker create")
        start = self.start_command(container_id)
        metadata.update({"container_id": container_id, "start_command": start})
        write_json(log.with_suffix(".json"), metadata)
        if policy._deadline_epoch:
            self.arm_watchdog(run_id, container_id, log, policy)
        with log.open("wb") as stream:
            process = subprocess.Popen(start, stdin=subprocess.PIPE, stdout=stream,
                                       stderr=subprocess.STDOUT, env=env)
            try:
                if policy._deadline_epoch or policy._cancel_file:
                    self.wait_process(process, prompt, policy)
                else:
                    process.communicate(prompt, timeout=policy.timeout_seconds)
                if process.returncode:
                    raise LoopError("Harness executor failed (exit {}); inspect executor.log".format(
                        process.returncode))
            except (subprocess.TimeoutExpired, KeyboardInterrupt, LoopError):
                process.kill()
                process.communicate()
                raise LoopError("execution interrupted or timed out; partial evidence retained")
