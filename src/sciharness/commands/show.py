"""``sci show``: resolve a stable record ID to its canonical location.

Deterministic navigation only.  It prints identity, references, the canonical
record path, and the generated-output workspace; it does not dump full
scientific content or summarize with an LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..project import (
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
    "exploration": (("question", "Question"),),
    "experiment": (("question", "Question"), ("exploration", "Source exploration")),
    "decision": (
        ("question", "Question"),
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

    print(record.id)
    print("Title: {}".format(record.title))
    print("Status: {}".format(record.status))
    for field, label in _FIELD_LABELS[record.kind]:
        value = record.data.get(field)
        if value is not None and str(value).strip():
            print("{}: {}".format(label, value))

    print("\nRecord:")
    print("  {}".format(relative_path(root, record.path)))

    group = _OUTPUT_GROUPS.get(record.kind)
    if group is not None:
        workspace = root / "outputs" / group / record.id
        if workspace.is_dir():
            print("\nOutputs:")
            print("  {}/".format(relative_path(root, workspace)))
    return 0


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
