"""Explicit opt-in policy; unsupported permissions fail closed."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml
import re
from urllib.parse import urlsplit

from .storage import LoopError, digest, safe_path


@dataclass
class Policy:
    mode: str = "record_only"
    image: str = ""
    read_files: list = field(default_factory=lambda: ["docs/CHARTER.md", "docs/STATE.md"])
    timeout_seconds: int = 600
    max_input_bytes: int = 256_000
    max_output_bytes: int = 10_000_000
    max_files: int = 100
    memory_mb: int = 2048
    cpus: int = 2
    network: str = "bridge"
    backend: str = "codex"
    runtime: str = "docker"
    model: str = ""
    base_url: str = ""
    max_turns: int = 24
    max_context_bytes: int = 1_000_000
    max_completion_tokens: int = 4096
    read_mounts: dict = field(default_factory=dict)
    # Controller-owned execution controls, never accepted from policy.yaml.
    _deadline_epoch: float = 0
    _cancel_file: str = ""

    @property
    def fingerprint(self):
        values = asdict(self)
        defaults = asdict(Policy())
        new = {"backend", "runtime", "model", "base_url", "max_turns",
               "max_context_bytes", "max_completion_tokens", "read_mounts"}
        # Keep v0.1 approvals valid when all new options retain their defaults.
        return digest({k: v for k, v in values.items() if not k.startswith("_")
                       and (k not in new or v != defaults[k])})


def dataset_mounts(root: Path, policy: Policy) -> dict:
    result = {}
    for alias, relative in policy.read_mounts.items():
        if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", alias):
            raise LoopError("invalid dataset mount alias")
        source = safe_path(root, relative)
        parts = source.relative_to(root).parts
        if len(parts) < 2 or parts[0] != "data" or any(p in (".git", ".sci") for p in parts):
            raise LoopError("dataset mounts must select paths beneath project data/")
        if not (source.is_dir() or source.is_file()):
            raise LoopError("dataset mount must exist: " + relative)
        result[alias] = source
    return result


def load_policy(root: Path) -> Policy:
    path = safe_path(root, ".sci/loop/policy.yaml")
    if not path.exists():
        return Policy()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LoopError("invalid policy YAML") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise LoopError("policy requires schema_version: 1")
    allowed = {k for k in Policy.__dataclass_fields__ if not k.startswith("_")} | {"schema_version"}
    if set(raw) - allowed:
        raise LoopError("unknown policy keys: {}".format(sorted(set(raw) - allowed)))
    policy = Policy(**{k: v for k, v in raw.items() if k != "schema_version"})
    if policy.mode not in ("record_only", "suggest", "step", "guarded_auto"):
        raise LoopError("mode must be record_only, suggest, step, or guarded_auto")
    if policy.backend not in ("codex", "deepseek", "dsh") or policy.runtime != "docker":
        raise LoopError("unsupported backend/runtime; supported: codex/deepseek/dsh with docker")
    if not isinstance(policy.model, str) or not isinstance(policy.base_url, str):
        raise LoopError("model and base_url must be strings")
    if policy.backend == "deepseek" and not policy.model.strip():
        raise LoopError("DeepSeek requires an explicitly selected model")
    if policy.base_url:
        try:
            url = urlsplit(policy.base_url)
            invalid = (url.scheme not in ("https", "http") or not url.hostname
                       or url.username or url.password or url.query or url.fragment
                       or (url.scheme == "http"
                           and url.hostname not in ("localhost", "127.0.0.1", "::1")))
        except ValueError as exc:
            raise LoopError("invalid base_url") from exc
        if invalid:
            raise LoopError("base_url must use HTTPS (HTTP allowed only for loopback testing)")
    if policy.backend == "codex" and policy.base_url:
        raise LoopError("base_url is a DeepSeek/DSH adapter option")
    if not isinstance(policy.read_mounts, dict):
        raise LoopError("read_mounts must map aliases to project data paths")
    dataset_mounts(root, policy)
    if policy.network not in ("bridge", "none"):
        raise LoopError("network must be bridge or none; host networking is forbidden")
    if not isinstance(policy.image, str) or policy.image.startswith("-"):
        raise LoopError("invalid executor image")
    if not isinstance(policy.read_files, list) or not all(
        isinstance(p, str) for p in policy.read_files
    ):
        raise LoopError("read_files must be an explicit list of files")
    for relative in policy.read_files:
        path = safe_path(root, relative)
        if any(part in (".git", ".sci") for part in path.relative_to(root).parts):
            raise LoopError("Git metadata and loop state cannot be agent inputs")
    limits = {
        "timeout_seconds": 86400, "max_input_bytes": 10_000_000,
        "max_output_bytes": 100_000_000, "max_files": 10000,
        "memory_mb": 65536, "cpus": 32,
        "max_turns": 1000, "max_context_bytes": 10_000_000,
        "max_completion_tokens": 32768,
    }
    for name, upper in limits.items():
        value = getattr(policy, name)
        if type(value) is not int or not 1 <= value <= upper:
            raise LoopError("{} must be an integer in [1, {}]".format(name, upper))
    return policy
