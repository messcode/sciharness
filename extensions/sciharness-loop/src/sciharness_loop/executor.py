"""Replaceable executor contract and a Docker-isolated Codex implementation.

The live project, controller state, host home, and Docker socket are NEVER
mounted in the container. A fresh, bounded input copy is the only read mount.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from .policy import Policy
from .storage import LoopError, write_json


class Executor(Protocol):
    """A bounded action runner.

    ``execute`` must not leave a live executor behind: the caller invokes
    ``stop`` after a normal return and after a failure, and treats an
    unconfirmed stop as ``recovery_required``.
    """

    def execute(self, run_id: str, inputs: Path, work: Path, log: Path,
                policy: Policy) -> None: ...

    def stop(self, run_id: str) -> None: ...


class CodexExecutor:
    """Local Docker daemon is trusted; no unsandboxed fallback is permitted."""

    def __init__(self):
        binary = shutil.which("docker")
        if not binary:
            raise LoopError("Docker is required for isolated execution; no host fallback")
        self.docker = [binary, "--host", "unix:///var/run/docker.sock"]

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

    def command(self, run_id, inputs, work, policy):
        if not policy.image:
            raise LoopError("policy.image must name a trusted, locally built Codex image")
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
            "--env", "HOME=/tmp/home", "--env", "CODEX_HOME=/tmp/codex",
            "--env", "CODEX_API_KEY", "--workdir", "/work",
            "--mount", "type=bind,src={},dst=/input,readonly".format(inputs),
            "--mount", "type=bind,src={},dst=/work".format(work),
            "--entrypoint", "codex", policy.image,
            "--ask-for-approval", "never", "exec", "--skip-git-repo-check",
            # Docker is the outer isolation boundary. Nested OS sandboxes are
            # not portable across Docker hosts. No host filesystem is exposed.
            "--sandbox", "danger-full-access", "--json",
            "--output-schema", "/input/schema.json",
            "--output-last-message", "/work/result.json", "-",
        ]
        return command

    def start_command(self, container_id):
        return self.docker + ["start", "--attach", "--interactive", container_id]

    def execute(self, run_id, inputs, work, log, policy):
        if not os.environ.get("CODEX_API_KEY"):
            raise LoopError("set CODEX_API_KEY for this invocation (never store it in policy)")
        prompt = (inputs / "prompt.txt").read_bytes()
        # Pass only a narrow environment to Docker; no inherited host auth,
        # Docker config, proxy, or arbitrary service credentials. The container
        # itself receives only the explicit --env values below.
        env = {"PATH": os.environ.get("PATH", ""), "CODEX_API_KEY": os.environ["CODEX_API_KEY"]}
        command = self.command(run_id, inputs, work, policy)
        inspected = subprocess.run(self.docker + ["image", "inspect", "--format", "{{.Id}}",
                                                 policy.image],
                                   capture_output=True, text=True, encoding="utf-8",
                                   timeout=30)
        if inspected.returncode or not inspected.stdout.strip().startswith("sha256:"):
            raise LoopError("trusted Codex image is not available locally")
        # Execute the exact inspected image, even if its mutable tag moves later.
        image_id = inspected.stdout.strip()
        command[command.index("--entrypoint") + 2] = image_id
        metadata = {
            "backend": "docker-codex", "image": image_id, "command": command,
            "credential_env": "CODEX_API_KEY", "credential_value": "not recorded",
        }
        write_json(log.with_suffix(".json"), metadata)
        created = subprocess.run(command, capture_output=True, text=True,
                                 encoding="utf-8", timeout=60, env=env)
        if created.returncode:
            raise LoopError("cannot create executor container: " + (
                created.stderr.strip() or "Docker exited {}".format(created.returncode)))
        container_id = created.stdout.strip().splitlines()[-1] if created.stdout.strip() else ""
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise LoopError("unexpected container ID from docker create")
        start = self.start_command(container_id)
        metadata.update({"container_id": container_id, "start_command": start})
        write_json(log.with_suffix(".json"), metadata)
        with log.open("wb") as stream:
            process = subprocess.Popen(start, stdin=subprocess.PIPE, stdout=stream,
                                       stderr=subprocess.STDOUT, env=env)
            try:
                process.communicate(prompt, timeout=policy.timeout_seconds)
                if process.returncode:
                    raise LoopError("Codex executor failed (exit {}); inspect executor.log".format(
                        process.returncode))
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                process.kill()
                process.communicate()
                raise LoopError("execution interrupted or timed out; partial evidence retained")
