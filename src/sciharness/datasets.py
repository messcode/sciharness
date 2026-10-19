"""Dataset registry loading and structural validation."""
from __future__ import annotations

import datetime
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from .project import ProjectError, resolve_project_path

REGISTRY_PATH = Path("data") / "registry.yaml"
DATASET_ID_RE = re.compile(r"^DS\d{3,}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def registry_path(root: Path) -> Path:
    return Path(root) / REGISTRY_PATH


def load_registry(root: Path) -> Optional[Dict[str, Any]]:
    path = registry_path(root)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProjectError("cannot parse {}: {}".format(REGISTRY_PATH, exc)) from exc
    if not isinstance(data, dict):
        raise ProjectError("{} must contain a YAML mapping".format(REGISTRY_PATH))
    return data


def is_dataset_id(value: Any) -> bool:
    return isinstance(value, str) and DATASET_ID_RE.match(value.strip()) is not None


def dataset_ids(root: Path) -> Set[str]:
    """IDs declared in the registry; malformed registries yield an empty set."""
    try:
        data = load_registry(root)
    except ProjectError:
        return set()
    if data is None:
        return set()
    entries = data.get("datasets")
    if not isinstance(entries, list):
        return set()
    ids: Set[str] = set()
    for entry in entries:
        if isinstance(entry, dict):
            identifier = entry.get("id")
            if isinstance(identifier, str):
                ids.add(identifier.strip())
    return ids


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_date(value: Any) -> bool:
    if isinstance(value, datetime.datetime):
        return True
    if isinstance(value, datetime.date):
        return True
    if isinstance(value, str) and value.strip():
        try:
            datetime.date.fromisoformat(value.strip())
        except ValueError:
            return False
        return True
    return False


def dataset_problems(root: Path, verify_hashes: bool = False) -> List[str]:
    """Return structural problems in ``data/registry.yaml`` (empty when absent)."""
    root = Path(root)
    try:
        data = load_registry(root)
    except ProjectError as exc:
        return [str(exc)]
    if data is None:
        return []

    rel = REGISTRY_PATH.as_posix()
    problems: List[str] = []
    if data.get("schema_version") != 1:
        problems.append("{}: schema_version must be 1".format(rel))
    entries = data.get("datasets")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        return problems + ["{}: datasets must be a list".format(rel)]

    seen: Set[str] = set()
    for index, entry in enumerate(entries):
        label = "{}: datasets[{}]".format(rel, index)
        if not isinstance(entry, dict):
            problems.append("{} must be a mapping".format(label))
            continue
        identifier = entry.get("id")
        normalized_id = identifier.strip() if isinstance(identifier, str) else ""
        if not normalized_id:
            problems.append("{}.id must be a non-empty string".format(label))
        elif not is_dataset_id(normalized_id):
            problems.append(
                "{}.id {!r} must look like DS###".format(label, identifier)
            )
        elif normalized_id in seen:
            problems.append(
                "{}: duplicate dataset id {!r}".format(label, normalized_id)
            )
        else:
            seen.add(normalized_id)

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append("{}.name must be a non-empty string".format(label))

        storage = entry.get("storage", "local")
        if storage not in ("local", "external"):
            problems.append(
                "{}.storage {!r} must be 'local' or 'external'".format(
                    label, storage
                )
            )
            storage = "local"

        resolved = None
        if storage == "local":
            path_value = entry.get("path")
            if not isinstance(path_value, str) or not path_value.strip():
                problems.append(
                    "{}.path is required for a local dataset".format(label)
                )
            else:
                try:
                    resolved = resolve_project_path(
                        root, path_value, "{}.path".format(label)
                    )
                except ProjectError as exc:
                    problems.append(str(exc))
                else:
                    if not resolved.is_file():
                        problems.append(
                            "{}.path does not exist: {!r}".format(
                                label, path_value
                            )
                        )
        else:
            uri = entry.get("uri")
            if not isinstance(uri, str) or not uri.strip():
                problems.append(
                    "{}.uri is required for an external dataset".format(label)
                )

        digest = entry.get("sha256")
        if digest is not None:
            if not isinstance(digest, str) or not _SHA256_RE.match(digest.strip()):
                problems.append(
                    "{}.sha256 must be a 64-character hex digest".format(label)
                )
            elif verify_hashes and resolved is not None and resolved.is_file():
                actual = sha256_file(resolved)
                if actual.lower() != digest.strip().lower():
                    problems.append(
                        "{}.sha256 does not match {}: expected {}, got {}".format(
                            label, resolved, digest.strip().lower(), actual
                        )
                    )

        acquired = entry.get("acquired", entry.get("created"))
        if acquired is not None and not _valid_date(acquired):
            problems.append(
                "{}.acquired must be an ISO date (YYYY-MM-DD)".format(label)
            )
    return problems
