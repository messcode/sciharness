"""Explicit opt-in policy; unsupported permissions fail closed."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

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

    @property
    def fingerprint(self):
        return digest(asdict(self))


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
    allowed = set(Policy.__dataclass_fields__) | {"schema_version"}
    if set(raw) - allowed:
        raise LoopError("unknown policy keys: {}".format(sorted(set(raw) - allowed)))
    policy = Policy(**{k: v for k, v in raw.items() if k != "schema_version"})
    if policy.mode not in ("record_only", "suggest", "step"):
        raise LoopError("mode must be record_only, suggest, or step")
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
    }
    for name, upper in limits.items():
        value = getattr(policy, name)
        if type(value) is not int or not 1 <= value <= upper:
            raise LoopError("{} must be an integer in [1, {}]".format(name, upper))
    return policy
