"""``sci status``: deterministic project summary from the filesystem."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from ..project import (
    Record,
    find_project_root,
    id_number,
    load_config,
    load_records,
)
from .validate import validate_project

RECENT_DECISIONS = 5


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    config = load_config(root)
    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    name = (project or {}).get("name") or root.name

    questions, _ = load_records(root, "question")
    explorations, _ = load_records(root, "exploration")
    experiments, _ = load_records(root, "experiment")
    decisions, _ = load_records(root, "decision")

    print("Project: {}".format(name))

    _section("Active questions", [r for r in questions if r.status == "open"])
    _section(
        "Active explorations", [r for r in explorations if r.status == "active"]
    )
    _section(
        "Active experiments",
        [r for r in experiments if r.status in ("planned", "running")],
    )
    recent = sorted(decisions, key=lambda record: id_number(record.id), reverse=True)
    _section("Recent decisions", recent[:RECENT_DECISIONS])

    problems = validate_project(root)
    print("\nValidation")
    if not problems:
        print("  no problems")
    else:
        print("  {} problem(s) — run `sci validate`".format(len(problems)))

    return 0


def _section(title: str, records: List[Record]) -> None:
    print("\n{}".format(title))
    if not records:
        print("  (none)")
        return
    for record in records:
        print("  {}  {}".format(record.id, record.title))
