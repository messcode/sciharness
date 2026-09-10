"""``sci validate``: structural checks without scientific judgment.

Validation checks that files exist, parse, carry required fields, and
reference each other consistently.  It never evaluates whether a hypothesis,
experiment, or decision is scientifically sound.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml

from ..project import (
    CONFIG_NAME,
    DIRECTORY_PATH_KEYS,
    FILE_PATH_KEYS,
    KINDS,
    REFERENCE_FIELDS,
    REQUIRED_PATH_KEYS,
    SUPPORTED_SCHEMA_VERSION,
    ProjectError,
    Record,
    find_project_root,
    id_number,
    load_config,
    load_records,
    relative_path,
)


def validate_project(root: Path) -> List[str]:
    """Return a list of human-readable structural problems (empty when OK)."""
    root = Path(root)
    problems: List[str] = []
    try:
        config = load_config(root)
    except ProjectError as exc:
        return [str(exc)]

    problems.extend(_validate_config(root, config))

    records_by_kind: Dict[str, List[Record]] = {}
    ids_by_kind: Dict[str, Set[str]] = {}
    for kind in KINDS:
        records, record_problems = load_records(root, kind)
        problems.extend(record_problems)
        records_by_kind[kind] = records
        ids_by_kind[kind] = {record.id for record in records}

    for kind in KINDS:
        for record in records_by_kind[kind]:
            rel = relative_path(root, record.path)
            for field, target_kind in REFERENCE_FIELDS.get(kind, ()):
                problems.extend(
                    _check_reference(
                        rel,
                        record.data.get(field),
                        field,
                        target_kind,
                        ids_by_kind[target_kind],
                    )
                )
            if kind == "decision":
                problems.extend(_check_supersedes(rel, record, ids_by_kind["decision"]))
            if kind == "experiment":
                problems.extend(_validate_experiment_config(root, record))

    problems.extend(_validate_registry(root))
    return problems


def _validate_config(root: Path, config: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if config.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        problems.append(
            "{}: schema_version must be {}".format(CONFIG_NAME, SUPPORTED_SCHEMA_VERSION)
        )
    project = config.get("project")
    if not isinstance(project, dict):
        problems.append("{}: project must be a mapping".format(CONFIG_NAME))
    else:
        name = project.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append("{}: project.name must be a non-empty string".format(CONFIG_NAME))
        if not _valid_date(project.get("created")):
            problems.append(
                "{}: project.created must be an ISO date (YYYY-MM-DD)".format(CONFIG_NAME)
            )
    paths = config.get("paths")
    if not isinstance(paths, dict):
        problems.append("{}: paths must be a mapping".format(CONFIG_NAME))
        return problems
    for key in REQUIRED_PATH_KEYS:
        if key not in paths:
            problems.append("{}: paths.{} is required".format(CONFIG_NAME, key))
            continue
        value = paths[key]
        if not isinstance(value, str) or not value.strip():
            problems.append(
                "{}: paths.{} must be a non-empty string".format(CONFIG_NAME, key)
            )
            continue
        target = root / value
        if not target.exists():
            problems.append(
                "{}: paths.{} does not exist: {}".format(CONFIG_NAME, key, value)
            )
        elif key in FILE_PATH_KEYS and not target.is_file():
            problems.append(
                "{}: paths.{} must be a file: {}".format(CONFIG_NAME, key, value)
            )
        elif key in DIRECTORY_PATH_KEYS and not target.is_dir():
            problems.append(
                "{}: paths.{} must be a directory: {}".format(CONFIG_NAME, key, value)
            )
    return problems


def _valid_date(value: Any) -> bool:
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.date):
        return True
    if isinstance(value, str) and value.strip():
        try:
            datetime.date.fromisoformat(value.strip())
        except ValueError:
            return False
        return True
    return False


def _check_reference(
    rel: str, value: Any, field: str, target_kind: str, existing: Set[str]
) -> List[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return []
    if not isinstance(value, str):
        return ["{}: {} must be a string ID".format(rel, field)]
    if value not in existing:
        return [
            "{}: {} {!r} not found among {} records".format(
                rel, field, value, target_kind
            )
        ]
    return []


def _check_supersedes(rel: str, record: Record, decisions: Set[str]) -> List[str]:
    supersedes = record.data.get("supersedes")
    if supersedes is None or (isinstance(supersedes, str) and not supersedes.strip()):
        return []
    if not isinstance(supersedes, str):
        return ["{}: supersedes must be a string ID".format(rel)]
    if supersedes not in decisions:
        return [
            "{}: supersedes {!r} not found among decision records".format(rel, supersedes)
        ]
    if id_number(supersedes) >= id_number(record.id):
        return [
            "{}: supersedes {!r} must refer to an earlier decision".format(
                rel, supersedes
            )
        ]
    return []


def _validate_experiment_config(root: Path, record: Record) -> List[str]:
    problems: List[str] = []
    config_path = record.path.parent / "config.yaml"
    rel = relative_path(root, config_path)
    if not config_path.is_file():
        return ["{}: missing experiment config".format(rel)]
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return ["{}: invalid YAML: {}".format(rel, exc)]
    if not isinstance(data, dict):
        return ["{}: must contain a YAML mapping".format(rel)]
    for field in ("id", "title"):
        if data.get(field) != record.data.get(field):
            problems.append(
                "{}: {} does not match README.md front matter".format(rel, field)
            )
    return problems


def _validate_registry(root: Path) -> List[str]:
    path = root / "data" / "registry.yaml"
    if not path.is_file():
        return []
    rel = relative_path(root, path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return ["{}: invalid YAML: {}".format(rel, exc)]
    if not isinstance(data, dict):
        return ["{}: must contain a YAML mapping".format(rel)]
    datasets = data.get("datasets")
    if datasets is not None and not isinstance(datasets, list):
        return ["{}: datasets must be a list".format(rel)]
    return []


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    problems = validate_project(root)
    if problems:
        print("Validation failed: {} problem(s) in {}".format(len(problems), root))
        for problem in problems:
            print("  - {}".format(problem))
        return 1
    print("Validation OK: {}".format(root))
    print(
        "  {} parses; expected paths exist; IDs are unique; references resolve.".format(
            CONFIG_NAME
        )
    )
    return 0
