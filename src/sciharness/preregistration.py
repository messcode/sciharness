"""Experiment pre-registration hashing and the ``sci start`` transition."""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict

import yaml

from .project import (
    ProjectError,
    Record,
    load_records,
    render_record,
    relative_path,
)

_FRONT_MATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

PREREGISTRATION_SECTIONS: tuple = (
    "Competing hypotheses",
    "Design",
    "Primary estimand",
    "Falsification / decision rule",
)

RUN_FILE = "run.yaml"


def _split_markdown(path: Path) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        raise ProjectError("missing YAML front matter in {}".format(path))
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ProjectError("invalid YAML front matter in {}: {}".format(path, exc))
    if not isinstance(data, dict):
        raise ProjectError("front matter must be a YAML mapping")
    return {"data": data, "body": text[match.end():]}


def _normalize_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


_CANONICAL_SECTIONS = {
    _normalize_heading(item): item for item in PREREGISTRATION_SECTIONS
}


def _sections(body: str) -> Dict[str, str]:
    matches = list(_SECTION_RE.finditer(body))
    found: Dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        key = _normalize_heading(match.group(1))
        canonical = _CANONICAL_SECTIONS.get(key)
        if canonical is None:
            continue
        found[canonical] = body[match.end():end].strip()
    return found


def preregistration_payload(record: Record) -> Dict[str, Any]:
    """Return the reviewable, pre-run content of an experiment record."""
    parsed = _split_markdown(record.path)
    sections = _sections(parsed["body"])
    return {
        "id": record.id,
        "title": record.title,
        "question": record.data.get("question"),
        "exploration": record.data.get("exploration"),
        "motivated_by": record.data.get("motivated_by", []),
        "datasets": record.data.get("datasets", []),
        "sections": {
            name: sections.get(name, "") for name in PREREGISTRATION_SECTIONS
        },
    }


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def preregistration_hash(record: Record) -> str:
    payload = _canonical(preregistration_payload(record))
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def start_experiment(root: Path, record_id: str) -> Dict[str, str]:
    """Mark a planned experiment as running and freeze its pre-registration."""
    root = Path(root)
    records, _problems = load_records(root, "experiment")
    normalized = str(record_id).strip().upper()
    matches = [record for record in records if record.id == normalized]
    if not matches:
        raise ProjectError("no experiment record with id {!r}".format(record_id))
    record = matches[0]
    if record.status != "planned":
        raise ProjectError(
            "experiment {} must be 'planned' to start, got {!r}".format(
                record.id, record.status
            )
        )

    digest = preregistration_hash(record)
    parsed = _split_markdown(record.path)
    front = dict(parsed["data"])
    front["status"] = "running"
    front["started"] = datetime.date.today().isoformat()
    record.path.write_text(
        render_record(front, parsed["body"]), encoding="utf-8"
    )

    run_path = record.path.parent / RUN_FILE
    run: Dict[str, Any] = {}
    if run_path.is_file():
        try:
            existing = yaml.safe_load(run_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ProjectError("cannot parse {}: {}".format(run_path, exc)) from exc
        if existing is not None and not isinstance(existing, dict):
            raise ProjectError("{} must contain a YAML mapping".format(run_path))
        if isinstance(existing, dict):
            run = dict(existing)
            if run.get("record") not in (None, record.id):
                raise ProjectError(
                    "{} belongs to record {!r}, not {}".format(
                        run_path, run.get("record"), record.id
                    )
                )
    run.update(
        {
            "schema_version": 1,
            "record": record.id,
            "started_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "preregistration_sha256": digest,
        }
    )
    datasets = record.data.get("datasets")
    if not isinstance(datasets, list):
        datasets = []
    run.setdefault("datasets", list(datasets))
    run_path.write_text(
        "# Run provenance. Fill command/commit/environment after the run;\n"
        "# do not rewrite the pre-registered README design sections.\n"
        + yaml.safe_dump(run, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return {
        "record": record.id,
        "record_path": relative_path(root, record.path),
        "run": relative_path(root, run_path),
        "preregistration_sha256": digest,
    }
