"""Harness-specific invocation, independent of the execution runtime."""
from __future__ import annotations

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


def adapter_for(name: str) -> HarnessAdapter:
    adapters = {"codex": CodexAdapter, "deepseek": DeepSeekAdapter}
    if name not in adapters:
        raise LoopError("unsupported harness adapter: " + str(name))
    return adapters[name]()
