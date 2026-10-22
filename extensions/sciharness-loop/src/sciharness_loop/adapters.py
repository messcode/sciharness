"""Harness-specific invocation, independent of the execution runtime."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .policy import Policy
from .storage import LoopError


@dataclass(frozen=True)
class Invocation:
    backend: str
    entrypoint: str
    args: tuple[str, ...]
    environment: tuple[str, ...]
    credentials: tuple[str, ...]


class HarnessAdapter(Protocol):
    def invocation(self, policy: Policy) -> Invocation: ...


class CodexAdapter:
    def invocation(self, policy):
        args = ["--ask-for-approval", "never", "exec", "--skip-git-repo-check",
                "--sandbox", "danger-full-access", "--json",
                "--output-schema", "/input/schema.json",
                "--output-last-message", "/work/result.json"]
        if policy.model:
            args.extend(["--model", policy.model])
        return Invocation("codex", "codex", tuple(args + ["-"]),
                          ("CODEX_HOME=/tmp/codex",), ("CODEX_API_KEY",))


class DeepSeekAdapter:
    def invocation(self, policy):
        if not policy.model.strip():
            raise LoopError("DeepSeek requires an explicitly selected model")
        return Invocation("deepseek", "python3", (
            "/opt/sciharness/deepseek_runner.py", "--model", policy.model,
            "--base-url", policy.base_url or "https://api.deepseek.com",
            "--max-turns", str(policy.max_turns),
            "--context-bytes", str(policy.max_context_bytes),
            "--completion-tokens", str(policy.max_completion_tokens),
        ), (), ("DEEPSEEK_API_KEY",))


class DshAdapter:
    """Use DSH's headless one-shot bundle inside the Docker boundary.

    The wrapper handles DSH-specific details: profile/home setup, non-interactive
    permissions, the model patch, the minimal tool surface, the NDJSON stream,
    and mapping the final answer to /work/result.json.
    """
    def invocation(self, policy):
        args = ["/opt/sciharness/dsh_runner.py"]
        if policy.model:
            args += ["--model", policy.model]
        if policy.base_url:
            args += ["--base-url", policy.base_url]
        mcp_servers = (policy.mcp or {}).get("servers", [])
        if mcp_servers:
            args += ["--mcp-json", json.dumps(policy.mcp, sort_keys=True)]
        credentials = ["DEEPSEEK_API_KEY"]
        for server in mcp_servers:
            for name in server.get("env", []):
                if name not in credentials:
                    credentials.append(name)
        return Invocation("dsh", "python3", tuple(args),
                          ("DSH_HOME=/tmp/dsh-home",
                           "DSH_PERMISSION_MODE=danger-full-access"),
                          tuple(credentials))


def adapter_for(name: str) -> HarnessAdapter:
    adapters = {"codex": CodexAdapter, "deepseek": DeepSeekAdapter, "dsh": DshAdapter}
    if name not in adapters:
        raise LoopError("unsupported harness adapter: " + str(name))
    return adapters[name]()
