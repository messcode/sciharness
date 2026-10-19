"""``sci validate``: structural checks without scientific judgment.

Validation checks that files exist, parse, carry required fields, and
reference each other consistently.  It never evaluates whether a hypothesis,
experiment, or decision is scientifically sound.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

from ..datasets import (
    dataset_ids,
    dataset_problems,
    is_dataset_id,
)
from ..output import (
    EXIT_OK,
    EXIT_VALIDATION,
    diagnostics_from_problems,
    emit,
    envelope,
    project_info,
)
from ..preregistration import preregistration_hash
from ..project import (
    CONFIG_NAME,
    DIRECTORY_PATH_KEYS,
    EVIDENCE_KINDS,
    FILE_PATH_KEYS,
    ID_PREFIX,
    KINDS,
    MOTIVATED_BY_KINDS,
    REFERENCE_FIELDS,
    REQUIRED_PATH_KEYS,
    SUPPORTED_SCHEMA_VERSION,
    ProjectError,
    Record,
    find_project_root,
    id_matches_kind,
    id_number,
    load_config,
    load_records,
    relative_path,
    resolve_project_path,
)


def validate_project(root: Path, verify_hashes: bool = False) -> List[str]:
    """Return a list of human-readable structural problems (empty when OK)."""
    root = Path(root)
    problems: List[str] = []
    try:
        config = load_config(root)
    except ProjectError as exc:
        return [str(exc)]

    problems.extend(_validate_config(root, config))
    problems.extend(dataset_problems(root, verify_hashes=verify_hashes))
    declared_datasets = dataset_ids(root)

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
                problems.extend(
                    _check_id_list(
                        rel,
                        record.data.get("evidence"),
                        "evidence",
                        EVIDENCE_KINDS,
                        ids_by_kind,
                    )
                )
            if kind in ("exploration", "experiment"):
                problems.extend(
                    _check_id_list(
                        rel,
                        record.data.get("motivated_by"),
                        "motivated_by",
                        MOTIVATED_BY_KINDS,
                        ids_by_kind,
                    )
                )
            if kind == "experiment":
                problems.extend(
                    _check_dataset_list(
                        rel,
                        record.data.get("datasets"),
                        "datasets",
                        declared_datasets,
                    )
                )
                problems.extend(_validate_experiment_config(root, record))
                problems.extend(
                    _validate_run_config(root, record, declared_datasets)
                )
    return problems


def _validate_config(root: Path, config: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    version = config.get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        if version is None:
            problems.append(
                "{}: schema_version is missing (run `sci migrate`)".format(
                    CONFIG_NAME
                )
            )
        elif isinstance(version, int) and version < SUPPORTED_SCHEMA_VERSION:
            problems.append(
                "{}: schema_version {} is older than {} (run `sci migrate`)"
                .format(CONFIG_NAME, version, SUPPORTED_SCHEMA_VERSION)
            )
        else:
            problems.append(
                "{}: schema_version must be {}".format(
                    CONFIG_NAME, SUPPORTED_SCHEMA_VERSION
                )
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
        try:
            target = resolve_project_path(
                root, value, "{}: paths.{}".format(CONFIG_NAME, key)
            )
        except ProjectError as exc:
            problems.append(str(exc))
            continue
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


def _check_id_list(
    rel: str,
    value: Any,
    field: str,
    allowed_kinds: Tuple[str, ...],
    ids_by_kind: Dict[str, Set[str]],
) -> List[str]:
    """Structurally validate an optional list of provenance IDs.

    Checks list shape, non-empty string elements, allowed ID types, existence,
    and duplicates. It never judges the scientific relationship itself.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return ["{}: {} must be a YAML list of IDs".format(rel, field)]
    allowed = " or ".join("{}###".format(ID_PREFIX[kind]) for kind in allowed_kinds)
    problems: List[str] = []
    seen: Set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            problems.append(
                "{}: {}[{}] must be a non-empty string ID".format(rel, field, index)
            )
            continue
        item = item.strip()
        if item in seen:
            problems.append(
                "{}: {} contains duplicate ID {!r}".format(rel, field, item)
            )
            continue
        seen.add(item)
        matched = [kind for kind in allowed_kinds if id_matches_kind(item, kind)]
        if not matched:
            problems.append(
                "{}: {} {!r} must be an ID of type {}".format(rel, field, item, allowed)
            )
            continue
        if not any(item in ids_by_kind[kind] for kind in matched):
            targets = " or ".join("{} records".format(kind) for kind in matched)
            problems.append(
                "{}: {} {!r} not found among {}".format(rel, field, item, targets)
            )
    return problems


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
    schema_version = data.get("schema_version")
    if schema_version is not None and schema_version != 1:
        problems.append("{}: schema_version must be 1".format(rel))
    # New configs point at the record with `record:` and do not duplicate
    # identity/status/provenance.  Legacy configs that still carry `id` and/or
    # `title` are accepted, but must agree with README.md.
    declared_record = data.get("record")
    legacy_id = data.get("id")
    if declared_record is None and legacy_id is None:
        problems.append(
            "{}: must declare the owning record as `record: EXP###`".format(rel)
        )
    elif declared_record is not None and declared_record != record.id:
        problems.append(
            "{}: record does not match README.md front matter".format(rel)
        )
    if legacy_id is not None and legacy_id != record.id:
        problems.append(
            "{}: id does not match README.md front matter".format(rel)
        )
    if "title" in data and data.get("title") != record.data.get("title"):
        problems.append(
            "{}: title does not match README.md front matter".format(rel)
        )
    if "parameters" in data and not isinstance(data["parameters"], dict):
        problems.append("{}: parameters must be a mapping".format(rel))
    return problems


def _check_dataset_list(
    rel: str, value: Any, field: str, declared: Set[str]
) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return ["{}: {} must be a YAML list of dataset IDs".format(rel, field)]
    problems: List[str] = []
    seen: Set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            problems.append(
                "{}: {}[{}] must be a non-empty string".format(rel, field, index)
            )
            continue
        item = item.strip()
        if not is_dataset_id(item):
            problems.append(
                "{}: {}[{}] {!r} must look like DS###".format(
                    rel, field, index, item
                )
            )
            continue
        if item in seen:
            problems.append(
                "{}: {} contains duplicate dataset ID {!r}".format(
                    rel, field, item
                )
            )
            continue
        seen.add(item)
        if item not in declared:
            problems.append(
                "{}: {} {!r} is not declared in data/registry.yaml".format(
                    rel, field, item
                )
            )
    return problems


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def _validate_run_config(
    root: Path, record: Record, declared_datasets: Set[str]
) -> List[str]:
    path = record.path.parent / "run.yaml"
    if not path.is_file():
        return []
    rel = relative_path(root, path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return ["{}: invalid YAML: {}".format(rel, exc)]
    if not isinstance(data, dict):
        return ["{}: must contain a YAML mapping".format(rel)]

    problems: List[str] = []
    if data.get("schema_version") != 1:
        problems.append("{}: schema_version must be 1".format(rel))
    if data.get("record") != record.id:
        problems.append(
            "{}: record {!r} does not match {}".format(
                rel, data.get("record"), record.id
            )
        )

    command = data.get("command")
    if command is not None:
        if isinstance(command, str):
            if not command.strip():
                problems.append("{}: command must not be empty".format(rel))
        elif isinstance(command, list):
            if not command or any(
                not isinstance(item, str) or not item.strip()
                for item in command
            ):
                problems.append(
                    "{}: command must be a non-empty string or list of strings"
                    .format(rel)
                )
        else:
            problems.append(
                "{}: command must be a string or list of strings".format(rel)
            )

    if "code_commit" in data and not isinstance(data["code_commit"], str):
        problems.append("{}: code_commit must be a string".format(rel))
    for field in ("started_at", "finished_at"):
        if field in data and not _valid_timestamp(data[field]):
            problems.append(
                "{}: {} must be an ISO timestamp".format(rel, field)
            )
    for field in ("environment", "seeds"):
        if field in data and not isinstance(data[field], dict):
            problems.append("{}: {} must be a mapping".format(rel, field))
    problems.extend(
        _check_dataset_list(rel, data.get("datasets"), "datasets", declared_datasets)
    )

    manifest_value = data.get("outputs_manifest")
    if manifest_value is not None:
        if not isinstance(manifest_value, str) or not manifest_value.strip():
            problems.append(
                "{}: outputs_manifest must be a non-empty string".format(rel)
            )
        else:
            try:
                resolve_project_path(
                    root, manifest_value, "{}: outputs_manifest".format(rel)
                )
            except ProjectError as exc:
                problems.append(str(exc))

    digest = data.get("preregistration_sha256")
    if digest is not None:
        if not isinstance(digest, str) or len(digest.strip()) != 64:
            problems.append(
                "{}: preregistration_sha256 must be a 64-character hash".format(
                    rel
                )
            )
        else:
            try:
                expected = preregistration_hash(record)
            except ProjectError as exc:
                problems.append("{}: cannot hash pre-registration: {}".format(rel, exc))
            else:
                if digest.strip().lower() != expected:
                    problems.append(
                        "{}: pre-registration changed after `sci start` "
                        "(recorded {}, current {})".format(
                            rel, digest.strip().lower(), expected
                        )
                    )
    return problems


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    problems = validate_project(
        root, verify_hashes=bool(getattr(args, "verify_hashes", False))
    )
    diagnostics = diagnostics_from_problems(problems)
    if getattr(args, "json", False):
        emit(
            envelope(
                "validate",
                project=project_info(root),
                ok=not problems,
                diagnostics=diagnostics,
                data={"problem_count": len(problems)},
            )
        )
        return EXIT_OK if not problems else EXIT_VALIDATION
    if problems:
        print("Validation failed: {} problem(s) in {}".format(len(problems), root))
        for problem in problems:
            print("  - {}".format(problem))
        return EXIT_VALIDATION
    print("Validation OK: {}".format(root))
    print(
        "  {} parses; expected paths exist; IDs are unique; references resolve.".format(
            CONFIG_NAME
        )
    )
    return EXIT_OK
