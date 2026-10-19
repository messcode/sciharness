"""``sci show``: resolve a stable record ID to its canonical location.

Deterministic navigation only.  It prints identity, references, the canonical
record path, and the generated-output workspace; it does not dump full
scientific content or summarize with an LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..output import EXIT_OK, emit, envelope, project_info
from ..project import (
    KINDS,
    RELATIONS,
    ProjectError,
    Record,
    find_project_root,
    load_records,
    relative_path,
)

# Longest prefixes first so EXP### is never mistaken for an exploration.
_ID_PREFIXES: Tuple[Tuple[str, str], ...] = (
    ("EXP", "experiment"),
    ("Q", "question"),
    ("X", "exploration"),
    ("D", "decision"),
)

_FIELD_LABELS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "question": (),
    "exploration": (
        ("question", "Question"),
        ("motivated_by", "Motivated by"),
    ),
    "experiment": (
        ("question", "Question"),
        ("exploration", "Source exploration"),
        ("motivated_by", "Motivated by"),
    ),
    "decision": (
        ("question", "Question"),
        ("evidence", "Evidence"),
        ("experiment", "Experiment"),
        ("supersedes", "Supersedes"),
    ),
}

_OUTPUT_GROUPS: Dict[str, str] = {
    "exploration": "explorations",
    "experiment": "experiments",
}


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    record = _resolve(root, args.record_id)
    references = _forward_references(record)
    backlinks = _backlinks(root, record)
    output_path = _output_path(root, record)

    if getattr(args, "json", False):
        emit(
            envelope(
                "show",
                project=project_info(root),
                data={
                    "record": {
                        "id": record.id,
                        "kind": record.kind,
                        "title": record.title,
                        "status": record.status,
                        "created": record.created,
                        "path": relative_path(root, record.path),
                        "outputs": output_path,
                        "references": references,
                        "backlinks": backlinks,
                    }
                },
            )
        )
        return EXIT_OK

    print(record.id)
    print("Title: {}".format(record.title))
    print("Status: {}".format(record.status))
    for field, label in _FIELD_LABELS[record.kind]:
        text = _render_field(record.data.get(field))
        if text:
            print("{}: {}".format(label, text))

    print("\nRecord:")
    print("  {}".format(relative_path(root, record.path)))

    if output_path is not None:
        print("\nOutputs:")
        print("  {}/".format(output_path))

    if getattr(args, "related", False):
        print("\nReferenced by:")
        if not backlinks:
            print("  (none)")
        for link in backlinks:
            print(
                "  {}  [{}]  {}  ({})".format(
                    link["source"],
                    link["source_kind"],
                    link["source_title"],
                    link["relation"],
                )
            )
    return EXIT_OK


def _render_field(value: Any) -> str:
    """Render a scalar or list front-matter value for display."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(
            str(item).strip() for item in value if str(item).strip()
        )
    return str(value).strip()


def _values(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _forward_references(record: Record) -> List[Dict[str, str]]:
    references: List[Dict[str, str]] = []
    for field, _label in _FIELD_LABELS[record.kind]:
        values = _values(record.data.get(field))
        if not values:
            continue
        target_kind = _target_kind(record.kind, field)
        for value in values:
            references.append(
                {
                    "relation": field,
                    "target": value,
                    "target_kind": target_kind or _kind_for(value) or "",
                }
            )
    return references


def _target_kind(source_kind: str, relation: str) -> Optional[str]:
    if source_kind == "decision" and relation == "experiment":
        # Legacy compatibility field: recorded as Decision evidence.
        return "experiment"
    for item in RELATIONS:
        if item.name == relation and source_kind in item.sources:
            return item.targets[0] if len(item.targets) == 1 else None
    return None


def _backlinks(root: Path, record: Record) -> List[Dict[str, str]]:
    backlinks: List[Dict[str, str]] = []
    seen: set = set()
    for source_kind in KINDS:
        records, _ = load_records(root, source_kind)
        for source in records:
            for relation in RELATIONS:
                if source_kind not in relation.sources:
                    continue
                if record.kind not in relation.targets:
                    continue
                if record.id not in _values(source.data.get(relation.name)):
                    continue
                key = (source.id, relation.name)
                if key in seen:
                    continue
                seen.add(key)
                backlinks.append(
                    {
                        "source": source.id,
                        "source_kind": source.kind,
                        "source_title": source.title,
                        "source_status": source.status,
                        "relation": relation.name,
                        "inverse": relation.inverse,
                        "path": relative_path(root, source.path),
                    }
                )
    backlinks.sort(key=lambda item: (item["source_kind"], item["source"]))
    return backlinks


def _output_path(root: Path, record: Record) -> Optional[str]:
    group = _OUTPUT_GROUPS.get(record.kind)
    if group is None:
        return None
    workspace = root / "outputs" / group / record.id
    if not workspace.is_dir():
        return None
    return relative_path(root, workspace)


def _resolve(root: Path, record_id: str) -> Record:
    kind = _kind_for(record_id)
    if kind is None:
        raise ProjectError(
            "unrecognized record id {!r}: expected Q###, X###, EXP###, or D###".format(
                record_id
            )
        )
    normalized = record_id.strip().upper()
    records, _ = load_records(root, kind)
    matches = [record for record in records if record.id == normalized]
    if not matches:
        raise ProjectError("no {} record with id {!r}".format(kind, record_id))
    if len(matches) > 1:
        raise ProjectError(
            "id {!r} is ambiguous: {} records match".format(record_id, len(matches))
        )
    return matches[0]


def _kind_for(record_id: Any) -> Optional[str]:
    if not isinstance(record_id, str):
        return None
    text = record_id.strip().upper()
    for prefix, kind in _ID_PREFIXES:
        remainder = text[len(prefix):]
        if text.startswith(prefix) and remainder.isdigit():
            return kind
    return None
